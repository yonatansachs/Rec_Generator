import json
import hashlib
from datetime import datetime

from bson import ObjectId
from flask import (
    Flask, render_template, request, session,
    flash, redirect, url_for
)
from flask_session import Session
from pymongo import MongoClient
from pulp import (
    LpProblem, LpMinimize, LpVariable, lpSum, value,
    LpBinary, LpInteger, LpContinuous, PULP_CBC_CMD
)

# ─────────────────────────── Flask setup ────────────────────────────
app = Flask(__name__)
app.secret_key = "your_secret_key_here"          # ← change in production!

app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR="./.flask_session",
    SESSION_FILE_THRESHOLD=100 * 1024 * 1024,
    SESSION_PERMANENT=False,
)
Session(app)
print("Session backend:", app.session_interface)

# ───────────────────────── MongoDB Atlas ────────────────────────────
MONGO_URI = (
    "MONGO_URI"
)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["Rec_Generator"]
print("Connected to database:", db.name)

users_collection   = db["users"]
ratings_collection = db["ratings"]
db["system_metadata"]                                # ensure collection exists

users_collection.create_index("username", unique=True)
ratings_collection.create_index(
    [("user_id", 1), ("system", 1), ("item_id", 1)], unique=True
)

# ───────────────────────  SYSTEMS registry  ─────────────────────────
SYSTEMS = {
    "Restaurants": {
        "display": "Restaurants",
        "mapping": {
            "id": "aaaid",
            "name": "name",
            "description": "description",
            "image": "image",
            "featureVector": "featureVector",
        },
    },
    "movie": {
        "display": "Movies",
        "mapping": {
            "id": "aaaid",
            "name": "aaamovieName",
            "description": "directors_names",
            "image": "image",
            "featureVector": "featureVector",
        },
    },
}

# ────────────────  load_existing_collections()  ─────────────────────
def load_existing_collections() -> None:
    """
    Register every non-utility Mongo collection as a system.
    If we stored a user-defined mapping in `system_metadata`,
    use it; otherwise fall back to default field names.
    """
    exclude = {
        "users", "ratings", "system.indexes", "system_metadata"
    }
    for cname in db.list_collection_names():
        if cname in exclude or cname in SYSTEMS:
            continue

        meta = db["system_metadata"].find_one({"collection_name": cname})
        mapping = (
            meta["mapping"]
            if meta and "mapping" in meta else {
                "id": "id",
                "name": "name",
                "description": "description",
                "image": "image",
                "featureVector": "featureVector",
            }
        )
        SYSTEMS[cname] = {
            "display": cname.capitalize(),
            "mapping": mapping,
        }
        print(f"Registered '{cname}' with mapping {mapping}")

load_existing_collections()

# ───────────────────── helper functions ─────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def create_user(username, password):
    return users_collection.insert_one({
        "username": username,
        "password_hash": hash_pw(password),
        "taste_vector": {},
    }).inserted_id

def find_user(username):
    return users_collection.find_one({"username": username})

def check_pw(user, pw):
    return user["password_hash"] == hash_pw(pw)

def set_taste(u_id, system, vec):
    users_collection.update_one(
        {"_id": ObjectId(u_id)},
        {"$set": {f"taste_vector.{system}": vec}},
    )

def get_taste(u_id, system):
    user = users_collection.find_one({"_id": ObjectId(u_id)})
    return user.get("taste_vector", {}).get(system)

def load_data(system):
    items = list(db[system].find())
    print(f"Loaded {len(items)} items from '{system}'")
    return items

def normalize(data, mapping):
    out = []
    for it in data:
        if mapping["id"] not in it or mapping["featureVector"] not in it:
            raise Exception("Dataset missing mapped fields")
        out.append({
            "id":           str(it[mapping["id"]]),
            "name":         it.get(mapping["name"], "Unknown"),
            "description":  it.get(mapping["description"], ""),
            "image":        it.get(mapping["image"], ""),
            "featureVector": it[mapping["featureVector"]],
        })
    return out

# ────────────────── recommendation mathematics ─────────────────────
s = 5
def calc_delta(ratings, n):
    return [n - (n * (r - 1) / (s - 1)) for r in ratings]

def solve_profile(vectors, deltas):
    n, m = len(vectors[0]), len(vectors)
    prob = LpProblem("p", LpMinimize)
    x  = [LpVariable(f"x{i}", -1, 1, LpInteger) for i in range(n)]
    xl = [LpVariable(f"xl{i}", cat=LpBinary)   for i in range(n)]
    xd = [LpVariable(f"xd{i}", cat=LpBinary)   for i in range(n)]
    z  = [LpVariable(f"z{i}")                  for i in range(m)]
    prob += lpSum(z)
    for i in range(m):
        expr = lpSum(xl[j] if vectors[i][j]==0 else xd[j] for j in range(n))
        prob += expr + z[i] >= deltas[i]
        prob += expr - z[i] <= deltas[i]
    for j in range(n):
        prob += x[j] + 2*xd[j] <= 1; prob += x[j] + xd[j] >= 0
        prob += x[j] - xl[j] <= 0;  prob += x[j] - 2*xl[j] >= -1
    prob.solve(PULP_CBC_CMD(msg=False))
    return [v.varValue for v in x]

def est_rating(profile, features, n):
    delta = sum((u==-1 and r==1) or (u==1 and r==0)
                for u, r in zip(profile, features))
    return s - (delta*(s-1)/n)

# ────────────────────────  routes ───────────────────────────
@app.route("/")
def root(): return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        if find_user(u):
            flash("Username already exists.", "danger")
            return render_template("signup.html")
        uid = create_user(u, p)
        session.update(username=u, user_id=str(uid))
        flash("Sign-up successful!", "success")
        return redirect(url_for("choose_system"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        user = find_user(u)
        if not user or not check_pw(user, p):
            flash("Invalid credentials.", "danger")
            return render_template("login.html")
        session.update(username=u, user_id=str(user["_id"]))
        return redirect(url_for("choose_system"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

@app.route("/choose_system")
def choose_system():
    if "username" not in session: return redirect(url_for("login"))
    available = {}
    for sys, cfg in SYSTEMS.items():
        if db[sys].count_documents({}) > 0:
            available[sys] = cfg
    if not available:
        flash("No datasets available. Upload one!", "warning")
    return render_template("choose_system.html", systems=available)
@app.route("/index")
def index():
    if "username" not in session:
        return redirect(url_for("login"))

    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS:
        flash("Invalid system selected.", "danger")
        return redirect(url_for("choose_system"))

    # Raw inputs
    price_raw    = request.args.get("price", "")
    cuisine_raw  = request.args.get("cuisine", "")
    meal_raw     = request.args.get("meal_type", "")

    # Clean up: only keep non-empty selections
    cuisines = [cuisine_raw] if cuisine_raw else []
    # Build feature filters
    feature_filters = []
    if price_raw:
        feature_filters.append(f"priceLevel.{price_raw}")
    if cuisines:
        feature_filters += [f"cuisines.{c}" for c in cuisines]
    if meal_raw:
        feature_filters.append(f"mealTypes.{meal_raw}")

    # If any filters, apply $all; otherwise empty query
    mongo_q = {"features": {"$all": feature_filters}} if feature_filters else {}

    try:
        raw_items = db[system].find(mongo_q)
        items     = normalize(list(raw_items), SYSTEMS[system]["mapping"])
    except Exception as e:
        flash(f"Error loading data: {e}", "danger")
        items = []

    return render_template(
        "index.html",
        restaurants=items,
        system=system,
        current_price=price_raw,
        current_cuisines=cuisines,
        current_meal=meal_raw,
        user_has_vector=(get_taste(session["user_id"], system) is not None)
    )


@app.route("/show_recommendations")
def show_recommendations():
    if "username" not in session: return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS: flash("Invalid system", "danger"); return redirect(url_for("choose_system"))
    if not get_taste(session["user_id"], system):
        flash("Rate some items first.", "warning")
        mapping = SYSTEMS[system]["mapping"]
        try:
            norm = normalize(load_data(system), mapping)
        except Exception:
            norm = []
        return render_template("index.html", restaurants=norm, system=system, user_has_vector=False)
    return redirect(url_for("dashboard", system=system))

@app.route("/recommend", methods=["POST"])
def recommend():
    if "username" not in session: return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system not in SYSTEMS: flash("Invalid system", "danger"); return redirect(url_for("choose_system"))
    mapping = SYSTEMS[system]["mapping"]
    try:
        norm = normalize(load_data(system), mapping)
    except Exception as e:
        flash(f"Dataset error: {e}", "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)

    ids_str = request.form.get("selected_ids", "").strip()
    if not ids_str:
        flash("Select at least one item.", "danger")
        return render_template("index.html", restaurants=norm, system=system, user_has_vector=False)

    selected_ids = ids_str.split(",")
    u_id = session["user_id"]
    for sid in selected_ids:
        rating_val = request.form.get(f"rating_{sid}")
        if not rating_val: continue
        try: r = float(rating_val)
        except ValueError: continue
        ratings_collection.update_one(
            {"user_id": ObjectId(u_id), "system": system, "item_id": sid},
            {"$set": {"rating": r, "timestamp": datetime.utcnow()}},
            upsert=True,
        )

    existing = {
        r["item_id"]: r["rating"]
        for r in ratings_collection.find({"user_id": ObjectId(u_id), "system": system})
    }
    if not get_taste(u_id, system) and len(existing) < 4:
        flash("Rate at least 4 items.", "danger")
        return render_template("index.html", restaurants=norm, system=system, user_has_vector=False)

    vectors=[]
    for it in norm:
        fv = it["featureVector"][:] + [existing.get(it["id"], 3.0)]
        vectors.append(fv)
    n = len(norm[0]["featureVector"])
    rated_vecs=[]; deltas=[]
    for it in norm:
        if it["id"] in existing:
            rated_vecs.append(vectors[norm.index(it)])
            deltas.append(existing[it["id"]])
    profile = solve_profile(rated_vecs, calc_delta(deltas, n))
    set_taste(u_id, system, profile)

    rated=[]
    for it in norm:
        rated.append((
            it["name"],
            it["image"],
            est_rating(profile, it["featureVector"], n),
            it["id"],
        ))
    rated.sort(key=lambda x: x[2], reverse=True)
    return render_template("recommendations.html", recommendations=rated[:10], system=system)

@app.route("/update_ratings", methods=["POST"])
def update_ratings():
    if "username" not in session: return redirect(url_for("login"))
    system = request.args.get("system","restaurants")
    if system not in SYSTEMS: flash("Invalid system","danger"); return redirect(url_for("choose_system"))
    u_id = session["user_id"]
    updated_ids_str = request.form.get("updated_ids","")
    if not updated_ids_str:
        flash("No ratings updated.","warning"); return redirect(url_for("dashboard", system=system))
    updated_ids = updated_ids_str.split(",")
    for item_id in updated_ids:
        val = request.form.get(f"rating_{item_id}")
        if not val: continue
        try: new_r = float(val)
        except ValueError: continue
        ratings_collection.update_one(
            {"user_id": ObjectId(u_id), "system": system, "item_id": item_id},
            {"$set": {"rating": new_r, "timestamp": datetime.utcnow()}},
            upsert=True,
        )

    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    existing = {
        r["item_id"]: r["rating"]
        for r in ratings_collection.find({"user_id": ObjectId(u_id), "system": system})
    }
    vectors=[ it["featureVector"][:] + [existing.get(it["id"],3.0)] for it in norm ]
    n=len(norm[0]["featureVector"])
    rated_vecs=[]; deltas=[]
    for i,it in enumerate(norm):
        if it["id"] in existing:
            rated_vecs.append(vectors[i]); deltas.append(existing[it["id"]])
    profile = solve_profile(rated_vecs, calc_delta(deltas, n))
    set_taste(u_id, system, profile)
    flash("Ratings updated.","success")
    return redirect(url_for("dashboard", system=system))

@app.route("/update_item_rating")
def update_item_rating():
    if "username" not in session: return redirect(url_for("login"))
    system = request.args.get("system","restaurants")
    if system not in SYSTEMS: flash("Invalid system","danger"); return redirect(url_for("choose_system"))
    item_id = request.args.get("id")
    try: new_r = float(request.args.get("rating"))
    except (TypeError,ValueError): flash("Invalid rating","danger"); return redirect(url_for("dashboard", system=system))
    u_id = session["user_id"]
    ratings_collection.update_one(
        {"user_id":ObjectId(u_id), "system":system, "item_id":item_id},
        {"$set":{"rating":new_r, "timestamp":datetime.utcnow()}},
        upsert=True,
    )

    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    existing = {
        r["item_id"]: r["rating"]
        for r in ratings_collection.find({"user_id": ObjectId(u_id), "system": system})
    }
    vectors=[ it["featureVector"][:] + [existing.get(it["id"],3.0)] for it in norm ]
    n=len(norm[0]["featureVector"])
    rated_vecs=[]; deltas=[]
    for i,it in enumerate(norm):
        if it["id"] in existing:
            rated_vecs.append(vectors[i]); deltas.append(existing[it["id"]])
    profile = solve_profile(rated_vecs, calc_delta(deltas, n))
    set_taste(u_id, system, profile)
    flash("Rating updated.","success")
    return redirect(url_for("dashboard", system=system))

@app.route("/reset_taste")
def reset_taste():
    if "username" not in session: return redirect(url_for("login"))
    system = request.args.get("system","restaurants")
    if system not in SYSTEMS: flash("Invalid system","danger"); return redirect(url_for("choose_system"))
    u_id = session["user_id"]
    ratings_collection.delete_many({"user_id":ObjectId(u_id), "system":system})
    users_collection.update_one(
        {"_id": ObjectId(u_id)},
        {"$unset": {f"taste_vector.{system}": ""}},
    )
    flash("Selections reset.","info")
    return redirect(url_for("index", system=system))

@app.route("/item_detail")
def item_detail():
    if "username" not in session: return redirect(url_for("login"))
    system = request.args.get("system","restaurants")
    if system not in SYSTEMS: flash("Invalid system","danger"); return redirect(url_for("choose_system"))
    item_id = request.args.get("id")
    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    item = next((it for it in norm if it["id"] == str(item_id)), None)
    if not item:
        flash("Item not found.","danger"); return redirect(url_for("index", system=system))
    rec = ratings_collection.find_one({"user_id":ObjectId(session["user_id"]), "system":system, "item_id":item_id})
    return render_template("item_detail.html", item=item, system=system, current_rating=rec["rating"] if rec else 0)

@app.route("/dashboard")
def dashboard():
    if "username" not in session: return redirect(url_for("login"))
    system = request.args.get("system","restaurants")
    if system not in SYSTEMS: flash("Invalid system","danger"); return redirect(url_for("choose_system"))
    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    profile = get_taste(session["user_id"], system)
    if not profile:
        flash("Rate some items first.","warning"); return redirect(url_for("index", system=system))
    n=len(norm[0]["featureVector"])
    rated=[ (it["name"], it["image"], est_rating(profile,it["featureVector"],n), it["id"]) for it in norm ]
    rated.sort(key=lambda x:x[2], reverse=True)
    return render_template("recommendations.html", recommendations=rated[:10], system=system)

@app.route("/my_ratings")
def my_ratings():
    if "username" not in session: return redirect(url_for("login"))
    system = request.args.get("system","restaurants")
    if system not in SYSTEMS: flash("Invalid system","danger"); return redirect(url_for("choose_system"))
    mapping = SYSTEMS[system]["mapping"]
    norm = normalize(load_data(system), mapping)
    recs = list(ratings_collection.find({"user_id":ObjectId(session["user_id"]), "system":system}))
    ratings_map = {r["item_id"]:r["rating"] for r in recs}
    rated_items = [
        {
            "id":it["id"],
            "name":it["name"],
            "image":it["image"],
            "description":it["description"],
            "rating":ratings_map[it["id"]],
        }
        for it in norm if it["id"] in ratings_map
    ]
    return render_template("my_ratings.html", rated_items=rated_items, system=system)

# ──────────────  dataset upload / mapping  ────────────────
@app.route("/upload_dataset", methods=["GET", "POST"])
def upload_dataset():
    if "username" not in session: return render_template("login.html")
    errors={}
    if request.method=="POST":
        if "dataset" not in request.files:
            errors["file_error"]="No file part."; return render_template("upload_dataset.html", errors=errors)
        f = request.files["dataset"]
        if f.filename=="" or not f.filename.lower().endswith(".json"):
            errors["file_error"]="Choose a JSON file."; return render_template("upload_dataset.html", errors=errors)
        cname = request.form.get("collection_name","").strip().lower()
        if not cname or not cname.isalnum():
            errors["collection_error"]="Bad collection name."; return render_template("upload_dataset.html", errors=errors)
        if cname in db.list_collection_names() or cname in {"users","ratings","system_metadata"}:
            errors["collection_error"]="Collection exists/reserved."; return render_template("upload_dataset.html", errors=errors)
        try:
            data=json.load(f)
            if not (isinstance(data,list) and all(isinstance(i,dict) for i in data)):
                raise ValueError("JSON must be an array of objects.")
        except Exception as e:
            errors["file_error"]=f"Invalid JSON: {e}"; return render_template("upload_dataset.html", errors=errors)

        session["dataset_data"]=data; session["collection_name"]=cname
        flash("Dataset uploaded. Map the fields.","success")
        return redirect(url_for("map_dataset"))
    return render_template("upload_dataset.html", errors=errors)

@app.route("/map_dataset", methods=["GET","POST"])
def map_dataset():
    if "username" not in session: return render_template("login.html")
    if "dataset_data" not in session: flash("Upload a dataset first.","danger"); return redirect(url_for("upload_dataset"))
    data = session["dataset_data"]; cname=session["collection_name"]; errors={}
    if request.method=="POST":
        mapping={
            "id":request.form.get("id_field","id"),
            "name":request.form.get("name_field","name"),
            "description":request.form.get("desc_field","description"),
            "image":request.form.get("image_field","image"),
            "featureVector":request.form.get("vector_field","featureVector"),
        }
        found_id     = any(mapping["id"] in it for it in data)
        found_vector = any(mapping["featureVector"] in it for it in data)
        if not found_id: errors["id_error"]=f"'{mapping['id']}' not found."
        if not found_vector: errors["vector_error"]=f"'{mapping['featureVector']}' not found."
        if errors: return render_template("map_dataset.html", errors=errors)

        db[cname].insert_many(data)
        db["system_metadata"].update_one(
            {"collection_name":cname},
            {"$set":{"mapping":mapping}},
            upsert=True,
        )
        SYSTEMS[cname]={"display":cname.capitalize(),"mapping":mapping}
        session.pop("dataset_data"); session.pop("collection_name")
        flash(f"Dataset '{cname}' saved.","success")
        return redirect(url_for("index", system=cname))
    return render_template("map_dataset.html", errors=errors)

@app.route("/delete_dataset/<collection_name>")
def delete_dataset(collection_name):
    if "username" not in session: return redirect(url_for("login"))
    if collection_name in {"movies","restaurants"}:
        flash("Cannot delete predefined datasets.","danger"); return redirect(url_for("choose_system"))
    if collection_name not in db.list_collection_names():
        flash("Dataset not found.","danger"); return redirect(url_for("choose_system"))
    db[collection_name].drop()
    db["system_metadata"].delete_one({"collection_name":collection_name})
    SYSTEMS.pop(collection_name, None)
    ratings_collection.delete_many({"system":collection_name})
    users_collection.update_many({}, {"$unset":{f"taste_vector.{collection_name}":""}})
    flash(f"Dataset '{collection_name}' deleted.","success")
    return redirect(url_for("choose_system"))

# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
