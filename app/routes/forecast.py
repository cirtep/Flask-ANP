import json
from flask import Blueprint, current_app, request
# from flask.config import T
from flask_jwt_extended import get_jwt_identity, jwt_required
import pandas as pd
import numpy as np
from prophet import Prophet
from sqlalchemy import func
from app import db
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.forecast_parameter import ForecastParameter, TuningJob
from app.utils.security import success_response, error_response
from datetime import datetime, timezone
from app.models.saved_forecast import SavedForecast

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
            item['yhat'] = round(float(item['yhat']), 2)
            item['yhat_lower'] = max(0, round(float(item['yhat_lower']), 2))  # Ensure non-negative
            item['yhat_upper'] = round(float(item['yhat_upper']), 2)
        
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
            if forecast_item.get('is_historical', False):
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
                'yhat': forecast_item.get('yhat'),
                'yhat_lower': forecast_item.get('yhat_lower'),
                'yhat_upper': forecast_item.get('yhat_upper')
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
        
        # Format the response
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
            data=forecast_data,
            message="Saved forecasts retrieved successfully"
        )
            
    except Exception as e:
        current_app.logger.error(f"Error retrieving saved forecasts: {str(e)}")
        return error_response(f"Error retrieving saved forecasts: {str(e)}", 500)