from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models.user import User
from app import db
from datetime import datetime

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify(
            {"success": False, "message": "Username and password are required"}
        ), 400
    # Find user
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify(
            {"success": False, "message": "Invalid username or password"}
        ), 401
    if not user.is_active:
        return jsonify({"success": False, "message": "User account is inactive"}), 403
    # Update last login time
    user.last_login = datetime.now()
    db.session.commit()
    # Generate access token
    access_token = create_access_token(
        identity=str(user.id)
    )  # Convert ke string
    return jsonify(
        {   "success": True,
            "message": "Login successful",
            "data": {"user": user.to_dict(), "access_token": access_token},}), 200
