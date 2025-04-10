from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from app.models.customer import Customer
from app.models.transaction import Transaction
from app import db
from app.utils.security import success_response, error_response
from sqlalchemy import or_, func
from datetime import datetime, timedelta

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


@customer_bp.route("/<customer_id>", methods=["GET"])
@jwt_required()
def get_customer(customer_id):
    """
    Endpoint untuk mengambil data satu Customer berdasarkan ID.
    """
    try:
        customer = Customer.query.filter_by(customer_id=customer_id).first()
        if not customer:
            return error_response("Customer not found", 404)
        
        return success_response(
            data=customer.to_dict(), message="Customer retrieved successfully"
        )
    except Exception as e:
        return error_response(str(e), 500)


@customer_bp.route("/<customer_id>/sales", methods=["GET"]) 
@jwt_required()
def get_customer_sales(customer_id):
    """
    Endpoint untuk mendapatkan data penjualan Customer.
    """
    try:
        # Check if customer exists
        # customer = Customer.query.filter_by(customer_id=customer_id).first()
        # if not customer:
        #     return error_response("Customer not found", 404)
        
        # Get time range filter from query params (default: last 6 months)
        months = int(request.args.get("months", 6))
        start_date = datetime.now() - timedelta(days=30 * months)
        
        # Group transactions by invoice_id
        invoices = db.session.query(
            Transaction.invoice_id,
            func.min(Transaction.invoice_date).label("invoice_date"),
            func.sum(Transaction.total_amount).label("total_amount")
        ).filter(
            Transaction.customer_id == customer_id,
            Transaction.invoice_date >= start_date
        ).group_by(Transaction.invoice_id).order_by(func.min(Transaction.invoice_date).desc()).all()

        # Format invoice list
        transaction_list = [
            {
                "invoice_id": inv.invoice_id,
                "invoice_date": inv.invoice_date.strftime("%Y-%m-%d"),
                "total_amount": float(inv.total_amount)
            }
            for inv in invoices
        ]

        
        # Calculate sales summary
        total_sales = sum(t["total_amount"] for t in transaction_list)
        total_orders = len(set(t["invoice_id"] for t in transaction_list))
        
        # Group by month for time series
        monthly_sales = db.session.query(
            func.date_format(Transaction.invoice_date, '%Y-%m-01').label('month'),
            func.sum(Transaction.total_amount).label('amount')
        ).filter(
            Transaction.customer_id == customer_id,
            Transaction.invoice_date >= start_date
        ).group_by('month').order_by('month').all()
        
        # Format monthly sales untuk frontend charts
        sales_by_month = [
            {
                "month": datetime.strptime(entry[0], "%Y-%m-%d").strftime("%b %Y"),
                "amount": float(entry[1])
            }
            for entry in monthly_sales
        ]

        
        # Get top products for this customer
        top_products = db.session.query(
            Transaction.product_id,
            Transaction.product_name,
            func.sum(Transaction.total_amount).label('amount'),
            func.sum(Transaction.qty).label('qty')
        ).filter(
            Transaction.customer_id == customer_id,
            Transaction.invoice_date >= start_date
        ).group_by(
            Transaction.product_id,
            Transaction.product_name
        ).order_by(func.sum(Transaction.total_amount).desc()).limit(8).all()
        
        # Format product data
        product_data = [
            {
                "product_id": p[0],
                "product_name": p[1],
                "total_amount": float(p[2]),
                "qty": int(p[3])
            }
            for p in top_products
        ]
        
        return success_response(
            data={
                # "customer": customer.to_dict(),
                "total_sales": total_sales,
                "total_orders": total_orders,
                "sales_by_month": sales_by_month,
                "top_products": product_data,
                "recent_transactions": transaction_list[:10]  # Last 10 transactions
            },
            message="Customer sales data retrieved successfully"
        )
    except Exception as e:
        return error_response(str(e), 500)

@customer_bp.route("/search", methods=["GET"])
@jwt_required()
def search_customers():

    """
    Endpoint untuk mencari Customer berdasarkan query.
    """
    try:
        query = request.args.get("q", "")
        if not query:
            return success_response(data=[], message="Empty search query")
        
        # Search by name, code, or ID
        customers = Customer.query.filter(
            or_(
                Customer.business_name.ilike(f"%{query}%"),
                Customer.customer_code.ilike(f"%{query}%"),
                Customer.customer_id.ilike(f"%{query}%"),
                Customer.city.ilike(f"%{query}%")
            )
        ).all()
        
        customer_list = [customer.to_dict() for customer in customers]
        return success_response(
            data=customer_list, message="Search results retrieved successfully"
        )
    except Exception as e:
        return error_response(str(e), 500)
    

@customer_bp.route("/create", methods=["POST"])
@jwt_required()
def create_customer():
    """
    Endpoint untuk membuat Customer baru.
    """
    try:
        data = request.get_json()
        
        # Validasi data yang diperlukan
        required_fields = ["customer_code", "customer_id", "business_name"]
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Periksa jika customer_code atau customer_id sudah ada
        existing_customer = Customer.query.filter(
            or_(
                Customer.customer_code == data["customer_code"],
                Customer.customer_id == data["customer_id"]
            )
        ).first()
        
        if existing_customer:
            return error_response("Customer code or ID already exists", 400)
        
        customer = Customer(
            customer_code=data["customer_code"],
            customer_id=data["customer_id"],
            business_name=data["business_name"],
            npwp=data.get("npwp"),
            nik=data.get("nik"),
            extra=data.get("extra"),
            price_type=data.get("price_type"),
            city=data.get("city"),
            address_1=data.get("address_1"),
            address_2=data.get("address_2"),
            address_3=data.get("address_3"),
            address_4=data.get("address_4"),
            address_5=data.get("address_5"),
            owner_name=data.get("owner_name"),
            owner_address_1=data.get("owner_address_1"),
            owner_address_2=data.get("owner_address_2"),
            owner_address_3=data.get("owner_address_3"),
            owner_address_4=data.get("owner_address_4"),
            owner_address_5=data.get("owner_address_5"),
            religion=data.get("religion"),
            additional_address=data.get("additional_address"),
            additional_address_1=data.get("additional_address_1"),
            additional_address_2=data.get("additional_address_2"),
            additional_address_3=data.get("additional_address_3"),
            additional_address_4=data.get("additional_address_4"),
            additional_address_5=data.get("additional_address_5")
        )
        
        db.session.add(customer)
        db.session.commit()
        
        return success_response(
            data=customer.to_dict(), message="Customer created successfully"
        )
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)


@customer_bp.route("/update/<customer_id>", methods=["PUT"])
@jwt_required()
def update_customer(customer_id):
    """
    Endpoint untuk mengubah data Customer.
    """
    try:
        customer = Customer.query.filter_by(customer_id=customer_id).first()
        if not customer:
            return error_response("Customer not found", 404)
        
        data = request.get_json()
        
        # Update fields
        for field in data:
            if hasattr(customer, field):
                setattr(customer, field, data[field])
        
        db.session.commit()
        
        return success_response(
            data=customer.to_dict(), message="Customer updated successfully"
        )
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)


@customer_bp.route("/delete/<customer_id>", methods=["DELETE"])
@jwt_required()
def delete_customer(customer_id):
    """
    Endpoint untuk menghapus Customer.
    """
    try:
        customer = Customer.query.filter_by(customer_id=customer_id).first()
        if not customer:
            return error_response("Customer not found", 404)
        
        db.session.delete(customer)
        db.session.commit()
        
        return success_response(message="Customer deleted successfully")
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)
