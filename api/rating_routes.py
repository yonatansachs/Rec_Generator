from datetime import datetime
from bson import ObjectId
from flask import (
    Blueprint, session, redirect, url_for, flash,
    request, render_template, jsonify
)

from core.math_utils import solve_profile, calc_delta
from core.users import set_taste
from core.data_utils import load_data, normalize
from db.collections import SYSTEMS, get_ratings_collection

rating_bp = Blueprint("rating", __name__)

@rating_bp.route("/batch_ratings", methods=["POST"])
def add_batch_ratings():
    return jsonify({"message": "Batch ratings endpoint works"})


# ─────────── Route: Update Multiple Ratings ───────────
@rating_bp.route("/update_ratings", methods=["POST"])
def update_ratings():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system", "danger")
        return redirect(url_for("system.choose_system"))

    u_id = session["user_id"]
    updated_ids_str = request.form.get("updated_ids", "")
    if not updated_ids_str:
        flash("No ratings updated.", "warning")
        return redirect(url_for("rec.dashboard", system=system))

    updated_ids = updated_ids_str.split(",")
    ratings_col = get_ratings_collection()

    for item_id in updated_ids:
        val = request.form.get(f"rating_{item_id}")
        if not val:
            continue
        try:
            new_r = float(val)
        except ValueError:
            continue
        ratings_col.update_one(
            {"user_id": ObjectId(u_id), "system": system, "item_id": item_id},
            {"$set": {"rating": new_r, "timestamp": datetime.utcnow()}},
            upsert=True,
        )

    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    existing = {
        r["item_id"]: r["rating"]
        for r in ratings_col.find({"user_id": ObjectId(u_id), "system": system})
    }

    vectors = [
        it["featureVector"][:] + [existing.get(it["id"], 3.0)]
        for it in norm
    ]
    n = len(norm[0]["featureVector"])
    rated_vecs, deltas = [], []

    for i, it in enumerate(norm):
        if it["id"] in existing:
            rated_vecs.append(vectors[i])
            deltas.append(existing[it["id"]])

    profile = solve_profile(rated_vecs, calc_delta(deltas, n))
    set_taste(u_id, system, profile)

    flash("Ratings updated.", "success")
    return redirect(url_for("rec.dashboard", system=system))


# ─────────── Route: Update Single Rating ───────────
@rating_bp.route("/update_item_rating")
def update_item_rating():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system", "danger")
        return redirect(url_for("system.choose_system"))

    item_id = request.args.get("id")
    try:
        new_r = float(request.args.get("rating"))
    except (TypeError, ValueError):
        flash("Invalid rating", "danger")
        return redirect(url_for("rec.dashboard", system=system))

    u_id = session["user_id"]
    ratings_col = get_ratings_collection()
    ratings_col.update_one(
        {"user_id": ObjectId(u_id), "system": system, "item_id": item_id},
        {"$set": {"rating": new_r, "timestamp": datetime.utcnow()}},
        upsert=True,
    )

    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    existing = {
        r["item_id"]: r["rating"]
        for r in ratings_col.find({"user_id": ObjectId(u_id), "system": system})
    }

    vectors = [
        it["featureVector"][:] + [existing.get(it["id"], 3.0)]
        for it in norm
    ]
    n = len(norm[0]["featureVector"])
    rated_vecs, deltas = [], []

    for i, it in enumerate(norm):
        if it["id"] in existing:
            rated_vecs.append(vectors[i])
            deltas.append(existing[it["id"]])

    profile = solve_profile(rated_vecs, calc_delta(deltas, n))
    set_taste(u_id, system, profile)

    flash("Rating updated.", "success")
    return redirect(url_for("rec.dashboard", system=system))


# ─────────── Route: My Ratings Page ───────────
@rating_bp.route("/my_ratings")
def my_ratings():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system", "danger")
        return redirect(url_for("system.choose_system"))

    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    ratings_col = get_ratings_collection()
    recs = list(ratings_col.find({"user_id": ObjectId(session["user_id"]), "system": system}))
    ratings_map = {r["item_id"]: r["rating"] for r in recs}

    rated_items = [
        {
            "id": it["id"],
            "name": it["name"],
            "image": it["image"],
            "description": it["description"],
            "rating": ratings_map[it["id"]],
        }
        for it in norm if it["id"] in ratings_map
    ]

    all_items = [
        {
            "id": it["id"],
            "name": it["name"],
            "image": it.get("image"),
            "description": it.get("description", ""),
        }
        for it in norm
    ]

    return render_template(
        "my_ratings.html",
        rated_items=rated_items,
        system=system,
        all_items=all_items
    )

