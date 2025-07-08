from pydantic import BaseModel


class AuthData(BaseModel):
    app_login: str
    app_password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
