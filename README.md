# Flask-ANP Backend

This repository contains the **Flask**-based backend for **CV. Aneka Niaga Pratama (ANP)**, providing RESTful APIs for user management, customer & product data import/export, transactions, inventory, and sales forecasting.

---

## Table of Contents

1. [Features](#features)  
2. [Tech Stack](#tech-stack)  
3. [Prerequisites](#prerequisites)  
4. [Installation](#installation)  
5. [Configuration](#configuration)  
6. [Database Models](#database-models)  
7. [API Endpoints](#api-endpoints)  
   - [Authentication](#authentication)  
   - [User Management](#user-management)  
   - [Customer](#customer)  
   - [Product](#product)  
   - [Inventory](#inventory)  
   - [Transactions](#transactions)  
   - [Import/Export](#importexport)  
   - [Sales Forecasting](#sales-forecasting)  
8. [Running Tests](#running-tests)  
9. [License](#license)  

---

## Features

- **JWT-based Authentication** (login, token generation)  
- **User Management** (create, read, update, deactivate)  
- **Customer CRUD & Export**  
- **Product CRUD & Export**  
- **Inventory (Stock) Management**  
- **Transaction Recording & Reporting**  
- **Bulk Import (Excel/CSV)** for Customers, Products, Inventory, Transactions  
- **Sales Forecasting** (monthly/weekly) using **Prophet** with parameter tuning support  
- **Country-specific Holidays** (Indonesia) integrated into forecasting  

---

## Tech Stack

- **Python 3.8+**  
- **Flask**  
- **Flask-JWT-Extended** (JWT auth)  
- **Flask-SQLAlchemy** (ORM)  
- **Flask-Migrate** (database migrations)  
- **Pandas & openpyxl** (Excel import/export)  
- **Prophet** (time series forecasting)  
- **MySQL / MariaDB**  
- **Docker (optional)**  

---

## Prerequisites

- Python 3.8 or higher  
- MySQL or MariaDB server running  
- Virtualenv (recommended)  
- Optional: Docker & Docker Compose  

---

## Installation

1. **Clone the repository**  
   ```bash
   git clone https://github.com/<your-username>/Flask-ANP.git
   cd Flask-ANP
   ```

2. **Create & activate a virtual environment**  
   ```bash
   python3 -m venv venv
   source venv/bin/activate         # macOS/Linux
   venv\Scripts\activate            # Windows
   ```

3. **Install Python dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

4. **Database setup**  
   - Ensure MySQL is running, and create a database, e.g.:  
     ```sql
     CREATE DATABASE aneka_niaga_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
     ```
   - (Optional) Create a MySQL user and grant privileges:
     ```sql
     CREATE USER 'anp_user'@'localhost' IDENTIFIED BY 'your_password';
     GRANT ALL PRIVILEGES ON aneka_niaga_db.* TO 'anp_user'@'localhost';
     FLUSH PRIVILEGES;
     ```

5. **Initialize database & run migrations**  
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

---

## Configuration

Create a file named `.env` in the project root (or set environment variables directly). Sample `.env`:
```text
# Flask settings
FLASK_ENV=development
FLASK_APP=run.py
SECRET_KEY=your_flask_secret_key

# JWT settings
JWT_SECRET_KEY=your_jwt_secret_key
JWT_ACCESS_TOKEN_EXPIRES=28800   # 8 hours in seconds

# Database settings
DATABASE_URL=mysql+pymysql://anp_user:your_password@localhost/aneka_niaga_db

# Optional: Prophet parameters per category (if using dynamic tuning)
# e.g. category: 'Electronics'
PROPHET_CHANGPOINT_PRIOR_SCALE=0.05
PROPHET_SEASONALITY_PRIOR_SCALE=10
PROPHET_HOLIDAYS_PRIOR_SCALE=10
```

- **`FLASK_ENV`**: `development` or `production`  
- **`SECRET_KEY`**: Flask application secret  
- **`JWT_SECRET_KEY`**: JWT signing key  
- **`DATABASE_URL`**: SQLAlchemy connection string for MySQL  

---

## Database Models

- **User**  
  - `id`, `username`, `password_hash`, `full_name`, `role`, `is_active`, `last_login`, `created_at`, `updated_at`  

- **Customer**  
  - `id`, `extra`, `price_type`, `customer_code`, `business_name`, `tax_id`, `national_id`, `city`, `address_1`…`address_5`, `owner_name`, `owner_address_1`…`owner_address_5`, `religion`, `additional_address_1`…`additional_address_5`, `created_at`, `updated_at`  

- **Product**  
  - `id`, `product_code`, `product_name`, `product_id`, `category`, `standard_price`, `retail_price`, `tax_type`, `min_stock`, `max_stock`, `supplier_id`, `supplier_name`, `use_forecast` (boolean), `created_at`, `updated_at`  

- **ProductStock**  
  - `id`, `product_id (FK)`, `report_date`, `location`, `qty`, `unit`, `price`, `created_at`, `updated_at`  

- **Transaction**  
  - `id`, `customer_id (FK)`, `product_id (FK)`, `invoice_code`, `invoice_date`, `agent_name`, `quantity`, `unit`, `total_amount`, `order_sequence`, `price_after_discount`, `price_before_discount`, `discount_percentage`, `shipping_cost`, `shipping_cost_per_item`, `invoice_note`, `category`, `brand`, `cost_price`, `total_cost`, `created_at`, `updated_at`  

- **ForecastParameter** (optional)  
  - Stores per-category Prophet hyperparameters: `id`, `category`, `changepoint_prior_scale`, `seasonality_prior_scale`, `holidays_prior_scale`, `seasonality_mode`, `created_at`, `updated_at`  

---

## API Endpoints

### 🔐 Authentication

- **POST** `/api/auth/login`  
  - Body: `{ "username": "<username>", "password": "<password>" }`  
  - Response: `{ "success": true, "data": { user: {...}, access_token: "..." } }`  

### 👤 User Management

> Requires superuser/admin role

- **GET** `/api/users`  
  - List all users  
- **GET** `/api/users/<id>`  
  - Get user by ID  
- **POST** `/api/users`  
  - Create new user; Body: `{ "username", "password", "full_name", "role" }`  
- **PUT** `/api/users/<id>`  
  - Update user (full_name, role, is_active)  
- **DELETE** `/api/users/<id>`  
  - Deactivate user (set `is_active = False`)  

### 🤝 Customer

- **GET** `/api/customers?city=<city>`  
  - List all customers (optional filter: city)  
- **GET** `/api/customers/<customer_id>`  
  - Get a single customer  
- **POST** `/api/customers`  
  - Create new customer; Body: all required fields  
- **PUT** `/api/customers/<customer_id>`  
  - Update customer  
- **DELETE** `/api/customers/<customer_id>`  
  - Deactivate customer (set `is_active = False`)  
- **GET** `/api/customers/<customer_id>/sales?months=<n>`  
  - Get customer’s sales summary last _n_ months (default 6)  

### 📦 Product

- **GET** `/api/products?category=<category>`  
  - List products (optional filter: category)  
- **GET** `/api/products/<product_code>`  
  - Get single product details  
- **POST** `/api/products`  
  - Create new product  
- **PUT** `/api/products/<product_code>`  
  - Update product  
- **DELETE** `/api/products/<product_code>`  
  - Deactivate product  
- **GET** `/api/products/<product_code>/stock`  
  - Get product’s current stock records  

### 📊 Inventory (ProductStock)

- **GET** `/api/inventory?category=<category>`  
  - List inventory stock (join Product & ProductStock)  
- **GET** `/api/inventory/<stock_id>`  
  - Get single stock record  
- **POST** `/api/inventory`  
  - Create stock record (body: `product_id`, `report_date`, `location`, `qty`, `unit`, `price`)  
- **PUT** `/api/inventory/<stock_id>`  
  - Update stock record  
- **DELETE** `/api/inventory/<stock_id>`  
  - Delete stock record  

### 💳 Transactions

- **GET** `/api/transactions?product_id=<product_code>&customer_id=<customer_id>&from=<YYYY-MM-DD>&to=<YYYY-MM-DD>`  
  - List transactions (filterable)  
- **GET** `/api/transactions/<invoice_code>`  
  - Get all detail lines for a given invoice  
- **POST** `/api/transactions`  
  - Create new transaction line; Body: all required fields  
- **PUT** `/api/transactions/<transaction_id>`  
  - Update transaction line  
- **DELETE** `/api/transactions/<transaction_id>`  
  - Delete transaction line  

### 🔄 Import / Export

- **POST** `/api/import/customers`  
  - Form-data: `file` (xls/xlsx/csv) → Import customers  
- **POST** `/api/import/products`  
  - Form-data: `file` → Import products+stock  
- **POST** `/api/import/inventory`  
  - Form-data: `file` → Import inventory stock  
- **POST** `/api/import/transactions`  
  - Form-data: `file` → Import transactions  
- **GET** `/api/customers/export?city=<city>`  
  - Export customers → Excel download  
- **GET** `/api/products/export?category=<category>`  
  - Export products → Excel download  
- **GET** `/api/inventory/export?category=<category>`  
  - Export inventory → Excel download  

### 📈 Sales Forecasting

- **GET** `/api/sales_forecast?product_code=<code>&periods=<3|6>`  
  - Forecast next 3 or 6 months’ sales for a given product.  
  - Response includes: `forecast: [{ ds, yhat, yhat_lower, yhat_upper, is_historical } …]`, `mape`, `periods`.

---

## Running Tests

> _(Optional: If you have unit tests)_

1. Install testing dependencies:  
   ```bash
   pip install pytest pytest-flask
   ```
2. Run tests:  
   ```bash
   pytest tests/
   ```

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.  
