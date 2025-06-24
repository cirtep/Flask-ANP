from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from ..db import db
from app.utils.security import success_response, error_response
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.saved_forecast import SavedForecast
from sqlalchemy import func, and_, extract
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from collections import defaultdict

# Create a new blueprint
goals_bp = Blueprint("goals", __name__)

@goals_bp.route("/goals", methods=["GET"])
@jwt_required()
def get_goals_data():
    """
    Endpoint to retrieve data for the goals dashboard.
    Compares saved forecasts (targets) with actual sales.
    """
    try:
        # Get query parameters
        start_date = request.args.get("start_date", None)
        end_date = request.args.get("end_date", None)
        category = request.args.get("category", None)
        product_id = request.args.get("product_id", None)
        
        # Validate and parse dates
        if not start_date:
            # Default to 6 months ago
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        
        if not end_date:
            # Default to current date
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        # Convert string dates to datetime objects
        start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Build query filters for products
        product_filters = []
        if category:
            product_filters.append(Product.category == category)
        if product_id:
            product_filters.append(Product.product_id == product_id)
        
        # Get products matching filters
        products_query = db.session.query(Product)
        if product_filters:
            products_query = products_query.filter(*product_filters)
        
        products = products_query.all()
        
        if not products:
            return error_response("No products found matching the filters", 404)
        
        # Create data structure for response
        product_data = []
        all_forecasts = 0
        all_actuals = 0
        
        # For tracking top and underperformers
        performance_data = []
        
        # Process each product
        for product in products:
            # Get saved forecasts for this product within date range
            forecasts = db.session.query(SavedForecast).filter(
                SavedForecast.product_id == product.product_id,
                SavedForecast.forecast_date >= start_datetime,
                SavedForecast.forecast_date <= end_datetime
            ).order_by(SavedForecast.forecast_date).all()
            
            # Skip products with no forecasts
            if not forecasts:
                continue
            
            # Get actual sales for this product by month
            sales_query = db.session.query(
                func.date_format(Transaction.invoice_date, '%Y-%m-01').label('month'),
                func.sum(Transaction.qty).label('quantity')
            ).filter(
                Transaction.product_id == product.product_id,
                Transaction.invoice_date >= start_datetime,
                Transaction.invoice_date <= end_datetime
            ).group_by('month').all()
            
            # Convert to dict for easy lookup
            actual_sales = {row.month: float(row.quantity) for row in sales_query}
            
            # Process monthly data
            monthly_data = []
            product_forecast_total = 0
            product_actual_total = 0
            
            for forecast in forecasts:
                # Format date as YYYY-MM-01 for comparison
                date_str = forecast.forecast_date.strftime("%Y-%m-01")
                
                # Get forecast value
                forecast_data = forecast.get_forecast_data()
                forecast_value = round(float(forecast_data.get('yhat', 0)))
                
                # Get actual value if exists, otherwise 0
                actual_value = round(actual_sales.get(date_str, 0))
                
                # Calculate variance and achievement
                variance = actual_value - forecast_value
                achievement = (actual_value / forecast_value * 100) if forecast_value > 0 else 0
                
                # Add to totals
                product_forecast_total += forecast_value
                product_actual_total += actual_value
                
                # Add to monthly data array
                monthly_data.append({
                    'date': date_str,
                    'forecast': forecast_value,
                    'actual': actual_value,
                    'variance': variance,
                    'achievement': achievement
                })
            
            # Add to overall totals
            all_forecasts += product_forecast_total
            all_actuals += product_actual_total
            
            # Calculate product total achievement
            product_achievement = (product_actual_total / product_forecast_total * 100) if product_forecast_total > 0 else 0
            
            # Add product data
            product_data.append({
                'product_id': product.product_id,
                'product_name': product.product_name,
                'category': product.category,
                'monthly_data': monthly_data
            })
            
            # Add to performance tracking
            performance_data.append({
                'product_id': product.product_id,
                'product_name': product.product_name,
                'category': product.category,
                'forecast': product_forecast_total,
                'actual': product_actual_total,
                'variance': product_actual_total - product_forecast_total,
                'achievement': product_achievement
            })
        
        # Overall achievement
        overall_achievement = (all_actuals / all_forecasts * 100) if all_forecasts > 0 else 0
        
        # Sort performance data by achievement to get top/under performers
        performance_data.sort(key=lambda x: x['achievement'], reverse=True)
        
        # Get top performers (achievement >= 100%)
        top_performers = [p for p in performance_data if p['achievement'] >= 100]
        
        # Get underperformers (achievement < 100%)
        under_performers = [p for p in performance_data if p['achievement'] < 100]
        
        # Create summary
        summary = {
            'total_forecast': all_forecasts,
            'total_actual': all_actuals,
            'overall_achievement': overall_achievement,
            'top_performers': top_performers[:5],  # Limit to top 5
            'under_performers': under_performers[:5]  # Limit to bottom 5
        }
        
        return success_response(
            data={
                'product_data': product_data,
                'summary': summary
            },
            message="Goals data retrieved successfully"
        )
        
    except Exception as e:
        return error_response(f"Error retrieving goals data: {str(e)}", 500)

# Route to get products by category
@goals_bp.route("/by-category", methods=["GET"])
@jwt_required()
def get_products_by_category():
    """Get products filtered by category"""
    try:
        category = request.args.get("category")
        
        if not category:
            return error_response("Category parameter is required", 400)
        
        # Query products by category
        products = Product.query.filter_by(category=category).all()
        
        if not products:
            return success_response(data=[], message="No products found in this category")
        
        # Format response
        product_list = [
            {
                'product_id': product.product_id,
                'product_name': product.product_name,
                'category': product.category
            } 
            for product in products
        ]
        
        return success_response(
            data=product_list,
            message="Products retrieved successfully"
        )
            
    except Exception as e:
        return error_response(f"Error retrieving products: {str(e)}", 500)