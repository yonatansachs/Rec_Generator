from flask import Blueprint, request, jsonify

from core.ratings import add_ratings
from core.users import create_user

api = Blueprint("api", __name__)

@api.route("/api/batch_ratings", methods=["POST"])
def api_batch_ratings():
    data = request.json
    user_id = data.get("user_id")
    system = data.get("system")
    ratings = data.get("ratings", [])
    add_ratings(user_id, system, ratings)
    return jsonify({"message": "Ratings added."}), 201


@api.route("/api/create_user", methods=["POST"])
def api_create_user():
    data = request.json
    user_id = data.get("user_id")
    password = data.get("password")
    create_user(user_id, password)
    return jsonify({"message": "User added."}), 201