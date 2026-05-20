"""Auth utilities: password hashing + JWT."""
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import settings
from app.models.db import AdminRole, AdminUser, User

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "type": "user"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_admin_access_token(admin_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=8)
    payload = {"sub": admin_id, "exp": expire, "type": "admin"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_typed_token(token: str, expected_type: str) -> str:
    """Decode a JWT and assert its type. Returns the subject id string."""
    cred_exc = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            raise cred_exc
        sub = payload.get("sub")
        if not sub:
            raise cred_exc
        return str(sub)
    except (JWTError, ValueError, TypeError):
        raise cred_exc


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    cred_exc = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        tok_type = payload.get("type", "user")
        if tok_type != "user":
            raise cred_exc
        user_id = payload.get("sub")
        if not user_id:
            raise cred_exc
    except (JWTError, ValueError, TypeError):
        raise cred_exc
    user = await User.get(user_id)
    if not user:
        raise cred_exc
    if user.disabled_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return user


admin_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/auth/login")


async def get_current_admin(token: str = Depends(admin_oauth2_scheme)) -> AdminUser:
    admin_id = _decode_typed_token(token, "admin")
    admin = await AdminUser.get(admin_id)
    if not admin:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return admin


async def require_super_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.role != AdminRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super-admin role required")
    return admin
