from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required
from app.models.customer import Customer
from app.models.transaction import Transaction
from app import db
from app.utils.security import success_response, error_response
from sqlalchemy import or_, func, desc, and_
from datetime import datetime, timedelta
import csv
import io

customer_bp = Blueprint("customer", __name__)


@customer_bp.route("/all", methods=["GET"])
@jwt_required()
def get_customers():
    """
    Endpoint to get all customers with their total purchase amount (sorted by purchase amount)
    """
    try:
        # First get all transactions summed by customer
        customer_transactions = db.session.query(
            Transaction.customer_id,
            func.sum(Transaction.total_amount).label('total_purchases')
        ).group_by(
            Transaction.customer_id
        ).subquery()
        
        # Then join with customer table to get all customer details
        customers_query = db.session.query(
            Customer,
            customer_transactions.c.total_purchases
        ).outerjoin(
            customer_transactions,
            Customer.customer_id == customer_transactions.c.customer_id
        ).order_by(
            desc(customer_transactions.c.total_purchases)
        ).all()
        
        customer_list = []
        for customer, total_purchases in customers_query:
            customer_data = customer.to_dict()
            customer_data['total_purchases'] = float(total_purchases) if total_purchases else 0
            customer_list.append(customer_data)
        
        return success_response(
            data=customer_list, message="Customers retrieved successfully"
        )
    except Exception as e:
        return error_response(str(e), 500)


@customer_bp.route("/<customer_id>", methods=["GET"])
@jwt_required()
def get_customer(customer_id):
    """
    Endpoint for retrieving a single customer
    """
    try:
        customer = Customer.query.filter_by(customer_id=customer_id).first()
        if not customer:
            return error_response("Customer not found", 404)
        
        # Get total purchases for this customer
        total_purchases = db.session.query(
            func.sum(Transaction.total_amount)
        ).filter(
            Transaction.customer_id == customer_id
        ).scalar() or 0
        
        customer_data = customer.to_dict()
        customer_data['total_purchases'] = float(total_purchases)
        
        return success_response(
            data=customer_data, message="Customer retrieved successfully"
        )
    except Exception as e:
        return error_response(str(e), 500)


@customer_bp.route("/<customer_id>/sales", methods=["GET"]) 
@jwt_required()
def get_customer_sales(customer_id):
    """
    Endpoint to get sales data for a specific customer
    """
    try:
        # Check if customer exists
        customer = Customer.query.filter_by(customer_id=customer_id).first()
        if not customer:
            return error_response("Customer not found", 404)
        
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
        total_orders = len(transaction_list)
        
        # Group by month for time series
        monthly_sales = db.session.query(
            func.date_format(Transaction.invoice_date, '%Y-%m-01').label('month'),
            func.sum(Transaction.total_amount).label('amount')
        ).filter(
            Transaction.customer_id == customer_id,
            Transaction.invoice_date >= start_date
        ).group_by('month').order_by('month').all()
        
        # Format monthly sales for frontend charts
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
                "customer": customer.to_dict(),
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
    Endpoint to search for customers
    """
    try:
        query = request.args.get("q", "")
        city_filter = request.args.get("city", "")
        
        if not query and not city_filter:
            return success_response(data=[], message="No search criteria provided")
        
        # Base query
        customer_query = Customer.query
        
        # Apply city filter if provided
        if city_filter:
            customer_query = customer_query.filter(Customer.city == city_filter)
            
        # Apply search term if provided
        if query:
            customer_query = customer_query.filter(
                or_(
                    Customer.business_name.ilike(f"%{query}%"),
                    Customer.customer_code.ilike(f"%{query}%"),
                    Customer.customer_id.ilike(f"%{query}%"),
                    Customer.city.ilike(f"%{query}%"),
                    Customer.owner_name.ilike(f"%{query}%")
                )
            )
        
        # Execute query
        customers = customer_query.all()
        
        # Get purchase data
        customer_ids = [c.customer_id for c in customers]
        
        # If we have customers, get their purchase totals
        purchase_data = {}
        if customer_ids:
            purchase_query = db.session.query(
                Transaction.customer_id,
                func.sum(Transaction.total_amount).label('total_purchases')
            ).filter(
                Transaction.customer_id.in_(customer_ids)
            ).group_by(
                Transaction.customer_id
            ).all()
            
            purchase_data = {cid: float(total) for cid, total in purchase_query}
        
        # Format response
        customer_list = []
        for customer in customers:
            customer_data = customer.to_dict()
            customer_data['total_purchases'] = purchase_data.get(customer.customer_id, 0)
            customer_list.append(customer_data)
            
        # Sort by purchase amount
        customer_list.sort(key=lambda x: x['total_purchases'], reverse=True)
        
        return success_response(
            data=customer_list, message="Search results retrieved successfully"
        )
    except Exception as e:
        return error_response(str(e), 500)


@customer_bp.route("/cities", methods=["GET"])
@jwt_required()
def get_cities():
    """
    Endpoint to get all unique cities for filtering
    """
    try:
        cities = db.session.query(Customer.city).filter(
            Customer.city != None, 
            Customer.city != ''
        ).distinct().order_by(Customer.city).all()
        
        city_list = [city[0] for city in cities]
        
        return success_response(
            data=city_list, message="Cities retrieved successfully"
        )
    except Exception as e:
        return error_response(str(e), 500)


@customer_bp.route("/export", methods=["GET"])
@jwt_required()
def export_customers():
    """
    Endpoint to export all customers to CSV
    """
    try:
        # Get filter parameters
        city_filter = request.args.get("city", "")
        
        # Base query
        customer_query = Customer.query
        
        # Apply city filter if provided
        if city_filter:
            customer_query = customer_query.filter(Customer.city == city_filter)
            
        # Order by business_name
        customers = customer_query.order_by(Customer.business_name).all()
        
        # Get purchase data
        customer_ids = [c.customer_id for c in customers]
        
        # If we have customers, get their purchase totals
        purchase_data = {}
        if customer_ids:
            purchase_query = db.session.query(
                Transaction.customer_id,
                func.sum(Transaction.total_amount).label('total_purchases')
            ).filter(
                Transaction.customer_id.in_(customer_ids)
            ).group_by(
                Transaction.customer_id
            ).all()
            
            purchase_data = {cid: float(total) for cid, total in purchase_query}
        
        # Create CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        writer.writerow([
            'Customer ID', 'Business Name', 'Owner Name', 'City', 'Phone',
            'Address', 'NPWP', 'NIK', 'Price Type', 'Total Purchases'
        ])
        
        # Write data rows
        for customer in customers:
            writer.writerow([
                customer.customer_id,
                customer.business_name,
                customer.owner_name,
                customer.city,
                customer.phone if hasattr(customer, 'phone') else '',
                customer.address_1,
                customer.npwp,
                customer.nik,
                customer.price_type,
                f"{purchase_data.get(customer.customer_id, 0):,.2f}"
            ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=customers_export_{datetime.now().strftime('%Y%m%d')}.csv"
        response.headers["Content-type"] = "text/csv"
        
        return response
    except Exception as e:
        return error_response(str(e), 500)


@customer_bp.route("/create", methods=["POST"])
@jwt_required()
def create_customer():
    """
    Endpoint for creating a new customer
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ["customer_code", "customer_id", "business_name"]
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Check if customer already exists
        existing_customer = Customer.query.filter(
            or_(
                Customer.customer_code == data["customer_code"],
                Customer.customer_id == data["customer_id"]
            )
        ).first()
        
        if existing_customer:
            return error_response("Customer code or ID already exists", 400)
        
        # Create new customer
        new_customer = Customer(
            customer_code=data["customer_code"],
            customer_id=data["customer_id"],
            business_name=data["business_name"],
            owner_name=data.get("owner_name"),
            city=data.get("city"),
            phone=data.get("phone"),
            address_1=data.get("address_1"),
            npwp=data.get("npwp"),
            nik=data.get("nik"),
            price_type=data.get("price_type", "Standard"),
            extra=data.get("extra"),
            address_2=data.get("address_2"),
            address_3=data.get("address_3"),
            address_4=data.get("address_4"),
            address_5=data.get("address_5"),
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
            additional_address_5=data.get("additional_address_5"),
        )
        
        db.session.add(new_customer)
        db.session.commit()
        
        return success_response(
            data=new_customer.to_dict(),
            message="Customer created successfully"
        )
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)


@customer_bp.route("/update/<customer_id>", methods=["PUT"])
@jwt_required()
def update_customer(customer_id):
    """
    Endpoint for updating a customer
    """
    try:
        customer = Customer.query.filter_by(customer_id=customer_id).first()
        if not customer:
            return error_response("Customer not found", 404)
        
        data = request.get_json()
        
        # Update customer fields
        for field in data:
            if hasattr(customer, field):
                setattr(customer, field, data[field])
        
        db.session.commit()
        
        return success_response(
            data=customer.to_dict(),
            message="Customer updated successfully"
        )
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)


@customer_bp.route("/delete/<customer_id>", methods=["DELETE"])
@jwt_required()
def delete_customer(customer_id):
    """
    Endpoint for deleting a customer
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