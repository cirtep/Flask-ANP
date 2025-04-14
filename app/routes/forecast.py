from flask import Blueprint, current_app, request
# from flask.config import T
from flask_jwt_extended import jwt_required
import pandas as pd
import numpy as np
from prophet import Prophet
from app import db
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.forecast_parameter import ForecastParameter, TuningJob
from app.utils.security import success_response, error_response
from datetime import datetime, timezone

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
    """Endpoint untuk sales forecasting berdasarkan Prophet (weekly/monthly) tanpa nilai negatif"""
    try:
        # Ambil parameter filter dari request (jika ada)
        product_id = request.args.get("product_id")  # Optional
        customer_id = request.args.get("customer_id")  # Optional
        forecast_periods = int(
            request.args.get("periods", 12)
        )  # Default 12 periode ke depan
        aggregation = request.args.get("aggregation", "W")  # Default Weekly ('W')

        # Validasi aggregation (hanya 'W' atau 'M' yang diperbolehkan)
        if aggregation not in ["W", "M"]:
            return error_response(
                "Invalid aggregation type. Use 'W' for weekly or 'M' for monthly", 400
            )

        # Query data transaksi berdasarkan filter
        query = db.session.query(
            Transaction.invoice_date.label("ds"), Transaction.qty.label("y")
        )

        if product_id:
            query = query.filter(Transaction.product_code == product_id)
        if customer_id:
            query = query.filter(Transaction.customer_code == customer_id)

        # Eksekusi query dan ubah ke DataFrame
        transactions = query.all()

        if not transactions:
            return error_response(
                "No sales data available for the selected filter", 404
            )

        # Konversi hasil query ke DataFrame
        df = pd.DataFrame(transactions, columns=["ds", "y"])
        df["ds"] = pd.to_datetime(df["ds"])
        
        # Convert to float to avoid decimal issues
        df["y"] = df["y"].astype(float)

        # Pastikan semua nilai `y` positif
        df["y"] = df["y"].clip(lower=0)

        # Tentukan freq berdasarkan aggregation
        freq = 'MS' if aggregation == 'M' else 'W-MON'
        
        # Ensure contiguous time series with proper frequency
        df_agg = df.groupby(pd.Grouper(key='ds', freq=freq))['y'].sum().reset_index()
        
        # Fill in any missing periods
        all_dates = pd.date_range(start=df_agg['ds'].min(), end=df_agg['ds'].max(), freq=freq)
        df_complete = pd.DataFrame({'ds': all_dates})
        df_agg = pd.merge(df_complete, df_agg, on='ds', how='left').fillna(0)
        
        # Add month dummies as additional regressors
        df_agg['month'] = df_agg['ds'].dt.month
        for m_val in range(1, 13):
            df_agg[f'is_{m_val:02d}'] = (df_agg['month'] == m_val).astype(int)

        # Terapkan log transformasi agar Prophet tidak memprediksi negatif
        df_agg['y_orig'] = df_agg['y']  # Save original values
        df_agg['y'] = np.log1p(df_agg['y'])  # log(1 + y) untuk menghindari log(0)

        # Check if we have saved parameters for the category
        category = None
        if product_id:
            product = Product.query.filter_by(product_code=product_id).first()
            if product:
                category = product.category

        # Try to load parameters for the specific category
        prophet_params = {}
        
        if category:
            # Try to get category-specific parameters
            category_params = ForecastParameter.query.filter_by(category=category).first()
            if category_params:
                prophet_params = category_params.get_parameters()
        
        # Use default params if nothing is saved
        if not prophet_params:
            prophet_params = {
                "seasonality_mode": "additive",
                "changepoint_prior_scale": 0.05,
                "seasonality_prior_scale": 10.0
            }

        # Create Prophet model with optimized parameters
        model = Prophet(
            interval_width=0.95,  # Confidence Interval 95%
            weekly_seasonality=(aggregation == "W"),
            daily_seasonality=False,
            **prophet_params  # Apply all optimized parameters
        )
        
        # Add country holidays if available
        if "holidays_prior_scale" in prophet_params:
            model.add_country_holidays(country_name='ID')
        
        # Add monthly dummy regressors
        for m_val in range(1, 13):
            model.add_regressor(f'is_{m_val:02d}')
            
        model.fit(df_agg)

        # Buat dataframe untuk prediksi
        future = model.make_future_dataframe(periods=forecast_periods, freq=freq)
        
        # Add monthly dummies to future dataframe
        future['month'] = future['ds'].dt.month
        for m_val in range(1, 13):
            future[f'is_{m_val:02d}'] = (future['month'] == m_val).astype(int)

        # Lakukan prediksi
        forecast = model.predict(future)

        # Konversi kembali hasil prediksi dari log ke nilai asli
        forecast["yhat"] = np.expm1(forecast["yhat"])  # exp(yhat) - 1
        forecast["yhat_lower"] = np.expm1(forecast["yhat_lower"])
        forecast["yhat_upper"] = np.expm1(forecast["yhat_upper"])

        # Pastikan tidak ada nilai negatif dalam hasil akhir
        forecast[["yhat", "yhat_lower", "yhat_upper"]] = forecast[
            ["yhat", "yhat_lower", "yhat_upper"]
        ].clip(lower=0)

        # Format hasil prediksi - ambil hanya bagian forecast ke depan
        result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(
            forecast_periods
        )
        result_dict = result.to_dict(orient="records")

        return success_response(
            data=result_dict,
            message=f"Sales forecast ({aggregation}) generated successfully",
        )

    except Exception as e:
        current_app.logger.error(f"Error in forecasting: {str(e)}")
        return error_response(f"Error in forecasting: {str(e)}", 500)