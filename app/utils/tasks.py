import threading
import pandas as pd
import numpy as np
import json
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
from datetime import datetime, timezone
from joblib import Parallel, delayed
from app import db
from app.models.transaction import Transaction
from app.models.forecast_parameter import ForecastParameter, TuningJob
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

def run_parameter_tuning_task(job_id):
    """
    Background task to run parameter tuning with parallel processing
    """
    # Use app context for database operations
    from app import create_app
    app = create_app()
    
    with app.app_context():
        try:
            # Get job details
            job = TuningJob.query.get(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return
            
            # Update job status
            job.status = "running"
            job.progress = 5
            db.session.commit()
            
            logger.info(f"Starting parameter tuning job {job_id} for category: {job.category}")
            
            # Get parameters to test
            params_config = job.get_parameters()
            category = job.category
            selected_parameters = params_config.get("selected_parameters", [])
            parameter_values = params_config.get("parameters", {})
            
            # Get historical data for the category
            query = db.session.query(
                Transaction.invoice_date.label("ds"), 
                func.sum(Transaction.qty).label("y")
            ).filter(
                Transaction.category == category
            ).group_by(
                Transaction.invoice_date
            ).order_by(
                Transaction.invoice_date
            )
            
            # Get the data
            transactions = query.all()  
            
            if not transactions:
                raise ValueError("No sales data available for the selected category")
            
            # Update progress
            job.progress = 10
            db.session.commit()
            
            # Convert to DataFrame 
            df = pd.DataFrame(transactions, columns=["ds", "y"])
            df["ds"] = pd.to_datetime(df["ds"])
            
            # Handle decimal type
            df["y"] = df["y"].astype(float)
            
            # Ensure data is sorted by date
            df = df.sort_values("ds")
            
            # Ensure positive values
            # df["y"] = df["y"].clip(lower=0)
            
            # Prepare monthly data with proper frequency
            freq = "MS"  # Monthly start frequency
            df_monthly = df.groupby(pd.Grouper(key='ds', freq=freq))['y'].sum().reset_index()
            
            # Ensure the date range is complete with all months
            all_dates = pd.date_range(start=df_monthly['ds'].min(), end=df_monthly['ds'].max(), freq=freq)
            df_complete = pd.DataFrame({'ds': all_dates})
            df_monthly = pd.merge(df_complete, df_monthly, on='ds', how='left').fillna(0)

            # Add month dummies as additional regressors
            df_monthly['month'] = df_monthly['ds'].dt.month
            for m_val in range(1, 13):
                df_monthly[f'is_{m_val:02d}'] = (df_monthly['month'] == m_val).astype(int)
            df_monthly = df_monthly.drop(columns=['month'])

            # Update progress
            job.progress = 20
            db.session.commit()
            
            # Check if we have enough data
            if len(df_monthly) < 12:
                raise ValueError("Insufficient data for parameter tuning. Need at least 12 months of data.")
                
            # Optional: Apply log transformation to avoid negative forecasts
            df_monthly['y_orig'] = df_monthly['y']  # Save original values
            df_monthly['y'] = np.log1p(df_monthly['y'])  # log(1 + y) to avoid log(0)
            
            # Generate the grid of parameters to test
            param_grid = {}
            for param in selected_parameters:
                param_grid[param] = parameter_values.get(param, [])
            
            # Generate all combinations of parameters
            from itertools import product as itertools_product
            all_params = []
            param_names = list(param_grid.keys())
            param_values = [param_grid[name] for name in param_names]
            
            # Create all combinations 
            for items in itertools_product(*param_values):
                params = {}
                for i, name in enumerate(param_names):
                    params[name] = items[i]
                all_params.append(params)
            
            if not all_params:
                raise ValueError("No valid parameter combinations to test")
            
            # Update progress
            job.progress = 30
            db.session.commit()
            
            # Configure cross-validation
            # Use 60% of data for training by default, or at least 12 months
            data_months = len(df_monthly)
            training_months = max(int(data_months * 0.6), 12)
            initial_period = f"{training_months * 30} days"
            initial_period = "360 days"  # Set to 12 months for initial period

            # Define evaluation function for parallel processing
            def evaluate_params(params):
                try:
                    # Create model with current parameters
                    model = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False,**params)
                    # model = Prophet(**params)

                    # Add Indonesia country holidays if holidays_prior_scale is in parameters
                    if "holidays_prior_scale" in params:
                        model.add_country_holidays(country_name='ID')
                    
                    # Add monthly dummy regressors
                    for m_val in range(1, 13):
                        model.add_regressor(f'is_{m_val:02d}')
                    

                    # Fit model
                    model.fit(df_monthly)
                    
                    # Perform cross-validation with appropriate settings
                    df_cv = cross_validation(
                        model,
                        initial=initial_period,
                        period="30 days",  # Test 1 month at a time
                        horizon="30 days", # Forecast 1 month ahead
                        parallel="processes"
                    )
                    
                    # Convert predictions and actuals back from log space if we applied log transform
                    df_cv["yhat"] = np.expm1(df_cv["yhat"])
                    df_cv["y"] = np.expm1(df_cv["y"])
                    df_cv["yhat_lower"] = np.expm1(df_cv["yhat_lower"])
                    df_cv["yhat_upper"] = np.expm1(df_cv["yhat_upper"])
                    
                    # Calculate metrics - standard and with better handling of edge cases
                    df_p = performance_metrics(df_cv)
                    rmse = df_p["rmse"].mean()
                    rmse = df_p["rmse"].values[0]

                    # Calculate MAPE manually to handle edge cases better (avoid division by zero)
                    df_cv['ape'] = np.where(
                        df_cv['y'] > 0,  # Only where y > 0
                        np.abs((df_cv['y'] - df_cv['yhat']) / df_cv['y']),
                        np.nan  # Mark as NaN where y = 0
                    )
                    mape = np.nanmean(df_cv['ape']) * 100  # Convert to percentage
                    
                    return {
                        "parameters": params,
                        "mape": mape,
                        "rmse": rmse,
                        "success": True
                    }
                    
                except Exception as e:
                    logger.error(f"Error in parameter set: {str(e)}")
                    return {
                        "parameters": params,
                        "error": str(e),
                        "success": False
                    }
            
            # Run parallel parameter evaluation
            total_params = len(all_params)
            logger.info(f"Testing {total_params} parameter combinations in parallel")
            
            # Determine the number of jobs based on CPU cores, but limit it
            n_jobs = min(total_params, 4)  # Use at most 4 cores to avoid overloading
            
            results = Parallel(n_jobs=n_jobs)(
                delayed(evaluate_params)(params) for params in all_params
            )
            
            # Update progress
            job.progress = 90
            db.session.commit()
            
            # Process results
            successful_results = [r for r in results if r["success"]]
            
            if not successful_results:
                raise ValueError("No valid parameter combinations found during testing")
            
            # Find best parameters (lowest MAPE)
            best_result = min(successful_results, key=lambda x: x["mape"])
            best_params = best_result["parameters"]
            best_mape = best_result["mape"]
            best_rmse = best_result["rmse"]
            
            # Sort all results by MAPE for better presentation
            sorted_results = sorted(successful_results, key=lambda x: x["mape"])
            
            # Save the best parameters to ForecastParameter table
            try:
                # Check if parameters already exist for this category
                existing = ForecastParameter.query.filter_by(category=category).first()
                
                if existing:
                    # Update existing parameter
                    existing.set_parameters(best_params)
                    existing.mape = best_mape
                    existing.rmse = best_rmse
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new parameter
                    new_param = ForecastParameter(
                        category=category,
                        parameters=json.dumps(best_params),
                        mape=best_mape,
                        rmse=best_rmse
                    )
                    db.session.add(new_param)
                
                db.session.commit()
            except Exception as e:
                logger.error(f"Error saving parameters: {str(e)}")
                # Continue processing - we still want to return results even if saving failed
            
            # Update job with results
            job.status = "completed"
            job.progress = 100
            job.set_result({
                "best_parameters": best_params,
                "mape": best_mape,
                "rmse": best_rmse,
                "all_results": sorted_results,
                "total_combinations_tested": total_params,
                "successful_combinations": len(successful_results)
            })
            db.session.commit()
            
            logger.info(f"Completed parameter tuning job {job_id}")
            
        except Exception as e:
            logger.error(f"Job {job_id} failed: {str(e)}")
            
            # Update job status to failed
            job = TuningJob.query.get(job_id)
            if job:
                job.status = "failed"
                job.error = str(e)
                db.session.commit()


def start_parameter_tuning_background(job_id):
    """Start a background thread to run the parameter tuning job"""
    thread = threading.Thread(target=run_parameter_tuning_task, args=(job_id,))
    thread.daemon = True  # Allow the thread to be terminated when the main process exits
    thread.start()
    return thread


