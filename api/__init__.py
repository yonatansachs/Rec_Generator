from .auth_routes import auth_bp
from .rating_routes import rating_bp
from .rec_routes import rec_bp
from .dataset_routes import dataset_bp
from .system_routes import system_bp
from .item_routes import item_bp


def register_all_routes(app):
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(rating_bp, url_prefix="/rating")
    app.register_blueprint(rec_bp, url_prefix="/recommend")
    app.register_blueprint(dataset_bp, url_prefix="/dataset")
    app.register_blueprint(system_bp)
    app.register_blueprint(item_bp)

