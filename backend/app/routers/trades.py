"""Trade endpoints: place trade, list trades, stats."""
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db import AdjustmentStatus, BalanceAdjustment, PaymentType, Trade, TradeStatus, User
from app.models.schemas import BalanceAdjustOut, TradePlace, TradeOut, StatsOut, TransactionRequestIn, UserOut
from app.routers.admin import save_proof_file
from app.services.auth import get_current_user
from app.services.db import get_session
from app.services.mt5_feed import price_feed

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.post("", response_model=TradeOut)
async def place_trade(
    data: TradePlace,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # validate
    if data.symbol not in settings.SYMBOLS:
        raise HTTPException(400, f"Symbol must be one of {settings.SYMBOLS}")
    if data.expiry_seconds not in settings.EXPIRY_OPTIONS_SECONDS:
        raise HTTPException(400, f"Expiry must be one of {settings.EXPIRY_OPTIONS_SECONDS}")
    if not (settings.MIN_TRADE_AMOUNT <= data.amount <= settings.MAX_TRADE_AMOUNT):
        raise HTTPException(400, "Amount out of bounds")
    if user.balance < data.amount:
        raise HTTPException(400, "Insufficient balance")

    entry = price_feed.get_price(data.symbol)
    if entry is None:
        raise HTTPException(503, "Price unavailable, try again")
    # market-closed guard: if the last tick is too old, refuse the trade.
    # 60s window — covers normal forex weekend close and broker outages.
    import time as _time
    last = price_feed.latest.get(data.symbol)
    if last and (_time.time() - last["time"]) > 60:
        raise HTTPException(400, f"Market closed for {data.symbol}. Try a different symbol or wait for the session to reopen.")

    # deduct stake immediately
    user.balance -= data.amount

    now = datetime.utcnow()
    trade = Trade(
        user_id=user.id,
        symbol=data.symbol,
        direction=data.direction,
        amount=data.amount,
        payout_rate=settings.DEFAULT_PAYOUT,
        entry_price=entry,
        opened_at=now,
        expires_at=now + timedelta(seconds=data.expiry_seconds),
        status=TradeStatus.OPEN,
    )
    session.add(trade)
    await session.commit()
    await session.refresh(trade)
    return TradeOut.model_validate(trade)


@router.get("", response_model=list[TradeOut])
async def list_trades(
    limit: int = 50,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Trade).where(Trade.user_id == user.id)
        .order_by(Trade.opened_at.desc()).limit(limit)
    )
    return [TradeOut.model_validate(t) for t in result.scalars().all()]


@router.get("/stats", response_model=StatsOut)
async def trade_stats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Trade.status, func.count(Trade.id), func.coalesce(func.sum(Trade.profit), 0.0))
        .where(Trade.user_id == user.id, Trade.status != TradeStatus.OPEN)
        .group_by(Trade.status)
    )
    rows = result.all()
    wins = losses = 0
    total_profit = 0.0
    for status_val, count, profit in rows:
        total_profit += float(profit)
        if status_val == TradeStatus.WON:
            wins = count
        elif status_val == TradeStatus.LOST:
            losses = count
    total = wins + losses
    return StatsOut(
        total_trades=total, wins=wins, losses=losses,
        win_rate=(wins / total * 100) if total else 0.0,
        total_profit=total_profit, balance=user.balance,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.get("/transactions")
async def my_transactions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The current user's own balance adjustments (deposits / withdrawals), including pending requests."""
    import json as _json
    result = await session.execute(
        select(BalanceAdjustment, PaymentType.name.label("payment_type_name"))
        .join(PaymentType, PaymentType.id == BalanceAdjustment.payment_type_id, isouter=True)
        .where(BalanceAdjustment.user_id == user.id)
        .order_by(BalanceAdjustment.created_at.desc())
    )
    out = []
    for adj, payment_type_name in result.all():
        bd = None
        if adj.bank_details:
            try: bd = _json.loads(adj.bank_details)
            except Exception: bd = None
        out.append({
            "id": adj.id,
            "user_id": adj.user_id,
            "admin_id": adj.admin_id,
            "requested_by_user_id": adj.requested_by_user_id,
            "payment_type_id": adj.payment_type_id,
            "payment_type_name": payment_type_name,
            "amount": float(adj.amount),
            "balance_before": float(adj.balance_before) if adj.balance_before is not None else None,
            "balance_after": float(adj.balance_after) if adj.balance_after is not None else None,
            "reason": adj.reason,
            "status": adj.status.value if hasattr(adj.status, "value") else adj.status,
            "proof_image_path": adj.proof_image_path,
            "bank_details": bd,
            "reject_reason": adj.reject_reason,
            "created_at": adj.created_at.isoformat(),
            "processed_at": adj.processed_at.isoformat() if adj.processed_at else None,
        })
    return out


@router.get("/payment_types")
async def list_payment_types_for_client(
    direction: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Enabled payment types the client can pick from. Filter by direction (deposit | withdrawal)."""
    q = select(PaymentType).where(PaymentType.enabled == True)
    if direction == "deposit":
        q = q.where(PaymentType.deposit_enabled == True)
    elif direction == "withdrawal":
        q = q.where(PaymentType.withdrawal_enabled == True)
    q = q.order_by(PaymentType.display_order.asc(), PaymentType.id.asc())
    import json as _json
    rows = (await session.execute(q)).scalars().all()
    out = []
    for p in rows:
        fields = []
        if p.fields:
            try: fields = _json.loads(p.fields)
            except Exception: fields = []
        out.append({
            "id": p.id, "name": p.name,
            "deposit_min": float(p.deposit_min), "deposit_max": float(p.deposit_max),
            "withdrawal_min": float(p.withdrawal_min), "withdrawal_max": float(p.withdrawal_max),
            "deposit_enabled": p.deposit_enabled, "withdrawal_enabled": p.withdrawal_enabled,
            "instructions": p.instructions,
            "fields": fields,
            "has_image": bool(p.image_path),
        })
    return out


@router.get("/payment_types/{pt_id}/image")
async def get_payment_type_image_client(
    pt_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = await session.get(PaymentType, pt_id)
    if not p or not p.enabled or not p.image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No image")
    backend_root = Path(__file__).resolve().parent.parent.parent
    full = backend_root / p.image_path
    if not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image file missing")
    return FileResponse(full)


@router.post("/transactions", response_model=BalanceAdjustOut)
async def request_transaction(
    data: TransactionRequestIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Client creates a pending deposit or withdrawal request. Admin must approve before balance changes."""
    # If any payment types exist and are enabled for this direction, picking one is required.
    pt = None
    if data.payment_type_id is not None:
        pt = await session.get(PaymentType, data.payment_type_id)
        if not pt or not pt.enabled:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected payment type is not available")
        if data.direction == "deposit" and not pt.deposit_enabled:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{pt.name}' is not available for deposits")
        if data.direction == "withdrawal" and not pt.withdrawal_enabled:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{pt.name}' is not available for withdrawals")
        # enforce per-type min/max limits
        lo = pt.deposit_min if data.direction == "deposit" else pt.withdrawal_min
        hi = pt.deposit_max if data.direction == "deposit" else pt.withdrawal_max
        if data.amount < lo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Minimum {data.direction} via {pt.name} is ${lo:.2f}")
        if data.amount > hi:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Maximum {data.direction} via {pt.name} is ${hi:.2f}")
    else:
        # if at least one payment type exists for this direction, require selection
        col = PaymentType.deposit_enabled if data.direction == "deposit" else PaymentType.withdrawal_enabled
        any_available = await session.scalar(
            select(func.count(PaymentType.id)).where(PaymentType.enabled == True, col == True)
        )
        if any_available and any_available > 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please pick a payment type")

    if data.direction == "withdrawal":
        # sum of *other* pending withdrawal requests reduces what's available now
        pending_out = await session.scalar(
            select(func.coalesce(func.sum(BalanceAdjustment.amount), 0.0)).where(
                BalanceAdjustment.user_id == user.id,
                BalanceAdjustment.status == AdjustmentStatus.PENDING,
                BalanceAdjustment.amount < 0,
            )
        )
        # pending_out is a negative number (sum of negative amounts); take abs
        reserved = abs(float(pending_out or 0.0))
        available = round(float(user.balance) - reserved, 2)
        if data.amount > available:
            if reserved > 0:
                msg = (
                    f"Cannot withdraw ${data.amount:.2f}. Your balance is ${user.balance:.2f} "
                    f"and ${reserved:.2f} is already in pending withdrawal requests — "
                    f"only ${max(available, 0):.2f} is available."
                )
            else:
                msg = f"Cannot withdraw ${data.amount:.2f} — your balance is only ${user.balance:.2f}."
            raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)

    if data.direction == "withdrawal" and not data.bank_details:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bank details are required for withdrawals")

    import json as _json
    bank_json = _json.dumps(data.bank_details) if data.bank_details else None

    signed = data.amount if data.direction == "deposit" else -data.amount
    adj = BalanceAdjustment(
        user_id=user.id,
        requested_by_user_id=user.id,
        admin_id=None,
        amount=signed,
        reason=data.note.strip(),
        status=AdjustmentStatus.PENDING,
        balance_before=None,
        balance_after=None,
        bank_details=bank_json,
        payment_type_id=pt.id if pt else None,
    )
    session.add(adj)
    await session.commit()
    await session.refresh(adj)
    return BalanceAdjustOut.model_validate(adj)


@router.post("/transactions/{txn_id}/proof", response_model=BalanceAdjustOut)
async def upload_transaction_proof(
    txn_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Attach a proof image (receipt) to one of YOUR transactions. Only the owner can upload."""
    adj = await session.get(BalanceAdjustment, txn_id)
    if not adj or adj.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    adj.proof_image_path = await save_proof_file(file)
    await session.commit()
    await session.refresh(adj)
    return BalanceAdjustOut.model_validate(adj)


@router.get("/transactions/{txn_id}/proof")
async def get_transaction_proof(
    txn_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    adj = await session.get(BalanceAdjustment, txn_id)
    if not adj or adj.user_id != user.id or not adj.proof_image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No proof image")
    backend_root = Path(__file__).resolve().parent.parent.parent
    full = backend_root / adj.proof_image_path
    if not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proof file missing")
    return FileResponse(full)


MAX_RESETS = 3


@router.post("/reset", response_model=UserOut)
async def reset_balance(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.balance_resets_used >= MAX_RESETS:
        raise HTTPException(400, f"Maximum of {MAX_RESETS} resets reached")
    user.balance = settings.STARTING_BALANCE
    user.balance_resets_used += 1
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)
