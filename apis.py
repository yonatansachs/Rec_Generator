from flask import Blueprint, request, jsonify

from core.math_utils import calc_delta, solve_profile, est_rating
from core.ratings import add_ratings, delete_all_ratings
from core.users import create_user, get_user, update_user, delete_user
from core.ratings import (
    add_rating, get_ratings, update_rating, delete_rating
)
from core.systems import create_system, get_system, update_system, delete_system, list_systems, get_features
from core.systems import add_items_to_system

api_routes = Blueprint("api", __name__)

# <---CRUD FOR USER--->
@api_routes.route("/create_user", methods=["POST"])
def api_create_user():
    data = request.json
    user_name = data.get("user_name")
    password = data.get("password")

    new_user_id = create_user(user_name, password)
    if not new_user_id:
        return jsonify({"error": "Username already exists."}), 400

    return jsonify({"message": "User added."}), 201


# Read user
@api_routes.route("/get_user/<user_id>", methods=["GET"])
def api_get_user(user_id):
    user = get_user(user_id)
    if user:
        return jsonify(user), 200
    else:
        return jsonify({"error": "User not found."}), 404

# Update user
@api_routes.route("/update_user/<user_id>", methods=["PUT"])
def api_update_user(user_id):
    data = request.json
    updated_fields = data.get("updated_fields", {})
    success = update_user(user_id, updated_fields)
    if success:
        return jsonify({"message": "User updated."}), 200
    else:
        return jsonify({"error": "User not found or update failed."}), 400

# Delete user
@api_routes.route("/delete_user/<user_id>", methods=["DELETE"])
def api_delete_user(user_id):
    success = delete_user(user_id)
    if success:
        return jsonify({"message": "User deleted."}), 200
    else:
        return jsonify({"error": "User not found or delete failed."}), 400



#-------- MULTIPLE RATING CRUD--------
# Add ratings in batch
@api_routes.route("/batch_ratings", methods=["POST"])
def api_batch_ratings():
    data = request.json
    user_id = data.get("user_id")
    system = data.get("system")
    ratings = data.get("ratings", [])

    # בדיקה אם המשתמש קיים
    if not get_user(user_id):
        return jsonify({"error": f"User '{user_id}' not found."}), 404

    # בדיקה אם המערכת קיימת
    if not get_system(system):
        return jsonify({"error": f"System '{system}' not found."}), 404

    # אם הכל תקין – הוספת הדירוגים
    add_ratings(user_id, system, ratings)
    return jsonify({"message": "Ratings added."}), 201



# Get all ratings for a user and system
@api_routes.route("/ratings/<user_id>/<system>", methods=["GET"])
def api_get_ratings(user_id, system):
    ratings = get_ratings(user_id, system)
    return jsonify(ratings), 200

@api_routes.route("/ratings/<user_id>/<system>", methods=["DELETE"])
def api_delete_all_ratings(user_id, system):
    deleted_count = delete_all_ratings(user_id, system)
    return jsonify({
        "message": f"Deleted {deleted_count} rating(s) for user '{user_id}' in system '{system}'."
    }), 200

@api_routes.route("/ratings/<user_id>", methods=["DELETE"])
def api_delete_all_user_ratings(user_id):
    from core.ratings import delete_all_user_ratings
    deleted_count = delete_all_user_ratings(user_id)
    return jsonify({
        "message": f"Deleted {deleted_count} rating(s) for user '{user_id}' across all systems."
    }), 200

@api_routes.route("/ratings/system/<system_id>", methods=["DELETE"])
def api_delete_all_ratings_in_system(system_id):
    from core.ratings import delete_all_ratings_in_system
    deleted_count = delete_all_ratings_in_system(system_id)
    return jsonify({
        "message": f"Deleted {deleted_count} rating(s) in system '{system_id}'."
    }), 200


#-------- SINGLE RATING CRUD ---------
# Add a single rating
@api_routes.route("/rating", methods=["POST"])
def api_add_rating():
    data = request.json
    user_id = data.get("user_id")
    system = data.get("system")
    item_id = data.get("item_id")
    value = data.get("value")

    # בדיקת קיום משתמש
    if not get_user(user_id):
        return jsonify({"error": f"User '{user_id}' not found."}), 404

    # בדיקת קיום מערכת
    if not get_system(system):
        return jsonify({"error": f"System '{system}' not found."}), 404

    # הוספת דירוג
    success = add_rating(user_id, system, item_id, value)
    if not success:
        return jsonify({"error": "Rating already exists for this item."}), 400

    return jsonify({"message": "Rating added."}), 201



# Update a single rating
@api_routes.route("/rating", methods=["PUT"])
def api_update_rating():
    data = request.json
    success = update_rating(data["user_id"], data["system"], data["item_id"], data["value"])
    if success:
        return jsonify({"message": "Rating updated."}), 200
    else:
        return jsonify({"error": "Rating not found."}), 404

# Delete a single rating
@api_routes.route("/rating", methods=["DELETE"])
def api_delete_rating():
    data = request.json
    success = delete_rating(data["user_id"], data["system"], data["item_id"])
    if success:
        return jsonify({"message": "Rating deleted."}), 200
    else:
        return jsonify({"error": "Rating not found."}), 404


#------- SYSTEM CRUD-------

@api_routes.route("/system", methods=["POST"])
def api_create_system():
    data = request.json
    system_id = data.get("system_id")
    display = data.get("display")
    mapping = data.get("mapping")
    create_system(system_id, display, mapping)
    return jsonify({"message": "System created."}), 201

@api_routes.route("/system/<system_id>", methods=["GET"])
def api_get_system(system_id):
    system = get_system(system_id)
    if system:
        return jsonify(system), 200
    return jsonify({"error": "System not found"}), 404

@api_routes.route("/system/<system_id>", methods=["PUT"])
def api_update_system(system_id):
    updates = request.json.get("updates", {})
    success = update_system(system_id, updates)
    if success:
        return jsonify({"message": "System updated."}), 200
    return jsonify({"error": "System not found or update failed."}), 400

@api_routes.route("/system/<system_id>", methods=["DELETE"])
def api_delete_system(system_id):
    success = delete_system(system_id)
    if success:
        return jsonify({"message": "System deleted."}), 200
    return jsonify({"error": "System not found or delete failed."}), 400

@api_routes.route("/systems", methods=["GET"])
def api_list_systems():
    systems = list_systems()
    filtered = []
    for s in systems:
        filtered.append({
            "id": s.get("system_id") or s.get("id"),
            "name": s.get("display") or s.get("name") or s.get("system_id")
        })
    return jsonify(filtered), 200



@api_routes.route("/add_items", methods=["POST"])
def api_add_items():
    data = request.json
    system_id = data.get("system_id")
    new_items = data.get("items", [])

    success = add_items_to_system(system_id, new_items)
    if success:
        return jsonify({"message": "Items added."}), 200
    return jsonify({"error": "Failed to add items."}), 400

@api_routes.route("/edit_item", methods=["PUT"])
def api_edit_item():
    data = request.json
    system_id = data.get("system_id")
    item_id = data.get("item_id")
    updated_fields = data.get("updated_fields", {})
    from core.systems import edit_item_in_system  # This function will be created

    success = edit_item_in_system(system_id, item_id, updated_fields)
    if success:
        return jsonify({"message": "Item updated."}), 200
    return jsonify({"error": "Item not found or update failed."}), 400

@api_routes.route("/get_ratings_by_items", methods=["POST"])
def api_get_ratings_by_items():
    data = request.json
    user_id = data.get("user_id")
    system = data.get("system")
    item_ids = data.get("item_ids", [])
    from core.ratings import get_ratings_by_items  # ניצור את הפונקציה הזו

    ratings = get_ratings_by_items(user_id, system, item_ids)
    return jsonify(ratings), 200

from flask import request, jsonify
import logging

@api_routes.route("/estimated_ratings", methods=["POST"])
def api_estimated_ratings():
    from core.ratings import get_ratings
    from core.systems import get_features
    from core.math_utils import calc_delta, solve_profile, est_rating
    import logging

    try:
        data = request.json
        user_id = data.get("user_id")
        system = data.get("system")
        item_ids = data.get("item_ids", [])

        # Basic validations
        if not user_id or not system or not item_ids:
            return jsonify({"error": "Missing user_id, system, or item_ids"}), 400
        if not isinstance(item_ids, list):
            return jsonify({"error": "item_ids must be a list"}), 400

        # Step 1: Get user ratings
        user_ratings = get_ratings(user_id, system)
        if not user_ratings:
            return jsonify({"error": f"No ratings found for user '{user_id}' in system '{system}'"}), 400

        # Step 2: Prepare data to build profile
        rated_vectors = []
        ratings = []
        logging.debug(f"User rated items: {[r['item_id'] for r in user_ratings]}")

        for rating in user_ratings:
            try:
                vector = get_features(rating["item_id"], system)
                rated_vectors.append(vector)
                ratings.append(rating["value"])
            except Exception as e:
                logging.warning(f"Skipping item {rating['item_id']}: {e}")

        if len(rated_vectors) == 0:
            return jsonify({"error": "No valid feature vectors found for rated items"}), 400

        # Step 3: Build user profile
        n = len(rated_vectors[0])
        deltas = calc_delta(ratings, n)
        profile = solve_profile(rated_vectors, deltas)

        # Step 4: Estimate ratings
        result = {}
        for item_id in item_ids:
            try:
                features = get_features(item_id, system)
                est = est_rating(profile, features, n)

                logging.debug(f"Estimated rating for item {item_id}: {est}")
                result[item_id] = round(est, 2)
            except Exception as e:
                logging.error(f"est_rating failed for item {item_id}: {e}")
                result[item_id] = None

        return jsonify(result), 200

    except Exception as e:
        logging.error(f"Unexpected error in /estimated_ratings: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


