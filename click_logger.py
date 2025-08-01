
from flask import Blueprint, request, jsonify
from db.collections import get_click_logs_collection

click_api = Blueprint("click_api", __name__)

@click_api.route("/log_click", methods=["POST"])
def log_click():
    data = request.get_json()
    data["ip"] = request.remote_addr
    data["ua"] = request.headers.get("User-Agent")
    get_click_logs_collection().insert_one(data)

    return jsonify({"status": "logged"}), 200
