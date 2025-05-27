import os

def configure_app(app):
    app.config.update(
        SESSION_TYPE="filesystem",
        SESSION_FILE_DIR="./.flask_session",
        SESSION_FILE_THRESHOLD=100 * 1024 * 1024,
        SESSION_PERMANENT=False,
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev_secret")
    )
