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
