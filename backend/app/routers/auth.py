"""Auth endpoints: register + login."""
import random
from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.models.db import User
from app.models.schemas import UserCreate, UserLogin, TokenOut, UserOut
from app.services.auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _generate_account_number() -> str:
    """6-digit account number, unique across users."""
    for _ in range(20):
        n = f"{random.randint(100_000, 999_999)}"
        if not await User.find_one(User.account_number == n):
            return n
    raise HTTPException(500, "Could not allocate account number")


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        account_number=user.account_number,
        email=user.email,
        full_name=user.full_name,
        balance=user.balance,
        balance_resets_used=user.balance_resets_used,
        disabled_at=user.disabled_at,
        created_at=user.created_at,
    )


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(data: UserCreate):
    if await User.find_one(User.email == data.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")

    user = User(
        account_number=await _generate_account_number(),
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        phone_number=data.phone_number,
        country=data.country,
        referral_source=data.referral_source,
        agreed_to_marketing=data.agreed_to_marketing,
        balance=settings.STARTING_BALANCE,
    )
    await user.insert()
    token = create_access_token(str(user.id))
    return TokenOut(access_token=token, user=_user_out(user))


@router.post("/login", response_model=TokenOut)
async def login(data: UserLogin):
    user = await User.find_one(User.email == data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if user.disabled_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled. Please contact support.")
    token = create_access_token(str(user.id))
    return TokenOut(access_token=token, user=_user_out(user))
