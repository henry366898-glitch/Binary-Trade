"""Lead-capture endpoints: academy click logging, etc."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import AcademyClick, Trade, TradeStatus, User
from app.services.auth import get_current_user
from app.services.db import get_session

router = APIRouter(prefix="/api/leads", tags=["leads"])

ALLOWED_ACADEMIES = {"stewarts"}
ALLOWED_SURFACES = {"modal_low", "modal_zero", "nudge_streak", "footer", "toast"}


class AcademyClickIn(BaseModel):
    academy_name: str = Field(min_length=1, max_length=64)
    surface: str = Field(min_length=1, max_length=32)


@router.post("/academy_click")
async def log_academy_click(
    data: AcademyClickIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    name = data.academy_name.strip().lower()
    if name not in ALLOWED_ACADEMIES:
        raise HTTPException(400, f"Unknown academy: {data.academy_name}")
    if data.surface not in ALLOWED_SURFACES:
        raise HTTPException(400, f"Unknown surface: {data.surface}")

    settled_count = await session.scalar(
        select(func.count(Trade.id)).where(
            Trade.user_id == user.id,
            Trade.status != TradeStatus.OPEN,
        )
    )

    click = AcademyClick(
        user_id=user.id,
        academy_name=name,
        surface=data.surface,
        balance_at_click=user.balance,
        total_trades_at_click=int(settled_count or 0),
    )
    session.add(click)
    await session.commit()
    return {"ok": True, "id": click.id}
