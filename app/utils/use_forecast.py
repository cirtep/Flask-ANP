# app/utils/use_forecast.py
from app.models.saved_forecast import SavedForecast
from app.models.product import Product
from app.models.product_stock import ProductStock
from ..db import db
from sqlalchemy import desc, extract
from datetime import datetime

def get_stock_limits(product, with_forecast=True):
    """
    Helper function to get min_stock and max_stock values based on use_forecast setting
    
    Args:
        product: The Product model instance
        with_forecast: Whether to consider the use_forecast flag (default True)
        
    Returns:
        tuple: (min_stock, max_stock) values to use
    """
    # Default values
    min_stock = float(product.min_stock) if product.min_stock else 0
    max_stock = float(product.max_stock) if product.max_stock else 0
    
    # If use_forecast is enabled and we want to consider it
    if with_forecast and product.use_forecast:
        # Get the current month and year
        current_date = datetime.now()
        current_month = current_date.month
        current_year = current_date.year
        
        # Get the forecast for the current month
        current_month_forecast = SavedForecast.query.filter(
            SavedForecast.product_id == product.product_id,
            extract('month', SavedForecast.forecast_date) == current_month,
            extract('year', SavedForecast.forecast_date) == current_year
        ).first()
        
        if current_month_forecast:
            forecast_data = current_month_forecast.get_forecast_data()
            # Use forecast lower bound as min_stock
            forecast_min = float(forecast_data.get('yhat_lower', 0))
            # Use forecast upper bound as max_stock
            forecast_max = float(forecast_data.get('yhat_upper', 0))
            
            # Validation: Ensure min is less than max and values are non-negative
            if forecast_min < forecast_max and forecast_min >= 0 and forecast_max > 0:
                min_stock = forecast_min
                max_stock = forecast_max
            else:
                # If validation fails, use default values
                min_stock = float(product.min_stock) if product.min_stock else 0
                max_stock = float(product.max_stock) if product.max_stock else 0
    
    # Ensure final values are valid, even if coming from default product values
    if min_stock > max_stock:
        # Swap values if min is greater than max
        min_stock, max_stock = max_stock, min_stock
    
    # Ensure non-negative values
    min_stock = max(0, min_stock)
    max_stock = max(0, max_stock)
    
    return min_stock, max_stock
