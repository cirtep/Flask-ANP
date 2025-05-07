from app import db
from datetime import datetime, timezone


class Product(db.Model):
    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)  # Auto Increment ID
    product_code = db.Column(
        db.String(50), unique=True, nullable=False
    )  # cstkpk (kode barang)
    product_id = db.Column(
        db.String(50), unique=True, nullable=False
    )  # cstdcode (id barang)
    product_name = db.Column(db.String(255), nullable=False)  # cstkdesc (nama barang)
    standard_price = db.Column(db.Float, nullable=False)  # nstdprice (harga)
    retail_price = db.Column(db.Float, nullable=False)  # nstdretail (harga retail)
    ppn = db.Column(db.Integer, nullable=True)  # nstkppn (jenis ppn)
    category = db.Column(db.String(100), nullable=True)  # cgrpdesc (kategori barang)
    min_stock = db.Column(db.Integer, nullable=True, default=0)  # nstkmin (min stok)
    max_stock = db.Column(db.Integer, nullable=True, default=0)  # nstkmax (stok max)
    supplier_id = db.Column(db.String(50), nullable=True)  # supp (id supplier)
    supplier_name = db.Column(db.String(255), nullable=True)  # namasupp (nama supplier)
    use_forecast = db.Column(db.Boolean, nullable=False, default=False)  # Default to false for existing records
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        """Mengonversi objek Product ke dictionary"""
        return {
            "id": self.id,
            "product_code": self.product_code,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "standard_price": self.standard_price,
            "retail_price": self.retail_price,
            "ppn": self.ppn,
            "category": self.category,
            "min_stock": self.min_stock,
            "max_stock": self.max_stock,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "use_forecast": self.use_forecast,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
