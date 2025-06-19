import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get("SECRET_KEY") 

    # Database configuration
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT configuration
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") 

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)

    
    