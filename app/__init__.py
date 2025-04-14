from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from app.config import Config

# Initialize extensions
db = SQLAlchemy()
jwt = JWTManager()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions with app
    db.init_app(app)
    jwt.init_app(app)
    CORS(app)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.import_data import import_data_bp
    from app.routes.customer import customer_bp
    from app.routes.inventory import inventory_bp
    from app.routes.inventory_analytics import inventory_analytics_bp  # Import the new blueprint
    from app.routes.forecast import forecast_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(import_data_bp, url_prefix="/api/import")
    app.register_blueprint(customer_bp, url_prefix="/api/customer")
    app.register_blueprint(inventory_bp, url_prefix="/api/inventory")
    app.register_blueprint(inventory_analytics_bp, url_prefix="/api/inventory")  # Register with same prefix
    app.register_blueprint(forecast_bp, url_prefix="/api/forecast")

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app
