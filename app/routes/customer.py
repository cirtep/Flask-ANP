from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from app.models.customer import Customer
from app import db
from app.utils.security import success_response, error_response
from sqlalchemy import or_

customer_bp = Blueprint("customer", __name__)


@customer_bp.route("/all", methods=["GET"])
@jwt_required()
def get_customers():
    """
    Endpoint untuk mengambil semua data Customer.
    Data dikembalikan dalam format JSON untuk diisi ke tabel di halaman Customer.
    """
    try:
        customers = Customer.query.all()
        customer_list = [customer.to_dict() for customer in customers]
        return success_response(
            data=customer_list, message="Customers retrieved successfully"
        )
    except Exception as e:
        return error_response(str(e), 500)
