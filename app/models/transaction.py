from app import db
from datetime import datetime, timezone


class Transaction(db.Model):
    __tablename__ = "transaction"

    id = db.Column(db.Integer, primary_key=True)  # Auto Increment ID
    invoice_id = db.Column(db.String(50), nullable=False)  # cinvrefno (ID Invoice)
    invoice_date = db.Column(db.Date, nullable=False)  # dinvdate (Date)
    customer_id = db.Column(
        db.String(50), db.ForeignKey("customer.customer_id"), nullable=False
    )  # cinvfkentcode (ID Customer)
    agent_name = db.Column(db.String(100), nullable=True)  # csamdesc (Nama Agent Sales)
    product_id = db.Column(
        db.String(50), db.ForeignKey("product.product_id"), nullable=False
    )  # civdcode (ID Barang)
    product_name = db.Column(db.String(255), nullable=False)  # cstkdesc (Nama Barang)
    qty = db.Column(db.Integer, nullable=False)  # mqty (Jumlah)
    unit = db.Column(db.String(50), nullable=True)  # civdunit (Satuan)
    total_amount = db.Column(db.Float, nullable=False)  # nivdamount (Total)
    order_sequence = db.Column(
        db.Integer, nullable=True
    )  # nivdorder (Urutan Barang Dalam 1 Nota)
    price_after_discount = db.Column(
        db.Float, nullable=False
    )  # nprice (Harga Barang Setelah Diskon)
    shipping_cost = db.Column(db.Float, nullable=True)  # ninvfreight (Ongkos Kirim)
    shipping_cost_per_item = db.Column(
        db.Float, nullable=True
    )  # npindah (Ongkos Kirim per Barang)
    invoice_note = db.Column(db.String(255), nullable=True)  # cinvremark (Catatan Nota)
    category = db.Column(db.String(100), nullable=True)  # cgrpdesc (Kategori Barang)
    discount_percentage = db.Column(
        db.Float, nullable=True
    )  # nivddisc1 (Diskon Harga %)
    price_before_discount = db.Column(
        db.Float, nullable=False
    )  # nivdprice (Harga Barang Sebelum Diskon)
    brand = db.Column(db.String(100), nullable=True)  # merek (Merek)
    cost_price = db.Column(db.Float, nullable=False)  # nstkbuy (Modal)
    total_cost = db.Column(db.Float, nullable=False)  # nivdpokok (Total Modal)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relasi ke Customer dan Product
    customer = db.relationship(
        "Customer", backref=db.backref("transactions", lazy=True)
    )
    product = db.relationship("Product", backref=db.backref("transactions", lazy=True))

    def to_dict(self):
        """Mengonversi objek Transaction ke dictionary"""
        return {
            "id": self.id,
            "invoice_id": self.invoice_id,
            "invoice_date": self.invoice_date.isoformat()
            if self.invoice_date
            else None,
            "customer_id": self.customer_id,
            "agent_name": self.agent_name,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "qty": self.qty,
            "unit": self.unit,
            "total_amount": self.total_amount,
            "order_sequence": self.order_sequence,
            "price_after_discount": self.price_after_discount,
            "shipping_cost": self.shipping_cost,
            "shipping_cost_per_item": self.shipping_cost_per_item,
            "invoice_note": self.invoice_note,
            "category": self.category,
            "discount_percentage": self.discount_percentage,
            "price_before_discount": self.price_before_discount,
            "brand": self.brand,
            "cost_price": self.cost_price,
            "total_cost": self.total_cost,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
