
from core.users import create_user, get_user, update_user, delete_user
from core.systems import create_system, update_system, delete_system, list_systems,add_items_to_system,edit_item_in_system
from core.ratings import get_ratings,get_ratings_by_items,delete_all_user_ratings,delete_all_ratings_in_system,add_rating, update_rating, delete_rating,add_ratings, delete_all_ratings
import logging
import random
from flask import Blueprint, request, jsonify
from core.math_utils import calc_delta, solve_profile, est_rating
from core.systems import get_system, get_features

api_routes = Blueprint("api", __name__)

# <---CRUD FOR USER--->
@api_routes.route("/create_user", methods=["POST"])
def api_create_user():
    data = request.json
    user_name = str(data.get("user_name"))
    password = data.get("password")

    new_user_id = create_user(user_name, password)
    if not new_user_id:
        return jsonify({"error": "Username already exists."}), 400

    return jsonify({"message": "User added."}), 201


@api_routes.route("/get_user/<user_id>", methods=["GET"])
def api_get_user(user_id):
    user_id = str(user_id)
    user = get_user(user_id)
    if user:
        return jsonify(user), 200
    else:
        return jsonify({"error": "User not found."}), 404


@api_routes.route("/update_user/<user_id>", methods=["PUT"])
def api_update_user(user_id):
    user_id = str(user_id)
    data = request.json
    updated_fields = data.get("updated_fields", {})
    success = update_user(user_id, updated_fields)
    if success:
        return jsonify({"message": "User updated."}), 200
    else:
        return jsonify({"error": "User not found or update failed."}), 400



@api_routes.route("/delete_user/<user_id>", methods=["DELETE"])
def api_delete_user(user_id):
    user_id = str(user_id)
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
    user_id = str(data.get("user_id"))
    system = str(data.get("system"))
    raw_ratings = data.get("ratings", [])

    if not get_user(user_id):
        return jsonify({"error": f"User '{user_id}' not found."}), 404
    if not get_system(system):
        return jsonify({"error": f"System '{system}' not found."}), 404

    ratings = []
    for r in raw_ratings:
        try:
            item_id = str(r["item_id"])
            value = float(r["value"])
            ratings.append({"item_id": item_id, "value": value})
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": f"Invalid rating format: {r}"}), 400

    add_ratings(user_id, system, ratings)
    return jsonify({"message": "Ratings added."}), 201




# Get all ratings for a user and system
@api_routes.route("/get_ratings_of_user_in_system/<user_id>/<system>", methods=["GET"])
def api_get_ratings(user_id, system):
    from db.collections import get_ratings_collection
    from flask import jsonify
    import logging

    try:
        user_id = str(user_id)
        system = str(system)

        # Debug logging
        logging.info(f"Fetching ratings for user_id: {user_id}, system: {system}")

        # Query ratings collection
        cursor = get_ratings_collection().find({"user_id": user_id, "system": system})
        ratings = []
        for doc in cursor:
            ratings.append({
                "item_id": doc.get("item_id"),
                "value": doc.get("value")
            })

        return jsonify(ratings), 200

    except Exception as e:
        logging.error(f"Error in /get_ratings_of_user_in_system: {e}")
        return jsonify({"error": str(e)}), 500



@api_routes.route("/delete_ratings_of_user_in_system/<user_id>/<system>", methods=["DELETE"])
def api_delete_all_ratings(user_id, system):
    user_id, system = str(user_id), str(system)
    deleted_count = delete_all_ratings(user_id, system)
    return jsonify({
        "message": f"Deleted {deleted_count} rating(s) for user '{user_id}' in system '{system}'."
    }), 200


@api_routes.route("/delete_all_user_ratings/<user_id>", methods=["DELETE"])
def api_delete_all_user_ratings(user_id):
    try:
        deleted_count = delete_all_user_ratings(user_id)

        return jsonify({
            "message": f"Deleted {deleted_count} rating(s) for user '{user_id}' across all systems."
        }), 200

    except Exception as e:
        logging.error(f"Error deleting ratings for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500




@api_routes.route("/delete_all_ratings_in_system/system/<system_id>", methods=["DELETE"])
def api_delete_all_ratings_in_system(system_id):
    system_id = str(system_id)
    deleted_count = delete_all_ratings_in_system(system_id)
    return jsonify({
        "message": f"Deleted {deleted_count} rating(s) in system '{system_id}'."
    }), 200



#-------- SINGLE RATING CRUD ---------
# Add a single rating
@api_routes.route("/add_rating", methods=["POST"])
def api_add_rating():
    data = request.json
    user_id = str(data.get("user_id"))
    system = str(data.get("system"))
    item_id = str(data.get("item_id"))
    try:
        value = float(data.get("value"))
    except (TypeError, ValueError):
        return jsonify({"error": "Rating value must be a number"}), 400

    if not get_user(user_id):
        return jsonify({"error": f"User '{user_id}' not found."}), 404
    if not get_system(system):
        return jsonify({"error": f"System '{system}' not found."}), 404

    success = add_rating(user_id, system, item_id, value)
    if not success:
        return jsonify({"error": "Rating already exists for this item."}), 400

    return jsonify({"message": "Rating added."}), 201


# Update a single rating
@api_routes.route("/update_rating", methods=["PUT"])
def api_update_rating():
    data = request.json
    success = update_rating(data["user_id"], data["system"], data["item_id"], data["value"])
    if success:
        return jsonify({"message": "Rating updated."}), 200
    else:
        return jsonify({"error": "Rating not found."}), 404

# Delete a single rating
@api_routes.route("/delete_rating", methods=["DELETE"])
def api_delete_rating():
    data = request.json
    success = delete_rating(data["user_id"], data["system"], data["item_id"])
    if success:
        return jsonify({"message": "Rating deleted."}), 200
    else:
        return jsonify({"error": "Rating not found."}), 404


#------- SYSTEM CRUD-------
@api_routes.route("/create_system", methods=["POST"])
def api_create_system():
    data = request.json
    system_id = data.get("system_id")
    display = data.get("display")
    mapping = data.get("mapping")
    create_system(system_id, display, mapping)
    return jsonify({"message": "System created."}), 201

@api_routes.route("/get_system/<system_id>", methods=["GET"])
def api_get_system(system_name):
    system = get_system(system_name)
    if system:
        return jsonify(system), 200
    return jsonify({"error": "System not found"}), 404

@api_routes.route("/update_system/<system_id>", methods=["PUT"])
def api_update_system(system_id):
    updates = request.json.get("updates", {})
    success = update_system(system_id, updates)
    if success:
        return jsonify({"message": "System updated."}), 200
    return jsonify({"error": "System not found or update failed."}), 400

@api_routes.route("/delete_system/<system_id>", methods=["DELETE"])
def api_delete_system(system_id):
    success = delete_system(system_id)
    if success:
        return jsonify({"message": "System deleted."}), 200
    return jsonify({"error": "System not found or delete failed."}), 400

@api_routes.route("/get_systems", methods=["GET"])
def api_list_systems():
    systems = list_systems()

    # Return only the collection_name field as system names
    names = [s.get("collection_name", "unknown") for s in systems]

    return jsonify(names), 200






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

    ratings = get_ratings_by_items(user_id, system, item_ids)
    return jsonify(ratings), 200


@api_routes.route("/estimated_ratings", methods=["POST"])
def api_estimated_ratings():
    from core.data_utils import load_data, normalize
    from db.collections import SYSTEMS, get_ratings_collection, get_users_collection
    from core.math_utils import solve_profile, calc_delta, est_rating
    from bson import ObjectId
    import logging

    try:
        data = request.json
        username = data.get("user_id")
        system = data.get("system")
        item_ids = data.get("item_ids", [])

        if not username or not system or not item_ids:
            return jsonify({"error": "Missing user_id, system, or item_ids"}), 400
        if not isinstance(item_ids, list):
            return jsonify({"error": "item_ids must be a list"}), 400
        if system not in SYSTEMS:
            return jsonify({"error": f"System '{system}' not found"}), 404

        username = username.strip().rstrip(",")

        # Get user document
        user_doc = get_users_collection().find_one({"username": {"$regex": f"^{username},?$"}})
        if not user_doc:
            return jsonify({"error": f"User '{username}' not found"}), 404
        user_obj_id = user_doc["_id"]

        # Load and normalize system data
        mapping = SYSTEMS[system]["mapping"]
        norm = normalize(load_data(system), mapping)

        # Support both user_id formats and allow system=None
        collection = get_ratings_collection()
        query = {
            "$or": [
                {"user_id": username},
                {"user_id": user_obj_id}
            ]
        }
        # Only include "system" if it's present in the documents
        try:
            test_doc = collection.find_one()
            if test_doc and "system" in test_doc:
                query["system"] = system
        except Exception:
            pass

        # Fetch user ratings
        user_ratings = {
            doc["item_id"]: doc.get("value") or doc.get("rating")
            for doc in collection.find(query)
            if doc.get("value") is not None or doc.get("rating") is not None
        }

        print("User ratings found:", user_ratings)

        if len(user_ratings) < 4:
            return jsonify({"error": "At least 4 ratings are required to estimate."}), 400

        # Build user profile
        n = len(norm[0]["featureVector"])
        rated_vecs, deltas = [], []
        for item in norm:
            if item["id"] in user_ratings:
                vec = item["featureVector"][:] + [user_ratings[item["id"]]]
                rated_vecs.append(vec)
                deltas.append(user_ratings[item["id"]])

        profile = solve_profile(rated_vecs, calc_delta(deltas, n))

        # Estimate ratings
        result = {}
        for item in norm:
            if item["id"] in item_ids:
                rating = est_rating(profile, item["featureVector"], n)
                result[item["id"]] = round(rating, 2)

        return jsonify(result), 200

    except Exception as e:
        logging.exception("Unexpected error in /estimated_ratings")
        return jsonify({"error": f"Server error: {str(e)}"}), 500





@api_routes.route("/evaluate_mae", methods=["POST"])
def api_evaluate_mae():
    data = request.get_json() or {}

    system   = data.get("system")
    item_ids = data.get("item_ids", [])
    ratings  = data.get("ratings", [])

    # 1. Basic validations
    if not system:
        return jsonify({"error": "Missing 'system' field."}), 400
    if not isinstance(item_ids, list) or not isinstance(ratings, list):
        return jsonify({"error": "'item_ids' and 'ratings' must be lists."}), 400
    if len(item_ids) != 8 or len(ratings) != 8:
        return jsonify({"error": "Exactly 8 items and 8 ratings are required."}), 400
    if not get_system(system):
        return jsonify({"error": f"System '{system}' not found."}), 404

    total_indices = list(range(8))
    # Pre-fetch one feature vector length
    try:
        sample_vec = get_features(item_ids[0], system)
        n_features = len(sample_vec)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch features for item {item_ids[0]}: {e}"}), 500

    # 2. For each train_size, run 10 tests and record MAEs
    avg_maes = {}
    for train_size in range(4, 8):  # 4,5,6,7
        maes = []
        for _ in range(10):
            # 2a. Random split
            train_idx = random.sample(total_indices, train_size)
            test_idx  = [i for i in total_indices if i not in train_idx]

            # 2b. Build profile from training subset
            train_vecs   = []
            train_ratings = []
            for i in train_idx:
                vec = get_features(item_ids[i], system)
                train_vecs.append(vec)
                train_ratings.append(ratings[i])

            deltas  = calc_delta(train_ratings, n_features)
            profile = solve_profile(train_vecs, deltas)

            # 2c. Estimate & compute MAE on test subset
            errors = []
            for i in test_idx:
                feats = get_features(item_ids[i], system)
                pred  = est_rating(profile, feats, n_features)
                errors.append(abs(ratings[i] - pred))

            # if for some reason no test items, skip (shouldn’t happen)
            if errors:
                maes.append(sum(errors) / len(errors))

        # 2d. Average the 10 MAEs for this train_size
        if maes:
            avg_maes[str(train_size)] = round(sum(maes) / len(maes), 4)
        else:
            avg_maes[str(train_size)] = None

    # 3. Return all four averages
    return jsonify({
        "average_mae_by_train_size": avg_maes
    }), 200


@api_routes.route("/get_rating/<user_id>/<system>/<item_id>", methods=["GET"])
def api_get_single_rating(user_id, system, item_id):
    if not get_user(user_id):
        return jsonify({"error": f"User '{user_id}' not found."}), 404

    if not get_system(system):
        return jsonify({"error": f"System '{system}' not found."}), 404

    ratings = get_ratings(user_id, system)
    for r in ratings:
        if r["item_id"] == item_id:
            return jsonify(r), 200
    return jsonify({"error": f"No rating found for item '{item_id}' by user '{user_id}'."}), 404
