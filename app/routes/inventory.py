from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from app import db
from app.utils.security import success_response, error_response
from sqlalchemy import or_
from sqlalchemy.sql import text
from app.models.product import Product
from app.models.product_stock import ProductStock

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/all", methods=["GET"])
@jwt_required()
def get_inventory():
    """
    Endpoint to retrieve comprehensive inventory data with stock information.
    """
    try:
        # Use SQLAlchemy ORM for more reliable data conversion
        query = db.session.query(Product, ProductStock).join(
            ProductStock, Product.product_id == ProductStock.product_id
        )

        # Execute the query
        results = query.all()

        # Manual conversion to ensure proper dictionary format
        inventory_list = []
        for product, stock in results:
            item = {
                # From Product model
                "id": product.id,
                "product_code": product.product_code,
                "product_id": product.product_id,
                "product_name": product.product_name,
                "standard_price": float(product.standard_price),  # Ensure numeric
                "retail_price": float(product.retail_price),
                "ppn": float(product.ppn),
                "category": product.category,
                "min_stock": float(product.min_stock),
                "max_stock": float(product.max_stock),
                "supplier_id": product.supplier_id,
                "supplier_name": product.supplier_name,
                # From ProductStock model
                "report_date": product.created_at.isoformat()
                if product.created_at
                else None,
                "location": stock.location,
                "qty": float(stock.qty),
                "unit": stock.unit,
            }
            inventory_list.append(item)

        # Calculate metrics
        metrics = {
            "total_items": len(inventory_list),
            "total_value": sum(
                item["standard_price"] * item["qty"] for item in inventory_list
            ),
            "low_stock_items": sum(
                1 for item in inventory_list if item["qty"] <= item["min_stock"]
            ),
            "critical_stock_items": sum(
                1 for item in inventory_list if item["qty"] <= (item["min_stock"] / 2)
            ),
        }

        return jsonify(
            {
                "success": True,
                "data": inventory_list,
                "metrics": metrics,
                "message": "Inventory retrieved successfully",
            }
        ), 200

    except Exception as e:
        # Log the full error for debugging
        current_app.logger.error(f"Inventory retrieval error: {str(e)}")

        return jsonify(
            {"success": False, "message": f"Error retrieving inventory: {str(e)}"}
        ), 500
