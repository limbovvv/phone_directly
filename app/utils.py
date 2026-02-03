from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
signer = URLSafeSerializer(settings.SECRET_KEY)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def sign_session(data: dict) -> str:
    return signer.dumps(data)


def unsign_session(token: str):
    try:
        return signer.loads(token)
    except Exception:
        return None
