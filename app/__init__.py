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

    app.register_blueprint(auth_bp, url_prefix="/api/auth")

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app
