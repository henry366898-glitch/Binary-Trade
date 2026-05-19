"""Auth utilities: password hashing + JWT."""
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.db import AdminRole, AdminUser, User
from app.services.db import get_session

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire, "type": "user"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_admin_access_token(admin_id: int) -> str:
    # admins use a shorter token lifetime than customer accounts
    expire = datetime.utcnow() + timedelta(hours=8)
    payload = {"sub": str(admin_id), "exp": expire, "type": "admin"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_typed_token(token: str, expected_type: str) -> int:
    """Decode a JWT and assert its type. Returns the subject id."""
    cred_exc = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            raise cred_exc
        return int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise cred_exc


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    cred_exc = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    # accept legacy tokens (no type claim) AND new typed user tokens
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        tok_type = payload.get("type", "user")
        if tok_type != "user":
            raise cred_exc
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise cred_exc
    user = await session.get(User, user_id)
    if not user:
        raise cred_exc
    if user.disabled_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return user


admin_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/auth/login")


async def get_current_admin(
    token: str = Depends(admin_oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    admin_id = _decode_typed_token(token, "admin")
    admin = await session.get(AdminUser, admin_id)
    if not admin:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return admin


async def require_super_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.role != AdminRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super-admin role required")
    return admin
