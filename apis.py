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
    user_name = data.get("user_id")
    system = data.get("system")
    ratings = data.get("ratings", [])
    add_ratings(user_name, system, ratings)
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


#-------- SINGLE RATING CRUD ---------
# Add a single rating
@api_routes.route("/rating", methods=["POST"])
def api_add_rating():
    data = request.json
    success = add_rating(data["user_id"], data["system"], data["item_id"], data["value"])
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
    try:
        logging.debug(request)
        data = request.json
        user_id = data.get("user_id")
        system = data.get("system")
        item_ids = data.get("item_ids", [])

        logging.debug(f"Received estimated_ratings request: user_id={user_id}, system={system}, item_ids={item_ids}")

        # Validate input
        if not user_id:
            logging.warning("Missing user_id")
            return jsonify({"error": "Missing user_id"}), 400

        if not system:
            logging.warning("Missing system")
            return jsonify({"error": "Missing system"}), 400

        if not isinstance(item_ids, list) or not item_ids:
            logging.warning("item_ids must be a non-empty list")
            return jsonify({"error": "item_ids must be a non-empty list"}), 400

        # 1. Get user's rated items & their ratings
        try:
            user_ratings = get_ratings(user_id, system)  # [{"item_id": ..., "value": ...}]
        except Exception as e:
            logging.error(f"get_ratings error: {e}")
            return jsonify({"error": f"Failed to get user ratings: {e}"}), 500

        if not user_ratings or len(user_ratings) < 1:
            logging.info("User has no ratings")
            return jsonify({"error": "User has no ratings"}), 400

        # 2. Get feature vectors for those items
        rated_ids = [r["item_id"] for r in user_ratings]
        try:
            rated_vectors = [get_features(item_id, system) for item_id in rated_ids]
        except Exception as e:
            logging.error(f"get_features (rated_ids) error: {e}")
            return jsonify({"error": f"Failed to get features for rated items: {e}"}), 500

        if not rated_vectors or any(v is None for v in rated_vectors):
            logging.error("Some rated items have missing features")
            return jsonify({"error": "Some rated items have missing features"}), 500

        ratings = [r["value"] for r in user_ratings]

        if not rated_vectors or not ratings or len(rated_vectors) != len(ratings):
            logging.error("Mismatch between ratings and feature vectors")
            return jsonify({"error": "Mismatch between ratings and feature vectors"}), 500

        n = len(rated_vectors[0])
        logging.debug(f"Rated_vectors dimension: {n}")

        # 3. Build deltas
        try:
            deltas = calc_delta(ratings, n)
        except Exception as e:
            logging.error(f"calc_delta error: {e}")
            return jsonify({"error": f"Failed to calculate deltas: {e}"}), 500

        # 4. Build user profile
        try:
            profile = solve_profile(rated_vectors, deltas)
        except Exception as e:
            logging.error(f"solve_profile error: {e}")
            return jsonify({"error": f"Failed to solve user profile: {e}"}), 500

        # 5. For each requested item, estimate rating
        result = {}
        for item_id in item_ids:
            try:
                features = get_features(item_id, system)
                if features is None:
                    logging.warning(f"Missing features for item_id {item_id}")
                    result[item_id] = None
                    continue
                est = est_rating(profile, features, n)
                result[item_id] = round(est, 2)
            except Exception as e:
                logging.error(f"est_rating failed for item {item_id}: {e}")
                result[item_id] = None

        logging.debug(f"Estimation results: {result}")
        return jsonify(result), 200

    except Exception as e:
        logging.error(f"Fatal error in /estimated_ratings: {e}")
        return jsonify({"error": f"Server error: {e}"}), 500

