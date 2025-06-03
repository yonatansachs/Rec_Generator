from math import radians, sin, sqrt, cos, atan2

from bson import ObjectId
from flask import Blueprint, session, redirect, url_for, flash, render_template, request

from core.data_utils import normalize, load_data
from core.users import get_taste
from db.collections import SYSTEMS, get_ratings_collection
from db.connection import get_db


item_bp = Blueprint("item", __name__)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Compute Haversine distance (in kilometers) between (lat1, lon1) and (lat2, lon2).
    """
    R = 6371.0  # Earth radius in kilometers

    φ1 = radians(lat1)
    φ2 = radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lon2 - lon1)

    a = sin(Δφ / 2)**2 + cos(φ1) * cos(φ2) * sin(Δλ / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

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

    # -- 1) Build your regular “feature filters” (price, cuisine, meal type):
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

    # -- 2) Load from MongoDB and normalize:
    db = get_db()
    try:
        raw_items = db[system].find(mongo_q)
        items = normalize(list(raw_items), SYSTEMS[system]["mapping"])
    except Exception as e:
        flash(f"Error loading data: {e}", "danger")
        items = []

    # -- 3) “Near Me” logic: check for nearest/user_lat/user_lon
    nearest_flag = request.args.get("nearest", "")
    user_lat_str = request.args.get("user_lat", "")
    user_lon_str = request.args.get("user_lon", "")

    if nearest_flag == "true" and user_lat_str and user_lon_str:
        try:
            user_lat = float(user_lat_str)
            user_lon = float(user_lon_str)
        except ValueError:
            # If parsing fails, just ignore “Near Me” rather than crash
            user_lat = user_lon = None

        if user_lat is not None and user_lon is not None:
            # Compute distance for each item (if item has valid lat/lon keys)
            for it in items:
                # Adjust these keys if your normalized items use different field names:
                item_lat = it.get("latitude", None)
                item_lon = it.get("longitude", None)
                if item_lat is not None and item_lon is not None:
                    # Calculate distance in kilometers
                    try:
                        dist = haversine_distance(
                            user_lat, user_lon,
                            float(item_lat), float(item_lon)
                        )
                        it["distance"] = dist
                    except (ValueError, TypeError):
                        # If item_lat/item_lon are not valid floats, skip distance
                        it["distance"] = float("inf")
                else:
                    # If there’s no lat/lon on this item, push it to “infinite” distance
                    it["distance"] = float("inf")

            # Sort items by the computed “distance” key (smallest first)
            items = sorted(items, key=lambda x: x.get("distance", float("inf")))

    # -- 4) Finally render the template, passing “items” (some now have it["distance"])
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
