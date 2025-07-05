from flask import Blueprint, render_template, session, redirect, url_for
from db.collections import SYSTEMS

system_bp = Blueprint("system", __name__)


@system_bp.route("/choose_system")
def choose_system():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    return render_template("choose_system.html", systems=SYSTEMS)
