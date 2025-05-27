import json

from flask import (
    Blueprint, session, render_template, request,
    flash, redirect, url_for
)
from db.connection import get_db
from db.collections import SYSTEMS, get_ratings_collection, get_users_collection

dataset_bp = Blueprint("dataset", __name__)

# ────────────── API Check ──────────────
@dataset_bp.route("/upload", methods=["POST"])
def upload_dataset_api():
    return {"message": "Upload dataset endpoint works"}


# ────────────── Upload Dataset ──────────────
@dataset_bp.route("/upload_dataset", methods=["GET", "POST"])
def upload_dataset():
    if "username" not in session:
        return render_template("login.html")

    db = get_db()
    errors = {}

    if request.method == "POST":
        if "dataset" not in request.files:
            errors["file_error"] = "No file part."
            return render_template("upload_dataset.html", errors=errors)

        f = request.files["dataset"]
        if f.filename == "" or not f.filename.lower().endswith(".json"):
            errors["file_error"] = "Choose a JSON file."
            return render_template("upload_dataset.html", errors=errors)

        cname = request.form.get("collection_name", "").strip().lower()
        if not cname or not cname.isalnum():
            errors["collection_error"] = "Bad collection name."
            return render_template("upload_dataset.html", errors=errors)

        if cname in db.list_collection_names() or cname in {"users", "ratings", "system_metadata"}:
            errors["collection_error"] = "Collection exists/reserved."
            return render_template("upload_dataset.html", errors=errors)

        try:
            data = json.load(f)
            if not (isinstance(data, list) and all(isinstance(i, dict) for i in data)):
                raise ValueError("JSON must be an array of objects.")
        except Exception as e:
            errors["file_error"] = f"Invalid JSON: {e}"
            return render_template("upload_dataset.html", errors=errors)

        session["dataset_data"] = data
        session["collection_name"] = cname
        flash("Dataset uploaded. Map the fields.", "success")
        return redirect(url_for("dataset.map_dataset"))

    return render_template("upload_dataset.html", errors=errors)


# ────────────── Map Dataset ──────────────
@dataset_bp.route("/map_dataset", methods=["GET", "POST"])
def map_dataset():
    if "username" not in session:
        return render_template("login.html")

    db = get_db()

    if "dataset_data" not in session:
        flash("Upload a dataset first.", "danger")
        return redirect(url_for("dataset.upload_dataset"))

    data = session["dataset_data"]
    cname = session["collection_name"]
    errors = {}

    if request.method == "POST":
        mapping = {
            "id": request.form.get("id_field", "id"),
            "name": request.form.get("name_field", "name"),
            "description": request.form.get("desc_field", "description"),
            "image": request.form.get("image_field", "image"),
            "featureVector": request.form.get("vector_field", "featureVector"),
        }

        found_id = any(mapping["id"] in it for it in data)
        found_vector = any(mapping["featureVector"] in it for it in data)

        if not found_id:
            errors["id_error"] = f"'{mapping['id']}' not found."
        if not found_vector:
            errors["vector_error"] = f"'{mapping['featureVector']}' not found."

        if errors:
            return render_template("map_dataset.html", errors=errors)

        db[cname].insert_many(data)
        db["system_metadata"].update_one(
            {"collection_name": cname},
            {"$set": {"mapping": mapping}},
            upsert=True,
        )

        SYSTEMS[cname] = {
            "display": cname.capitalize(),
            "mapping": mapping,
        }

        session.pop("dataset_data")
        session.pop("collection_name")

        flash(f"Dataset '{cname}' saved.", "success")
        return redirect(url_for("item.index", system=cname))

    return render_template("map_dataset.html", errors=errors)


# ────────────── Delete Dataset ──────────────
@dataset_bp.route("/delete_dataset/<collection_name>")
def delete_dataset(collection_name):
    if "username" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    ratings_collection = get_ratings_collection()
    users_collection = get_users_collection()

    if collection_name in {"movies", "restaurants"}:
        flash("Cannot delete predefined datasets.", "danger")
        return redirect(url_for("system.choose_system"))

    if collection_name not in db.list_collection_names():
        flash("Dataset not found.", "danger")
        return redirect(url_for("system.choose_system"))

    db[collection_name].drop()
    db["system_metadata"].delete_one({"collection_name": collection_name})
    SYSTEMS.pop(collection_name, None)

    ratings_collection.delete_many({"system": collection_name})
    users_collection.update_many({}, {"$unset": {f"taste_vector.{collection_name}": ""}})

    flash(f"Dataset '{collection_name}' deleted.", "success")
    return redirect(url_for("system.choose_system"))
