import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
    APP_PORT = int(os.getenv('APP_PORT', 8000))
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://app:app@localhost:5432/phone_directly')
    SECRET_KEY = os.getenv('SECRET_KEY', 'changeme')
    SESSION_COOKIE_NAME = os.getenv('SESSION_COOKIE_NAME', 'phone_session')
    MAX_CONTACTS_PER_PHONE_DEFAULT = int(os.getenv('MAX_CONTACTS_PER_PHONE_DEFAULT', 1))
    UPLOAD_DIR = os.getenv('UPLOAD_DIR', os.path.abspath('uploads'))

settings = Settings()
