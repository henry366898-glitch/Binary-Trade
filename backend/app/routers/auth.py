"""Auth endpoints: register + login."""
import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db import User
from app.models.schemas import UserCreate, UserLogin, TokenOut, UserOut
from app.services.auth import hash_password, verify_password, create_access_token
from app.services.db import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _generate_account_number(session: AsyncSession) -> str:
    """6-digit account number, unique across users."""
    for _ in range(20):
        n = f"{random.randint(100_000, 999_999)}"
        exists = await session.execute(select(User.id).where(User.account_number == n))
        if exists.scalar_one_or_none() is None:
            return n
    raise HTTPException(500, "Could not allocate account number")


@router.post("/register", response_model=TokenOut)
async def register(data: UserCreate, session: AsyncSession = Depends(get_session)):
    existing = await session.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")

    user = User(
        account_number=await _generate_account_number(session),
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        phone_number=data.phone_number,
        country=data.country,
        referral_source=data.referral_source,
        agreed_to_marketing=data.agreed_to_marketing,
        balance=settings.STARTING_BALANCE,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(data: UserLogin, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if user.disabled_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled. Please contact support.")
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))
