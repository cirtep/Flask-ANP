from app import db
from datetime import datetime, timezone


class Customer(db.Model):
    __tablename__ = "customer"

    id = db.Column(db.Integer, primary_key=True)  # Auto Increment ID
    customer_code = db.Column(db.String(50), unique=True, nullable=False)  # centpk
    customer_id = db.Column(db.String(50), unique=True, nullable=False)  # centcode
    business_name = db.Column(db.String(255), nullable=False)  # centdesc
    extra = db.Column(db.String(50), nullable=True)  # cextra
    price_type = db.Column(db.String(50), nullable=True)  # jharga
    npwp = db.Column(db.String(20), nullable=True)  # centnpwp
    nik = db.Column(db.String(20), nullable=True)  # centbill
    city = db.Column(db.String(100), nullable=True)  # ccitdesc
    address_1 = db.Column(db.String(255), nullable=True)  # centadd1
    address_2 = db.Column(db.String(255), nullable=True)  # centadd2
    address_3 = db.Column(db.String(255), nullable=True)  # centadd3
    address_4 = db.Column(db.String(255), nullable=True)  # centadd4
    address_5 = db.Column(db.String(255), nullable=True)  # centadd5
    owner_name = db.Column(db.String(255), nullable=True)  # centdescp
    owner_address_1 = db.Column(db.String(255), nullable=True)  # centadd1p
    owner_address_2 = db.Column(db.String(255), nullable=True)  # centadd2p
    owner_address_3 = db.Column(db.String(255), nullable=True)  # centadd3p
    owner_address_4 = db.Column(db.String(255), nullable=True)  # centadd4p
    owner_address_5 = db.Column(db.String(255), nullable=True)  # centadd5p
    religion = db.Column(db.String(50), nullable=True)  # centagama
    additional_address = db.Column(db.String(255), nullable=True)  # centadds
    additional_address_1 = db.Column(db.String(255), nullable=True)  # centadd1s
    additional_address_2 = db.Column(db.String(255), nullable=True)  # centadd2s
    additional_address_3 = db.Column(db.String(255), nullable=True)  # centadd3s
    additional_address_4 = db.Column(db.String(255), nullable=True)  # centadd4s
    additional_address_5 = db.Column(db.String(255), nullable=True)  # centadd5s
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        """Mengonversi objek Customer ke dictionary"""
        return {
            "id": self.id,
            "customer_code": self.customer_code,
            "customer_id": self.customer_id,
            "business_name": self.business_name,
            "npwp": self.npwp,
            "nik": self.nik,
            "extra": self.extra,
            "price_type": self.price_type,
            "city": self.city,
            "address_1": self.address_1,
            "address_2": self.address_2,
            "address_3": self.address_3,
            "address_4": self.address_4,
            "address_5": self.address_5,
            "owner_name": self.owner_name,
            "owner_address_1": self.owner_address_1,
            "owner_address_2": self.owner_address_2,
            "owner_address_3": self.owner_address_3,
            "owner_address_4": self.owner_address_4,
            "owner_address_5": self.owner_address_5,
            "religion": self.religion,
            "additional_address": self.additional_address,
            "additional_address_1": self.additional_address_1,
            "additional_address_2": self.additional_address_2,
            "additional_address_3": self.additional_address_3,
            "additional_address_4": self.additional_address_4,
            "additional_address_5": self.additional_address_5,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
