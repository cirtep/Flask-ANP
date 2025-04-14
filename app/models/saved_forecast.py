from app import db
from datetime import datetime, timezone
import json

class SavedForecast(db.Model):
    __tablename__ = "saved_forecast"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(50), db.ForeignKey("product.product_id"), nullable=False)
    forecast_date = db.Column(db.Date, nullable=False)  # Date of the forecast point
    forecast_data = db.Column(db.Text, nullable=False)  # JSON stored as text (contains yhat, yhat_lower, yhat_upper)
    created_by = db.Column(db.String(50), nullable=True)  # ID of user who created forecast
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship to product
    product = db.relationship("Product", backref=db.backref("forecasts", lazy=True))
    
    # Composite unique constraint to ensure one forecast per product per date
    __table_args__ = (
        db.UniqueConstraint('product_id', 'forecast_date', name='uix_forecast_product_date'),
    )

    def get_forecast_data(self):
        """Get forecast data as dictionary from JSON string"""
        return json.loads(self.forecast_data)

    def set_forecast_data(self, data):
        """Set forecast data from dict to JSON string"""
        self.forecast_data = json.dumps(data)

    def to_dict(self):
        """Convert object to dictionary"""
        return {
            "id": self.id,
            "product_id": self.product_id,
            "forecast_date": self.forecast_date.strftime('%Y-%m-%d') if self.forecast_date else None,
            "forecast_data": self.get_forecast_data(),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }