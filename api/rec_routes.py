from datetime import datetime
from bson import ObjectId
from flask import (
    Blueprint, session, redirect, url_for,
    request, flash, render_template
)

from core.math_utils import solve_profile, calc_delta, est_rating
from core.users import get_taste, set_taste
from core.data_utils import load_data, normalize
from db.collections import SYSTEMS, get_ratings_collection, get_users_collection

rec_bp = Blueprint("rec", __name__)

@rec_bp.route("/recommendations", methods=["GET"])
def get_recommendations():
    return {"message": "Recommendation endpoint works"}

@rec_bp.route("/show_recommendations")
def show_recommendations():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system", "danger")
        return redirect(url_for("system.choose_system"))

    if not get_taste(session["user_id"], system):
        flash("Rate some items first.", "warning")
        mapping = SYSTEMS[system]["mapping"]
        try:
            norm = normalize(load_data(system), mapping)
        except Exception:
            norm = []
        return render_template("index.html", restaurants=norm, system=system, user_has_vector=False)

    return redirect(url_for("rec.dashboard", system=system))


@rec_bp.route("/recommend", methods=["GET", "POST"])
def recommend():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system", "danger")
        return redirect(url_for("system.choose_system"))

    mapping = SYSTEMS[system]["mapping"]
    try:
        norm = normalize(load_data(system), mapping)
    except Exception as e:
        flash(f"Dataset error: {e}", "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)

    u_id = session["user_id"]
    ratings_collection = get_ratings_collection()

    if request.method == "POST":
        privacy_mode = request.form.get("privacy_mode") == "1"
        ids_str = request.form.get("selected_ids", "").strip()
        if ids_str:
            selected_ids = ids_str.split(",")
            for sid in selected_ids:
                rating_val = request.form.get(f"rating_{sid}")
                if not rating_val:
                    continue
                try:
                    r = float(rating_val)
                except ValueError:
                    continue
                if not privacy_mode:
                    ratings_collection.update_one(
                        {"user_id": ObjectId(u_id), "system": system, "item_id": sid},
                        {"$set": {"rating": r, "timestamp": datetime.utcnow()}},
                        upsert=True,
                    )

    privacy_mode = request.form.get("privacy_mode") == "1" if request.method == "POST" else False

    if privacy_mode:
        ids_str = request.form.get("selected_ids", "").strip()
        if ids_str:
            selected_ids = ids_str.split(",")
            existing = {}
            for sid in selected_ids:
                rating_val = request.form.get(f"rating_{sid}")
                if not rating_val:
                    continue
                try:
                    r = float(rating_val)
                except ValueError:
                    continue
                existing[sid] = r
        else:
            existing = {}
    else:
        existing = {
            r["item_id"]: r["rating"]
            for r in ratings_collection.find({"user_id": ObjectId(u_id), "system": system})
        }

    if len(existing) < 4:
        flash("Please rate at least 4 items to get recommendations.", "danger")
        return render_template("index.html", restaurants=norm, system=system, user_has_vector=False)

    vectors = []
    for it in norm:
        fv = it["featureVector"][:] + [existing.get(it["id"], 3.0)]
        vectors.append(fv)

    n = len(norm[0]["featureVector"])
    rated_vecs, deltas = [], []
    for it in norm:
        if it["id"] in existing:
            rated_vecs.append(vectors[norm.index(it)])
            deltas.append(existing[it["id"]])

    profile = solve_profile(rated_vecs, calc_delta(deltas, n))
    set_taste(u_id, system, profile)

    # ───── COMPUTE RECOMMENDATIONS ─────
    rated = []
    for it in norm:
        rated.append((
            it["name"],
            it["image"],
            est_rating(profile, it["featureVector"], n),
            it["id"],
        ))
    rated.sort(key=lambda x: x[2], reverse=True)

    return render_template("recommendations.html", recommendations=rated[:10], system=system)


# ───────────── Dashboard View ─────────────
@rec_bp.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system", "danger")
        return redirect(url_for("system.choose_system"))

    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    profile = get_taste(session["user_id"], system)

    if not profile:
        flash("Rate some items first.", "warning")
        return redirect(url_for("index", system=system))

    n = len(norm[0]["featureVector"])
    rated = [
        (it["name"], it["image"], est_rating(profile, it["featureVector"], n), it["id"])
        for it in norm
    ]
    rated.sort(key=lambda x: x[2], reverse=True)

    return render_template("recommendations.html", recommendations=rated[:10], system=system)


@rec_bp.route("/reset_taste")
def reset_taste():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system", "danger")
        return redirect(url_for("system.choose_system"))

    u_id = session["user_id"]
    ratings_collection = get_ratings_collection()
    users_collection = get_users_collection()

    ratings_collection.delete_many({"user_id": ObjectId(u_id), "system": system})
    users_collection.update_one(
        {"_id": ObjectId(u_id)},
        {"$unset": {f"taste_vector.{system}": ""}},
    )

    flash("Selections reset.", "info")
    return redirect(url_for("item.index", system=system, reset_local="1"))
