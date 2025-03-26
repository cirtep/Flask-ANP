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
    Endpoint untuk mengambil data Customer dengan pagination, filtering, dan sorting.
    Data dikembalikan dalam format JSON untuk diisi ke tabel di halaman Customer.
    """
    try:
        # Ambil parameter pagination
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("limit", 10, type=int)

        # Ambil query pencarian jika ada
        search_query = request.args.get("search", "")

        # Ambil parameter sorting
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "asc")

        # Build query dasar
        query = Customer.query

        # Terapkan filter pencarian jika diberikan
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                or_(
                    Customer.name.ilike(search_term),
                    Customer.code.ilike(search_term),
                    Customer.phone.ilike(search_term),
                    Customer.city.ilike(search_term),
                    Customer.address1.ilike(search_term),
                )
            )

        # Validasi apakah kolom sorting valid, default ke Customer.id jika tidak
        if hasattr(Customer, sort_by):
            sort_attr = getattr(Customer, sort_by)
        else:
            sort_attr = Customer.id

        # Terapkan sorting
        if sort_order.lower() == "asc":
            query = query.order_by(sort_attr.asc())
        else:
            query = query.order_by(sort_attr.desc())

        # Terapkan pagination
        paginated_customers = query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Siapkan response data, gabungkan data customers dan metadata pagination
        data = {
            "customers": [customer.to_dict() for customer in paginated_customers.items],
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": paginated_customers.total,
                "pages": paginated_customers.pages,
            },
        }

        return success_response(data=data, message="Customers retrieved successfully")
    except Exception as e:
        return error_response(str(e), 500)
