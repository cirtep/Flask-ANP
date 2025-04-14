from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from app import db
from app.utils.security import success_response, error_response
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.transaction import Transaction
from app.models.customer import Customer
from sqlalchemy import func, desc, and_, extract
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import calendar

inventory_analytics_bp = Blueprint("inventory_analytics", __name__)


@inventory_analytics_bp.route("/<product_id>", methods=["GET"])
@jwt_required()
def get_product_details(product_id):
    """
    Endpoint to get detailed information about a specific product
    """
    try:
        # Query product
        product = db.session.query(Product).filter(Product.product_id == product_id).first()
        
        if not product:
            return error_response("Product not found", 404)
        
        # Get latest stock information
        stock = db.session.query(ProductStock).filter(
            ProductStock.product_id == product_id
        ).order_by(ProductStock.report_date.desc()).first()
        
        if not stock:
            return error_response("Stock information not found", 404)
        
        # Calculate sales analytics
        
        # 1. Monthly sales quantities
        monthly_sales_query = db.session.query(
            func.date_format(Transaction.invoice_date, '%Y-%m-01').label('month'),
            func.sum(Transaction.qty).label('quantity'),
            func.sum(Transaction.total_amount).label('revenue')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(start_date, end_date)
        ).group_by('month').order_by('month').all()
        
        monthly_sales = [
            {
                "month": datetime.strptime(item.month, "%Y-%m-%d").strftime("%b %Y"),
                "quantity": int(item.quantity),
                "revenue": float(item.revenue)
            }
            for item in monthly_sales_query
        ]
        
        # 2. Calculate total revenue and units sold for current and previous periods
        current_period_query = db.session.query(
            func.sum(Transaction.qty).label('units'),
            func.sum(Transaction.total_amount).label('revenue')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(start_date, end_date)
        ).first()
        
        previous_period_query = db.session.query(
            func.sum(Transaction.qty).label('units'),
            func.sum(Transaction.total_amount).label('revenue')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(prev_start_date, prev_end_date)
        ).first()
        
        # Handle null results
        total_units_sold = int(current_period_query.units or 0)
        total_revenue = float(current_period_query.revenue or 0)
        prev_units = int(previous_period_query.units or 0)
        prev_revenue = float(previous_period_query.revenue or 0)
        
        # Calculate growth rates
        units_growth = ((total_units_sold - prev_units) / max(prev_units, 1)) * 100 if prev_units != 0 else 0
        revenue_growth = ((total_revenue - prev_revenue) / max(prev_revenue, 1)) * 100 if prev_revenue != 0 else 0
        
        # Calculate average selling price
        avg_selling_price = total_revenue / total_units_sold if total_units_sold > 0 else 0
        prev_avg_price = prev_revenue / prev_units if prev_units > 0 else 0
        price_growth = ((avg_selling_price - prev_avg_price) / max(prev_avg_price, 1)) * 100 if prev_avg_price != 0 else 0
        
        # 3. Year-over-Year comparison
        current_year_monthly_query = db.session.query(
            extract('month', Transaction.invoice_date).label('month_num'),
            func.sum(Transaction.qty).label('quantity')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(start_date, end_date)
        ).group_by('month_num').all()
        
        previous_year_monthly_query = db.session.query(
            extract('month', Transaction.invoice_date).label('month_num'),
            func.sum(Transaction.qty).label('quantity')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(year_ago_start, year_ago_end)
        ).group_by('month_num').all()
        
        # Create monthly data for YoY comparison
        yoy_comparison = []
        month_names = [calendar.month_abbr[m] for m in range(1, 13)]
        
        current_year_data = {item.month_num: int(item.quantity) for item in current_year_monthly_query}
        previous_year_data = {item.month_num: int(item.quantity) for item in previous_year_monthly_query}
        
        # Get start month number to align comparison
        start_month_num = start_date.month
        
        for i in range(months):
            month_num = ((start_month_num - 1 + i) % 12) + 1
            month_name = month_names[month_num - 1]
            
            yoy_comparison.append({
                "month": month_name,
                "current_year": current_year_data.get(month_num, 0),
                "previous_year": previous_year_data.get(month_num, 0)
            })
        
        # 4. Quarterly performance
        quarters = {
            1: "Q1",
            2: "Q1",
            3: "Q1",
            4: "Q2",
            5: "Q2",
            6: "Q2",
            7: "Q3",
            8: "Q3",
            9: "Q3",
            10: "Q4",
            11: "Q4",
            12: "Q4"
        }
        
        quarterly_query = db.session.query(
            func.concat(
                "Q",
                func.ceiling(extract('month', Transaction.invoice_date) / 3)
            ).label('quarter'),
            func.sum(Transaction.qty).label('units'),
            func.sum(Transaction.total_amount).label('revenue')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(start_date, end_date)
        ).group_by('quarter').order_by('quarter').all()
        
        quarterly_performance = [
            {
                "quarter": item.quarter,
                "units": int(item.units),
                "revenue": float(item.revenue)
            }
            for item in quarterly_query
        ]
        
        # 5. Calculate year-over-year growth
        current_year_total_query = db.session.query(
            func.sum(Transaction.qty).label('quantity')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(start_date, end_date)
        ).scalar()
        
        previous_year_total_query = db.session.query(
            func.sum(Transaction.qty).label('quantity')
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(year_ago_start, year_ago_end)
        ).scalar()
        
        current_year_total = int(current_year_total_query or 0)
        previous_year_total = int(previous_year_total_query or 0)
        
        year_over_year_growth = ((current_year_total - previous_year_total) / max(previous_year_total, 1)) * 100 if previous_year_total != 0 else 0
        
        # 6. Calculate average monthly sales
        avg_monthly_sales = current_year_total / months if months > 0 else 0
        
        # 7. Generate sales ranking data
        # Get total number of products in the same category
        category_products_count = db.session.query(func.count(Product.id)).filter(
            Product.category == product.category
        ).scalar()
        
        # Get sales ranking within category
        category_sales_ranking_query = db.session.query(
            Transaction.product_id,
            func.sum(Transaction.qty).label('total_qty')
        ).join(
            Product, Transaction.product_id == Product.product_id
        ).filter(
            Product.category == product.category,
            Transaction.invoice_date.between(start_date, end_date)
        ).group_by(
            Transaction.product_id
        ).order_by(
            desc('total_qty')
        ).all()
        
        # Convert to a list of product IDs ordered by sales quantity
        ranked_products = [item.product_id for item in category_sales_ranking_query]
        
        # Find position of current product in the ranking
        product_rank = ranked_products.index(product_id) + 1 if product_id in ranked_products else category_products_count
        
        # Calculate percentile (higher is better)
        percentile = ((category_products_count - product_rank) / max(category_products_count - 1, 1)) * 100 if category_products_count > 1 else 100
        
        # Get top 5 products in category
        top_products_query = db.session.query(
            Product.product_id,
            Product.product_name,
            func.sum(Transaction.qty).label('units_sold'),
            func.sum(Transaction.total_amount).label('revenue')
        ).join(
            Transaction, Product.product_id == Transaction.product_id
        ).filter(
            Product.category == product.category,
            Transaction.invoice_date.between(start_date, end_date)
        ).group_by(
            Product.product_id,
            Product.product_name
        ).order_by(
            desc('units_sold')
        ).limit(5).all()
        
        top_products = [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "units_sold": int(item.units_sold),
                "revenue": float(item.revenue)
            }
            for item in top_products_query
        ]
        
        # 8. Inventory movement analysis
        # For this demo, we'll simulate inventory movement data
        # In a real application, you would query actual inventory transactions
        inventory_movement = {
            "total_inbound": int(total_units_sold * 1.2),  # Simulate inbound as 120% of sales
            "total_outbound": total_units_sold,
            "turnover_rate": total_units_sold / max(stock.qty, 1) if stock.qty > 0 else 0,
            "avg_days_in_stock": 30,  # Simulated value
            "monthly_movement": [],
            "recent_movements": []
        }
        
        # Simulate monthly movement data
        for i, sales in enumerate(monthly_sales):
            month_name = sales["month"]
            outbound = sales["quantity"]
            inbound = int(outbound * (1.1 + (i % 3) * 0.1))  # Vary inbound slightly
            balance = inbound - outbound
            
            inventory_movement["monthly_movement"].append({
                "month": month_name,
                "inbound": inbound,
                "outbound": outbound,
                "balance": balance
            })
        
        # Simulate recent movement history
        for i in range(10):
            is_inbound = i % 3 == 0
            qty = int(10 + i * 5) if is_inbound else int(8 + i * 4)
            movement_date = end_date - timedelta(days=i * 3)
            balance = stock.qty + (qty if is_inbound else -qty)
            
            inventory_movement["recent_movements"].append({
                "date": movement_date.strftime("%Y-%m-%d"),
                "type": "inbound" if is_inbound else "outbound",
                "quantity": qty,
                "reference": f"{'PO' if is_inbound else 'SO'}-{100 + i}",
                "balance_after": balance
            })
        
        # 9. Top customers analysis
        top_customers_query = db.session.query(
            Transaction.customer_id,
            Customer.business_name,
            func.count(func.distinct(Transaction.invoice_id)).label('order_count'),
            func.sum(Transaction.qty).label('quantity'),
            func.sum(Transaction.total_amount).label('total_amount')
        ).join(
            Customer, Transaction.customer_id == Customer.customer_id
        ).filter(
            Transaction.product_id == product_id,
            Transaction.invoice_date.between(start_date, end_date)
        ).group_by(
            Transaction.customer_id,
            Customer.business_name
        ).order_by(
            desc('total_amount')
        ).limit(5).all()
        
        top_customers = [
            {
                "customer_id": item.customer_id,
                "customer_name": item.business_name,
                "order_count": int(item.order_count),
                "quantity": int(item.quantity),
                "total_amount": float(item.total_amount)
            }
            for item in top_customers_query
        ]
        
        # 10. Customer purchase trends (simplified simulation)
        customer_purchase_trends = []
        for i in range(months):
            month_date = start_date + relativedelta(months=i)
            month_name = month_date.strftime("%b %Y")
            
            month_data = {
                "month": month_name,
            }
            
            # Add data for top 3 customers
            for j, customer in enumerate(top_customers[:3]):
                # Simulate varying purchases
                multiplier = 0.8 + (i % 4) * 0.1 + (j % 3) * 0.1
                month_data[f"customer{j+1}"] = int(customer["quantity"] * multiplier / months)
                month_data["customer_name"] = customer["customer_name"]  # For tooltip
                
            customer_purchase_trends.append(month_data)
        
        # 11. Recent customer orders
        recent_orders_query = db.session.query(
            Transaction.invoice_date,
            Transaction.invoice_id,
            Customer.business_name,
            Transaction.qty,
            Transaction.total_amount
        ).join(
            Customer, Transaction.customer_id == Customer.customer_id
        ).filter(
            Transaction.product_id == product_id
        ).order_by(
            Transaction.invoice_date.desc()
        ).limit(10).all()
        
        recent_customer_orders = [
            {
                "date": item.invoice_date.strftime("%Y-%m-%d"),
                "invoice_id": item.invoice_id,
                "customer_name": item.business_name,
                "quantity": int(item.qty),
                "amount": float(item.total_amount)
            }
            for item in recent_orders_query
        ]
        
        if not product:
            return error_response("Product not found", 404)
        
        # Query latest stock information
        stock = db.session.query(ProductStock).filter(
            ProductStock.product_id == product_id
        ).order_by(ProductStock.report_date.desc()).first()
        
        if not stock:
            return error_response("Stock information not found", 404)
        
        # Assemble and return analytics data
        analytics_data = {
            "monthly_sales": monthly_sales,
            "total_units_sold": total_units_sold,
            "total_revenue": total_revenue,
            "avg_selling_price": avg_selling_price,
            "units_growth": units_growth,
            "revenue_growth": revenue_growth,
            "price_growth": price_growth,
            "year_over_year_growth": year_over_year_growth,
            "avg_monthly_sales": avg_monthly_sales,
            "yoy_comparison": yoy_comparison,
            "quarterly_performance": quarterly_performance,
            "sales_ranking": {
                "rank": product_rank,
                "total_products": category_products_count,
                "percentile": percentile,
                "top_products": top_products
            },
            "inventory_movement": inventory_movement,
            "top_customers": top_customers,
            "customer_purchase_trends": customer_purchase_trends,
            "recent_customer_orders": recent_customer_orders
        }
        
        return success_response(
            data=analytics_data,
            message="Product analytics retrieved successfully"
        )
    except Exception as e:
        current_app.logger.error(f"Error retrieving product analytics: {str(e)}")
        return error_response(f"Error retrieving product analytics: {str(e)}", 500)

