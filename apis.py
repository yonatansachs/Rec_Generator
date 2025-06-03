from flask import Blueprint, request, jsonify
from core.ratings import add_ratings, delete_all_ratings
from core.users import create_user, get_user, update_user, delete_user
from core.ratings import (
    add_rating, get_ratings, update_rating, delete_rating
)
from core.systems import create_system, get_system, update_system, delete_system, list_systems

api_routes = Blueprint("api", __name__)

# <---CRUD FOR USER--->
@api_routes.route("/api/create_user", methods=["POST"])
def api_create_user():
    data = request.json
    user_name = data.get("user_name")
    password = data.get("password")
    create_user(user_name, password)
    return jsonify({"message": "User added."}), 201

# Read user
@api_routes.route("/api/get_user/<user_id>", methods=["GET"])
def api_get_user(user_id):
    user = get_user(user_id)
    if user:
        return jsonify(user), 200
    else:
        return jsonify({"error": "User not found."}), 404

# Update user
@api_routes.route("/api/update_user/<user_id>", methods=["PUT"])
def api_update_user(user_id):
    data = request.json
    updated_fields = data.get("updated_fields", {})
    success = update_user(user_id, updated_fields)
    if success:
        return jsonify({"message": "User updated."}), 200
    else:
        return jsonify({"error": "User not found or update failed."}), 400

# Delete user
@api_routes.route("/api/delete_user/<user_id>", methods=["DELETE"])
def api_delete_user(user_id):
    success = delete_user(user_id)
    if success:
        return jsonify({"message": "User deleted."}), 200
    else:
        return jsonify({"error": "User not found or delete failed."}), 400



#-------- MULTIPLE RATING CRUD--------
# Add ratings in batch
@api_routes.route("/api/batch_ratings", methods=["POST"])
def api_batch_ratings():
    data = request.json
    user_name = data.get("user_id")
    system = data.get("system")
    ratings = data.get("ratings", [])
    add_ratings(user_name, system, ratings)
    return jsonify({"message": "Ratings added."}), 201


# Get all ratings for a user and system
@api_routes.route("/api/ratings/<user_id>/<system>", methods=["GET"])
def api_get_ratings(user_id, system):
    ratings = get_ratings(user_id, system)
    return jsonify(ratings), 200

@api_routes.route("/api/ratings/<user_id>/<system>", methods=["DELETE"])
def api_delete_all_ratings(user_id, system):
    deleted_count = delete_all_ratings(user_id, system)
    return jsonify({
        "message": f"Deleted {deleted_count} rating(s) for user '{user_id}' in system '{system}'."
    }), 200


#-------- SINGLE RATING CRUD ---------
# Add a single rating
@api_routes.route("/api/rating", methods=["POST"])
def api_add_rating():
    data = request.json
    add_rating(data["user_id"], data["system"], data["item_id"], data["value"])
    return jsonify({"message": "Rating added."}), 201


# Update a single rating
@api_routes.route("/api/rating", methods=["PUT"])
def api_update_rating():
    data = request.json
    success = update_rating(data["user_id"], data["system"], data["item_id"], data["value"])
    if success:
        return jsonify({"message": "Rating updated."}), 200
    else:
        return jsonify({"error": "Rating not found."}), 404

# Delete a single rating
@api_routes.route("/api/rating", methods=["DELETE"])
def api_delete_rating():
    data = request.json
    success = delete_rating(data["user_id"], data["system"], data["item_id"])
    if success:
        return jsonify({"message": "Rating deleted."}), 200
    else:
        return jsonify({"error": "Rating not found."}), 404


#------- SYSTEM CRUD-------

@api_routes.route("/api/system", methods=["POST"])
def api_create_system():
    data = request.json
    system_id = data.get("system_id")
    display = data.get("display")
    mapping = data.get("mapping")
    create_system(system_id, display, mapping)
    return jsonify({"message": "System created."}), 201

@api_routes.route("/api/system/<system_id>", methods=["GET"])
def api_get_system(system_id):
    system = get_system(system_id)
    if system:
        return jsonify(system), 200
    return jsonify({"error": "System not found"}), 404

@api_routes.route("/api/system/<system_id>", methods=["PUT"])
def api_update_system(system_id):
    updates = request.json.get("updates", {})
    success = update_system(system_id, updates)
    if success:
        return jsonify({"message": "System updated."}), 200
    return jsonify({"error": "System not found or update failed."}), 400

@api_routes.route("/api/system/<system_id>", methods=["DELETE"])
def api_delete_system(system_id):
    success = delete_system(system_id)
    if success:
        return jsonify({"message": "System deleted."}), 200
    return jsonify({"error": "System not found or delete failed."}), 400

@api_routes.route("/api/systems", methods=["GET"])
def api_list_systems():
    return jsonify(list_systems()), 200

