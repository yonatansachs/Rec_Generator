from flask import (
    Blueprint, request, flash, render_template,
    session, redirect, url_for
)
from core.users import find_user, create_user, check_pw

auth_bp = Blueprint("auth", __name__)

# ─────────── Sign-Up Route ───────────
@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        if find_user(u):
            flash("Username already exists.", "danger")
            return render_template("signup.html")
        uid = create_user(u, p)

        session["username"] = u
        session["user_id"] = str(uid)

        flash("Sign-up successful!", "success")
        return redirect(url_for("system.choose_system"))

    return render_template("signup.html")

# ─────────── Login Route ───────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        user = find_user(u)
        if not user or not check_pw(user, p):
            flash("Invalid credentials.", "danger")
            return render_template("login.html")

        session["username"] = u
        session["user_id"] = str(user["_id"])

        return redirect(url_for("system.choose_system"))

    return render_template("login.html")

# ─────────── Logout Route ───────────
@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))
