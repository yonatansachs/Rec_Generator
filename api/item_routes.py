from bson import ObjectId
from flask import Blueprint, session, redirect, url_for, flash, render_template, request

from core.data_utils import normalize, load_data
from core.users import get_taste
from db.collections import SYSTEMS, get_ratings_collection
from db.connection import get_db


item_bp = Blueprint("item", __name__)

@item_bp.route("/choose_system")
def choose_system():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    available = {}
    for sys, cfg in SYSTEMS.items():
        if db[sys].count_documents({}) > 0:
            available[sys] = cfg
    if not available:
        flash("No datasets available. Upload one!", "warning")
    return render_template("choose_system.html", systems=available)


@item_bp.route("/index")
def index():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("system.choose_system"))

    price_raw    = request.args.get("price", "")
    cuisine_raw  = request.args.get("cuisine", "")
    meal_raw     = request.args.get("meal_type", "")

    cuisines = [cuisine_raw] if cuisine_raw else []
    feature_filters = []
    if price_raw:
        feature_filters.append(f"priceLevel.{price_raw}")
    if cuisines:
        feature_filters += [f"cuisines.{c}" for c in cuisines]
    if meal_raw:
        feature_filters.append(f"mealTypes.{meal_raw}")

    mongo_q = {"features": {"$all": feature_filters}} if feature_filters else {}

    db = get_db()
    try:
        raw_items = db[system].find(mongo_q)
        items = normalize(list(raw_items), SYSTEMS[system]["mapping"])
    except Exception as e:
        flash(f"Error loading data: {e}", "danger")
        items = []

    return render_template(
        "index.html",
        restaurants=items,
        system=system,
        current_price=price_raw,
        current_cuisines=cuisines,
        current_meal=meal_raw,
        user_has_vector=(get_taste(session["user_id"], system) is not None)
    )


@item_bp.route("/item_detail")
def item_detail():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system", "danger")
        return redirect(url_for("system.choose_system"))

    item_id = request.args.get("id")
    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    item = next((it for it in norm if it["id"] == str(item_id)), None)
    if not item:
        flash("Item not found.", "danger")
        return redirect(url_for("item.index", system=system))

    rec = get_ratings_collection().find_one({
        "user_id": ObjectId(session["user_id"]),
        "system": system,
        "item_id": item_id
    })

    return render_template("item_detail.html", item=item, system=system, current_rating=rec["rating"] if rec else 0)
