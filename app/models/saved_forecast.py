from app import db
from datetime import datetime, timezone


class SavedForecast(db.Model):
    __tablename__ = "saved_forecast"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(50), db.ForeignKey("product.product_id"), nullable=False)
    forecast_data = db.Column(db.Text, nullable=False)  # JSON stored as text
    periods = db.Column(db.Integer, default=6)  # Number of forecast periods (6 or 12 months)
    created_by = db.Column(db.String(50), nullable=True)  # ID of user who created forecast
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship to product
    product = db.relationship("Product", backref=db.backref("forecasts", lazy=True))

    def get_forecast_data(self):
        """Get forecast data as dictionary from JSON string"""
        import json
        return json.loads(self.forecast_data)

    def set_forecast_data(self, data):
        """Set forecast data from list/dict to JSON string"""
        import json
        self.forecast_data = json.dumps(data)

    def to_dict(self):
        """Convert object to dictionary"""
        return {
            "id": self.id,
            "product_id": self.product_id,
            "forecast_data": self.get_forecast_data(),
            "periods": self.periods,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }