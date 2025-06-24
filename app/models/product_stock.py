from ..db import db
from datetime import datetime, timezone


class ProductStock(db.Model):
    __tablename__ = "product_stock"

    id = db.Column(db.Integer, primary_key=True)  # Auto Increment ID
    product_id = db.Column(
        db.String(50), db.ForeignKey("product.product_id"), nullable=False
    )  # cstdcode (id barang)
    report_date = db.Column(db.Date, nullable=False)  # judul (Per Tgl. XX-XX-XXXX)
    purchase_date = db.Column(db.Date, nullable=True)  # tglbeli (tgl beli)
    location = db.Column(db.String(100), nullable=True)  # cwhsdesc (lokasi)
    qty = db.Column(db.Integer, nullable=False)  # qty2 (qty)
    unit = db.Column(db.String(50), nullable=True)  # cunidesc (satuan)
    price = db.Column(db.Float, nullable=False)  # harga2 (harga2)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relasi ke Product
    product = db.relationship("Product", backref=db.backref("product_stock", lazy=True))

    def to_dict(self):
        """Mengonversi objek Stock ke dictionary"""
        return {
            "id": self.id,
            "product_id": self.product_id,
            "report_date": self.report_date.isoformat() if self.report_date else None,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "location": self.location,
            "qty": self.qty,
            "unit": self.unit,
            "price": self.price,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
