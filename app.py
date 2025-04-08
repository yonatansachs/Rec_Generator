import os, json, hashlib, pulp
from datetime import datetime
from flask import Flask, render_template, request, session, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from pulp import (
    LpProblem, LpMinimize, LpVariable, lpSum, value,
    LpBinary, LpInteger, LpContinuous, PULP_CBC_CMD
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Replace with a secure key

# Use SQLite for simplicity
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Set the uploads folder relative to app.root_path so that it works on Colab/deployment.
UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = SQLAlchemy(app)


# --------------------------
# Database Models
# --------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # taste_vector stores a JSON mapping of system names to vectors.
    taste_vector = db.Column(db.Text, nullable=True)

    def set_password(self, password):
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()

    def check_password(self, password):
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()

    def set_taste_vector(self, system, vector):
        if self.taste_vector:
            vectors = json.loads(self.taste_vector)
        else:
            vectors = {}
        vectors[system] = vector
        self.taste_vector = json.dumps(vectors)

    def get_taste_vector(self, system):
        if self.taste_vector:
            vectors = json.loads(self.taste_vector)
            return vectors.get(system)
        return None


class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    system = db.Column(db.String(50), nullable=False)
    item_id = db.Column(db.String(80), nullable=False)
    rating = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# New model for permanently saving custom datasets.
class CustomDataset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    dataset_name = db.Column(db.String(120), nullable=False)
    dataset_path = db.Column(db.String(200), nullable=False)
    mapping = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()

# --------------------------
# Pre-defined System Configuration
# --------------------------
SYSTEMS = {
    "restaurants": {
        "display": "Restaurants",
        "file": "Data/feat1000_v2.json",
        "mapping": {
            "id": "aaaid",
            "name": "name",
            "description": "description",
            "image": "image",
            "featureVector": "featureVector"
        }
    },
    "movies": {
        "display": "Movies",
        "file": "Data/movies.json",
        "mapping": {
            "id": "aaaid",
            "name": "aaamovieName",
            "description": "movie_url",
            "image": "image",
            "featureVector": "featureVector"
        }
    }
}


# For custom datasets we use system "custom".
# For temporary workflow, the uploaded file path and mapping are stored in:
#   session["custom_dataset_path"] and session["custom_mapping"]

def load_data(filepath):
    # If filepath is not absolute, build the absolute path using app.root_path.
    if not os.path.isabs(filepath):
        filepath = os.path.join(app.root_path, filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_data(data, mapping):
    """
    Normalize the data based on the provided mapping.
    Requires each item to contain mapping["id"] and mapping["featureVector"].
    Raises Exception if a required field is missing.
    """
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
        if User.query.filter_by(username=username).first():
            flash("Username already exists. Please choose another.", "danger")
            return render_template("signup.html")
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session["username"] = username
        flash("Sign up successful! You are now logged in.", "success")
        return redirect(url_for("choose_system"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("Invalid credentials. Please try again.", "danger")
            return render_template("login.html")
        session["username"] = username
        flash("Logged in successfully!", "success")
        return redirect(url_for("choose_system"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/choose_system")
def choose_system():
    if "username" not in session:
        return redirect(url_for("login"))
    user = User.query.filter_by(username=session["username"]).first()
    from sqlalchemy import desc
    custom_datasets = CustomDataset.query.filter_by(user_id=user.id).order_by(
        desc(CustomDataset.timestamp)).all() if user else []
    return render_template("choose_system.html", systems=SYSTEMS, custom_datasets=custom_datasets)


@app.route("/index")
def index():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"]
    try:
        data = load_data(SYSTEMS[system]["file"])
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
    user = User.query.filter_by(username=session["username"]).first()
    user_vector = user.get_taste_vector(system)
    user_has_vector = user_vector is not None
    return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=user_has_vector)


@app.route("/show_recommendations")
def show_recommendations():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    if system == "custom":
        flash("For your custom dataset, please use the custom rating page.", "warning")
        return redirect(url_for("custom_index"))
    user = User.query.filter_by(username=session["username"]).first()
    user_vector = user.get_taste_vector(system)
    if not user_vector:
        flash("You haven't rated any items yet. Please rate some items first.", "warning")
        try:
            data = load_data(SYSTEMS[system]["file"])
            normalized_data = normalize_data(data, SYSTEMS[system]["mapping"])
        except Exception as e:
            normalized_data = []
        return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    return redirect(url_for("dashboard", system=system))


@app.route("/recommend", methods=["POST"])
def recommend():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"]
    try:
        data = load_data(SYSTEMS[system]["file"])
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
    ids_str = request.form.get("selected_ids")
    if not ids_str or ids_str.strip() == "":
        flash("No items were selected to rate. Please select at least one item.", "danger")
        return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    selected_ids = ids_str.split(",")
    user = User.query.filter_by(username=session["username"]).first()
    for sid in selected_ids:
        rating_val = request.form.get(f"rating_{sid}")
        if rating_val is None:
            continue
        try:
            rating = float(rating_val)
        except ValueError:
            continue
        rating_record = Rating.query.filter_by(user_id=user.id, system=system, item_id=sid).first()
        if rating_record:
            rating_record.rating = rating
            rating_record.timestamp = datetime.utcnow()
        else:
            new_rating = Rating(user_id=user.id, system=system, item_id=sid, rating=rating)
            db.session.add(new_rating)
    db.session.commit()
    existing_ratings = {r.item_id: r.rating for r in Rating.query.filter_by(user_id=user.id, system=system).all()}
    if not user.get_taste_vector(system) and len(existing_ratings) < 4:
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
    user.set_taste_vector(system, profile_vector)
    db.session.commit()
    rated_items = []
    for item in normalized_data:
        est_rating = calculate_estimated_rating(user_profile=profile_vector, item_features=item["featureVector"], s=s,
                                                n=n_features)
        rated_items.append((item["name"], item["image"], est_rating, item["id"]))
    rated_items.sort(key=lambda x: x[2], reverse=True)
    top_recommendations = rated_items[:10]
    return render_template("recommendations.html", recommendations=top_recommendations, system=system)


@app.route("/update_ratings", methods=["POST"])
def update_ratings():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    updated_ids_str = request.form.get("updated_ids")
    if not updated_ids_str:
        flash("No ratings were updated.", "warning")
        if system == "custom":
            dataset_id = request.form.get("dataset_id")
            return redirect(url_for("custom_index", dataset_id=dataset_id))
        else:
            return redirect(url_for("dashboard", system=system))
    updated_ids = updated_ids_str.split(",")
    user = User.query.filter_by(username=session["username"]).first()
    for item_id in updated_ids:
        rating_val = request.form.get(f"rating_{item_id}")
        if rating_val is not None:
            try:
                new_rating = float(rating_val)
            except ValueError:
                continue
            rating_record = Rating.query.filter_by(user_id=user.id, system=system, item_id=item_id).first()
            if rating_record:
                rating_record.rating = new_rating
                rating_record.timestamp = datetime.utcnow()
            else:
                new_rec = Rating(user_id=user.id, system=system, item_id=item_id, rating=new_rating)
                db.session.add(new_rec)
    db.session.commit()
    existing_ratings = {r.item_id: r.rating for r in Rating.query.filter_by(user_id=user.id, system=system).all()}

    if system == "custom":
        dataset_id = request.form.get("dataset_id")
        if dataset_id:
            ds = CustomDataset.query.filter_by(id=dataset_id).first()
            if ds is None:
                flash("Custom dataset not found.", "danger")
                return redirect(url_for("choose_system"))
            dataset_path = ds.dataset_path
            mapping = json.loads(ds.mapping)
        else:
            if "custom_dataset_path" not in session or "custom_mapping" not in session:
                flash("Please upload a dataset and set its mapping first.", "danger")
                return redirect(url_for("upload_dataset"))
            dataset_path = session["custom_dataset_path"]
            mapping = json.loads(session["custom_mapping"])
        try:
            data = load_data(dataset_path)
            normalized_data = normalize_data(data, mapping)
        except Exception as e:
            flash("Error in dataset: " + str(e), "danger")
            return redirect(url_for("custom_index", dataset_id=dataset_id))
    else:
        mapping = SYSTEMS[system]["mapping"]
        try:
            data = load_data(SYSTEMS[system]["file"])
            normalized_data = normalize_data(data, mapping)
        except Exception as e:
            flash("Error in dataset: " + str(e), "danger")
            return redirect(url_for("dashboard", system=system))

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
    user.set_taste_vector(system, profile_vector)
    db.session.commit()
    flash("Ratings updated and recommendations re-calculated.", "success")
    return redirect(url_for("dashboard", system=system))


@app.route("/update_item_rating")
def update_item_rating():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    item_id = request.args.get("id")
    new_rating_str = request.args.get("rating")
    try:
        new_rating = float(new_rating_str)
    except (ValueError, TypeError):
        flash("Invalid rating value.", "danger")
        return redirect(url_for("dashboard", system=system))
    user = User.query.filter_by(username=session["username"]).first()
    rating_record = Rating.query.filter_by(user_id=user.id, system=system, item_id=item_id).first()
    if rating_record:
        rating_record.rating = new_rating
        rating_record.timestamp = datetime.utcnow()
    else:
        new_rec = Rating(user_id=user.id, system=system, item_id=item_id, rating=new_rating)
        db.session.add(new_rec)
    db.session.commit()

    if system == "custom":
        dataset_id = request.args.get("dataset_id")
        if dataset_id:
            ds = CustomDataset.query.filter_by(id=dataset_id).first()
            if ds is None:
                flash("Custom dataset not found.", "danger")
                return redirect(url_for("choose_system"))
            dataset_path = ds.dataset_path
            mapping = json.loads(ds.mapping)
        else:
            if "custom_dataset_path" not in session or "custom_mapping" not in session:
                flash("Please upload a dataset and set its mapping first.", "danger")
                return redirect(url_for("upload_dataset"))
            dataset_path = session["custom_dataset_path"]
            mapping = json.loads(session["custom_mapping"])
        try:
            data = load_data(dataset_path)
            normalized_data = normalize_data(data, mapping)
        except Exception as e:
            flash("Error in dataset: " + str(e), "danger")
            return redirect(url_for("dashboard", system=system))
    else:
        mapping = SYSTEMS[system]["mapping"]
        try:
            data = load_data(SYSTEMS[system]["file"])
            normalized_data = normalize_data(data, mapping)
        except Exception as e:
            flash("Error in dataset: " + str(e), "danger")
            return redirect(url_for("dashboard", system=system))

    existing_ratings = {r.item_id: r.rating for r in Rating.query.filter_by(user_id=user.id, system=system).all()}
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
    user.set_taste_vector(system, profile_vector)
    db.session.commit()
    flash("Rating updated and recommendations re-calculated.", "success")
    return redirect(url_for("dashboard", system=system))


@app.route("/reset_taste")
def reset_taste():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    user = User.query.filter_by(username=session["username"]).first()

    # Delete all ratings for the specified system.
    Rating.query.filter_by(user_id=user.id, system=system).delete()

    # Reset the taste vector for this system.
    if user.taste_vector:
        vectors = json.loads(user.taste_vector)
    else:
        vectors = {}
    if system in vectors:
        del vectors[system]
    user.taste_vector = json.dumps(vectors)
    db.session.commit()

    flash("Your recommendations and ratings have been reset. Please rate items again to get new recommendations.",
          "info")

    if system == "custom":
        dataset_id = request.args.get("dataset_id")
        if dataset_id:
            ds = CustomDataset.query.filter_by(id=dataset_id).first()
            if ds:
                # If a permanent record exists, redirect to custom index using it.
                return redirect(url_for("custom_index", dataset_id=dataset_id))
            else:
                # If dataset_id is provided but not found, fall back to session-based custom dataset.
                if "custom_dataset_path" in session and "custom_mapping" in session:
                    return redirect(url_for("custom_index"))
                else:
                    flash("Custom dataset not found.", "danger")
                    return redirect(url_for("choose_system"))
        else:
            # For temporary custom datasets, redirect to custom index.
            return redirect(url_for("custom_index"))
    else:
        return redirect(url_for("index", system=system))


@app.route("/item_detail")
def item_detail():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    item_id = request.args.get("id")
    if not item_id:
        flash("No item specified.", "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)

    # Get mapping and data based on system type.
    if system == "custom":
        dataset_id = request.args.get("dataset_id")
        if dataset_id:
            ds = CustomDataset.query.filter_by(id=dataset_id).first()
            if ds is None:
                flash("Custom dataset not found.", "danger")
                return redirect(url_for("choose_system"))
            dataset_path = ds.dataset_path
            mapping = json.loads(ds.mapping)
        else:
            if "custom_dataset_path" not in session or "custom_mapping" not in session:
                flash("Please upload a dataset and set its mapping first.", "danger")
                return redirect(url_for("upload_dataset"))
            dataset_path = session["custom_dataset_path"]
            mapping = json.loads(session["custom_mapping"])
        try:
            data = load_data(dataset_path)
            normalized_data = normalize_data(data, mapping)
        except Exception as e:
            flash("Error in dataset: " + str(e), "danger")
            return render_template("custom_index.html", items=[], system="custom")
    else:
        mapping = SYSTEMS[system]["mapping"]
        try:
            data = load_data(SYSTEMS[system]["file"])
            normalized_data = normalize_data(data, mapping)
        except Exception as e:
            flash("Error in dataset: " + str(e), "danger")
            return render_template("index.html", restaurants=[], system=system, user_has_vector=False)

    item = next((it for it in normalized_data if it["id"] == str(item_id)), None)
    if not item:
        flash("Item not found.", "danger")
        if system == "custom":
            return render_template("custom_index.html", items=normalized_data, system=system)
        else:
            return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    user = User.query.filter_by(username=session["username"]).first()
    rating_record = Rating.query.filter_by(user_id=user.id, system=system, item_id=item_id).first()
    current_rating = rating_record.rating if rating_record else 0
    if system == "custom":
        return render_template("item_detail.html", item=item, system=system, current_rating=current_rating,
                               dataset_id=request.args.get("dataset_id"))
    else:
        return render_template("item_detail.html", item=item, system=system, current_rating=current_rating)


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"] if system != "custom" else None
    try:
        if system == "custom":
            dataset_id = request.args.get("dataset_id")
            if dataset_id:
                ds = CustomDataset.query.filter_by(id=dataset_id).first()
                if ds is None:
                    flash("Custom dataset not found.", "danger")
                    return redirect(url_for("choose_system"))
                dataset_path = ds.dataset_path
                mapping = json.loads(ds.mapping)
            else:
                if "custom_dataset_path" not in session or "custom_mapping" not in session:
                    flash("Please upload a dataset and set its mapping first.", "danger")
                    return redirect(url_for("upload_dataset"))
                dataset_path = session["custom_dataset_path"]
                mapping = json.loads(session["custom_mapping"])
            data = load_data(dataset_path)
            normalized_data = normalize_data(data, mapping)
        else:
            data = load_data(SYSTEMS[system]["file"])
            normalized_data = normalize_data(data, SYSTEMS[system]["mapping"])
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("index.html", restaurants=[], system=system, user_has_vector=False)
    user = User.query.filter_by(username=session["username"]).first()
    user_vector = user.get_taste_vector(system)
    if not user_vector:
        flash("You haven't rated any items yet. Please rate some items first.", "warning")
        if system == "custom":
            return render_template("custom_index.html", items=normalized_data, system="custom",
                                   dataset_id=request.args.get("dataset_id"))
        else:
            return render_template("index.html", restaurants=normalized_data, system=system, user_has_vector=False)
    n_features = len(normalized_data[0]["featureVector"])
    rated_items = []
    for item in normalized_data:
        est_rating = calculate_estimated_rating(user_profile=user_vector, item_features=item["featureVector"], s=s,
                                                n=n_features)
        rated_items.append((item["name"], item["image"], est_rating, item["id"]))
    rated_items.sort(key=lambda x: x[2], reverse=True)
    top_recommendations = rated_items[:10]
    if system == "custom":
        return render_template("custom_recommendations.html", recommendations=top_recommendations, system=system,
                               dataset_id=request.args.get("dataset_id"))
    else:
        return render_template("recommendations.html", recommendations=top_recommendations, system=system)


@app.route("/my_ratings")
def my_ratings():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    user = User.query.filter_by(username=session["username"]).first()
    if not user:
        flash("Please log in.", "warning")
        return render_template("login.html")
    rating_records = Rating.query.filter_by(user_id=user.id, system=system).all()
    mapping = None
    try:
        if system == "custom":
            dataset_id = request.args.get("dataset_id")
            if dataset_id:
                ds = CustomDataset.query.filter_by(id=dataset_id).first()
                if ds is None:
                    flash("Custom dataset not found.", "danger")
                    return redirect(url_for("choose_system"))
                mapping = json.loads(ds.mapping)
                data = load_data(ds.dataset_path)
            else:
                if "custom_dataset_path" not in session or "custom_mapping" not in session:
                    flash("Please upload a dataset and set its mapping first.", "danger")
                    return redirect(url_for("upload_dataset"))
                mapping = json.loads(session["custom_mapping"])
                data = load_data(session["custom_dataset_path"])
            normalized_data = normalize_data(data, mapping)
        else:
            mapping = SYSTEMS[system]["mapping"]
            data = load_data(SYSTEMS[system]["file"])
            normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("my_ratings.html", rated_items=[], system=system)
    item_to_rating = {r.item_id: r.rating for r in rating_records}
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


@app.route("/custom_my_rating")
def custom_my_ratings():
    if "username" not in session:
        return redirect(url_for("login"))

    # Get dataset_id from the URL (if the dataset has been permanently saved)
    dataset_id = request.args.get("dataset_id")
    if dataset_id:
        ds = CustomDataset.query.filter_by(id=dataset_id).first()
        if ds is None:
            flash("Custom dataset not found.", "danger")
            return redirect(url_for("choose_system"))
        dataset_path = ds.dataset_path
        mapping = json.loads(ds.mapping)
    else:
        # For temporary (not permanently saved) custom datasets:
        if "custom_dataset_path" not in session or "custom_mapping" not in session:
            flash("Please upload a dataset and set its mapping first.", "danger")
            return redirect(url_for("upload_dataset"))
        dataset_path = session["custom_dataset_path"]
        mapping = json.loads(session["custom_mapping"])
    try:
        data = load_data(dataset_path)
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error loading dataset: " + str(e), "danger")
        normalized_data = []
    user = User.query.filter_by(username=session["username"]).first()
    rating_records = Rating.query.filter_by(user_id=user.id, system="custom").all()
    # Build a mapping of item ids to ratings
    item_to_rating = {r.item_id: r.rating for r in rating_records}
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
    return render_template("custom_my_ratings.html", rated_items=rated_items, system="custom", dataset_id=dataset_id)


# --------------------------
# Custom Dataset Generator Routes
# --------------------------
@app.route("/upload_dataset", methods=["GET", "POST"])
def upload_dataset():
    if "username" not in session:
        return render_template("login.html")
    errors = {}
    if request.method == "POST":
        if "dataset" not in request.files:
            errors["file_error"] = "No file part."
            return render_template("upload_dataset.html", errors=errors)
        file = request.files["dataset"]
        if file.filename == "":
            errors["file_error"] = "No file selected."
            return render_template("upload_dataset.html", errors=errors)
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.root_path, "uploads", filename)
        file.save(file_path)
        session["custom_dataset_path"] = os.path.join("uploads", filename)
        flash("Dataset uploaded successfully.", "success")
        return redirect(url_for("map_dataset"))
    return render_template("upload_dataset.html", errors=errors)


@app.route("/map_dataset", methods=["GET", "POST"])
def map_dataset():
    if "username" not in session:
        return render_template("login.html")
    if "custom_dataset_path" not in session:
        errors = {"general_error": "Please upload a dataset first."}
        return render_template("upload_dataset.html", errors=errors)
    errors = {}
    if request.method == "POST":
        mapping = {
            "id": request.form.get("id_field", "id"),
            "name": request.form.get("name_field", "name"),
            "description": request.form.get("desc_field", "description"),
            "image": request.form.get("image_field", "image"),
            "featureVector": request.form.get("vector_field", "featureVector")
        }
        dataset_path = session["custom_dataset_path"]
        try:
            data = load_data(dataset_path)
            if mapping["id"] not in data[0] or data[0].get(mapping["id"]) is None:
                errors["id_error"] = f"Required field '{mapping['id']}' not found."
            if mapping["featureVector"] not in data[0] or data[0].get(mapping["featureVector"]) is None:
                errors["vector_error"] = f"Required field '{mapping['featureVector']}' not found."
        except Exception as e:
            errors["general_error"] = "Error loading dataset: " + str(e)
            return render_template("map_dataset.html", errors=errors, mapping=mapping)
        if errors:
            return render_template("map_dataset.html", errors=errors, mapping=mapping)
        session["custom_mapping"] = json.dumps(mapping)
        flash("Mapping saved successfully. Dataset is valid.", "success")
        return redirect(url_for("save_custom_dataset"))
    return render_template("map_dataset.html", errors=errors)


@app.route("/save_custom_dataset", methods=["GET", "POST"])
def save_custom_dataset():
    if "username" not in session:
        return render_template("login.html")
    if "custom_dataset_path" not in session or "custom_mapping" not in session:
        flash("Please upload a dataset and set its mapping first.", "danger")
        return redirect(url_for("upload_dataset"))
    if request.method == "POST":
        dataset_name = request.form.get("dataset_name")
        if not dataset_name:
            flash("Please provide a name for your dataset.", "danger")
            return render_template("save_custom_dataset.html")
        user = User.query.filter_by(username=session["username"]).first()
        new_custom = CustomDataset(
            user_id=user.id,
            dataset_name=dataset_name,
            dataset_path=session["custom_dataset_path"],
            mapping=session["custom_mapping"]
        )
        db.session.add(new_custom)
        db.session.commit()
        flash("Custom dataset saved successfully!", "success")
        session.pop("custom_dataset_path", None)
        session.pop("custom_mapping", None)
        return redirect(url_for("custom_index", dataset_id=new_custom.id))
    return render_template("save_custom_dataset.html")


@app.route("/custom_index")
def custom_index():
    if "username" not in session:
        return render_template("login.html")
    dataset_id = request.args.get("dataset_id")
    if dataset_id:
        ds = CustomDataset.query.filter_by(id=dataset_id).first()
        if ds is None:
            flash("Custom dataset not found.", "danger")
            return redirect(url_for("choose_system"))
        dataset_path = ds.dataset_path
        mapping = json.loads(ds.mapping)
    else:
        if "custom_dataset_path" not in session or "custom_mapping" not in session:
            flash("Please upload a dataset and set its mapping first.", "danger")
            return redirect(url_for("upload_dataset"))
        dataset_path = session["custom_dataset_path"]
        mapping = json.loads(session["custom_mapping"])
    try:
        data = load_data(dataset_path)
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error loading dataset: " + str(e), "danger")
        return redirect(url_for("upload_dataset"))
    return render_template("custom_index.html", items=normalized_data, system="custom", dataset_id=dataset_id)


@app.route("/custom_recommend", methods=["POST"])
def custom_recommend():
    if "username" not in session:
        return render_template("login.html")
    # Check if dataset_id is provided from the form (from a hidden field)
    dataset_id = request.form.get("dataset_id")
    if dataset_id:
        ds = CustomDataset.query.filter_by(id=dataset_id).first()
        if ds is None:
            flash("Custom dataset not found.", "danger")
            return redirect(url_for("choose_system"))
        dataset_path = ds.dataset_path
        mapping = json.loads(ds.mapping)
    else:
        if "custom_dataset_path" not in session or "custom_mapping" not in session:
            flash("Please upload a dataset and set its mapping first.", "danger")
            return redirect(url_for("upload_dataset"))
        dataset_path = session["custom_dataset_path"]
        mapping = json.loads(session["custom_mapping"])
    try:
        data = load_data(dataset_path)
        normalized_data = normalize_data(data, mapping)
    except Exception as e:
        flash("Error in dataset: " + str(e), "danger")
        return render_template("custom_index.html", items=[], system="custom")
    ids_str = request.form.get("selected_ids")
    if not ids_str or ids_str.strip() == "":
        flash("No items were selected to rate. Please select at least one item.", "danger")
        return render_template("custom_index.html", items=normalized_data, system="custom", dataset_id=dataset_id)
    selected_ids = ids_str.split(",")
    user = User.query.filter_by(username=session["username"]).first()
    for sid in selected_ids:
        rating_val = request.form.get(f"rating_{sid}")
        if rating_val is None:
            continue
        try:
            rating = float(rating_val)
        except ValueError:
            continue
        rating_record = Rating.query.filter_by(user_id=user.id, system="custom", item_id=sid).first()
        if rating_record:
            rating_record.rating = rating
            rating_record.timestamp = datetime.utcnow()
        else:
            new_rating = Rating(user_id=user.id, system="custom", item_id=sid, rating=rating)
            db.session.add(new_rating)
    db.session.commit()
    existing_ratings = {r.item_id: r.rating for r in Rating.query.filter_by(user_id=user.id, system="custom").all()}
    if len(existing_ratings) < 4:
        flash("You must rate at least 4 items.", "danger")
        return render_template("custom_index.html", items=normalized_data, system="custom", dataset_id=dataset_id)
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
    user.set_taste_vector("custom", profile_vector)
    db.session.commit()
    rated_items = []
    for item in normalized_data:
        est_rating = calculate_estimated_rating(user_profile=profile_vector, item_features=item["featureVector"], s=s,
                                                n=n_features)
        rated_items.append((item["name"], item["image"], est_rating, item["id"]))
    rated_items.sort(key=lambda x: x[2], reverse=True)
    top_recommendations = rated_items[:10]
    return render_template("custom_recommendations.html", recommendations=top_recommendations, system="custom",
                           dataset_id=dataset_id)


@app.route("/delete_custom_dataset/<int:dataset_id>", methods=["GET"])
def delete_custom_dataset(dataset_id):
    if "username" not in session:
        return redirect(url_for("login"))
    custom_dataset = CustomDataset.query.get(dataset_id)
    if custom_dataset is None:
        flash("Custom dataset not found.", "danger")
    else:
        db.session.delete(custom_dataset)
        db.session.commit()
        flash("Custom dataset deleted successfully.", "success")
    return redirect(url_for("choose_system"))


if __name__ == "__main__":
    app.run(debug=True)
