from flask import Flask, redirect, url_for
from flask_session import Session
from dotenv import load_dotenv
import os

from api import api_routes
from click_logger import click_api
from config_setup import configure_app
from db.collections import create_indexes, load_existing_collections
from db.connection import init_db

from api.__init__ import register_all_routes  # works IF __init__.py contains it

# ──────────────── Load Environment ────────────────
load_dotenv()

# ──────────────── App Setup ────────────────
app = Flask(__name__)
configure_app(app)
Session(app)
print("Session backend:", app.session_interface)

# ─────── DB + Collection Setup ───────
init_db()
create_indexes()
load_existing_collections()

# ─────── Register All API Routes ───────
register_all_routes(app)
app.register_blueprint(api_routes, url_prefix="/api")
app.register_blueprint(click_api, url_prefix="/api")

# ──────────────── Root Route ────────────────
@app.route("/")
def root():
    return redirect(url_for("auth.login"))  # matches Blueprint name

# ──────────────── Run Server ────────────────
if __name__ == "__main__":
    app.run(debug=True)
