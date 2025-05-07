import os
import tempfile
from flask import Blueprint, make_response, request, jsonify, current_app
from flask_jwt_extended import jwt_required
import pandas as pd
from app import db
from app.utils.security import success_response, error_response
from app.utils.use_forecast import get_stock_limits
from sqlalchemy import or_, func
from sqlalchemy.sql import text
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.transaction import Transaction
from app.models.customer import Customer
from datetime import datetime, timedelta

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/all", methods=["GET"])
@jwt_required()
def get_inventory():
    """
    Endpoint to retrieve comprehensive inventory data with stock information.
    Data is sorted by total sales amount.
    """
    try:
        # Use SQLAlchemy ORM for more reliable data conversion
        # First get product and stock data
        query = db.session.query(Product, ProductStock).join(
            ProductStock, Product.product_id == ProductStock.product_id
        )

        # Execute the query
        results = query.all()

        # Create a dictionary to hold total sales per product
        product_sales = {}
        
        # Query total sales amount for each product
        sales_data = db.session.query(
            Transaction.product_id,
            func.sum(Transaction.total_amount).label('total_sales'),
            func.sum(Transaction.qty).label('total_qty')
        ).group_by(
            Transaction.product_id
        ).all()
        
        # Convert to dictionary for easy lookup
        for product_id, total_sales, total_qty in sales_data:
            product_sales[product_id] = {
                'total_amount': float(total_sales) if total_sales else 0,
                'total_qty': int(total_qty) if total_qty else 0
            }

        # Manual conversion to ensure proper dictionary format and include sales data
        inventory_list = []
        for product, stock in results:
            # Get sales data for this product
            sales = product_sales.get(product.product_id, {'total_amount': 0, 'total_qty': 0})
            min_stock, max_stock = get_stock_limits(product)

            item = {
                # From Product model
                "id": product.id,
                "product_code": product.product_code,
                "product_id": product.product_id,
                "product_name": product.product_name,
                "standard_price": float(product.standard_price),  # Ensure numeric
                "retail_price": float(product.retail_price),
                "ppn": float(product.ppn) if product.ppn else 0,
                "category": product.category,
                "min_stock": min_stock,
                "max_stock": max_stock,
                "use_forecast": product.use_forecast,
                "supplier_id": product.supplier_id,
                "supplier_name": product.supplier_name,
                # From ProductStock model
                "report_date": stock.report_date.isoformat() if stock.report_date else None,
                "location": stock.location,
                "qty": float(stock.qty),
                "unit": stock.unit,
                # Sales data (not displayed in table but used for sorting)
                "total_amount": sales['total_amount'],
                "total_qty_sold": sales['total_qty']
            }
            inventory_list.append(item)


        # Sort by total_amount (highest sales first)
        inventory_list.sort(key=lambda x: x["total_amount"], reverse=True)

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
            "use_forecast": product.use_forecast,
            # From ProductStock model
            "report_date": product.created_at.isoformat() if product.created_at else None,
            "location": stock.location,
            "qty": float(stock.qty),
            "unit": stock.unit,
        }
        
        if product.use_forecast:
            # Get the most recent forecast for this product
            from app.models.saved_forecast import SavedForecast
            from sqlalchemy import desc
            
            latest_forecast = SavedForecast.query.filter_by(
                product_id=product_id
            ).order_by(desc(SavedForecast.forecast_date)).first()
            
            if latest_forecast:
                forecast_data = latest_forecast.get_forecast_data()
                # Use forecast lower bound as min_stock
                product_data["min_stock"] = float(forecast_data.get('yhat_lower', 0))
                # Use forecast upper bound as max_stock
                product_data["max_stock"] = float(forecast_data.get('yhat_upper', 0))
            else:
                # Fall back to regular values if no forecast is available
                product_data["min_stock"] = float(product.min_stock) if product.min_stock else 0
                product_data["max_stock"] = float(product.max_stock) if product.max_stock else 0
        else:
            # Use the regular min/max stock values
            product_data["min_stock"] = float(product.min_stock) if product.min_stock else 0
            product_data["max_stock"] = float(product.max_stock) if product.max_stock else 0

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
            return error_response(f"Product with ID {product_id} not found", 404)
            
        # Get time range filter from query params (default: last 6 months)
        months = int(request.args.get("months", 6))
        if months == 9999:  # "all" time range
            start_date = datetime(1900, 1, 1)  # Far past date to include all records
        else:
            start_date = datetime.now() - timedelta(days=30 * months)
        
        today = datetime.now()
        
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
                    "all_customers": [],
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
            
        # Get monthly sales data
        monthly_sales = db.session.query(
            func.date_format(Transaction.invoice_date, '%Y-%m-01').label('month'),
            func.sum(Transaction.total_amount).label('amount'),
            func.count(func.distinct(Transaction.invoice_id)).label('order_count')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= start_date
        ).group_by('month').order_by('month').all()
        
        # Format monthly sales for frontend charts
        sales_by_month = [
            {
                "month": datetime.strptime(entry[0], "%Y-%m-%d").strftime("%b %Y"),
                "amount": float(entry[1]),
                "order_count": int(entry[2])
            }
            for entry in monthly_sales
        ]
        
        # Get monthly cost data for profit margin calculations
        monthly_cost_query = db.session.query(
            func.date_format(Transaction.invoice_date, '%Y-%m-01').label('month'),
            func.sum(Transaction.total_cost).label('amount')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= start_date
        ).group_by('month').order_by('month').all()
        
        # Format monthly cost data
        cost_by_month = [
            {
                "month": datetime.strptime(entry[0], "%Y-%m-%d").strftime("%b %Y"),
                "amount": float(entry[1])
            }
            for entry in monthly_cost_query
        ]
        
        # Query all customers who ever purchased this product
        all_customers_query = db.session.query(
            Transaction.customer_id,
            Customer.business_name,
            func.sum(Transaction.qty).label('qty'),
            func.sum(Transaction.total_amount).label('total_amount'),
            func.min(Transaction.invoice_date).label('first_purchase'),
            func.max(Transaction.invoice_date).label('last_purchase'),
            func.count(func.distinct(Transaction.invoice_id)).label('purchase_count')
        ).join(
            Customer, Transaction.customer_id == Customer.customer_id
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= start_date
        ).group_by(
            Transaction.customer_id,
            Customer.business_name
        ).order_by(
            func.sum(Transaction.total_amount).desc()
        ).all()
        
        # Format all customers data
        all_customers = [
            {
                "customer_id": cust[0],
                "business_name": cust[1],
                "qty": int(cust[2]),
                "total_amount": float(cust[3]),
                "first_purchase": cust[4].isoformat() if cust[4] else None,
                "last_purchase": cust[5].isoformat() if cust[5] else None,
                "purchase_count": int(cust[6])
            }
            for cust in all_customers_query
        ]
        
        # Get top 8 customers for pie chart
        top_customers = all_customers[:8] if all_customers else []
        
        # Get recent transactions
        recent_transactions_query = db.session.query(
            Transaction.invoice_id,
            Transaction.invoice_date,
            Transaction.qty,
            Transaction.total_amount,
            Transaction.customer_id,
            Customer.business_name.label('customer_name')
        ).join(
            Customer, Transaction.customer_id == Customer.customer_id
        ).filter(
            Transaction.product_id == product_id
        ).order_by(
            Transaction.invoice_date.desc()
        ).limit(20).all()
        
        # Format recent transactions
        recent_transactions = [
            {
                "invoice_id": txn[0],
                "invoice_date": txn[1].isoformat() if txn[1] else None,
                "qty": txn[2],
                "total_amount": float(txn[3]),
                "customer_id": txn[4],
                "customer_name": txn[5]
            }
            for txn in recent_transactions_query
        ]
        
        # Calculate YTD and previous YTD sales for comparison
        current_year = datetime.now().year
        this_year_start = datetime(current_year, 1, 1)
        previous_year_start = datetime(current_year - 1, 1, 1)
        same_day_previous_year = datetime(current_year - 1, today.month, today.day)
        
        # This year to date
        this_ytd_sales = db.session.query(
            func.sum(Transaction.total_amount)
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= this_year_start,
            Transaction.invoice_date <= today
        ).scalar() or 0
        
        # Previous year to date (same period)
        previous_ytd_sales = db.session.query(
            func.sum(Transaction.total_amount)
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= previous_year_start,
            Transaction.invoice_date <= same_day_previous_year
        ).scalar() or 0
        
        # This month sales
        this_month_start = datetime(today.year, today.month, 1)
        this_month_sales = db.session.query(
            func.sum(Transaction.total_amount)
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= this_month_start
        ).scalar() or 0
        
        # Calculate YTD growth
        ytd_growth = 0
        if previous_ytd_sales > 0:
            ytd_growth = ((this_ytd_sales - previous_ytd_sales) / previous_ytd_sales) * 100
        
        # Calculate average quantity per invoice (transaction)
        avg_qty_per_invoice_query = db.session.query(
            func.avg(Transaction.qty)
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date >= start_date
        ).scalar() or 0

        # Return the compiled data
        result = {
            "total_sales": float(total_sales),
            "total_qty": int(total_qty),
            "profit_margin": float(profit_margin) if profit_margin is not None else None,
            "sales_by_month": sales_by_month,
            "cost_by_month": cost_by_month,
            "all_customers": all_customers,
            "top_customers": top_customers,
            "recent_transactions": recent_transactions,
            "this_ytd_sales": float(this_ytd_sales),
            "previous_ytd_sales": float(previous_ytd_sales),
            "this_month_sales": float(this_month_sales),
            "ytd_growth": float(ytd_growth),
            "avg_qty_per_invoice": float(avg_qty_per_invoice_query),
        }
        
        return success_response(
            data=result,
            message="Product sales data retrieved successfully"
        )
        
    except Exception as e:
        current_app.logger.error(f"Product sales retrieval error: {str(e)}")
        return error_response(f"Error retrieving product sales data: {str(e)}", 500)

#
@inventory_bp.route("/update/<product_id>", methods=["PUT"])
@jwt_required()
def update_product(product_id):
    """
    Endpoint to update product information and stock.
    All fields can be edited.
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
            
        # Validate required fields
        if 'product_name' not in data or not data['product_name'].strip():
            return error_response("Product name is required", 400)
            
        if 'standard_price' not in data or data['standard_price'] is None:
            return error_response("Standard price is required", 400)
            
        if 'qty' not in data or data['qty'] is None:
            return error_response("Quantity is required", 400)
            
        # Update product fields
        product.product_name = data['product_name']
        product.standard_price = data['standard_price']
        
        # Update optional product fields
        if 'retail_price' in data and data['retail_price'] is not None:
            product.retail_price = data['retail_price']
        if 'category' in data:
            product.category = data['category']
        if 'min_stock' in data and data['min_stock'] is not None:
            product.min_stock = data['min_stock']
        if 'max_stock' in data and data['max_stock'] is not None:
            product.max_stock = data['max_stock']
        if 'supplier_id' in data:
            product.supplier_id = data['supplier_id']
        if 'supplier_name' in data:
            product.supplier_name = data['supplier_name']
        if 'ppn' in data and data['ppn'] is not None:
            product.ppn = data['ppn']
        if 'use_forecast' in data:
            product.use_forecast = bool(data['use_forecast'])

        # Update stock fields
        if 'qty' in data and data['qty'] is not None:
            stock.qty = data['qty']
        if 'unit' in data:
            stock.unit = data['unit']
        if 'location' in data:
            stock.location = data['location']
        if 'price' in data and data['price'] is not None:
            stock.price = data['price']
        elif 'standard_price' in data:
            # If price isn't provided but standard_price is, update price to match
            stock.price = data['standard_price']
            
        # Update the report date to current date for tracking purposes
        stock.report_date = datetime.now().date()
                
        # Save changes
        db.session.commit()
        
        # Return updated product data
        updated_product = {
            "product_id": product.product_id,
            "product_code": product.product_code,
            "product_name": product.product_name,
            "standard_price": float(product.standard_price),
            "retail_price": float(product.retail_price),
            "category": product.category,
            "min_stock": float(product.min_stock) if product.min_stock else 0,
            "max_stock": float(product.max_stock) if product.max_stock else 0,
            "supplier_id": product.supplier_id,
            "supplier_name": product.supplier_name,
            "ppn": float(product.ppn) if product.ppn else 0,
            "use_forecast": product.use_forecast,
            "qty": float(stock.qty),
            "unit": stock.unit,
            "location": stock.location
        }
        
        return success_response(
            data=updated_product,
            message="Product updated successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Product update error: {str(e)}")
        return error_response(f"Error updating product: {str(e)}", 500)


@inventory_bp.route("/delete/<product_id>", methods=["DELETE"])
@jwt_required()
def delete_product(product_id):
    """
    Endpoint to delete a product.
    Products with transactions cannot be deleted.
    """
    try:
        # Get the product
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response("Product not found", 404)
            
        # Get stock info
        stock = ProductStock.query.filter_by(product_id=product_id).first()
        
        # Check if product has associated transactions
        transaction_count = Transaction.query.filter_by(product_id=product_id).count()
        
        # Create response data
        response_data = {
            "product_id": product_id,
            "product_name": product.product_name,
            "has_transactions": transaction_count > 0,
            "has_stock": stock is not None and stock.qty > 0,
            "transaction_count": transaction_count
        }
        
        # Check force parameter (for warnings with stock)
        force_delete = request.args.get('force', 'false').lower() == 'true'
        
        if transaction_count > 0:
            # Product has transactions - completely disallow deletion
            return jsonify({
                "success": False,
                "data": response_data,
                "message": f"Cannot delete product with {transaction_count} associated transactions.",
                "deletion_type": "disallowed"
            }), 400
        
        if stock and stock.qty > 0 and not force_delete:
            # Product has stock but no transactions - return warning but allow deletion
            return jsonify({
                "success": False,
                "data": response_data,
                "message": f"Product has remaining stock ({stock.qty} {stock.unit}). Confirm deletion?",
                "deletion_type": "warning"
            }), 400
            
        # No transactions or forced with stock - perform delete        
        # Delete stock first (due to foreign key constraint)
        if stock:
            db.session.delete(stock)
            
        # Delete product
        db.session.delete(product)
        db.session.commit()
        
        return success_response(
            data=response_data,
            message="Product deleted successfully",
            deletion_type="success"
        )
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Product deletion error: {str(e)}")
        return error_response(f"Error deleting product: {str(e)}", 500)


@inventory_bp.route("/export", methods=["GET"])
@jwt_required()
def export_inventory():
    """Export all inventory data to Excel format"""
    try:
        # Get filter parameters
        category_filter = request.args.get("category", "")
        
        # Base query - join Product and ProductStock
        query = db.session.query(Product, ProductStock).join(
            ProductStock, Product.product_id == ProductStock.product_id
        )
        
        # Apply category filter if provided
        if category_filter:
            query = query.filter(Product.category == category_filter)
            
        # Execute the query
        results = query.all()
        
        # Prepare data for export
        export_data = []
        for product, stock in results:
            # Calculate total purchases if available
            total_purchases = db.session.query(
                func.sum(Transaction.qty)
            ).filter(
                Transaction.product_id == product.product_id
            ).scalar() or 0
            
            # Get supplier name
            supplier_name = product.supplier_name or "N/A"
            
            # Calculate stock value
            stock_value = float(stock.qty) * float(product.standard_price)
            
            export_data.append({
                'Product ID': product.product_id,
                'Product Code': product.product_code,
                'Product Name': product.product_name,
                'Category': product.category or '',
                'Standard Price': float(product.standard_price),
                'Retail Price': float(product.retail_price),
                'Current Stock': float(stock.qty),
                'Unit': stock.unit or '',
                'Min Stock': float(product.min_stock) if product.min_stock else 0,
                'Max Stock': float(product.max_stock) if product.max_stock else 0,
                'Stock Value': stock_value,
                'Supplier': supplier_name,
                'Location': stock.location or '',
                'Total Sold': int(total_purchases)
            })
        
        # Convert to dataframe
        import pandas as pd
        df = pd.DataFrame(export_data)
        
        # Format the date for the filename
        from datetime import datetime
        today = datetime.now().strftime('%Y%m%d')
        
        # Export as Excel file
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp:
            # Write to Excel
            df.to_excel(temp.name, index=False, engine='openpyxl')
            temp_name = temp.name
        
        # Read the file
        with open(temp_name, 'rb') as f:
            data = f.read()
        
        # Clean up
        os.unlink(temp_name)
        
        # Prepare the filename
        filename = f"inventory_export_{today}"
        if category_filter:
            filename += f"_{category_filter.replace(' ', '_')}"
        filename += ".xlsx"
        
        # Create response
        from flask import make_response
        response = make_response(data)
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error exporting inventory: {str(e)}")
        return error_response(f"Error exporting inventory: {str(e)}", 500)
    