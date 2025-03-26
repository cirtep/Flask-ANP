# Import models to make them available for db.create_all()
from .user import User
from .customer import Customer
from .product import Product
from .product_stock import ProductStock
from .transaction import Transaction
