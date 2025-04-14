import json
from flask import Blueprint, current_app, request
# from flask.config import T
from flask_jwt_extended import get_jwt_identity, jwt_required
import pandas as pd
import numpy as np
from prophet import Prophet
from app import db
from app.models.product_stock import ProductStock
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
    

@forecast_bp.route("/save", methods=["POST"])
@jwt_required()
def save_forecast():
    """Endpoint to save a forecast for future reference"""
    try:
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)
        
        product_id = data.get("product_id")
        forecast_data = data.get("forecast_data")
        periods = data.get("periods", 6)
        
        if not product_id or not forecast_data:
            return error_response("Missing required fields: product_id, forecast_data", 400)
        
        # Check if the product exists
        product = Product.query.filter_by(product_id=product_id).first()
        if not product:
            return error_response(f"Product with ID {product_id} not found", 404)
        
        
        existing_forecast = SavedForecast.query.filter_by(product_id=product_id).first()
        
        if existing_forecast:
            # Update existing forecast
            existing_forecast.forecast_data = json.dumps(forecast_data)
            existing_forecast.periods = periods
            existing_forecast.updated_at = datetime.now(timezone.utc)
        else:
            # Create new forecast
            new_forecast = SavedForecast(
                product_id=product_id,
                forecast_data=json.dumps(forecast_data),
                periods=periods,
                created_by=get_jwt_identity()
            )
            db.session.add(new_forecast)
        
        db.session.commit()
        
        return success_response(
            message="Forecast saved successfully"
        )
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving forecast: {str(e)}")
        return error_response(f"Error saving forecast: {str(e)}", 500)
