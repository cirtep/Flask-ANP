import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key"

    # Database configuration
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "mysql+pymysql://root:@localhost/aneka_niaga_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT configuration
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or "jwt-secret-key"
    # JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)

    
    