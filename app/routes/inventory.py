from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from app import db
from app.utils.security import success_response, error_response
from sqlalchemy import or_, func
from sqlalchemy.sql import text
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.transaction import Transaction
from datetime import datetime, timedelta

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/all", methods=["GET"])
@jwt_required()
def get_inventory():
    """
    Endpoint to retrieve comprehensive inventory data with stock information.
    """
    try:
        # Use SQLAlchemy ORM for more reliable data conversion
        query = db.session.query(Product, ProductStock).join(
            ProductStock, Product.product_id == ProductStock.product_id
        )

        # Execute the query
        results = query.all()

        # Manual conversion to ensure proper dictionary format
        inventory_list = []
        for product, stock in results:
            item = {
                # From Product model
                "id": product.id,
                "product_code": product.product_code,
                "product_id": product.product_id,
                "product_name": product.product_name,
                "standard_price": float(product.standard_price),  # Ensure numeric
                "retail_price": float(product.retail_price),
                "ppn": float(product.ppn),
                "category": product.category,
                "min_stock": float(product.min_stock),
                "max_stock": float(product.max_stock),
                "supplier_id": product.supplier_id,
                "supplier_name": product.supplier_name,
                # From ProductStock model
                "report_date": product.created_at.isoformat()
                if product.created_at
                else None,
                "location": stock.location,
                "qty": float(stock.qty),
                "unit": stock.unit,
            }
            inventory_list.append(item)

        # Calculate metrics
        metrics = {
            "total_items": len(inventory_list),
            "total_value": sum(
                item["standard_price"] * item["qty"] for item in inventory_list
            ),
            "low_stock_items": sum(
                1 for item in inventory_list if item["qty"] <= item["min_stock"]
            ),
            "critical_stock_items": sum(
                1 for item in inventory_list if item["qty"] <= (item["min_stock"] / 2)
            ),
        }

        return jsonify(
            {
                "success": True,
                "data": inventory_list,
                "metrics": metrics,
                "message": "Inventory retrieved successfully",
            }
        ), 200

    except Exception as e:
        # Log the full error for debugging
        current_app.logger.error(f"Inventory retrieval error: {str(e)}")

        return jsonify(
            {"success": False, "message": f"Error retrieving inventory: {str(e)}"}
        ), 500


@inventory_bp.route("/<product_id>", methods=["GET"])
@jwt_required()
def get_product_detail(product_id):
    """
    Endpoint to retrieve detailed information for a specific product.
    """
    try:
        # Get product info
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response("Product not found", 404)
            
        # Get stock info
        stock = ProductStock.query.filter_by(product_id=product_id).first()
        if not stock:
            return error_response("Product stock information not found", 404)
            
        # Combine data
        product_data = {
            # From Product model
            "id": product.id,
            "product_code": product.product_code,
            "product_id": product.product_id,
            "product_name": product.product_name,
            "standard_price": float(product.standard_price),
            "retail_price": float(product.retail_price),
            "ppn": float(product.ppn),
            "category": product.category,
            "min_stock": float(product.min_stock),
            "max_stock": float(product.max_stock),
            "supplier_id": product.supplier_id,
            "supplier_name": product.supplier_name,
            # From ProductStock model
            "report_date": product.created_at.isoformat() if product.created_at else None,
            "location": stock.location,
            "qty": float(stock.qty),
            "unit": stock.unit,
        }
        
        return success_response(
            data=product_data, 
            message="Product details retrieved successfully"
        )
            
    except Exception as e:
        current_app.logger.error(f"Product detail retrieval error: {str(e)}")
        return error_response(f"Error retrieving product details: {str(e)}", 500)


@inventory_bp.route("/<product_id>/sales", methods=["GET"])
@jwt_required()
def get_product_sales(product_id):
    """
    Endpoint to retrieve sales data for a specific product.
    """
    try:
        # Check if product exists
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response("Product not found", 404)
            
        # Get time range filter from query params (default: last 6 months)
        months = int(request.args.get("months", 6))
        start_date = datetime.now() - timedelta(days=30 * months)
        
        # Get all transactions for this product
        transactions = Transaction.query.filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= start_date
        ).all()
        
        if not transactions:
            return success_response(
                data={
                    "total_sales": 0,
                    "total_qty": 0,
                    "profit_margin": 0,
                    "sales_by_month": [],
                    "top_customers": [],
                    "recent_transactions": []
                },
                message="No sales data available for this product"
            )
            
        # Calculate total sales and quantities
        total_sales = sum(t.total_amount for t in transactions)
        total_qty = sum(t.qty for t in transactions)
        
        # Calculate profit margin if possible
        total_cost = sum(t.total_cost for t in transactions if t.total_cost)
        profit_margin = None
        if total_cost and total_sales:
            profit_margin = ((total_sales - total_cost) / total_sales) * 100
            
        # Group by month for time series
        monthly_sales = db.session.query(
            func.date_format(Transaction.invoice_date, '%Y-%m-01').label('month'),
            func.sum(Transaction.total_amount).label('amount')
        ).filter(
            Transaction.product_id == product_id,
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
        
        # Get top customers who bought this product
        top_customers_query = db.session.query(
            Transaction.customer_id,
            func.sum(Transaction.total_amount).label('total_amount'),
            func.sum(Transaction.qty).label('qty')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= start_date
        ).group_by(
            Transaction.customer_id
        ).order_by(
            func.sum(Transaction.total_amount).desc()
        ).limit(8).all()
        
        # Get customer names
        from app.models.customer import Customer
        top_customers = []
        for customer_id, total_amount, qty in top_customers_query:
            customer = Customer.query.filter_by(customer_id=customer_id).first()
            if customer:
                top_customers.append({
                    "customer_id": customer_id,
                    "business_name": customer.business_name,
                    "total_amount": float(total_amount),
                    "qty": int(qty)
                })
        
        # Get recent transactions
        recent_transactions = []
        unique_invoices = set()
        
        for t in sorted(transactions, key=lambda x: x.invoice_date, reverse=True):
            if len(unique_invoices) >= 10:
                break
                
            if t.invoice_id not in unique_invoices:
                unique_invoices.add(t.invoice_id)
                recent_transactions.append({
                    "invoice_id": t.invoice_id,
                    "invoice_date": t.invoice_date.isoformat() if t.invoice_date else None,
                    "customer_id": t.customer_id,
                    "qty": t.qty,
                    "total_amount": float(t.total_amount)
                })
        
        # Return the compiled data
        result = {
            "total_sales": total_sales,
            "total_qty": total_qty,
            "profit_margin": profit_margin,
            "sales_by_month": sales_by_month,
            "top_customers": top_customers,
            "recent_transactions": recent_transactions
        }
        
        return success_response(
            data=result,
            message="Product sales data retrieved successfully"
        )
        
    except Exception as e:
        current_app.logger.error(f"Product sales retrieval error: {str(e)}")
        return error_response(f"Error retrieving product sales data: {str(e)}", 500)


@inventory_bp.route("/update/<product_id>", methods=["PUT"])
@jwt_required()
def update_product(product_id):
    """
    Endpoint to update product information.
    """
    try:
        # Get the product
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response("Product not found", 404)
            
        # Get stock info
        stock = ProductStock.query.filter_by(product_id=product_id).first()
        if not stock:
            return error_response("Product stock information not found", 404)
            
        # Get request data
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)
            
        # Update product fields
        for field in ["product_name", "standard_price", "retail_price", 
                      "category", "min_stock", "max_stock", 
                      "supplier_id", "supplier_name"]:
            if field in data:
                setattr(product, field, data[field])
                
        # Update stock fields
        for field in ["location", "qty", "unit"]:
            if field in data:
                setattr(stock, field, data[field])
                
        # Save changes
        db.session.commit()
        
        return success_response(
            message="Product updated successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Product update error: {str(e)}")
        return error_response(f"Error updating product: {str(e)}", 500)


@inventory_bp.route("/create", methods=["POST"])
@jwt_required()
def create_product():
    """
    Endpoint to create a new product.
    """
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)
            
        # Check required fields
        required_fields = ["product_code", "product_id", "product_name", 
                          "standard_price", "qty", "unit"]
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
                
        # Check if product already exists
        existing = Product.query.filter(
            or_(
                Product.product_code == data["product_code"],
                Product.product_id == data["product_id"]
            )
        ).first()
        
        if existing:
            return error_response("Product with this code or ID already exists", 400)
            
        # Create product
        product = Product(
            product_code=data["product_code"],
            product_id=data["product_id"],
            product_name=data["product_name"],
            standard_price=data["standard_price"],
            retail_price=data.get("retail_price", data["standard_price"]),
            ppn=data.get("ppn", 0),
            category=data.get("category"),
            min_stock=data.get("min_stock", 1),
            max_stock=data.get("max_stock", 9999),
            supplier_id=data.get("supplier_id"),
            supplier_name=data.get("supplier_name")
        )
        
        # Create stock entry
        stock = ProductStock(
            product_id=data["product_id"],
            report_date=datetime.now().date(),
            location=data.get("location"),
            qty=data["qty"],
            unit=data["unit"],
            price=data["standard_price"]
        )
        
        # Save to database
        db.session.add(product)
        db.session.add(stock)
        db.session.commit()
        
        return success_response(
            message="Product created successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Product creation error: {str(e)}")
        return error_response(f"Error creating product: {str(e)}", 500)


@inventory_bp.route("/delete/<product_id>", methods=["DELETE"])
@jwt_required()
def delete_product(product_id):
    """
    Endpoint to delete a product.
    """
    try:
        # Get the product
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response("Product not found", 404)
            
        # Get stock info
        stock = ProductStock.query.filter_by(product_id=product_id).first()
        
        # Delete stock first (due to foreign key constraint)
        if stock:
            db.session.delete(stock)
            
        # Delete product
        db.session.delete(product)
        db.session.commit()
        
        return success_response(
            message="Product deleted successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Product deletion error: {str(e)}")
        return error_response(f"Error deleting product: {str(e)}", 500)