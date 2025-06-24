# app/models/forecast_parameters.py
from ..db import db
from datetime import datetime, timezone
import json
import pytz

class ForecastParameter(db.Model):
    __tablename__ = "forecast_parameter"
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)  # Category for specific parameters
    parameters = db.Column(db.Text, nullable=False)  # JSON stored as text
    mape = db.Column(db.Float, nullable=True)  # Mean Absolute Percentage Error
    rmse = db.Column(db.Float, nullable=True)  # Root Mean Square Error
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    def get_parameters(self):
        """Get parameters as dictionary from JSON string"""
        return json.loads(self.parameters)
    
    def set_parameters(self, params_dict):
        """Set parameters from dictionary to JSON string"""
        self.parameters = json.dumps(params_dict)
    
    def format_date_makassar(self, date_obj):
        """Format date in Makassar timezone (UTC+8)"""
        if not date_obj:
            return None
        
        # Define Makassar timezone
        makassar_tz = pytz.timezone('Asia/Makassar')
        
        # Convert UTC date to Makassar timezone
        if date_obj.tzinfo is not None:
            makassar_date = date_obj.astimezone(makassar_tz)
        else:
            # If no timezone info, assume it's UTC
            utc_date = pytz.utc.localize(date_obj)
            makassar_date = utc_date.astimezone(makassar_tz)
        
        # Format the date as a string
        return makassar_date.strftime('%Y-%m-%d %H:%M:%S')
    
    def to_dict(self):
        """Convert object to dictionary"""
        return {
            "id": self.id,
            "category": self.category,
            "parameters": self.get_parameters(),
            "mape": self.mape,
            "rmse": self.rmse,
            "created_at": self.format_date_makassar(self.created_at),
            "updated_at": self.format_date_makassar(self.updated_at),
        }


class TuningJob(db.Model):
    __tablename__ = "tuning_jobs"
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)  # Category being tuned
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, running, completed, failed
    progress = db.Column(db.Integer, default=0)  # Progress percentage (0-100)
    parameters = db.Column(db.Text, nullable=False)  # JSON of parameters being tested
    result = db.Column(db.Text, nullable=True)  # JSON of results (when completed)
    error = db.Column(db.Text, nullable=True)  # Error message (if failed)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    def get_parameters(self):
        """Get parameters as dictionary from JSON string"""
        return json.loads(self.parameters)
    
    def set_parameters(self, params_dict):
        """Set parameters from dictionary to JSON string"""
        self.parameters = json.dumps(params_dict)
    
    def get_result(self):
        """Get result as dictionary from JSON string"""
        if self.result:
            return json.loads(self.result)
        return None
    
    def set_result(self, result_dict):
        """Set result from dictionary to JSON string"""
        self.result = json.dumps(result_dict)
    
    def format_date_makassar(self, date_obj):
        """Format date in Makassar timezone (UTC+8)"""
        if not date_obj:
            return None
        
        # Define Makassar timezone
        makassar_tz = pytz.timezone('Asia/Makassar')
        
        # Convert UTC date to Makassar timezone
        if date_obj.tzinfo is not None:
            makassar_date = date_obj.astimezone(makassar_tz)
        else:
            # If no timezone info, assume it's UTC
            utc_date = pytz.utc.localize(date_obj)
            makassar_date = utc_date.astimezone(makassar_tz)
        
        # Format the date as a string
        return makassar_date.strftime('%Y-%m-%d %H:%M:%S')
    
    def to_dict(self):
        """Convert object to dictionary"""
        result = {
            "id": self.id,
            "category": self.category,
            "status": self.status,
            "progress": self.progress,
            "parameters": self.get_parameters(),
            "created_at": self.format_date_makassar(self.created_at),
            "updated_at": self.format_date_makassar(self.updated_at),
        }
        
        if self.status == "completed":
            result["result"] = self.get_result()
        elif self.status == "failed":
            result["error"] = self.error
            
        return result