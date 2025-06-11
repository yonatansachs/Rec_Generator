from datetime import datetime

from bson import ObjectId
from flask import jsonify

from db.collections import SYSTEMS, get_ratings_collection, get_items_collection


def add_ratings(user_id, system, ratings):
    if not user_id or not system or not ratings:
        return False
    if system not in SYSTEMS:
        return False

    collection = get_ratings_collection()
    for r in ratings:
        item_id = r.get("item_id")
        val = r.get("rating") if "rating" in r else r.get("value")
        if not item_id or val is None:
            continue
        try:
            val = float(val)
        except ValueError:
            continue
        collection.update_one(
            {"user_id": user_id, "system": system, "item_id": item_id},
            {"$set": {"value": val, "timestamp": datetime.utcnow()}},
            upsert=True
        )
    return True



def add_rating(user_id, system, item_id, value):
    collection = get_ratings_collection()

    # בדיקה אם הדירוג כבר קיים
    existing = collection.find_one({
        "user_id": user_id,
        "system": system,
        "item_id": item_id
    })

    if existing:
        return False  # כבר קיים דירוג

    # אם לא קיים – תוסיף
    collection.insert_one({
        "user_id": user_id,
        "system": system,
        "item_id": item_id,
        "value": value,
        "timestamp": datetime.utcnow()
    })
    return True

def get_ratings(user_id, system):
    cursor = get_ratings_collection().find({"user_id": user_id, "system": system})
    result = []
    for doc in cursor:
        result.append({
            "item_id": doc.get("item_id"),
            "value": doc.get("value")
        })
    return result


def update_rating(user_id, system, item_id, value):
    result = get_ratings_collection().update_one(
        {"user_id": user_id, "system": system, "item_id": item_id},
        {"$set": {"value": value}}
    )
    return result.modified_count > 0

def delete_rating(user_id, system, item_id):
    result = get_ratings_collection().delete_one(
        {"user_id": user_id, "system": system, "item_id": item_id}
    )
    return result.deleted_count > 0

def delete_all_ratings(user_id, system):
    result = get_ratings_collection().delete_many({
        "user_id": user_id,
        "system": system
    })
    return result.deleted_count

def get_ratings_by_items(user_id, system, item_ids):
    ratings_col = get_items_collection('ratings')
    query = {
        "user_id": user_id,
        "system": system,
        "item_id": {"$in": item_ids}
    }
    cursor = ratings_col.find(query)
    # תוצאה בפורמט {item_id: value}
    result = {r["item_id"]: r["value"] for r in cursor}
    return result

# core/ratings.py


def delete_all_user_ratings(user_id):
    collection = get_ratings_collection()
    result = collection.delete_many({"user_id": user_id})
    return result.deleted_count

def delete_all_ratings_in_system(system_id):
    collection = get_ratings_collection()
    result = collection.delete_many({"system": system_id})
    return result.deleted_count