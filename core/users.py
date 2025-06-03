from bson import ObjectId
from db.collections import get_users_collection
from utils.security import hash_pw

# ─────────── User Creation & Lookup ───────────

def create_user(username, password):
    return get_users_collection().insert_one({
        "username": username,
        "password_hash": hash_pw(password),
        "taste_vector": {},
    }).inserted_id

# ─────────── User Management ───────────

def get_user(username):
    user = get_users_collection().find_one({"username": username}, {"_id": 0, "password_hash": 0})
    return user

def update_user(username, updated_fields):
    if "password" in updated_fields:
        updated_fields["password_hash"] = hash_pw(updated_fields.pop("password"))
    result = get_users_collection().update_one({"username": username}, {"$set": updated_fields})
    return result.modified_count > 0

def delete_user(username):
    result = get_users_collection().delete_one({"username": username})
    return result.deleted_count > 0

def find_user(username):
    return get_users_collection().find_one({"username": username})

def check_pw(user, pw):
    return user["password_hash"] == hash_pw(pw)

# ─────────── Taste Vector Handling ───────────

def set_taste(user_id, system, vec):
    get_users_collection().update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {f"taste_vector.{system}": vec}},
    )

def get_taste(user_id, system):
    user = get_users_collection().find_one({"_id": ObjectId(user_id)})
    return user.get("taste_vector", {}).get(system)
