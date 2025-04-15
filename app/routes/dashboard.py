from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from app import db
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.customer import Customer
from app.utils.security import success_response, error_response
from sqlalchemy import func, desc, and_, extract
from datetime import datetime, timedelta
import calendar

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/summary", methods=["GET"])
@jwt_required()
def dashboard_summary():
    """
    Endpoint to retrieve summary data for the dashboard homepage.
    Including sales metrics, inventory status, recent transactions, and top products.
    """
    try:
        # Get date parameters for filtering
        today = datetime.now().date()
        current_month_start = datetime(today.year, today.month, 1).date()
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        last_month_end = current_month_start - timedelta(days=1)
        
        # Calculate days in current month for projections
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_passed = today.day
        month_progress_ratio = days_passed / days_in_month
        
        # ===== Sales Metrics =====
        
        # Current month sales
        current_month_sales_query = db.session.query(
            func.sum(Transaction.total_amount).label('total_amount'),
            func.count(func.distinct(Transaction.invoice_id)).label('order_count')
        ).filter(
            Transaction.invoice_date >= current_month_start,
            Transaction.invoice_date <= today
        ).first()
        
        current_month_sales = float(current_month_sales_query.total_amount or 0)
        current_month_orders = int(current_month_sales_query.order_count or 0)
        
        # Last month sales
        last_month_sales_query = db.session.query(
            func.sum(Transaction.total_amount).label('total_amount'),
            func.count(func.distinct(Transaction.invoice_id)).label('order_count')
        ).filter(
            Transaction.invoice_date >= last_month_start,
            Transaction.invoice_date <= last_month_end
        ).first()
        
        last_month_sales = float(last_month_sales_query.total_amount or 0)
        last_month_orders = int(last_month_sales_query.order_count or 0)
        
        # Calculate monthly growth and projection
        monthly_growth = 0
        if last_month_sales > 0:
            monthly_growth = ((current_month_sales / last_month_sales) - 1) * 100
        
        # Project month-end total if current pace continues
        projected_month_sales = current_month_sales / month_progress_ratio if month_progress_ratio > 0 else 0
        
        # Get sales for last 6 months for trend chart
        six_months_ago = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        for _ in range(4):  # Go back 5 more months
            six_months_ago = (six_months_ago - timedelta(days=1)).replace(day=1)
        
        monthly_sales_trend = db.session.query(
            func.date_format(Transaction.invoice_date, '%Y-%m').label('month'),
            func.sum(Transaction.total_amount).label('amount')
        ).filter(
            Transaction.invoice_date >= six_months_ago
        ).group_by('month').order_by('month').all()
        
        # Format monthly trend for frontend
        sales_trend = []
        for month_str, amount in monthly_sales_trend:
            year, month = map(int, month_str.split('-'))
            month_date = datetime(year, month, 1)
            month_name = month_date.strftime("%b %Y")
            
            sales_trend.append({
                "month": month_name,
                "amount": float(amount)
            })
            
        # ===== Inventory Metrics =====
        
        # Get inventory stats
        inventory_stats = db.session.query(
            func.count(Product.id).label('total_products'),
            func.sum(ProductStock.qty * Product.standard_price).label('inventory_value')
        ).join(
            ProductStock, Product.product_id == ProductStock.product_id
        ).first()
        
        total_products = int(inventory_stats.total_products or 0)
        inventory_value = float(inventory_stats.inventory_value or 0)
        
        # Get low stock alerts
        low_stock_query = db.session.query(
            Product, ProductStock
        ).join(
            ProductStock, Product.product_id == ProductStock.product_id
        ).filter(
            ProductStock.qty <= Product.min_stock
        ).all()
        
        low_stock_items = [
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "current_stock": stock.qty,
                "min_stock": product.min_stock,
                "unit": stock.unit
            }
            for product, stock in low_stock_query
        ]
        
        # ===== Customer Metrics =====
        
        # Total customers
        total_customers = Customer.query.count()
        
        # New customers this month
        new_customers_count = db.session.query(func.count(Customer.id)).filter(
            Customer.created_at >= current_month_start
        ).scalar() or 0
        
        # ===== Top Products =====
        
        # Get top selling products for current month
        top_products_query = db.session.query(
            Transaction.product_id,
            Transaction.product_name,
            func.sum(Transaction.qty).label('quantity'),
            func.sum(Transaction.total_amount).label('total_sales')
        ).filter(
            Transaction.invoice_date >= current_month_start
        ).group_by(
            Transaction.product_id,
            Transaction.product_name
        ).order_by(
            desc('total_sales')
        ).limit(5).all()
        
        top_products = [
            {
                "product_id": product_id,
                "product_name": product_name,
                "quantity": int(quantity) if quantity is not None else 0,
                "total_sales": float(total_sales) if total_sales is not None else 0
            }
            for product_id, product_name, quantity, total_sales in top_products_query
        ]
        
        # ===== Recent Transactions =====
        
        # Get recent transactions (last 10)
        recent_transactions_query = db.session.query(
            Transaction.invoice_id,
            Transaction.invoice_date,
            Transaction.customer_id,
            Customer.business_name,
            func.sum(Transaction.total_amount).label('total_amount')
        ).join(
            Customer, Transaction.customer_id == Customer.customer_id
        ).group_by(
            Transaction.invoice_id,
            Transaction.invoice_date,
            Transaction.customer_id,
            Customer.business_name
        ).order_by(
            Transaction.invoice_date.desc()
        ).limit(10).all()
        
        recent_transactions = [
            {
                "invoice_id": invoice_id,
                "date": invoice_date.strftime("%Y-%m-%d"),
                "customer_id": customer_id,
                "customer_name": business_name,
                "amount": float(total_amount)
            }
            for invoice_id, invoice_date, customer_id, business_name, total_amount in recent_transactions_query
        ]
        
        # Assemble all data for dashboard
        dashboard_data = {
            "sales": {
                "current_month": current_month_sales,
                "last_month": last_month_sales,
                "growth_percentage": monthly_growth,
                "projected_month_end": projected_month_sales,
                "current_month_orders": current_month_orders,
                "last_month_orders": last_month_orders,
                "trend": sales_trend
            },
            "inventory": {
                "total_products": total_products,
                "inventory_value": inventory_value,
                "low_stock_count": len(low_stock_items),
                "low_stock_items": low_stock_items[:5]  # Limit to 5 items
            },
            "customers": {
                "total_customers": total_customers,
                "new_customers": new_customers_count
            },
            "top_products": top_products,
            "recent_transactions": recent_transactions
        }
        
        return success_response(
            data=dashboard_data,
            message="Dashboard data retrieved successfully"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving dashboard data: {str(e)}", 500)