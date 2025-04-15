import json
from flask import Blueprint, current_app, request
# from flask.config import T
from flask_jwt_extended import get_jwt_identity, jwt_required
import pandas as pd
import numpy as np
from prophet import Prophet
from sqlalchemy import and_, extract, func
from app import db
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.forecast_parameter import ForecastParameter, TuningJob
from app.utils.security import success_response, error_response
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import calendar
from app.models.saved_forecast import SavedForecast
from app.models.product_stock import ProductStock

forecast_bp = Blueprint("forecast", __name__)

@forecast_bp.route("/categories", methods=["GET"])
@jwt_required()
def get_categories():
    """Endpoint untuk mendapatkan semua kategori produk yang tersedia"""
    try:
        # Get distinct categories from transactions
        categories = db.session.query(Transaction.category).distinct().all()
        
        # Extract category names and filter out None/empty values
        category_list = [cat[0] for cat in categories if cat[0]]
        category_list.sort()  # Sort for better UI display
        
        return success_response(
            data=category_list,
            message="Categories retrieved successfully"
        )
    except Exception as e:
        return error_response(f"Error retrieving categories: {str(e)}", 500)


@forecast_bp.route("/parameters", methods=["GET"])
@jwt_required()
def get_parameters():
    """Endpoint untuk mendapatkan semua parameter yang telah disimpan"""
    try:
        # Get all saved parameters
        params = ForecastParameter.query.all()
        params_list = [param.to_dict() for param in params]
        
        return success_response(
            data=params_list,
            message="Parameters retrieved successfully"
        )
    except Exception as e:
        return error_response(f"Error retrieving parameters: {str(e)}", 500)


@forecast_bp.route("/parameters/<int:param_id>", methods=["DELETE"])
@jwt_required()
def delete_parameter(param_id):
    """Endpoint untuk menghapus parameter yang disimpan"""
    try:
        param = ForecastParameter.query.get(param_id)
        if not param:
            return error_response("Parameter not found", 404)
        
        db.session.delete(param)
        db.session.commit()
        
        return success_response(
            message="Parameter deleted successfully"
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error deleting parameter: {str(e)}", 500)

@forecast_bp.route("/parameter_tuning", methods=["POST"])
@jwt_required()
def parameter_tuning():
    """Start an asynchronous parameter tuning job"""
    try:
        # Validate input
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)
        
        # Get required parameters
        category = data.get("category", "")
        if not category:
            return error_response("Category is required", 400)
            
        selected_parameters = data.get("selected_parameters", [])
        if not selected_parameters:
            return error_response("At least one parameter must be selected", 400)
            
        parameters = data.get("parameters", {})
        
        # Validate that each selected parameter has at least one value
        invalid_params = [p for p in selected_parameters if p not in parameters or not parameters.get(p)]
        if invalid_params:
            return error_response(f"Parameters with no values: {', '.join(invalid_params)}", 400)
        
        # Check if there's already a running job for this category
        existing_job = TuningJob.query.filter_by(
            category=category, 
            status="running"
        ).first()
        
        if existing_job:
            return error_response(
                f"A tuning job is already running for category '{category}'. "
                f"Job ID: {existing_job.id}, Started: {existing_job.created_at}",
                409  # Conflict
            )
        
        # Create a new job
        job = TuningJob(
            category=category,
            status="pending",
            progress=0
        )
        
        # Store the parameters configuration
        job.set_parameters({
            "selected_parameters": selected_parameters,
            "parameters": parameters
        })
        
        # Save to get an ID
        db.session.add(job)
        db.session.commit()
        
        # Start the background task
        from app.utils.tasks import start_parameter_tuning_background
        start_parameter_tuning_background(job.id)
        
        return success_response(
            data={
                "job_id": job.id,
                "status": job.status,
                "category": job.category,
                "message": "Parameter tuning job started"
            },
            message="Parameter tuning job has been queued. You can check the status using the job ID."
        )
            
    except Exception as e:
        current_app.logger.error(f"Error starting parameter tuning: {str(e)}")
        return error_response(f"Error starting parameter tuning: {str(e)}", 500)


@forecast_bp.route("/tuning_jobs", methods=["GET"])
@jwt_required()
def get_tuning_jobs():
    """Get all tuning jobs or filter by status"""
    try:
        status = request.args.get("status")
        category = request.args.get("category")
        
        # Build query with optional filters
        query = TuningJob.query
        
        if status:
            query = query.filter_by(status=status)
            
        if category:
            query = query.filter_by(category=category)
            
        # Order by latest first
        jobs = query.order_by(TuningJob.created_at.desc()).all()
        jobs_list = [job.to_dict() for job in jobs]
        
        return success_response(
            data=jobs_list,
            message="Jobs retrieved successfully"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving tuning jobs: {str(e)}")
        return error_response(f"Error retrieving tuning jobs: {str(e)}", 500)


@forecast_bp.route("/tuning_jobs/<int:job_id>", methods=["GET"])
@jwt_required()
def get_tuning_job(job_id):
    """Get a specific tuning job by ID"""
    try:
        job = TuningJob.query.get(job_id)
        
        if not job:
            return error_response(f"Job {job_id} not found", 404)
            
        return success_response(
            data=job.to_dict(),
            message="Job retrieved successfully"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving tuning job: {str(e)}")
        return error_response(f"Error retrieving tuning job: {str(e)}", 500)
    
@forecast_bp.route("/sales_forecast", methods=["GET"])
@jwt_required()
def sales_forecast():
    """Generate sales forecast for a specific product"""
    try:
        # Get query parameters
        product_id = request.args.get('product_id')
        periods = int(request.args.get('periods', 6))  # Default to 6 months
        
        # Validate periods - only allow 3 or 6 months
        if periods not in [3, 6]:
            return error_response("Periods must be either 3 or 6 months", 400)
        
        if not product_id:
            return error_response("Product ID is required", 400)
            
        # Check if product exists and get its category
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response(f"Product with ID {product_id} not found", 404)
        
        category = product.category
        
        # Get historical sales data for the product
        query = db.session.query(
            Transaction.invoice_date.label("ds"), 
            func.sum(Transaction.qty).label("y")
        ).filter(
            Transaction.product_id == product_id
        ).group_by(
            Transaction.invoice_date
        ).order_by(
            Transaction.invoice_date
        )
        
        transactions = query.all()
        
        if not transactions:
            return error_response("No historical sales data available for this product", 404)
            
        # Convert to DataFrame
        df = pd.DataFrame(transactions, columns=["ds", "y"])
        df["ds"] = pd.to_datetime(df["ds"])
        df["y"] = df["y"].astype(float)
        
        # Prepare monthly data with proper frequency
        freq = "MS"  # Monthly start frequency
        df_monthly = df.groupby(pd.Grouper(key='ds', freq=freq))['y'].sum().reset_index()
        
        # Ensure the date range is complete with all months
        all_dates = pd.date_range(start=df_monthly['ds'].min(), end=df_monthly['ds'].max(), freq=freq)
        df_complete = pd.DataFrame({'ds': all_dates})
        df_monthly = pd.merge(df_complete, df_monthly, on='ds', how='left').fillna(0)
        
        # Add month dummies as additional regressors for better monthly seasonality handling
        df_monthly['month'] = df_monthly['ds'].dt.month
        for m_val in range(1, 13):
            df_monthly[f'is_{m_val:02d}'] = (df_monthly['month'] == m_val).astype(int)
        df_monthly = df_monthly.drop(columns=['month'])
        
        # Check if we have saved parameters for this category
        params = None
        if category:
            params = ForecastParameter.query.filter_by(category=category).first()
        
        # Set up Prophet model
        if params:
            # Use saved parameters
            prophet_params = params.get_parameters()
            model = Prophet(**prophet_params)
            current_app.logger.info(f"Using custom parameters for category '{category}': {prophet_params}")
        else:
            # Use default parameters
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                seasonality_mode='multiplicative',
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10.0
            )
            current_app.logger.info(f"Using default parameters for product '{product_id}'")
            
        # Add Indonesia country holidays
        model.add_country_holidays(country_name='ID')
        
        # Add monthly dummy regressors
        for m_val in range(1, 13):
            model.add_regressor(f'is_{m_val:02d}')
        
        # Fit the model
        model.fit(df_monthly)
        
        # Create future dataframe for forecasting
        future = model.make_future_dataframe(periods=periods, freq='MS')
        
        # Add month dummies to future dataframe
        future['month'] = future['ds'].dt.month
        for m_val in range(1, 13):
            future[f'is_{m_val:02d}'] = (future['month'] == m_val).astype(int)
        future = future.drop(columns=['month'])
        
        # Generate forecast
        forecast = model.predict(future)
        
        # Format the forecast results
        # Include 2 months of historical data for continuity in the chart
        last_historical_date = df_monthly['ds'].max()
        
        # Get the 2 most recent historical months
        historical_data = forecast[forecast['ds'] <= last_historical_date].tail(2)[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].copy()
        historical_data['is_historical'] = True
        
        # Get future forecast periods
        future_data = forecast[forecast['ds'] > last_historical_date][['ds', 'yhat', 'yhat_lower', 'yhat_upper']].copy()
        future_data['is_historical'] = False
        
        # Combine historical and forecast data
        forecast_data = pd.concat([historical_data, future_data]).to_dict('records')
        
        # Ensure we only return the historical plus requested number of periods
        forecast_data = forecast_data[:periods + 2]
        
        # Convert dates to string format
        for item in forecast_data:
            item['ds'] = item['ds'].strftime('%Y-%m-%d')
            # Round values to integers since we're forecasting quantities
            item['yhat'] = max(0,round(float(item['yhat']), 2))
            item['yhat_lower'] = max(0, round(float(item['yhat_lower']), 2))  # Ensure non-negative
            item['yhat_upper'] = max(0,round(float(item['yhat_upper']), 2))
        
        return success_response(
            data=forecast_data,
            message="Forecast generated successfully"
        )
            
    except Exception as e:
        current_app.logger.error(f"Error generating forecast: {str(e)}")
        return error_response(f"Error generating forecast: {str(e)}", 500)

    
@forecast_bp.route("/save", methods=["POST"])
@jwt_required()
def save_forecast():
    """Endpoint to save forecasts as individual monthly records"""
    try:
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)
        
        product_id = data.get("product_id")
        forecast_data = data.get("forecast_data")
        current_user = get_jwt_identity()
        
        if not product_id or not forecast_data:
            return error_response("Missing required fields: product_id, forecast_data", 400)
        
        # Check if the product exists
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response(f"Product with ID {product_id} not found", 404)
        
        # Process each forecast month individually
        saved_count = 0
        updated_count = 0
        
        for forecast_item in forecast_data:
            # Skip historical items
            if forecast_item.get('type') != 'forecast':
                continue
                
            forecast_date = forecast_item.get('ds')
            if not forecast_date:
                continue
                
            # Convert to datetime if it's a string
            if isinstance(forecast_date, str):
                forecast_date = datetime.strptime(forecast_date, '%Y-%m-%d').date()
            
            # Check if forecast for this month already exists
            existing_forecast = SavedForecast.query.filter_by(
                product_id=product_id,
                forecast_date=forecast_date
            ).first()
            
            forecast_values = {
                'yhat': forecast_item.get('forecast'),
                'yhat_lower': forecast_item.get('lower'),
                'yhat_upper': forecast_item.get('upper')
            }
            
            if existing_forecast:
                # Update existing forecast
                existing_forecast.set_forecast_data(forecast_values)
                existing_forecast.updated_at = datetime.now(timezone.utc)
                updated_count += 1
            else:
                # Create new forecast
                new_forecast = SavedForecast(
                    product_id=product_id,
                    forecast_date=forecast_date,
                    forecast_data=json.dumps(forecast_values),
                    created_by=current_user
                )
                db.session.add(new_forecast)
                saved_count += 1
        
        db.session.commit()
        
        return success_response(
            data={
                'saved': saved_count,
                'updated': updated_count
            },
            message=f"Forecast saved successfully: {saved_count} new entries, {updated_count} updates"
        )
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving forecast: {str(e)}")
        return error_response(f"Error saving forecast: {str(e)}", 500)


@forecast_bp.route("/saved/<product_id>", methods=["GET"])
@jwt_required()
def get_saved_forecasts(product_id):
    """Endpoint to retrieve all saved forecasts for a product"""
    try:
        # Check if the product exists
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response(f"Product with ID {product_id} not found", 404)
        
        # Get the forecasts
        saved_forecasts = SavedForecast.query.filter_by(product_id=product_id).order_by(SavedForecast.forecast_date).all()
        
        # Format the response - ensure we return a proper array
        forecast_data = []
        for forecast in saved_forecasts:
            data = forecast.get_forecast_data()
            forecast_data.append({
                'ds': forecast.forecast_date.strftime('%Y-%m-%d'),
                'yhat': data.get('yhat'),
                'yhat_lower': data.get('yhat_lower'),
                'yhat_upper': data.get('yhat_upper'),
                'saved_at': forecast.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': forecast.updated_at.strftime('%Y-%m-%d %H:%M:%S') if forecast.updated_at else None,
                'saved_by': forecast.created_by
            })
        
        return success_response(
            data=forecast_data,  # This is now guaranteed to be an array
            message="Saved forecasts retrieved successfully"
        )
            
    except Exception as e:
        current_app.logger.error(f"Error retrieving saved forecasts: {str(e)}")
        return error_response(f"Error retrieving saved forecasts: {str(e)}", 500)
    
@forecast_bp.route("/goals", methods=["GET"])
@jwt_required()
def get_goals_data():
    """
    Endpoint to retrieve data comparing saved forecasts (targets) with actual sales
    for a specified month. If no month is specified, the current month is used.
    """
    try:
        # Get query parameters
        month_str = request.args.get('month')
        
        # Parse the month or use current month if not provided
        if month_str:
            try:
                year, month = map(int, month_str.split('-'))
                start_date = datetime(year, month, 1).date()
            except (ValueError, TypeError):
                return error_response("Invalid month format. Use YYYY-MM", 400)
        else:
            # Default to current month
            today = datetime.now()
            start_date = datetime(today.year, today.month, 1).date()
            
        # Calculate end date (last day of the month)
        _, last_day = calendar.monthrange(start_date.year, start_date.month)
        end_date = datetime(start_date.year, start_date.month, last_day).date()
        
        # Format month string for filtering saved forecasts
        month_str = start_date.strftime("%Y-%m")
        day_one_str = f"{month_str}-01"
        
        # Step 1: Get all products with saved forecasts for this month
        saved_forecasts_query = db.session.query(
            SavedForecast.product_id,
            Product.product_name,
            ProductStock.unit,  # Get unit from ProductStock, not Product
            Product.standard_price,
            SavedForecast.forecast_data
        ).join(
            Product, SavedForecast.product_id == Product.product_id
        ).join(
            ProductStock, ProductStock.product_id == Product.product_id,  # Join with ProductStock
            isouter=True  # Use left outer join in case some products don't have stock entries
        ).filter(
            func.date_format(SavedForecast.forecast_date, '%Y-%m') == month_str
        ).all()
        
        # If no saved forecasts found for this month, return empty result
        if not saved_forecasts_query:
            return success_response(
                data={
                    "month": month_str,
                    "month_name": start_date.strftime("%B %Y"),
                    "products": [],
                    "summary": {
                        "total_forecasted": 0,
                        "total_actual": 0,
                        "total_forecasted_revenue": 0,
                        "total_actual_revenue": 0,
                        "achievement_rate": 0,
                        "top_performers": [],
                        "under_performers": []
                    }
                },
                message="No saved forecasts found for this month"
            )
        
        # Process saved forecasts
        products_with_forecasts = []
        
        for product_id, product_name, unit, price, forecast_data in saved_forecasts_query:
            # Parse the forecast data
            forecast_values = json.loads(forecast_data)
            forecast_quantity = round(float(forecast_values.get('yhat', 0)))
            forecast_lower = round(float(forecast_values.get('yhat_lower', 0)))
            forecast_upper = round(float(forecast_values.get('yhat_upper', 0)))
            
            products_with_forecasts.append({
                "product_id": product_id,
                "product_name": product_name,
                "unit": unit or "Units",  # Default to "Units" if unit is None
                "price": float(price) if price is not None else 0,
                "forecast": forecast_quantity,
                "forecast_lower": forecast_lower,
                "forecast_upper": forecast_upper
            })
        
        # Step 2: Get actual sales for these products in the specified month
        product_ids = [p["product_id"] for p in products_with_forecasts]
        
        actual_sales_query = db.session.query(
            Transaction.product_id,
            func.sum(Transaction.qty).label('actual_qty'),
            func.sum(Transaction.total_amount).label('actual_amount')
        ).filter(
            Transaction.product_id.in_(product_ids),
            Transaction.invoice_date.between(start_date, end_date)
        ).group_by(
            Transaction.product_id
        ).all()
        
        # Create a lookup dictionary for actual sales
        actual_sales = {
            product_id: {
                'qty': int(qty) if qty is not None else 0,
                'amount': float(amount) if amount is not None else 0
            }
            for product_id, qty, amount in actual_sales_query
        }
        
        # Step 3: Combine forecast and actual data, calculate metrics
        products_comparison = []
        total_forecasted = 0
        total_actual = 0
        total_forecasted_revenue = 0
        total_actual_revenue = 0
        
        for product in products_with_forecasts:
            product_id = product["product_id"]
            forecast_qty = product["forecast"]
            price = product["price"]
            
            # Get actual sales from lookup, default to 0 if not found
            actual_qty = actual_sales.get(product_id, {}).get('qty', 0)
            actual_amount = actual_sales.get(product_id, {}).get('amount', 0)
            
            # Calculate forecast revenue (forecast quantity * price)
            forecast_revenue = forecast_qty * price
            
            # Calculate variance and achievement rate
            variance = actual_qty - forecast_qty
            achievement_rate = (actual_qty / forecast_qty * 100) if forecast_qty > 0 else 0
            
            # Determine performance status
            if achievement_rate >= 100:
                status = "exceeded"
            elif achievement_rate >= 95:
                status = "achieved"
            elif achievement_rate >= 80:
                status = "near"
            else:
                status = "below"
            
            # Add to totals
            total_forecasted += forecast_qty
            total_actual += actual_qty
            total_forecasted_revenue += forecast_revenue
            total_actual_revenue += actual_amount
            
            # Build product comparison data
            products_comparison.append({
                "product_id": product_id,
                "product_name": product["product_name"],
                "unit": product["unit"],
                "price": price,
                "forecast": forecast_qty,
                "forecast_lower": product["forecast_lower"],
                "forecast_upper": product["forecast_upper"],
                "actual": actual_qty,
                "variance": variance,
                "achievement_rate": achievement_rate,
                "status": status,
                "forecast_revenue": forecast_revenue,
                "actual_revenue": actual_amount,
                "revenue_variance": actual_amount - forecast_revenue
            })
        
        # Calculate overall achievement rate
        overall_achievement = (total_actual / total_forecasted * 100) if total_forecasted > 0 else 0
        
        # Sort products by achievement rate for top/under performers
        sorted_by_achievement = sorted(products_comparison, key=lambda x: x["achievement_rate"], reverse=True)
        
        # Get top performers (products with achievement >= 90%)
        top_performers = [p for p in sorted_by_achievement if p["achievement_rate"] >= 90][:3]
        
        # Get underperformers (products with achievement < 80%)
        under_performers = [p for p in sorted_by_achievement if p["achievement_rate"] < 80]
        under_performers = sorted(under_performers, key=lambda x: x["achievement_rate"])[:3]  # Sort by lowest achievement first
        
        # Step 4: Get historical data for trend analysis (last 6 months)
        historical_data = {}
        
        for product in products_with_forecasts:
            product_id = product["product_id"]
            # Get 6 months of historical data including current month
            historical_start = start_date - relativedelta(months=5)
            
            monthly_sales_query = db.session.query(
                func.date_format(Transaction.invoice_date, '%Y-%m').label('month'),
                func.sum(Transaction.qty).label('qty')
            ).filter(
                Transaction.product_id == product_id,
                Transaction.invoice_date >= historical_start,
                Transaction.invoice_date <= end_date
            ).group_by('month').order_by('month').all()
            
            # Convert query results to dict by month
            product_monthly_sales = {
                month: int(qty) if qty is not None else 0
                for month, qty in monthly_sales_query
            }
            
            # Get historical forecasts for this product if available
            historical_forecasts_query = db.session.query(
                func.date_format(SavedForecast.forecast_date, '%Y-%m').label('month'),
                SavedForecast.forecast_data
            ).filter(
                SavedForecast.product_id == product_id,
                SavedForecast.forecast_date >= historical_start,
                SavedForecast.forecast_date <= end_date
            ).all()
            
            # Convert forecast query results to dict by month
            product_monthly_forecasts = {}
            for month, forecast_data in historical_forecasts_query:
                forecast_values = json.loads(forecast_data)
                product_monthly_forecasts[month] = round(float(forecast_values.get('yhat', 0)))
            
            # Build month-by-month trend data
            trend_data = []
            current_date = historical_start
            while current_date <= start_date:
                month_str = current_date.strftime("%Y-%m")
                month_name = current_date.strftime("%b %Y")
                
                trend_data.append({
                    "month": month_str,
                    "month_name": month_name,
                    "forecast": product_monthly_forecasts.get(month_str, None),
                    "actual": product_monthly_sales.get(month_str, 0)
                })
                
                current_date = current_date + relativedelta(months=1)
            
            historical_data[product_id] = trend_data
        
        # Prepare the response data
        response_data = {
            "month": month_str,
            "month_name": start_date.strftime("%B %Y"),
            "products": products_comparison,
            "historical_data": historical_data,
            "summary": {
                "total_forecasted": total_forecasted,
                "total_actual": total_actual,
                "total_forecasted_revenue": total_forecasted_revenue,
                "total_actual_revenue": total_actual_revenue,
                "achievement_rate": overall_achievement,
                "top_performers": top_performers,
                "under_performers": under_performers
            }
        }
        
        return success_response(
            data=response_data,
            message="Goals data retrieved successfully"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving goals data: {str(e)}")
        return error_response(f"Error retrieving goals data: {str(e)}", 500)  
