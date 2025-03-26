from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import pandas as pd
import numpy as np
from prophet import Prophet
from app import db
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.customer import Customer
from app.utils.security import success_response, error_response

forecast_bp = Blueprint("forecast", __name__)


@forecast_bp.route("/sales_forecast", methods=["GET"])
# @jwt_required()
def sales_forecast():
    """Endpoint untuk sales forecasting berdasarkan Prophet (weekly/monthly) tanpa nilai negatif"""
    try:
        # Ambil parameter filter dari request (jika ada)
        product_id = request.args.get("product_id")  # Optional
        customer_id = request.args.get("customer_id")  # Optional
        forecast_periods = int(
            request.args.get("periods", 12)
        )  # Default 12 periode ke depan
        aggregation = request.args.get("aggregation", "W")  # Default Weekly ('W')

        # Validasi aggregation (hanya 'W' atau 'M' yang diperbolehkan)
        if aggregation not in ["W", "M"]:
            return error_response(
                "Invalid aggregation type. Use 'W' for weekly or 'M' for monthly", 400
            )

        # Query data transaksi berdasarkan filter
        query = db.session.query(
            Transaction.invoice_date.label("ds"), Transaction.qty.label("y")
        ).filter(
            Transaction.category == "BAHAN BAKU MINILAB CHEMICAL"
        )  # Filter kategori

        if product_id:
            query = query.filter(Transaction.product_code == product_id)
        if customer_id:
            query = query.filter(Transaction.customer_code == customer_id)

        # Eksekusi query dan ubah ke DataFrame
        transactions = query.all()

        if not transactions:
            return error_response(
                "No sales data available for the selected filter", 404
            )

        # Konversi hasil query ke DataFrame
        df = pd.DataFrame(transactions, columns=["ds", "y"])
        df["ds"] = pd.to_datetime(df["ds"])

        # Pastikan semua nilai `y` positif sebelum agregasi
        df["y"] = df["y"].clip(lower=0)

        # Agregasi penjualan berdasarkan pilihan pengguna (weekly atau monthly)
        df = df.groupby(pd.Grouper(key="ds", freq=aggregation)).sum().reset_index()

        # **🔹 Terapkan log transformasi agar Prophet tidak memprediksi negatif**
        df["y"] = np.log1p(df["y"])  # log(1 + y) untuk menghindari log(0)

        # Inisialisasi model Prophet dengan boundary floor=0
        model = Prophet(
            interval_width=0.95,  # Confidence Interval 95%
            yearly_seasonality=False,
            weekly_seasonality=(aggregation == "W"),
            daily_seasonality=False,
        )
        model.add_seasonality(name="custom_weekly", period=7, fourier_order=3)
        model.fit(df)

        # Buat dataframe untuk prediksi dengan interval yang sama dengan agregasi
        future = model.make_future_dataframe(periods=forecast_periods, freq=aggregation)

        # Lakukan prediksi
        forecast = model.predict(future)

        # **🔹 Konversi kembali hasil prediksi dari log ke nilai asli**
        forecast["yhat"] = np.expm1(forecast["yhat"])  # exp(yhat) - 1
        forecast["yhat_lower"] = np.expm1(forecast["yhat_lower"])
        forecast["yhat_upper"] = np.expm1(forecast["yhat_upper"])

        # **🔹 Pastikan tidak ada nilai negatif dalam hasil akhir**
        forecast[["yhat", "yhat_lower", "yhat_upper"]] = forecast[
            ["yhat", "yhat_lower", "yhat_upper"]
        ].clip(lower=0)

        # Format hasil prediksi
        result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(
            forecast_periods
        )
        result_dict = result.to_dict(orient="records")

        return success_response(
            data=result_dict,
            message=f"Sales forecast ({aggregation}) generated successfully",
        )

    except Exception as e:
        return error_response(f"Error in forecasting: {str(e)}", 500)
