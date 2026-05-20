"""Trade endpoints: place trade, list trades, stats."""
import time as _time
from datetime import datetime, timedelta
from pathlib import Path

from beanie import PydanticObjectId
from beanie.operators import Inc
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.config import settings
from app.models.db import AdjustmentStatus, BalanceAdjustment, PaymentType, Trade, TradeStatus, User
from app.models.schemas import BalanceAdjustOut, TradePlace, TradeOut, StatsOut, TransactionRequestIn, UserOut
from app.routers.admin import save_proof_file
from app.services.auth import get_current_user
from app.services.mt5_feed import price_feed

router = APIRouter(prefix="/api/trades", tags=["trades"])


def _trade_out(t: Trade) -> TradeOut:
    return TradeOut(
        id=str(t.id),
        symbol=t.symbol,
        direction=t.direction,
        amount=t.amount,
        payout_rate=t.payout_rate,
        entry_price=t.entry_price,
        exit_price=t.exit_price,
        opened_at=t.opened_at,
        expires_at=t.expires_at,
        settled_at=t.settled_at,
        status=t.status,
        profit=t.profit,
    )


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=str(u.id),
        account_number=u.account_number,
        email=u.email,
        full_name=u.full_name,
        balance=u.balance,
        balance_resets_used=u.balance_resets_used,
        disabled_at=u.disabled_at,
        created_at=u.created_at,
    )


def _adj_out(adj: BalanceAdjustment) -> BalanceAdjustOut:
    return BalanceAdjustOut(
        id=str(adj.id),
        user_id=str(adj.user_id),
        admin_id=str(adj.admin_id) if adj.admin_id else None,
        requested_by_user_id=str(adj.requested_by_user_id) if adj.requested_by_user_id else None,
        payment_type_id=str(adj.payment_type_id) if adj.payment_type_id else None,
        amount=adj.amount,
        balance_before=adj.balance_before,
        balance_after=adj.balance_after,
        reason=adj.reason,
        status=adj.status,
        proof_image_path=adj.proof_image_path,
        bank_details=adj.bank_details,
        reject_reason=adj.reject_reason,
        created_at=adj.created_at,
        processed_at=adj.processed_at,
    )


@router.post("", response_model=TradeOut, status_code=201)
async def place_trade(
    data: TradePlace,
    user: User = Depends(get_current_user),
):
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

    last = price_feed.latest.get(data.symbol)
    if last and (_time.time() - last["time"]) > 60:
        raise HTTPException(400, f"Market closed for {data.symbol}. Try a different symbol or wait for the session to reopen.")

    # Atomically deduct stake
    await User.find_one(User.id == user.id).update(Inc(User.balance, -data.amount))

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
    await trade.insert()
    return _trade_out(trade)


@router.get("", response_model=list[TradeOut])
async def list_trades(
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    trades = await Trade.find(Trade.user_id == user.id) \
        .sort(-Trade.opened_at).limit(limit).to_list()
    return [_trade_out(t) for t in trades]


@router.get("/stats", response_model=StatsOut)
async def trade_stats(user: User = Depends(get_current_user)):
    pipeline = [
        {"$match": {"user_id": user.id, "status": {"$ne": "open"}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "profit": {"$sum": "$profit"},
        }},
    ]
    rows = await Trade.get_motor_collection().aggregate(pipeline).to_list(None)
    wins = losses = 0
    total_profit = 0.0
    for row in rows:
        total_profit += float(row.get("profit", 0))
        if row["_id"] == "won":
            wins = row["count"]
        elif row["_id"] == "lost":
            losses = row["count"]
    total = wins + losses
    fresh = await User.get(user.id)
    return StatsOut(
        total_trades=total,
        wins=wins,
        losses=losses,
        win_rate=(wins / total * 100) if total else 0.0,
        total_profit=total_profit,
        balance=fresh.balance if fresh else user.balance,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.get("/transactions")
async def my_transactions(user: User = Depends(get_current_user)):
    adjs = await BalanceAdjustment.find(
        BalanceAdjustment.user_id == user.id
    ).sort(-BalanceAdjustment.created_at).to_list()

    out = []
    for adj in adjs:
        pt_name = None
        if adj.payment_type_id:
            pt = await PaymentType.get(adj.payment_type_id)
            pt_name = pt.name if pt else None
        d = _adj_out(adj).model_dump()
        d["payment_type_name"] = pt_name
        out.append(d)
    return out


@router.get("/payment_types")
async def list_payment_types_for_client(
    direction: str | None = None,
    user: User = Depends(get_current_user),
):
    query = PaymentType.find(PaymentType.enabled == True)
    if direction == "deposit":
        query = PaymentType.find(PaymentType.enabled == True, PaymentType.deposit_enabled == True)
    elif direction == "withdrawal":
        query = PaymentType.find(PaymentType.enabled == True, PaymentType.withdrawal_enabled == True)
    pts = await query.sort([(PaymentType.display_order, 1)]).to_list()

    out = []
    for p in pts:
        fields = [f for f in (p.fields or []) if isinstance(f, dict) and f.get("label")]
        out.append({
            "id": str(p.id), "name": p.name,
            "deposit_min": p.deposit_min, "deposit_max": p.deposit_max,
            "withdrawal_min": p.withdrawal_min, "withdrawal_max": p.withdrawal_max,
            "deposit_enabled": p.deposit_enabled, "withdrawal_enabled": p.withdrawal_enabled,
            "instructions": p.instructions,
            "fields": fields,
            "has_image": bool(p.image_path),
        })
    return out


@router.get("/payment_types/{pt_id}/image")
async def get_payment_type_image_client(
    pt_id: str,
    _: User = Depends(get_current_user),
):
    p = await PaymentType.get(pt_id)
    if not p or not p.enabled or not p.image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No image")
    backend_root = Path(__file__).resolve().parent.parent.parent
    full = backend_root / p.image_path
    if not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image file missing")
    return FileResponse(full)


@router.post("/transactions", response_model=BalanceAdjustOut, status_code=201)
async def request_transaction(
    data: TransactionRequestIn,
    user: User = Depends(get_current_user),
):
    pt = None
    if data.payment_type_id is not None:
        pt = await PaymentType.get(data.payment_type_id)
        if not pt or not pt.enabled:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected payment type is not available")
        if data.direction == "deposit" and not pt.deposit_enabled:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{pt.name}' is not available for deposits")
        if data.direction == "withdrawal" and not pt.withdrawal_enabled:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{pt.name}' is not available for withdrawals")
        lo = pt.deposit_min if data.direction == "deposit" else pt.withdrawal_min
        hi = pt.deposit_max if data.direction == "deposit" else pt.withdrawal_max
        if data.amount < lo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Minimum {data.direction} via {pt.name} is ${lo:.2f}")
        if data.amount > hi:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Maximum {data.direction} via {pt.name} is ${hi:.2f}")
    else:
        col_check = PaymentType.deposit_enabled if data.direction == "deposit" else PaymentType.withdrawal_enabled
        any_avail = await PaymentType.find(PaymentType.enabled == True, col_check == True).count()
        if any_avail > 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please pick a payment type")

    if data.direction == "withdrawal":
        pipeline = [
            {"$match": {
                "user_id": user.id,
                "status": "pending",
                "amount": {"$lt": 0},
            }},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        agg = await BalanceAdjustment.get_motor_collection().aggregate(pipeline).to_list(None)
        reserved = abs(float(agg[0]["total"]) if agg else 0.0)
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

    signed = data.amount if data.direction == "deposit" else -data.amount
    adj = BalanceAdjustment(
        user_id=user.id,
        requested_by_user_id=user.id,
        admin_id=None,
        amount=signed,
        reason=data.note.strip(),
        status=AdjustmentStatus.PENDING,
        bank_details=data.bank_details,
        payment_type_id=PydanticObjectId(pt.id) if pt else None,
    )
    await adj.insert()
    return _adj_out(adj)


@router.post("/transactions/{txn_id}/proof", response_model=BalanceAdjustOut)
async def upload_transaction_proof(
    txn_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    adj = await BalanceAdjustment.get(txn_id)
    if not adj or str(adj.user_id) != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    adj.proof_image_path = await save_proof_file(file)
    await adj.save()
    return _adj_out(adj)


@router.get("/transactions/{txn_id}/proof")
async def get_transaction_proof(
    txn_id: str,
    user: User = Depends(get_current_user),
):
    adj = await BalanceAdjustment.get(txn_id)
    if not adj or str(adj.user_id) != str(user.id) or not adj.proof_image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No proof image")
    backend_root = Path(__file__).resolve().parent.parent.parent
    full = backend_root / adj.proof_image_path
    if not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proof file missing")
    return FileResponse(full)


MAX_RESETS = 3


@router.post("/reset", response_model=UserOut)
async def reset_balance(user: User = Depends(get_current_user)):
    if user.balance_resets_used >= MAX_RESETS:
        raise HTTPException(400, f"Maximum of {MAX_RESETS} resets reached")
    user.balance = settings.STARTING_BALANCE
    user.balance_resets_used += 1
    await user.save()
    return _user_out(user)
