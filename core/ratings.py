from datetime import datetime

from bson import ObjectId
from flask import jsonify

from db.collections import SYSTEMS, ratings_collection


def add_ratings(user_id, system, ratings):
    if not user_id or not system or not ratings:
        return jsonify({"error": "Missing fields"}), 400
    if system not in SYSTEMS:
        return jsonify({"error": "Invalid system"}), 400

    for r in ratings:
        item_id = r.get("item_id")
        val = r.get("rating")
        if not item_id or val is None:
            continue
        try:
            val = float(val)
        except ValueError:
            continue
        ratings_collection.update_one(
            {"user_id": ObjectId(user_id), "system": system, "item_id": item_id},
            {"$set": {"rating": val, "timestamp": datetime.utcnow()}},
            upsert=True
        )