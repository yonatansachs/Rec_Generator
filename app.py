import json
import hashlib
from datetime import datetime
from bson import ObjectId
import pulp
from flask import Flask, render_template, request, session, flash, redirect, url_for
from pymongo import MongoClient
from pulp import (
    LpProblem, LpMinimize, LpVariable, lpSum, value,
    LpBinary, LpInteger, LpContinuous, PULP_CBC_CMD
)

# ─── at the top of app.py ───────────────────────────────────────────────────────
from flask_session import Session   # ← add this import

# …

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# ─── NEW: keep session data on disk, not in the browser cookie ────────────────
app.config.update(
    SESSION_TYPE="filesystem",         # where to store it
    SESSION_FILE_DIR="./.flask_session",   # any writable dir
    SESSION_FILE_THRESHOLD=100 * 1024 * 1024,   # 100 MB max per session
    SESSION_PERMANENT=False,           # nuke it when the browser closes
)
Session(app)
print("Session backend:", app.session_interface)
# ───────────────────────────────────────────────────────────────────────────────
  # initialise the server-side session

# MongoDB Configuration
MONGO_URI = "mongodb+srv://yonatansachs04:KAwr8Nc17qt4fV12@recgenerator.h80kkkm.mongodb.net/?retryWrites=true&w=majority&appName=RecGenerator"  # Adjust if using a remote MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["Rec_Generator"]

# Debug connection
print(f"Connected to database: {db.name}")
print(f"Collections: {db.list_collection_names()}")

# Collections
users_collection = db["users"]
ratings_collection = db["ratings"]

# Ensure indexes for efficient queries
users_collection.create_index("username", unique=True)
ratings_collection.create_index([("user_id", 1), ("system", 1), ("item_id", 1)], unique=True)

# --------------------------
# System Configuration
# --------------------------
SYSTEMS = {
    "Restaurants": {
        "display": "Restaurants",
        "mapping": {
            "id": "aaaid",
            "name": "name",
            "description": "description",
            "image": "image",
            "featureVector": "featureVector"
        }
    },
    "movie": {
        "display": "Movies",
        "mapping": {
            "id": "aaaid",
            "name": "aaamovieName",
            "description": "directors_names",
            "image": "image",
            "featureVector": "featureVector"
        }
    }
}

# Load existing collections as systems (excluding system collections)
def load_existing_collections():
    collections = db.list_collection_names()
    exclude = {"users", "ratings", "system.indexes"}
    for collection_name in collections:
        if collection_name in exclude or collection_name in SYSTEMS:
            continue
        collection = db[collection_name]
        sample_doc = collection.find_one()
        if sample_doc:
            mapping = {
                "id": "id",
                "name": "name",
                "description": "description",
                "image": "image",
                "featureVector": "featureVector"
            }
            SYSTEMS[collection_name] = {
                "display": collection_name.capitalize(),
                "mapping": mapping
            }
            print(f"Added existing collection '{collection_name}' to SYSTEMS")

# Run initialization
load_existing_collections()

# --------------------------
# User Management Functions
# --------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    user = {
        "username": username,
        "password_hash": hash_password(password),
        "taste_vector": {}
    }
    return users_collection.insert_one(user).inserted_id

def find_user_by_username(username):
    return users_collection.find_one({"username": username})

def check_password(user, password):
    return user["password_hash"] == hash_password(password)

def set_taste_vector(user_id, system, vector):
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {f"taste_vector.{system}": vector}}
    )

def get_taste_vector(user_id, system):
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    return user.get("taste_vector", {}).get(system)

# --------------------------
# Data Functions
# --------------------------
def load_data(system):
    collection = db[system]
    items = list(collection.find())
    print(f"Loaded {len(items)} items from collection: {system}")
    return items

def normalize_data(data, mapping):
    normalized = []
    for item in data:
        if mapping["id"] not in item or item.get(mapping["id"]) is None:
            raise Exception(f"Required field '{mapping['id']}' not found in item: {item}")
        if mapping["featureVector"] not in item or item.get(mapping["featureVector"]) is None:
            raise Exception(f"Required field '{mapping['featureVector']}' not found in item: {item}")
        normalized.append({
            "id": str(item.get(mapping["id"])),
            "name": item.get(mapping["name"], "Unknown"),
            "description": item.get(mapping["description"], ""),
            "image": item.get(mapping["image"], ""),
            "featureVector": item.get(mapping["featureVector"], [])
        })
    return normalized

# --------------------------
# Recommendation Functions
# --------------------------
s = 5  # Global rating scale

def calculate_delta(ratings, n):
    return [n - (n * (ri - 1) / (s - 1)) for ri in ratings]

def create_problem_with_pulp_dict(vectors, deltas):
    n = len(vectors[0])
    m = len(vectors)
    prob = LpProblem("MyProblem", LpMinimize)
    x = [LpVariable(f"x{i}", lowBound=-1, upBound=1, cat=LpInteger) for i in range(1, n + 1)]
    x_like = [LpVariable(f"x{i}_like", cat=LpBinary) for i in range(1, n + 1)]
    x_dislike = [LpVariable(f"x{i}_dislike", cat=LpBinary) for i in range(1, n + 1)]
    z = [LpVariable(f"z{i}", cat=LpContinuous) for i in range(1, m + 1)]
    prob += lpSum(z)
    for i in range(m):
        prob += lpSum([x_like[j] if vectors[i][j] == 0 else x_dislike[j] for j in range(n)]) + z[i] >= deltas[i]
        prob += lpSum([x_like[j] if vectors[i][j] == 0 else x_dislike[j] for j in range(n)]) - z[i] <= deltas[i]
    for j in range(n):
        prob += x[j] + 2 * x_dislike[j] <= 1
        prob += x[j] + x_dislike[j] >= 0
        prob += x[j] - x_like[j] <= 0
        prob += x[j] - 2 * x_like[j] >= -1
    prob.solve(PULP_CBC_CMD(msg=False))
    profile_vector = [v.varValue for v in x]
    return value(prob.objective), profile_vector

def calculate_estimated_rating(user_profile, item_features, s=5, n=20):
    delta = sum((u == -1 and r == 1) or (u == 1 and r == 0)
                for u, r in zip(user_profile, item_features))
    return s - (delta * (s - 1) / n)

# --------------------------
# Routes
# --------------------------
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if find_user_by_username(username):
            flash("Username already exists. Please choose another.", "danger")
            return render_template("signup.html")
        user_id = create_user(username, password)
        session["username"] = username
        session["user_id"] = str(user_id)
        flash("Sign up successful! You are now logged in.", "success")
        return redirect(url_for("choose_system"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = find_user_by_username(username)
        if not user or not check_password(user, password):
            flash("Invalid credentials. Please try again.", "danger")
            return render_template("login.html")
        session["username"] = username
        session["user_id"] = str(user["_id"])
        flash("Logged in successfully!", "success")
        return redirect(url_for("choose_system"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("user_id", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

@app.route("/choose_system")
def choose_system():
    if "username" not in session:
        return redirect(url_for("login"))
    collections = db.list_collection_names()
    print(f"All collections: {collections}")
    available_systems = {}
    for system, config in SYSTEMS.items():
        collection = db[system]
        count = collection.count_documents({})
        print(f"Collection {system} has {count} items")
        if count > 0:
            available_systems[system] = config
    if not available_systems:
        flash("No systems with data available. Please upload a dataset.", "warning")
    return render_template("choose_system.html", systems=available_systems)

@app.route("/index")
def index():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    mapping = SYSTEMS[system]["mapping"]
    try:
        data = load_data(system)
        if not data:
            flash(f"No items available for {SYSTEMS[system]['display']}.", "warning")
            return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
    user_vector = get_taste_vector(session["user_id"], system)
    user_has_vector = user_vector is not None
    return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=user_has_vector)

@app.route("/show_recommendations")
def show_recommendations():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    user_vector = get_taste_vector(session["user_id"], system)
    if not user_vector:
        flash("You haven't rated any items yet. Please rate some items first.", "warning")
        try:
            data = load_data(system)
            normalized_data = normalize_data(data, SYSTEMS[system]["mapping"]) if data else []
        except Exception as e:
            normalized_data = []
        return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    return redirect(url_for("dashboard", system=system))

@app.route("/recommend", methods=["POST"])
def recommend():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    mapping = SYSTEMS[system]["mapping"]
    try:
        data = load_data(system)
        if not data:
            flash(f"No items available for {SYSTEMS[system]['display']}.", "warning")
            return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
    ids_str = request.form.get("selected_ids")
    if not ids_str or ids_str.strip() == "":
        flash("No items were selected to rate. Please select at least one item.", "danger")
        return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    selected_ids = ids_str.split(",")
    user_id = session["user_id"]
    for sid in selected_ids:
        rating_val = request.form.get(f"rating_{sid}")
        if rating_val is None:
            continue
        try:
            rating = float(rating_val)
        except ValueError:
            continue
        ratings_collection.update_one(
            {"user_id": ObjectId(user_id), "system": system, "item_id": sid},
            {"$set": {"rating": rating, "timestamp": datetime.utcnow()}},
            upsert=True
        )
    existing_ratings = {r["item_id"]: r["rating"] for r in ratings_collection.find({"user_id": ObjectId(user_id), "system": system})}
    if not get_taste_vector(user_id, system) and len(existing_ratings) < 4:
        flash("You must rate at least 4 items.", "danger")
        return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    vectors = []
    for item in normalized_data:
        fv = item["featureVector"][:]
        if item["id"] in existing_ratings:
            fv_plus_rating = fv + [existing_ratings[item["id"]]]
        else:
            fv_plus_rating = fv + [3.0]
        vectors.append(fv_plus_rating)
    n_features = len(normalized_data[0]["featureVector"])
    rated_vectors = []
    ratings_for_optimization = []
    for item in normalized_data:
        if item["id"] in existing_ratings:
            rated_vectors.append(vectors[normalized_data.index(item)])
            ratings_for_optimization.append(existing_ratings[item["id"]])
    objective, profile_vector = create_problem_with_pulp_dict(
        vectors=rated_vectors,
        deltas=calculate_delta(ratings_for_optimization, n=n_features)
    )
    set_taste_vector(user_id, system, profile_vector)
    rated_items = []
    for item in normalized_data:
        est_rating = calculate_estimated_rating(user_profile=profile_vector, item_features=item["featureVector"], s=s, n=n_features)
        rated_items.append((item["name"], item["image"], est_rating, item["id"]))
    rated_items.sort(key=lambda x: x[2], reverse=True)
    top_recommendations = rated_items[:10]
    return render_template("recommendations.html", recommendations=top_recommendations, system=system)

@app.route("/update_ratings", methods=["POST"])
def update_ratings():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    user_id = session["user_id"]
    updated_ids_str = request.form.get("updated_ids", "")
    if not updated_ids_str:
        flash("No ratings were updated.", "warning")
        return redirect(url_for("dashboard", system=system))
    updated_ids = updated_ids_str.split(",")
    for item_id in updated_ids:
        val = request.form.get(f"rating_{item_id}")
        if val is None:
            continue
        try:
            new_rating = float(val)
        except ValueError:
            continue
        ratings_collection.update_one(
            {"user_id": ObjectId(user_id), "system": system, "item_id": item_id},
            {"$set": {"rating": new_rating, "timestamp": datetime.utcnow()}},
            upsert=True
        )
    mapping = SYSTEMS[system]["mapping"]
    try:
        data = load_data(system)
        if not data:
            flash(f"No items available for {SYSTEMS[system]['display']}.", "warning")
            return redirect(url_for("dashboard", system=system))
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error loading dataset: " + str(e), "danger")
        return redirect(url_for("dashboard", system=system))
    existing_ratings = {r["item_id"]: r["rating"] for r in ratings_collection.find({"user_id": ObjectId(user_id), "system": system})}
    vectors = []
    for item in normalized_data:
        fv = item["featureVector"][:]
        fv.append(existing_ratings.get(item["id"], 3.0))
        vectors.append(fv)
    n_features = len(normalized_data[0]["featureVector"])
    rated_vectors = []
    deltas = []
    for idx, item in enumerate(normalized_data):
        if item["id"] in existing_ratings:
            rated_vectors.append(vectors[idx])
            deltas.append(existing_ratings[item["id"]])
    _, profile_vector = create_problem_with_pulp_dict(
        vectors=rated_vectors,
        deltas=calculate_delta(deltas, n=n_features)
    )
    set_taste_vector(user_id, system, profile_vector)
    flash("Ratings updated and recommendations re-calculated.", "success")
    return redirect(url_for("dashboard", system=system))

@app.route("/update_item_rating")
def update_item_rating():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    item_id = request.args.get("id")
    rating_str = request.args.get("rating")
    try:
        new_rating = float(rating_str)
    except (ValueError, TypeError):
        flash("Invalid rating value.", "danger")
        return redirect(url_for("dashboard", system=system))
    user_id = session["user_id"]
    ratings_collection.update_one(
        {"user_id": ObjectId(user_id), "system": system, "item_id": item_id},
        {"$set": {"rating": new_rating, "timestamp": datetime.utcnow()}},
        upsert=True
    )
    try:
        items = normalize_data(load_data(system), SYSTEMS[system]["mapping"])
    except Exception as e:
        flash("Error loading dataset: " + str(e), "danger")
        return redirect(url_for("dashboard", system=system))
    existing = {r["item_id"]: r["rating"] for r in ratings_collection.find({"user_id": ObjectId(user_id), "system": system})}
    vectors = []
    for it in items:
        fv = it["featureVector"][:]
        fv.append(existing.get(it["id"], 3.0))
        vectors.append(fv)
    nfeat = len(items[0]["featureVector"])
    rated_vecs = []
    deltas = []
    for idx, it in enumerate(items):
        if it["id"] in existing:
            rated_vecs.append(vectors[idx])
            deltas.append(existing[it["id"]])
    _, profile = create_problem_with_pulp_dict(
        vectors=rated_vecs,
        deltas=calculate_delta(deltas, n=nfeat)
    )
    set_taste_vector(user_id, system, profile)
    flash("Rating updated and recommendations re-calculated.", "success")
    return redirect(url_for("dashboard", system=system))

@app.route("/reset_taste")
def reset_taste():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    user_id = session["user_id"]
    ratings_collection.delete_many({"user_id": ObjectId(user_id), "system": system})
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$unset": {f"taste_vector.{system}": ""}}
    )
    flash("Your recommendations and ratings have been reset. Please rate items again to get new recommendations.", "info")
    return redirect(url_for("index", system=system))

@app.route("/item_detail")
def item_detail():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    item_id = request.args.get("id")
    if not item_id:
        flash("No item specified.", "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
    mapping = SYSTEMS[system]["mapping"]
    try:
        data = load_data(system)
        if not data:
            flash(f"No items available for {SYSTEMS[system]['display']}.", "warning")
            return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
    item = next((it for it in normalized_data if it["id"] == str(item_id)), None)
    if not item:
        flash("Item not found.", "danger")
        return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    rating_record = ratings_collection.find_one({"user_id": ObjectId(session["user_id"]), "system": system, "item_id": item_id})
    current_rating = rating_record["rating"] if rating_record else 0
    return render_template("item_detail.html", item=item, system=system, current_rating=current_rating)

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    user_id = session["user_id"]
    mapping = SYSTEMS[system]["mapping"]
    try:
        data = load_data(system)
        if not data:
            flash(f"No items available for {SYSTEMS[system]['display']}.", "warning")
            return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
    user_vector = get_taste_vector(user_id, system)
    if not user_vector:
        flash("You haven't rated any items yet. Please rate some items first.", "warning")
        return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    n_features = len(normalized_data[0]["featureVector"])
    rated_items = []
    for item in normalized_data:
        est_rating = calculate_estimated_rating(user_profile=user_vector, item_features=item["featureVector"], s=s, n=n_features)
        rated_items.append((item["name"], item["image"], est_rating, item["id"]))
    rated_items.sort(key=lambda x: x[2], reverse=True)
    top_recommendations = rated_items[:10]
    return render_template("recommendations.html", recommendations=top_recommendations, system=system)

@app.route("/my_ratings")
def my_ratings():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))
    user_id = session["user_id"]
    rating_records = list(ratings_collection.find({"user_id": ObjectId(user_id), "system": system}))
    mapping = SYSTEMS[system]["mapping"]
    try:
        data = load_data(system)
        normalized_data = normalize_data(data, mapping) if data else []
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("my_ratings.html", rated_items=[], system=system)
    item_to_rating = {r["item_id"]: r["rating"] for r in rating_records}
    rated_items = []
    for it in normalized_data:
        if it["id"] in item_to_rating:
            rated_items.append({
                "id": it["id"],
                "name": it["name"],
                "image": it["image"],
                "description": it["description"],
                "rating": item_to_rating[it["id"]]
            })
    return render_template("my_ratings.html", rated_items=rated_items, system=system)

# --------------------------
# Dataset Upload Routes
# --------------------------
@app.route("/upload_dataset", methods=["GET", "POST"])
def upload_dataset():
    if "username" not in session:
        return render_template("login.html")
    errors = {}
    if request.method == "POST":
        print("Received POST request for upload_dataset")
        # Check if file part exists
        if "dataset" not in request.files:
            print("No file part in request.files")
            errors["file_error"] = "No file part."
            return render_template("upload_dataset.html", errors=errors)
        file = request.files["dataset"]
        print(f"File received: {file.filename}")
        if file.filename == "":
            print("No file selected")
            errors["file_error"] = "No file selected."
            return render_template("upload_dataset.html", errors=errors)
        # Check if the file is a JSON file
        if not file.filename.lower().endswith('.json'):
            print(f"File is not a JSON file: {file.filename}")
            errors["file_error"] = "Only JSON files are allowed."
            return render_template("upload_dataset.html", errors=errors)
        # Get the collection name
        collection_name = request.form.get("collection_name")
        print(f"Collection name provided: {collection_name}")
        if not collection_name:
            print("No collection name provided")
            errors["collection_error"] = "Please provide a collection name."
            return render_template("upload_dataset.html", errors=errors)
        # Validate collection name (basic validation)
        collection_name = collection_name.strip().lower()
        print(f"Processed collection name: {collection_name}")
        if not collection_name.isalnum():
            print("Collection name is not alphanumeric")
            errors["collection_error"] = "Collection name must contain only letters and numbers."
            return render_template("upload_dataset.html", errors=errors)
        # Check if collection already exists
        existing_collections = db.list_collection_names()
        print(f"Existing collections: {existing_collections}")
        if collection_name in existing_collections:
            print(f"Collection already exists: {collection_name}")
            errors["collection_error"] = f"Collection '{collection_name}' already exists. Please choose a different name."
            return render_template("upload_dataset.html", errors=errors)
        # Check for reserved names
        reserved_names = {"users", "ratings", "movies", "restaurants"}
        if collection_name in reserved_names:
            print(f"Collection name is reserved: {collection_name}")
            errors["collection_error"] = f"Collection name '{collection_name}' is reserved. Please choose a different name."
            return render_template("upload_dataset.html", errors=errors)
        try:
            # Read and parse the JSON file directly in memory
            print("Attempting to parse JSON file")
            data = json.load(file)
            print(f"Parsed data: {data[:2]}...")  # Log first two items for brevity
            if not isinstance(data, list):
                print("Data is not a JSON array")
                errors["file_error"] = "Dataset must be a JSON array of items."
                return render_template("upload_dataset.html", errors=errors)
            if not data:
                print("Dataset is empty")
                errors["file_error"] = "Dataset is empty."
                return render_template("upload_dataset.html", errors=errors)
            # Validate basic structure
            if not all(isinstance(item, dict) for item in data):
                print("Not all items in dataset are dictionaries")
                errors["file_error"] = "All items in the dataset must be JSON objects."
                return render_template("upload_dataset.html", errors=errors)
            # Store data and collection name in session for mapping
            print("Storing data in session")
            session["dataset_data"] = data
            session["collection_name"] = collection_name
            print("Flashing success message and redirecting to map_dataset")
            flash("Dataset uploaded successfully. Please map the fields.", "success")
            return redirect(url_for("map_dataset"))
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {str(e)}")
            errors["file_error"] = f"Invalid JSON format: {str(e)}"
            return render_template("upload_dataset.html", errors=errors)
        except Exception as e:
            print(f"Unexpected error during file processing: {str(e)}")
            errors["file_error"] = f"Error processing file: {str(e)}"
            return render_template("upload_dataset.html", errors=errors)
    print("Rendering upload_dataset.html for GET request")
    return render_template("upload_dataset.html", errors=errors)

@app.route("/map_dataset", methods=["GET", "POST"])
def map_dataset():
    if "username" not in session:
        return render_template("login.html")
    if "dataset_data" not in session or "collection_name" not in session:
        flash("Please upload a dataset first.", "danger")
        return redirect(url_for("upload_dataset"))
    errors = {}
    data = session["dataset_data"]
    collection_name = session["collection_name"]
    print(f"map_dataset: Collection name: {collection_name}, Data length: {len(data)}")
    if request.method == "POST":
        mapping = {
            "id": request.form.get("id_field", "id"),
            "name": request.form.get("name_field", "name"),
            "description": request.form.get("desc_field", "description"),
            "image": request.form.get("image_field", "image"),
            "featureVector": request.form.get("vector_field", "featureVector")
        }
        print(f"Mapping provided: {mapping}")
        # Validate that required fields exist in at least one item
        found_id = False
        found_vector = False
        for item in data:
            if mapping["id"] in item and item.get(mapping["id"]) is not None:
                found_id = True
            if mapping["featureVector"] in item and item.get(mapping["featureVector"]) is not None:
                found_vector = True
        if not found_id:
            print(f"Validation failed: ID field '{mapping['id']}' not found in any item")
            errors["id_error"] = f"Required field '{mapping['id']}' not found in any item."
        if not found_vector:
            print(f"Validation failed: featureVector field '{mapping['featureVector']}' not found in any item")
            errors["vector_error"] = f"Required field '{mapping['featureVector']}' not found in any item."
        if errors:
            print("Validation errors occurred, rendering map_dataset.html with errors")
            return render_template("map_dataset.html", errors=errors)
        # Create the new collection
        collection = db[collection_name]
        # Insert the data into the collection
        try:
            print(f"Inserting {len(data)} items into collection '{collection_name}'")
            collection.insert_many(data)
            print(f"Successfully inserted {len(data)} items into collection '{collection_name}'")
        except Exception as e:
            print(f"Error saving dataset to collection '{collection_name}': {str(e)}")
            flash(f"Error saving dataset to collection '{collection_name}': {str(e)}", "danger")
            return redirect(url_for("upload_dataset"))
        # Add to SYSTEMS
        SYSTEMS[collection_name] = {
            "display": collection_name.capitalize(),
            "mapping": mapping
        }
        print(f"Added new collection '{collection_name}' to SYSTEMS")
        # Clean up session only after successful save
        session.pop("dataset_data", None)
        session.pop("collection_name", None)
        flash(f"Dataset successfully saved to collection '{collection_name}'.", "success")
        return redirect(url_for("index", system=collection_name))
    print("Rendering map_dataset.html for GET request")
    return render_template("map_dataset.html", errors=errors)

@app.route("/delete_dataset/<collection_name>", methods=["GET"])
def delete_dataset(collection_name):
    if "username" not in session:
        return redirect(url_for("login"))
    if collection_name in {"movies", "restaurants"}:
        flash("Cannot delete predefined datasets.", "danger")
        return redirect(url_for("choose_system"))
    if collection_name not in db.list_collection_names():
        flash("Dataset not found.", "danger")
        return redirect(url_for("choose_system"))
    # Drop the collection
    db[collection_name].drop()
    # Remove from SYSTEMS
    SYSTEMS.pop(collection_name, None)
    # Remove associated ratings
    ratings_collection.delete_many({"user_id": ObjectId(session["user_id"]), "system": collection_name})
    # Remove taste vector
    users_collection.update_one(
        {"_id": ObjectId(session["user_id"])},
        {"$unset": {f"taste_vector.{collection_name}": ""}}
    )
    flash(f"Dataset '{collection_name}' deleted successfully.", "success")
    return redirect(url_for("choose_system"))

if __name__ == "__main__":
    app.run(debug=True)