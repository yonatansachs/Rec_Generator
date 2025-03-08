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
    # taste_vector is stored as a JSON string mapping system names to vectors.
    taste_vector = db.Column(db.Text, nullable=True)

    def set_password(self, password):
        # Using SHA256 here for demonstration; in production use bcrypt or similar.
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


# Create database tables (run once)
with app.app_context():
    db.create_all()

# --------------------------
# System Configuration
# --------------------------
# For restaurants, keys are: name, description, image, featureVector.
# For movies, we map "aaamovieName" to "name" and "movie_url" to "description".
SYSTEMS = {
    "restaurants": {
        "display": "Restaurants",
        "file": "Data/feat1000_v2.json",
        "mapping": {
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
    """Normalize each item to have keys: name, description, image, featureVector."""
    normalized = []
    for item in data:
        normalized.append({
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


# Application Routes (require login)
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
    sorted_data = sorted(normalized_data, key=lambda r: 0 if r["image"] else 1)
    return render_template("index.html", restaurants=sorted_data, system=system)


@app.route("/rate", methods=["POST"])
def rate():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"]
    data = load_data(SYSTEMS[system]["file"])
    normalized_data = normalize_data(data, mapping)
    selected_indexes = request.form.getlist("restaurant")
    selected_indexes = [int(i) for i in selected_indexes]
    selected_items = [normalized_data[i] for i in selected_indexes]
    return render_template("rate.html", restaurants=selected_items, indexes=selected_indexes, zip=zip, system=system)


@app.route("/recommend", methods=["POST"])
def recommend():
    if "username" not in session:
        return redirect(url_for("login"))
    system = request.args.get("system", "restaurants")
    mapping = SYSTEMS[system]["mapping"]
    data = load_data(SYSTEMS[system]["file"])
    normalized_data = normalize_data(data, mapping)

    indexes_str = request.form.get("indexes")
    selected_indexes = [int(i) for i in indexes_str.split(",") if i]

    user_ratings = []
    for idx in selected_indexes:
        rating = float(request.form.get(f"rating_{idx}"))
        user_ratings.append(rating)

    vectors = []
    for i, item in enumerate(normalized_data):
        fv = item["featureVector"][:]
        if i in selected_indexes:
            idx_in_selected = selected_indexes.index(i)
            user_rating = user_ratings[idx_in_selected]
            fv_plus_rating = fv + [user_rating]
        else:
            fv_plus_rating = fv + [3.0]
        vectors.append(fv_plus_rating)

    n_features = len(normalized_data[0]["featureVector"])
    objective, profile_vector = create_problem_with_pulp_dict(
        vectors=[vectors[i][:n_features] for i in selected_indexes],
        deltas=calculate_delta(user_ratings, n=n_features)
    )

    # Save the computed taste vector for the current system persistently.
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
        flash("No saved taste vector found. Please rate some items first.", "warning")
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


if __name__ == "__main__":
    app.run(debug=True)
