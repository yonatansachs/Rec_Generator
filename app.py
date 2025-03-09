from flask import Flask, render_template, request, redirect, url_for, session, flash
import json, hashlib
import pulp
from pulp import (
    LpProblem, LpMinimize, LpVariable, lpSum, value,
    LpBinary, LpInteger, LpContinuous, PULP_CBC_CMD
)
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Replace with a secure key in production
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"  # Using SQLite for simplicity
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# --------------------------
# Database Model for Users
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


with app.app_context():
    db.create_all()

# --------------------------
# System Configuration
# --------------------------
# For restaurants, we assume the JSON has a unique field "aaaid".
# For movies, adjust as necessary.
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
            "id": "aaaid",  # Change if movies use a different unique field name.
            "name": "aaamovieName",
            "description": "movie_url",
            "image": "image",
            "featureVector": "featureVector"
        }
    }
}


def load_data(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_data(data, mapping):
    normalized = []
    for item in data:
        normalized.append({
            "id": str(item.get(mapping["id"])),  # store id as string
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
# Root route always redirects to the login page.
@app.route("/")
def home():
    return redirect(url_for("login"))


# Authentication Routes
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if User.query.filter_by(username=username).first():
            flash("Username already exists. Please choose another.", "danger")
            return redirect(url_for("signup"))
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
            return redirect(url_for("login"))
        session["username"] = username
        flash("Logged in successfully!", "success")
        return redirect(url_for("choose_system"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# Application Routes (Require login)
@app.route("/choose_system")
def choose_system():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("choose_system.html", systems=SYSTEMS)


@app.route("/index")
def index():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"]
    data = load_data(SYSTEMS[system]["file"])
    normalized_data = normalize_data(data, mapping)
    # Preserve the original order from JSON.
    return render_template("index.html", restaurants=normalized_data, system=system)


@app.route("/rate", methods=["POST"])
def rate():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"]
    data = load_data(SYSTEMS[system]["file"])
    normalized_data = normalize_data(data, mapping)
    # Get selected unique ids from checkboxes (as strings)
    selected_ids = request.form.getlist("restaurant")
    if not selected_ids or len(selected_ids) < 4:
        flash("You must select at least 4 items to rate.", "danger")
        return redirect(url_for("index", system=system))
    # Filter normalized data for only those objects whose id is in selected_ids
    selected_items = [item for item in normalized_data if item["id"] in selected_ids]
    # Pass the selected ids as a hidden field (comma-separated) to the rate page
    return render_template("rate.html", restaurants=selected_items, selected_ids=",".join(selected_ids), system=system)


@app.route("/recommend", methods=["POST"])
def recommend():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"]
    data = load_data(SYSTEMS[system]["file"])
    normalized_data = normalize_data(data, mapping)

    ids_str = request.form.get("selected_ids")
    if not ids_str or ids_str.strip() == "":
        flash("No items were selected to rate. Please select at least one item.", "danger")
        return redirect(url_for("index", system=system))
    selected_ids = ids_str.split(",")

    # Build a lookup dictionary of items by id
    items_by_id = {item["id"]: item for item in normalized_data}

    user_ratings = []
    selected_items = []
    for sid in selected_ids:
        rating_val = request.form.get(f"rating_{sid}")
        if rating_val is None:
            continue
        try:
            rating = float(rating_val)
        except ValueError:
            continue
        user_ratings.append(rating)
        selected_items.append(items_by_id[sid])

    if len(selected_items) < 4:
        flash("You must rate at least 4 items.", "danger")
        return redirect(url_for("index", system=system))

    # Build vectors for each item in normalized_data:
    # Use the user rating for items in selected_items; otherwise, default to 3.0.
    vectors = []
    for item in normalized_data:
        fv = item["featureVector"][:]
        if item["id"] in selected_ids:
            idx = selected_ids.index(item["id"])
            user_rating = user_ratings[idx]
            fv_plus_rating = fv + [user_rating]
        else:
            fv_plus_rating = fv + [3.0]
        vectors.append(fv_plus_rating)

    n_features = len(normalized_data[0]["featureVector"])
    objective, profile_vector = create_problem_with_pulp_dict(
        vectors=[vectors[normalized_data.index(item)][:n_features] for item in selected_items],
        deltas=calculate_delta(user_ratings, n=n_features)
    )

    # Save the computed taste vector for the current system.
    user = User.query.filter_by(username=session["username"]).first()
    user.set_taste_vector(system, profile_vector)
    db.session.commit()

    rated_items = []
    for item in normalized_data:
        fv = item["featureVector"]
        est_rating = calculate_estimated_rating(user_profile=profile_vector, item_features=fv, s=s, n=n_features)
        rated_items.append((item["name"], item["image"], est_rating))
    rated_items.sort(key=lambda x: x[2], reverse=True)
    top_recommendations = rated_items[:10]
    return render_template("recommendations.html", recommendations=top_recommendations, system=system)


@app.route("/reset_taste")
def reset_taste():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    user = User.query.filter_by(username=session["username"]).first()
    if user.taste_vector:
        vectors = json.loads(user.taste_vector)
    else:
        vectors = {}
    if system in vectors:
        del vectors[system]
        user.taste_vector = json.dumps(vectors)
        db.session.commit()
        flash("Your recommendations have been reset. Please rate items again to get new recommendations.", "info")
    else:
        flash("No recommendations to reset.", "warning")
    return redirect(url_for("index", system=system))


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"]
    data = load_data(SYSTEMS[system]["file"])
    normalized_data = normalize_data(data, mapping)
    user = User.query.filter_by(username=session["username"]).first()
    user_vector = user.get_taste_vector(system)
    if not user_vector:
        flash("You haven't rated any items yet. Please rate some items first.", "warning")
        return redirect(url_for("index", system=system))
    n_features = len(normalized_data[0]["featureVector"])
    rated_items = []
    for item in normalized_data:
        fv = item["featureVector"]
        est_rating = calculate_estimated_rating(user_profile=user_vector, item_features=fv, s=s, n=n_features)
        rated_items.append((item["name"], item["image"], est_rating))
    rated_items.sort(key=lambda x: x[2], reverse=True)
    top_recommendations = rated_items[:10]
    return render_template("recommendations.html", recommendations=top_recommendations, system=system)


@app.route("/show_recommendations")
def show_recommendations():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    user = User.query.filter_by(username=session["username"]).first()
    user_vector = user.get_taste_vector(system)
    if not user_vector:
        flash("You haven't rated any items yet. Please rate some items first.", "warning")
        return redirect(url_for("index", system=system))
    return redirect(url_for("dashboard", system=system))


if __name__ == "__main__":
    app.run(debug=True)
