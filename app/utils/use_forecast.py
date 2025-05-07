from app.models.saved_forecast import SavedForecast
from sqlalchemy import desc

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
        # Get the most recent forecast for this product
        latest_forecast = SavedForecast.query.filter_by(
            product_id=product.product_id
        ).order_by(desc(SavedForecast.forecast_date)).first()
        
        if latest_forecast:
            forecast_data = latest_forecast.get_forecast_data()
            # Use forecast lower bound as min_stock
            min_stock = float(forecast_data.get('yhat_lower', min_stock))
            # Use forecast upper bound as max_stock
            max_stock = float(forecast_data.get('yhat_upper', max_stock))
    
    return min_stock, max_stock