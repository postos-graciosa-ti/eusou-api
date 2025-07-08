from datetime import datetime, timedelta

from decouple import config
from jose import jwt


def create_access_token(data: dict, expires_delta: timedelta = None):
    ACCESS_TOKEN_EXPIRE_MINUTES = 60

    SECRET_KEY = config("SECRET_KEY")

    ALGORITHM = config("ALGORITHM")

    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
