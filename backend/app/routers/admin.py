"""Admin endpoints — accounts, leads export. JWT auth + role checks."""
import csv
import hmac
import io
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db import AcademyClick, AdjustmentStatus, AdminRole, AdminUser, BalanceAdjustment, PaymentType, Trade, TradeStatus, User
from app.models.schemas import (
    AdminAuthStatus, AdminBootstrap, AdminCreate, AdminLogin, AdminOut, AdminTokenOut,
    BalanceAdjustIn, BalanceAdjustOut, PaymentTypeIn, PaymentTypeOut,
)
from app.services.auth import (
    create_admin_access_token, get_current_admin, hash_password, require_super_admin, verify_password,
)
from app.services.db import get_session


# ---------- File-upload helpers ----------

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads" / "proofs"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_PROOF_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
MAX_PROOF_BYTES = 5 * 1024 * 1024  # 5 MB


def _safe_ext(filename: str) -> str:
    ext = (Path(filename).suffix or "").lower()
    if ext not in ALLOWED_PROOF_EXTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File type {ext or 'unknown'} not allowed. Use: {sorted(ALLOWED_PROOF_EXTS)}")
    return ext


async def save_proof_file(upload: UploadFile) -> str:
    """Persist an uploaded proof file under uploads/proofs/. Returns relative path stored in DB."""
    ext = _safe_ext(upload.filename or "")
    data = await upload.read()
    if len(data) > MAX_PROOF_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File too large (max {MAX_PROOF_BYTES // 1024 // 1024}MB)")
    name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    target = UPLOAD_ROOT / name
    target.write_bytes(data)
    return str(target.relative_to(UPLOAD_ROOT.parent.parent))  # e.g. "uploads/proofs/foo.png"

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------- Auth & bootstrap ----------

@router.get("/auth/status", response_model=AdminAuthStatus)
async def auth_status(session: AsyncSession = Depends(get_session)):
    """Public: tells the UI whether any admin exists yet (bootstrap mode or login mode)."""
    count = await session.scalar(select(func.count(AdminUser.id)))
    return AdminAuthStatus(has_admins=bool(count and count > 0))


@router.post("/auth/bootstrap", response_model=AdminTokenOut)
async def bootstrap_first_admin(
    data: AdminBootstrap,
    session: AsyncSession = Depends(get_session),
):
    """One-time: create the first super_admin. Refuses once any admin exists."""
    expected = settings.ADMIN_SECRET or ""
    if not expected or not hmac.compare_digest(data.secret_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bootstrap secret")

    count = await session.scalar(select(func.count(AdminUser.id)))
    if count and count > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bootstrap already complete")

    admin = AdminUser(
        email=data.email,
        password_hash=hash_password(data.password),
        role=AdminRole.SUPER_ADMIN,
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    token = create_admin_access_token(admin.id)
    return AdminTokenOut(access_token=token, admin=AdminOut.model_validate(admin))


@router.post("/auth/login", response_model=AdminTokenOut)
async def admin_login(data: AdminLogin, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(AdminUser).where(AdminUser.email == data.email))
    admin = result.scalar_one_or_none()
    if not admin or not verify_password(data.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_admin_access_token(admin.id)
    return AdminTokenOut(access_token=token, admin=AdminOut.model_validate(admin))


@router.get("/auth/me", response_model=AdminOut)
async def admin_me(admin: AdminUser = Depends(get_current_admin)):
    return AdminOut.model_validate(admin)


# ---------- Admin user management (super_admin only) ----------

@router.get("/users", response_model=list[AdminOut])
async def list_admins(
    _: AdminUser = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(AdminUser).order_by(AdminUser.created_at.asc()))
    return [AdminOut.model_validate(a) for a in result.scalars().all()]


@router.post("/users", response_model=AdminOut)
async def create_admin(
    data: AdminCreate,
    actor: AdminUser = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.execute(select(AdminUser).where(AdminUser.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin with that email already exists")
    admin = AdminUser(
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        created_by_id=actor.id,
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return AdminOut.model_validate(admin)


@router.delete("/users/{admin_id}")
async def delete_admin(
    admin_id: int,
    actor: AdminUser = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
):
    if admin_id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")
    target = await session.get(AdminUser, admin_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin not found")
    # don't allow removing the last super_admin — that would orphan the platform
    if target.role == AdminRole.SUPER_ADMIN:
        remaining = await session.scalar(
            select(func.count(AdminUser.id)).where(
                AdminUser.role == AdminRole.SUPER_ADMIN,
                AdminUser.id != target.id,
            )
        )
        if not remaining:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete the last super_admin")
    await session.delete(target)
    await session.commit()
    return {"ok": True}


# ---------- Global trades + transactions (admin views) ----------

@router.get("/trades")
async def all_trades(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user_id: int | None = Query(None),
    symbol: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    format: str = Query("json", description="json | csv | xlsx"),
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """All trades across all clients. Filterable. format=csv for download."""
    q = select(Trade, User.full_name, User.email).join(User, User.id == Trade.user_id)
    if user_id is not None:
        q = q.where(Trade.user_id == user_id)
    if symbol:
        q = q.where(Trade.symbol == symbol)
    if status_filter:
        q = q.where(Trade.status == status_filter)
    q = q.order_by(Trade.opened_at.desc()).limit(limit).offset(offset)

    rows = (await session.execute(q)).all()
    out = []
    for trade, name, email in rows:
        out.append({
            "id": trade.id,
            "user_id": trade.user_id,
            "user_name": name,
            "user_email": email,
            "symbol": trade.symbol,
            "direction": trade.direction.value if hasattr(trade.direction, "value") else trade.direction,
            "amount": float(trade.amount),
            "payout_rate": float(trade.payout_rate),
            "entry_price": float(trade.entry_price),
            "exit_price": float(trade.exit_price) if trade.exit_price is not None else None,
            "opened_at": trade.opened_at.isoformat(),
            "expires_at": trade.expires_at.isoformat(),
            "settled_at": trade.settled_at.isoformat() if trade.settled_at else None,
            "status": trade.status.value if hasattr(trade.status, "value") else trade.status,
            "profit": float(trade.profit),
        })
    if format == "xlsx":
        return _rows_to_xlsx(out, filename="edgetrade_trades.xlsx", sheet_name="Trades")
    if format == "csv":
        return _rows_to_csv(out, filename="edgetrade_trades.csv")
    return {"count": len(out), "trades": out}


def _rows_to_csv(rows: list[dict], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    if rows:
        cols = list(rows[0].keys())
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in cols])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _rows_to_xlsx(rows: list[dict], filename: str, sheet_name: str = "Sheet1") -> StreamingResponse:
    """Stream an .xlsx file from a list of dicts. Stringifies nested dicts."""
    import json as _json
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31] or "Sheet1"
    if rows:
        cols = list(rows[0].keys())
        ws.append(cols)
        for r in rows:
            row = []
            for c in cols:
                v = r.get(c)
                if v is None:
                    row.append("")
                elif isinstance(v, (dict, list)):
                    row.append(_json.dumps(v, separators=(",", ":")))
                elif isinstance(v, bool):
                    row.append("yes" if v else "no")
                else:
                    row.append(v)
            ws.append(row)
        # auto-size-ish columns: cap at 40 chars
        for col_idx, col_name in enumerate(cols, 1):
            max_len = max([len(str(col_name))] + [len(str(r.get(col_name) or "")) for r in rows])
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 40)
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return StreamingResponse(
        iter([out.read()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/transactions")
async def all_transactions(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user_id: int | None = Query(None),
    direction: str | None = Query(None, description="deposit | withdrawal"),
    status_filter: str | None = Query(None, alias="status", description="pending | approved | rejected"),
    format: str = Query("json", description="json | csv | xlsx"),
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Every balance transaction across all clients. format=csv for download."""
    q = select(
        BalanceAdjustment,
        User.full_name,
        User.email,
        User.account_number,
        AdminUser.email.label("admin_email"),
        PaymentType.name.label("payment_type_name"),
    ).join(User, User.id == BalanceAdjustment.user_id) \
     .join(AdminUser, AdminUser.id == BalanceAdjustment.admin_id, isouter=True) \
     .join(PaymentType, PaymentType.id == BalanceAdjustment.payment_type_id, isouter=True)
    if user_id is not None:
        q = q.where(BalanceAdjustment.user_id == user_id)
    if direction == "deposit":
        q = q.where(BalanceAdjustment.amount > 0)
    elif direction == "withdrawal":
        q = q.where(BalanceAdjustment.amount < 0)
    if status_filter:
        q = q.where(BalanceAdjustment.status == status_filter)
    # pending first (so admin sees them at the top), then most recent
    q = q.order_by(
        (BalanceAdjustment.status != AdjustmentStatus.PENDING),
        BalanceAdjustment.created_at.desc(),
    ).limit(limit).offset(offset)

    rows = (await session.execute(q)).all()
    out = []
    for adj, name, email, account_number, admin_email, payment_type_name in rows:
        out.append({
            "id": adj.id,
            "user_id": adj.user_id,
            "user_name": name,
            "user_email": email,
            "user_account_number": account_number,
            "payment_type_id": adj.payment_type_id,
            "payment_type_name": payment_type_name,
            "amount": float(adj.amount),
            "direction": "deposit" if adj.amount > 0 else "withdrawal",
            "balance_before": float(adj.balance_before) if adj.balance_before is not None else None,
            "balance_after": float(adj.balance_after) if adj.balance_after is not None else None,
            "reason": adj.reason,
            "status": adj.status.value if hasattr(adj.status, "value") else adj.status,
            "admin_id": adj.admin_id,
            "admin_email": admin_email,
            "requested_by_user_id": adj.requested_by_user_id,
            "is_client_request": adj.requested_by_user_id is not None,
            "has_proof": bool(adj.proof_image_path),
            "bank_details": (lambda v: __import__("json").loads(v) if v else None)(adj.bank_details),
            "reject_reason": adj.reject_reason,
            "created_at": adj.created_at.isoformat(),
            "processed_at": adj.processed_at.isoformat() if adj.processed_at else None,
        })
    if format == "xlsx":
        return _rows_to_xlsx(out, filename="edgetrade_transactions.xlsx", sheet_name="Transactions")
    if format == "csv":
        return _rows_to_csv(out, filename="edgetrade_transactions.csv")
    return {"count": len(out), "transactions": out}


# ---------- Proof image upload (admin) ----------

@router.post("/transactions/{txn_id}/proof", response_model=BalanceAdjustOut)
async def upload_proof_admin(
    txn_id: int,
    file: UploadFile = File(...),
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    adj = await session.get(BalanceAdjustment, txn_id)
    if not adj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    adj.proof_image_path = await save_proof_file(file)
    await session.commit()
    await session.refresh(adj)
    return BalanceAdjustOut.model_validate(adj)


@router.get("/clients/{client_id}")
async def client_detail(
    client_id: int,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Full profile for one client: user fields + trade rollup + recent academy clicks."""
    user = await session.get(User, client_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    settled = case((Trade.status != TradeStatus.OPEN, 1), else_=0)
    won = case((Trade.status == TradeStatus.WON, 1), else_=0)
    lost = case((Trade.status == TradeStatus.LOST, 1), else_=0)
    tr = (await session.execute(
        select(
            func.coalesce(func.sum(settled), 0),
            func.coalesce(func.sum(won), 0),
            func.coalesce(func.sum(lost), 0),
            func.coalesce(func.sum(Trade.profit), 0.0),
        ).where(Trade.user_id == client_id)
    )).one()
    total_trades, wins, losses, total_profit = int(tr[0]), int(tr[1]), int(tr[2]), float(tr[3])
    win_rate = round((wins / total_trades * 100), 2) if total_trades else 0.0

    clicks = (await session.execute(
        select(AcademyClick).where(AcademyClick.user_id == client_id).order_by(AcademyClick.created_at.desc())
    )).scalars().all()

    return {
        "id": user.id,
        "account_number": user.account_number,
        "disabled_at": user.disabled_at.isoformat() if user.disabled_at else None,
        "signup_date": user.created_at.isoformat(),
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "country": user.country,
        "referral_source": user.referral_source or "",
        "agreed_to_marketing": bool(user.agreed_to_marketing),
        "balance": float(user.balance),
        "balance_resets_used": int(user.balance_resets_used),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "total_profit": round(total_profit, 2),
        "academy_clicks": [
            {
                "id": c.id,
                "academy_name": c.academy_name,
                "surface": c.surface,
                "balance_at_click": float(c.balance_at_click),
                "total_trades_at_click": int(c.total_trades_at_click),
                "created_at": c.created_at.isoformat(),
            } for c in clicks
        ],
    }


# ---------- Payment types (admin CRUD) ----------

def _payment_type_dict(p: PaymentType) -> dict:
    import json as _json
    fields = []
    if p.fields:
        try: fields = _json.loads(p.fields)
        except Exception: fields = []
    return {
        "id": p.id, "name": p.name, "enabled": p.enabled,
        "deposit_enabled": p.deposit_enabled, "withdrawal_enabled": p.withdrawal_enabled,
        "deposit_min": float(p.deposit_min), "deposit_max": float(p.deposit_max),
        "withdrawal_min": float(p.withdrawal_min), "withdrawal_max": float(p.withdrawal_max),
        "instructions": p.instructions,
        "fields": fields,
        "image_path": p.image_path,
        "has_image": bool(p.image_path),
        "display_order": p.display_order,
        "created_at": p.created_at.isoformat(),
    }


def _payment_type_data_to_db(data: PaymentTypeIn) -> dict:
    import json as _json
    d = data.model_dump()
    d["fields"] = _json.dumps([f for f in d["fields"] if (f.get("label") or "").strip()])
    return d


@router.get("/payment_types")
async def list_payment_types(
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(
        select(PaymentType).order_by(PaymentType.display_order.asc(), PaymentType.id.asc())
    )).scalars().all()
    return [_payment_type_dict(p) for p in rows]


@router.post("/payment_types")
async def create_payment_type(
    data: PaymentTypeIn,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.execute(select(PaymentType).where(PaymentType.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment type with that name already exists")
    p = PaymentType(**_payment_type_data_to_db(data))
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return _payment_type_dict(p)


@router.patch("/payment_types/{pt_id}")
async def update_payment_type(
    pt_id: int,
    data: PaymentTypeIn,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    p = await session.get(PaymentType, pt_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment type not found")
    for k, v in _payment_type_data_to_db(data).items():
        setattr(p, k, v)
    await session.commit()
    await session.refresh(p)
    return _payment_type_dict(p)


@router.delete("/payment_types/{pt_id}")
async def delete_payment_type(
    pt_id: int,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Soft delete via disable. Hard delete blocked if any transactions reference this type."""
    p = await session.get(PaymentType, pt_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment type not found")
    used = await session.scalar(select(func.count(BalanceAdjustment.id)).where(BalanceAdjustment.payment_type_id == pt_id))
    if used and used > 0:
        # disable instead, keep history intact
        p.enabled = False
        await session.commit()
        return {"ok": True, "disabled": True, "deleted": False, "used_by": int(used)}
    await session.delete(p)
    await session.commit()
    return {"ok": True, "disabled": False, "deleted": True}


@router.post("/payment_types/{pt_id}/image")
async def upload_payment_type_image(
    pt_id: int,
    file: UploadFile = File(...),
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    p = await session.get(PaymentType, pt_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment type not found")
    p.image_path = await save_proof_file(file)
    await session.commit()
    await session.refresh(p)
    return _payment_type_dict(p)


@router.get("/payment_types/{pt_id}/image")
async def get_payment_type_image_admin(
    pt_id: int,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    p = await session.get(PaymentType, pt_id)
    if not p or not p.image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No image")
    backend_root = Path(__file__).resolve().parent.parent.parent
    full = backend_root / p.image_path
    if not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image file missing")
    return FileResponse(full)


# ---------- Client enable / disable ----------

@router.post("/clients/{client_id}/disable")
async def disable_client(
    client_id: int,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, client_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    if user.disabled_at is None:
        user.disabled_at = datetime.utcnow()
        await session.commit()
    return {"ok": True, "disabled_at": user.disabled_at.isoformat() if user.disabled_at else None}


@router.post("/clients/{client_id}/enable")
async def enable_client(
    client_id: int,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, client_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    user.disabled_at = None
    await session.commit()
    return {"ok": True}


# ---------- Proof image serve ----------

@router.get("/transactions/{txn_id}/proof")
async def get_proof_image(
    txn_id: int,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    adj = await session.get(BalanceAdjustment, txn_id)
    if not adj or not adj.proof_image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No proof image")
    backend_root = Path(__file__).resolve().parent.parent.parent
    full = backend_root / adj.proof_image_path
    if not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proof file missing on disk")
    return FileResponse(full)


# ---------- Client (lead) balance adjustment ----------

@router.post("/leads/{user_id}/balance_adjust", response_model=BalanceAdjustOut)
async def adjust_balance(
    user_id: int,
    data: BalanceAdjustIn,
    actor: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Admin direct balance adjustment (applied immediately, status=APPROVED). Balance floored at 0."""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    before = float(user.balance)
    after = max(0.0, round(before + data.amount, 2))
    user.balance = after

    now = datetime.utcnow()
    adj = BalanceAdjustment(
        user_id=user.id,
        admin_id=actor.id,
        amount=round(data.amount, 2),
        balance_before=round(before, 2),
        balance_after=after,
        reason=data.reason.strip(),
        status=AdjustmentStatus.APPROVED,
        processed_at=now,
    )
    session.add(adj)
    await session.commit()
    await session.refresh(adj)
    return BalanceAdjustOut.model_validate(adj)


@router.post("/transactions/{txn_id}/approve", response_model=BalanceAdjustOut)
async def approve_transaction(
    txn_id: int,
    actor: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Approve a pending client-initiated transaction. Applies the balance change at THIS moment."""
    adj = await session.get(BalanceAdjustment, txn_id)
    if not adj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    if adj.status != AdjustmentStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Transaction is already {adj.status.value}")

    user = await session.get(User, adj.user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    before = float(user.balance)
    after = max(0.0, round(before + adj.amount, 2))
    user.balance = after

    adj.balance_before = round(before, 2)
    adj.balance_after = after
    adj.status = AdjustmentStatus.APPROVED
    adj.admin_id = actor.id
    adj.processed_at = datetime.utcnow()

    await session.commit()
    await session.refresh(adj)
    return BalanceAdjustOut.model_validate(adj)


class RejectReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


@router.post("/transactions/{txn_id}/reject", response_model=BalanceAdjustOut)
async def reject_transaction(
    txn_id: int,
    data: RejectReasonIn,
    actor: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Reject a pending client-initiated transaction. No balance change. Reason is required."""
    adj = await session.get(BalanceAdjustment, txn_id)
    if not adj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    if adj.status != AdjustmentStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Transaction is already {adj.status.value}")

    adj.status = AdjustmentStatus.REJECTED
    adj.admin_id = actor.id
    adj.processed_at = datetime.utcnow()
    adj.reject_reason = data.reason.strip()
    # balance_before/after remain NULL — no balance change applied

    await session.commit()
    await session.refresh(adj)
    return BalanceAdjustOut.model_validate(adj)


@router.get("/leads/{user_id}/adjustments", response_model=list[BalanceAdjustOut])
async def list_adjustments(
    user_id: int,
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Audit log of every balance adjustment made to one client."""
    rows = (await session.execute(
        select(BalanceAdjustment)
        .where(BalanceAdjustment.user_id == user_id)
        .order_by(BalanceAdjustment.created_at.desc())
    )).scalars().all()
    return [BalanceAdjustOut.model_validate(r) for r in rows]


# ---------- Leads export (any admin) ----------

@router.get("/leads")
async def export_leads(
    format: str = Query("csv", description="csv | json | xlsx"),
    _: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    """Lead export with engagement + trade stats."""
    settled = case((Trade.status != TradeStatus.OPEN, 1), else_=0)
    won = case((Trade.status == TradeStatus.WON, 1), else_=0)
    lost = case((Trade.status == TradeStatus.LOST, 1), else_=0)
    trade_rollup_q = (
        select(
            Trade.user_id.label("user_id"),
            func.coalesce(func.sum(settled), 0).label("total_trades"),
            func.coalesce(func.sum(won), 0).label("wins"),
            func.coalesce(func.sum(lost), 0).label("losses"),
            func.coalesce(func.sum(Trade.profit), 0.0).label("total_profit"),
        )
        .group_by(Trade.user_id)
    )
    trade_rows = (await session.execute(trade_rollup_q)).all()
    trade_by_user = {r.user_id: r for r in trade_rows}

    click_q = (
        select(
            AcademyClick.user_id.label("user_id"),
            func.count(AcademyClick.id).label("clicks_total"),
            func.max(AcademyClick.created_at).label("last_click_at"),
        )
        .group_by(AcademyClick.user_id)
    )
    click_rows = (await session.execute(click_q)).all()
    click_by_user = {r.user_id: r for r in click_rows}

    last_surface_q = select(AcademyClick.user_id, AcademyClick.surface, AcademyClick.created_at).order_by(
        AcademyClick.user_id, AcademyClick.created_at.desc()
    )
    last_surface_rows = (await session.execute(last_surface_q)).all()
    last_surface_by_user: dict[int, str] = {}
    for uid, surface, _ts in last_surface_rows:
        last_surface_by_user.setdefault(uid, surface)

    users = (await session.execute(select(User).order_by(User.created_at.desc()))).scalars().all()

    rows = []
    for u in users:
        tr = trade_by_user.get(u.id)
        total_trades = int(tr.total_trades) if tr else 0
        wins = int(tr.wins) if tr else 0
        losses = int(tr.losses) if tr else 0
        total_profit = float(tr.total_profit) if tr else 0.0
        win_rate = round((wins / total_trades * 100), 2) if total_trades else 0.0

        cr = click_by_user.get(u.id)
        clicks_total = int(cr.clicks_total) if cr else 0
        last_click_at = cr.last_click_at.isoformat() if cr and cr.last_click_at else ""
        last_click_surface = last_surface_by_user.get(u.id, "")

        rows.append({
            "id": u.id,
            "account_number": u.account_number,
            "signup_date": u.created_at.isoformat(),
            "full_name": u.full_name,
            "email": u.email,
            "phone_number": u.phone_number,
            "country": u.country,
            "referral_source": u.referral_source or "",
            "agreed_to_marketing": bool(u.agreed_to_marketing),
            "balance": round(float(u.balance), 2),
            "balance_resets_used": int(u.balance_resets_used),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": win_rate,
            "total_profit": round(total_profit, 2),
            "academy_clicks_total": clicks_total,
            "last_click_at": last_click_at,
            "last_click_surface": last_click_surface,
        })

    if format == "json":
        return {"count": len(rows), "leads": rows}
    if format == "xlsx":
        return _rows_to_xlsx(rows, filename="edgetrade_clients.xlsx", sheet_name="Clients")

    return _rows_to_csv(rows, filename="edgetrade_clients.csv")
