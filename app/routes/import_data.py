# app/routes/import_data.py
from calendar import c
from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
import pandas as pd
from ..db import db
from app.utils.security import success_response, error_response
from app.models.customer import Customer
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.transaction import Transaction
import re

import_data_bp = Blueprint("import_data", __name__)

# Daftar ekstensi file yang diperbolehkan
ALLOWED_EXTENSIONS = {"xls", "xlsx", "csv"}


def allowed_file(filename):
    """Cek apakah file memiliki ekstensi yang diperbolehkan"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_file(file):
    """Membaca file menggunakan pandas"""
    if file.filename.lower().endswith(".csv"):
        return pd.read_csv(file)
    else:
        return pd.read_excel(file)


@import_data_bp.route("/customers", methods=["POST"])
@jwt_required()
def import_customers():
    """Endpoint untuk import data customer dari file Excel"""

    file = request.files.get("file")
    if not file:
        return error_response("No file provided", 400)
    if not allowed_file(file.filename):
        return error_response("File type not allowed.", 400)

    try:
        # Baca file Excel
        df = read_file(file)

        # Daftar kolom yang diharapkan dalam file Excel
        EXPECTED_COLUMNS = {
            "cextra": "extra",
            "jharga": "price_type",
            "centpk": "customer_code",
            "centdesc": "business_name",
            "centnpwp": "npwp",
            "centbill": "nik",
            "centcode": "customer_id",
            "ccitdesc": "city",
            "centadd1": "address_1",
            "centadd2": "address_2",
            "centadd3": "address_3",
            "centadd4": "address_4",
            "centadd5": "address_5",
            "centdescp": "owner_name",
            "centadd1p": "owner_address_1",
            "centadd2p": "owner_address_2",
            "centadd3p": "owner_address_3",
            "centadd4p": "owner_address_4",
            "centadd5p": "owner_address_5",
            "centagama": "religion",
            "centadds": "additional_address",
            "centadd1s": "additional_address_1",
            "centadd2s": "additional_address_2",
            "centadd3s": "additional_address_3",
            "centadd4s": "additional_address_4",
            "centadd5s": "additional_address_5",
        }

        # Cek apakah semua kolom yang diperlukan ada
        missing_columns = [
            col for col in EXPECTED_COLUMNS.keys() if col not in df.columns
        ]
        if missing_columns:
            return error_response(
                f"Missing required columns: {', '.join(missing_columns)}", 400
            )

        # Rename kolom agar sesuai dengan model
        df = df.rename(columns=EXPECTED_COLUMNS)

        # Konversi NaN menjadi None untuk seluruh DataFrame
        df = df.where(pd.notna(df), None)

        # Ubah NaN, string "nan", dan string kosong menjadi None
        for col in df.columns:
                    # Check if column contains float values (common for NaN)
                    if df[col].dtype == 'float64':
                        # Replace NaN with None in this column
                        df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)

        # Iterasi dan validasi data sebelum dimasukkan ke database
        for index, row in df.iterrows():
            if pd.isna(row["customer_code"]) or pd.isna(row["business_name"]):
                return error_response(
                    f"Row {index + 1}: Customer code and business name cannot be null",
                    400,
                )

            # Cek apakah customer sudah ada berdasarkan customer_code
            existing_customer = Customer.query.filter_by(
                customer_code=row["customer_code"]
            ).first()
            if existing_customer:
                # return error_response(
                #     f"Row {index + 1}: Duplicate customer_code '{row['customer_code']}'",
                #     400,
                # )
                continue  # Skip to next row

            customer_data = {}
            for col in EXPECTED_COLUMNS.values():
                value = row[col]
                # Double-check that we don't pass NaN to MySQL
                if isinstance(value, float) and pd.isna(value):
                    customer_data[col] = None
                else:
                    customer_data[col] = value

            # Buat instance Customer dengan data yang sudah dibersihkan
            new_customer = Customer(**customer_data)

            # Tambahkan ke sesi database
            db.session.add(new_customer)

            # # Buat instance Customer dengan dictionary comprehension
            # new_customer = Customer(
            #     **{col: row[col] for col in EXPECTED_COLUMNS.values()}
            # )

            # # Tambahkan ke sesi database
            # db.session.add(new_customer)

        # Commit transaksi database setelah semua data valid
        db.session.commit()
        return success_response(message="Customers imported successfully")

    except Exception as e:
        db.session.rollback()
        return error_response(f"Error importing data: {str(e)}", 500)


@import_data_bp.route("/products", methods=["POST"])
@jwt_required()
def import_products():
    """Endpoint untuk import data product dari file Excel"""
    file = request.files.get("file")
    if not file:
        return error_response("No file provided", 400)
    if not allowed_file(file.filename):
        return error_response(
            "File type not allowed.", 400
        )

    try:
        # Baca file Excel
        df = read_file(file)

        # Cek apakah semua kolom yang diperlukan ada
        EXPECTED_COLUMNS = {
            "cstkpk": "product_code",
            "cstkdesc": "product_name",
            "nstdprice": "standard_price",
            "nstdretail": "retail_price",
            "cstdcode": "product_id",
            "nstkppn": "ppn",
            "cgrpdesc": "category",
            "nstkmin": "min_stock",
            "nstkmax": "max_stock",
            "supp": "supplier_id",
            "namasupp": "supplier_name",
        }

        missing_columns = [
            col for col in EXPECTED_COLUMNS.keys() if col not in df.columns
        ]
        if missing_columns:
            return error_response(
                f"Missing required columns: {', '.join(missing_columns)}", 400
            )

        # Rename kolom agar sesuai dengan model
        df = df.rename(columns=EXPECTED_COLUMNS)

        # Konversi NaN menjadi None untuk seluruh DataFrame
        df = df.where(pd.notna(df), None)

        # Iterasi data sebelum dimasukkan ke database
        for index, row in df.iterrows():
            if not row["product_id"] or not row["product_name"]:
                return error_response(
                    f"Row {index + 1}: Product id and name cannot be null", 400
                )

            # Cek apakah produk sudah ada berdasarkan product_id
            if Product.query.filter_by(product_id=row["product_id"]).first():
                # return error_response(
                #     f"Row {index + 1}: Duplicate product_id '{row['product_id']}'",
                #     400,
                # )
                continue  # Skip to next row

            # Buat instance Product dengan dictionary comprehension
            new_product = Product(
                **{col: row[col] for col in EXPECTED_COLUMNS.values()}
            )

            # Tambahkan ke sesi database
            db.session.add(new_product)

        # Commit transaksi database setelah semua data valid
        db.session.commit()
        return success_response(message="Products imported successfully")

    except Exception as e:
        db.session.rollback()
        return error_response(f"Error importing data: {str(e)}", 500)


@import_data_bp.route("/product_stock", methods=["POST"])
@jwt_required()
def import_product_stock():
    """Endpoint untuk import stok produk dari file Excel"""
    file = request.files.get("file")
    if not file:
        return error_response("No file provided", 400)
    if not allowed_file(file.filename):
        return error_response(
            "File type not allowed.", 400
        )

    try:
        # Baca file Excel
        df = read_file(file)

        # Cek apakah semua kolom yang diperlukan ada
        EXPECTED_COLUMNS = {
            "judul": "report_date",
            "cstdcode": "product_id",
            "cwhsdesc": "location",
            "qty2": "qty",
            "cunidesc": "unit",
            "harga2": "price",
        }

        missing_columns = [
            col for col in EXPECTED_COLUMNS.keys() if col not in df.columns
        ]
        if missing_columns:
            return error_response(
                f"Missing required columns: {', '.join(missing_columns)}", 400
            )

        # Rename kolom agar sesuai dengan model
        df = df.rename(columns=EXPECTED_COLUMNS)

        # Konversi NaN menjadi None untuk seluruh DataFrame
        df = df.where(pd.notna(df), None)

        # Ekstrak tanggal dari kolom `report_date` dengan regex
        def extract_date(text):
            match = re.search(r"\d{2}-\d{2}-\d{4}", str(text))
            if match:
                return pd.to_datetime(match.group(), format="%d-%m-%Y").date()
            return None  # Jika tidak ditemukan, set None

        df["report_date"] = df["report_date"].apply(extract_date)

        # Dictionary to keep track of which products we've updated
        updated_products = {}
        new_products = 0
        updated_count = 0
        skipped_count = 0

        # Iterasi data sebelum dimasukkan ke database
        for index, row in df.iterrows():
            if not row["product_id"] or not row["qty"]:
                return error_response(
                    f"Row {index + 1}: Product ID and quantity cannot be null", 400
                )

            # Cek apakah produk ada di database sebelum menambahkan stoknya
            product = Product.query.filter_by(product_id=row["product_id"]).first()
            if not product:
                # return error_response(
                #     f"Row {index + 1}: Product ID '{row['product_id']}' not found", 400
                # )
                skipped_count += 1
                continue  # Skip to next row

            # Check if this product stock already exists
            existing_stock = ProductStock.query.filter_by(
                product_id=row["product_id"]
            ).first()

            if existing_stock:
                # Product stock record exists, check the report date
                if row["report_date"] and existing_stock.report_date and row["report_date"] > existing_stock.report_date:
                    # Update the existing record as this report is newer
                    existing_stock.report_date = row["report_date"]
                    existing_stock.location = row["location"]
                    existing_stock.qty = row["qty"]
                    existing_stock.unit = row["unit"]
                    existing_stock.price = row["price"]
                    existing_stock.updated_at = datetime.now(timezone.utc)
                    
                    updated_products[row["product_id"]] = True
                    updated_count += 1
                else:
                    # Skip this record as the existing one is newer or same date
                    skipped_count += 1
                    continue
            else:
                # Create a new stock record
                new_stock = ProductStock(
                    product_id=row["product_id"],
                    report_date=row["report_date"],
                    location=row["location"],
                    qty=row["qty"],
                    unit=row["unit"],
                    price=row["price"]
                )
                db.session.add(new_stock)
                new_products += 1

        # Commit transaksi database setelah semua data valid
        db.session.commit()
        return success_response(
            message=f"Product stock imported successfully. New records: {new_products}, Updated records: {updated_count}, Skipped records: {skipped_count}"
        )

    except Exception as e:
        db.session.rollback()
        return error_response(f"Error importing data: {str(e)}", 500)


@import_data_bp.route("/transactions", methods=["POST"])
@jwt_required()
def import_transactions():
    """Endpoint untuk import transaksi dari file Excel"""
    file = request.files.get("file")
    if not file:
        return error_response("No file provided", 400)
    if not allowed_file(file.filename):
        return error_response(
            "File type not allowed.", 400
        )

    try:
        # Baca file Excel
        df = read_file(file)

        # Cek apakah semua kolom yang diperlukan ada
        EXPECTED_COLUMNS = {
            "cinvrefno": "invoice_id",
            "dinvdate": "invoice_date",
            "cinvfkentcode": "customer_id",
            "csamdesc": "agent_name",
            "civdcode": "product_id",
            "cstkdesc": "product_name",
            "mqty": "qty",
            "civdunit": "unit",
            "nivdamount": "total_amount",
            "nivdorder": "order_sequence",
            "nprice": "price_after_discount",
            "ninvfreight": "shipping_cost",
            "npindah": "shipping_cost_per_item",
            "cinvremark": "invoice_note",
            "cgrpdesc": "category",
            "nivddisc1": "discount_percentage",
            "nivdprice": "price_before_discount",
            "merek": "brand",
            "nstkbuy": "cost_price",
            "nivdpokok": "total_cost",
        }

        missing_columns = [
            col for col in EXPECTED_COLUMNS.keys() if col not in df.columns
        ]
        if missing_columns:
            return error_response(
                f"Missing required columns: {', '.join(missing_columns)}", 400
            )

        # Rename kolom agar sesuai dengan model
        df = df.rename(columns=EXPECTED_COLUMNS)

        # Konversi NaN menjadi None untuk seluruh DataFrame
        df = df.where(pd.notna(df), None)

        # Ubah format tanggal pada `invoice_date`
        df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce").dt.date

        # Iterasi data sebelum dimasukkan ke database
        for index, row in df.iterrows():
            if not row["invoice_id"] or not row["customer_id"] or not row["product_id"]:
                return error_response(
                    f"Row {index + 1}: Invoice id, customer id, and product id cannot be null",
                    400,
                )

            # Cek apakah transaksi sudah ada berdasarkan invoice_id (hindari duplikasi)
            if Transaction.query.filter_by(invoice_id=row["invoice_id"]).first():
                # return error_response(
                #     f"Row {index + 1}: Duplicate invoice_id '{row['invoice_id']}'",
                #     400,
                # )
                continue  # Skip to next row

            existing = Transaction.query.filter_by(
                invoice_id=row["invoice_id"],
                product_id=row["product_id"],
                order_sequence=row.get("order_sequence"),
            ).first()

            if existing:
                # return error_response(
                #     f"Row {index + 1}: Duplicate product '{row['product_id']}' with sequence '{row.get('order_sequence')}' in invoice '{row['invoice_id']}'",
                #     400,
                # )
                continue

            # Cek apakah customer_id sudah ada di database
            customer = Customer.query.filter_by(customer_id=row["customer_id"]).first()
            if not customer:
                # return error_response(
                #     f"Row {index + 1}: Customer id '{row['customer_id']}' not found",
                #     400,
                # )
                # continue to next row
                continue

            # Cek apakah product_id sudah ada di database
            product = Product.query.filter_by(product_id=row["product_id"]).first()
            if not product:
                # return error_response(
                #     f"Row {index + 1}: Product id '{row['product_id']}' not found",
                #     400,
                # )
                # continue to next row
                continue

            # Buat instance Transaction dengan dictionary comprehension
            new_transaction = Transaction(
                **{col: row[col] for col in EXPECTED_COLUMNS.values()}
            )

            # Tambahkan ke sesi database
            db.session.add(new_transaction)

        # Commit transaksi database setelah semua data valid
        db.session.commit()
        return success_response(message="Transactions imported successfully")

    except Exception as e:
        db.session.rollback()
        return error_response(f"Error importing data: {str(e)}", 500)
