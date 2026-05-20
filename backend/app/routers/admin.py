"""Admin endpoints — accounts, leads export. JWT auth + role checks."""
import csv
import hmac
import io
import os
import uuid
from datetime import datetime
from pathlib import Path

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.models.db import (
    AcademyClick, AdjustmentStatus, AdminRole, AdminUser,
    BalanceAdjustment, PaymentType, Trade, TradeStatus, User,
)
from app.models.schemas import (
    AdminAuthStatus, AdminBootstrap, AdminCreate, AdminLogin, AdminOut, AdminTokenOut,
    BalanceAdjustIn, BalanceAdjustOut, PaymentTypeIn,
)
from app.services.auth import (
    create_admin_access_token, get_current_admin, hash_password, require_super_admin, verify_password,
)


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
    ext = _safe_ext(upload.filename or "")
    data = await upload.read()
    if len(data) > MAX_PROOF_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File too large (max {MAX_PROOF_BYTES // 1024 // 1024}MB)")
    name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    target = UPLOAD_ROOT / name
    target.write_bytes(data)
    return str(target.relative_to(UPLOAD_ROOT.parent.parent))


router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------- Helper serialisers ----------

def _admin_out(a: AdminUser) -> AdminOut:
    return AdminOut(
        id=str(a.id),
        email=a.email,
        role=a.role,
        created_at=a.created_at,
        created_by_id=str(a.created_by_id) if a.created_by_id else None,
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


# ---------- CSV / XLSX helpers ----------

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


# ---------- Auth & bootstrap ----------

@router.get("/auth/status", response_model=AdminAuthStatus)
async def auth_status():
    count = await AdminUser.find().count()
    return AdminAuthStatus(has_admins=count > 0)


@router.post("/auth/bootstrap", response_model=AdminTokenOut)
async def bootstrap_first_admin(data: AdminBootstrap):
    expected = settings.ADMIN_SECRET or ""
    if not expected or not hmac.compare_digest(data.secret_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bootstrap secret")
    if await AdminUser.find().count() > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bootstrap already complete")
    admin = AdminUser(
        email=data.email,
        password_hash=hash_password(data.password),
        role=AdminRole.SUPER_ADMIN,
    )
    await admin.insert()
    token = create_admin_access_token(str(admin.id))
    return AdminTokenOut(access_token=token, admin=_admin_out(admin))


@router.post("/auth/login", response_model=AdminTokenOut)
async def admin_login(data: AdminLogin):
    admin = await AdminUser.find_one(AdminUser.email == data.email)
    if not admin or not verify_password(data.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_admin_access_token(str(admin.id))
    return AdminTokenOut(access_token=token, admin=_admin_out(admin))


@router.get("/auth/me", response_model=AdminOut)
async def admin_me(admin: AdminUser = Depends(get_current_admin)):
    return _admin_out(admin)


# ---------- Admin user management ----------

@router.get("/users", response_model=list[AdminOut])
async def list_admins(_: AdminUser = Depends(require_super_admin)):
    admins = await AdminUser.find().sort(AdminUser.created_at).to_list()
    return [_admin_out(a) for a in admins]


@router.post("/users", response_model=AdminOut)
async def create_admin(
    data: AdminCreate,
    actor: AdminUser = Depends(require_super_admin),
):
    if await AdminUser.find_one(AdminUser.email == data.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin with that email already exists")
    admin = AdminUser(
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        created_by_id=actor.id,
    )
    await admin.insert()
    return _admin_out(admin)


@router.delete("/users/{admin_id}")
async def delete_admin(
    admin_id: str,
    actor: AdminUser = Depends(require_super_admin),
):
    if admin_id == str(actor.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")
    target = await AdminUser.get(admin_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin not found")
    if target.role == AdminRole.SUPER_ADMIN:
        remaining = await AdminUser.find(
            AdminUser.role == AdminRole.SUPER_ADMIN,
            AdminUser.id != target.id,
        ).count()
        if not remaining:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete the last super_admin")
    await target.delete()
    return {"ok": True}


# ---------- Global trades (admin view) ----------

@router.get("/trades")
async def all_trades(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user_id: str | None = Query(None),
    symbol: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    format: str = Query("json", description="json | csv | xlsx"),
    _: AdminUser = Depends(get_current_admin),
):
    match: dict = {}
    if user_id:
        match["user_id"] = PydanticObjectId(user_id)
    if symbol:
        match["symbol"] = symbol
    if status_filter:
        match["status"] = status_filter

    pipeline = [
        *([ {"$match": match} ] if match else []),
        {"$sort": {"opened_at": -1}},
        {"$skip": offset},
        {"$limit": limit},
        {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "_id", "as": "user"}},
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "id": {"$toString": "$_id"},
            "user_id": {"$toString": "$user_id"},
            "user_name": "$user.full_name",
            "user_email": "$user.email",
            "symbol": 1, "direction": 1, "amount": 1, "payout_rate": 1,
            "entry_price": 1, "exit_price": 1,
            "opened_at": 1, "expires_at": 1, "settled_at": 1,
            "status": 1, "profit": 1,
        }},
    ]
    rows_raw = await Trade.get_motor_collection().aggregate(pipeline).to_list(None)
    rows = []
    for r in rows_raw:
        rows.append({
            "id": r.get("id"),
            "user_id": r.get("user_id"),
            "user_name": r.get("user_name"),
            "user_email": r.get("user_email"),
            "symbol": r.get("symbol"),
            "direction": r.get("direction"),
            "amount": r.get("amount"),
            "payout_rate": r.get("payout_rate"),
            "entry_price": r.get("entry_price"),
            "exit_price": r.get("exit_price"),
            "opened_at": r["opened_at"].isoformat() if r.get("opened_at") else None,
            "expires_at": r["expires_at"].isoformat() if r.get("expires_at") else None,
            "settled_at": r["settled_at"].isoformat() if r.get("settled_at") else None,
            "status": r.get("status"),
            "profit": r.get("profit"),
        })
    if format == "xlsx":
        return _rows_to_xlsx(rows, filename="edgetrade_trades.xlsx", sheet_name="Trades")
    if format == "csv":
        return _rows_to_csv(rows, filename="edgetrade_trades.csv")
    return {"count": len(rows), "trades": rows}


# ---------- Transactions (admin view) ----------

@router.get("/transactions")
async def all_transactions(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user_id: str | None = Query(None),
    direction: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    format: str = Query("json", description="json | csv | xlsx"),
    _: AdminUser = Depends(get_current_admin),
):
    match: dict = {}
    if user_id:
        match["user_id"] = PydanticObjectId(user_id)
    if direction == "deposit":
        match["amount"] = {"$gt": 0}
    elif direction == "withdrawal":
        match["amount"] = {"$lt": 0}
    if status_filter:
        match["status"] = status_filter

    # pending first, then most recent
    pipeline = [
        *([ {"$match": match} ] if match else []),
        {"$addFields": {"_is_pending": {"$eq": ["$status", "pending"]}}},
        {"$sort": {"_is_pending": -1, "created_at": -1}},
        {"$skip": offset},
        {"$limit": limit},
        {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "_id", "as": "user"}},
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "admin_users", "localField": "admin_id", "foreignField": "_id", "as": "admin"}},
        {"$unwind": {"path": "$admin", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "payment_types", "localField": "payment_type_id", "foreignField": "_id", "as": "pt"}},
        {"$unwind": {"path": "$pt", "preserveNullAndEmptyArrays": True}},
    ]
    rows_raw = await BalanceAdjustment.get_motor_collection().aggregate(pipeline).to_list(None)
    rows = []
    for r in rows_raw:
        rows.append({
            "id": str(r["_id"]),
            "user_id": str(r["user_id"]) if r.get("user_id") else None,
            "user_name": r.get("user", {}).get("full_name"),
            "user_email": r.get("user", {}).get("email"),
            "user_account_number": r.get("user", {}).get("account_number"),
            "payment_type_id": str(r["payment_type_id"]) if r.get("payment_type_id") else None,
            "payment_type_name": r.get("pt", {}).get("name"),
            "amount": r.get("amount"),
            "direction": "deposit" if (r.get("amount") or 0) > 0 else "withdrawal",
            "balance_before": r.get("balance_before"),
            "balance_after": r.get("balance_after"),
            "reason": r.get("reason"),
            "status": r.get("status"),
            "admin_id": str(r["admin_id"]) if r.get("admin_id") else None,
            "admin_email": r.get("admin", {}).get("email"),
            "requested_by_user_id": str(r["requested_by_user_id"]) if r.get("requested_by_user_id") else None,
            "is_client_request": r.get("requested_by_user_id") is not None,
            "has_proof": bool(r.get("proof_image_path")),
            "bank_details": r.get("bank_details"),
            "reject_reason": r.get("reject_reason"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "processed_at": r["processed_at"].isoformat() if r.get("processed_at") else None,
        })
    if format == "xlsx":
        return _rows_to_xlsx(rows, filename="edgetrade_transactions.xlsx", sheet_name="Transactions")
    if format == "csv":
        return _rows_to_csv(rows, filename="edgetrade_transactions.csv")
    return {"count": len(rows), "transactions": rows}


# ---------- Proof image upload (admin) ----------

@router.post("/transactions/{txn_id}/proof", response_model=BalanceAdjustOut)
async def upload_proof_admin(
    txn_id: str,
    file: UploadFile = File(...),
    _: AdminUser = Depends(get_current_admin),
):
    adj = await BalanceAdjustment.get(txn_id)
    if not adj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    adj.proof_image_path = await save_proof_file(file)
    await adj.save()
    return _adj_out(adj)


@router.get("/clients/{client_id}")
async def client_detail(
    client_id: str,
    _: AdminUser = Depends(get_current_admin),
):
    user = await User.get(client_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    pipeline = [
        {"$match": {"user_id": user.id}},
        {"$group": {
            "_id": None,
            "total_trades": {"$sum": {"$cond": [{"$ne": ["$status", "open"]}, 1, 0]}},
            "wins": {"$sum": {"$cond": [{"$eq": ["$status", "won"]}, 1, 0]}},
            "losses": {"$sum": {"$cond": [{"$eq": ["$status", "lost"]}, 1, 0]}},
            "total_profit": {"$sum": "$profit"},
        }},
    ]
    agg = await Trade.get_motor_collection().aggregate(pipeline).to_list(None)
    tr = agg[0] if agg else {}
    total_trades = int(tr.get("total_trades", 0))
    wins = int(tr.get("wins", 0))
    losses = int(tr.get("losses", 0))
    total_profit = float(tr.get("total_profit", 0.0))
    win_rate = round((wins / total_trades * 100), 2) if total_trades else 0.0

    clicks = await AcademyClick.find(
        AcademyClick.user_id == user.id
    ).sort(-AcademyClick.created_at).to_list()

    return {
        "id": str(user.id),
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
                "id": str(c.id),
                "academy_name": c.academy_name,
                "surface": c.surface,
                "balance_at_click": float(c.balance_at_click),
                "total_trades_at_click": int(c.total_trades_at_click),
                "created_at": c.created_at.isoformat(),
            } for c in clicks
        ],
    }


# ---------- Payment types (admin CRUD) ----------

def _pt_dict(p: PaymentType) -> dict:
    fields = [f for f in (p.fields or []) if isinstance(f, dict) and f.get("label")]
    return {
        "id": str(p.id), "name": p.name, "enabled": p.enabled,
        "deposit_enabled": p.deposit_enabled, "withdrawal_enabled": p.withdrawal_enabled,
        "deposit_min": p.deposit_min, "deposit_max": p.deposit_max,
        "withdrawal_min": p.withdrawal_min, "withdrawal_max": p.withdrawal_max,
        "instructions": p.instructions,
        "fields": fields,
        "image_path": p.image_path,
        "has_image": bool(p.image_path),
        "display_order": p.display_order,
        "created_at": p.created_at.isoformat(),
    }


@router.get("/payment_types")
async def list_payment_types(_: AdminUser = Depends(get_current_admin)):
    pts = await PaymentType.find().sort([(PaymentType.display_order, 1)]).to_list()
    return [_pt_dict(p) for p in pts]


@router.post("/payment_types")
async def create_payment_type(
    data: PaymentTypeIn,
    _: AdminUser = Depends(get_current_admin),
):
    if await PaymentType.find_one(PaymentType.name == data.name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment type with that name already exists")
    fields = [f.model_dump() for f in data.fields if f.label.strip()]
    p = PaymentType(
        name=data.name, enabled=data.enabled,
        deposit_enabled=data.deposit_enabled, withdrawal_enabled=data.withdrawal_enabled,
        deposit_min=data.deposit_min, deposit_max=data.deposit_max,
        withdrawal_min=data.withdrawal_min, withdrawal_max=data.withdrawal_max,
        instructions=data.instructions,
        fields=fields,
        display_order=data.display_order,
    )
    await p.insert()
    return _pt_dict(p)


@router.patch("/payment_types/{pt_id}")
async def update_payment_type(
    pt_id: str,
    data: PaymentTypeIn,
    _: AdminUser = Depends(get_current_admin),
):
    p = await PaymentType.get(pt_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment type not found")
    p.name = data.name
    p.enabled = data.enabled
    p.deposit_enabled = data.deposit_enabled
    p.withdrawal_enabled = data.withdrawal_enabled
    p.deposit_min = data.deposit_min
    p.deposit_max = data.deposit_max
    p.withdrawal_min = data.withdrawal_min
    p.withdrawal_max = data.withdrawal_max
    p.instructions = data.instructions
    p.fields = [f.model_dump() for f in data.fields if f.label.strip()]
    p.display_order = data.display_order
    await p.save()
    return _pt_dict(p)


@router.delete("/payment_types/{pt_id}")
async def delete_payment_type(
    pt_id: str,
    _: AdminUser = Depends(get_current_admin),
):
    p = await PaymentType.get(pt_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment type not found")
    used = await BalanceAdjustment.find(BalanceAdjustment.payment_type_id == p.id).count()
    if used > 0:
        p.enabled = False
        await p.save()
        return {"ok": True, "disabled": True, "deleted": False, "used_by": used}
    await p.delete()
    return {"ok": True, "disabled": False, "deleted": True}


@router.post("/payment_types/{pt_id}/image")
async def upload_payment_type_image(
    pt_id: str,
    file: UploadFile = File(...),
    _: AdminUser = Depends(get_current_admin),
):
    p = await PaymentType.get(pt_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment type not found")
    p.image_path = await save_proof_file(file)
    await p.save()
    return _pt_dict(p)


@router.get("/payment_types/{pt_id}/image")
async def get_payment_type_image_admin(
    pt_id: str,
    _: AdminUser = Depends(get_current_admin),
):
    p = await PaymentType.get(pt_id)
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
    client_id: str,
    _: AdminUser = Depends(get_current_admin),
):
    user = await User.get(client_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    if user.disabled_at is None:
        user.disabled_at = datetime.utcnow()
        await user.save()
    return {"ok": True, "disabled_at": user.disabled_at.isoformat() if user.disabled_at else None}


@router.post("/clients/{client_id}/enable")
async def enable_client(
    client_id: str,
    _: AdminUser = Depends(get_current_admin),
):
    user = await User.get(client_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    user.disabled_at = None
    await user.save()
    return {"ok": True}


# ---------- Proof image serve ----------

@router.get("/transactions/{txn_id}/proof")
async def get_proof_image(
    txn_id: str,
    _: AdminUser = Depends(get_current_admin),
):
    adj = await BalanceAdjustment.get(txn_id)
    if not adj or not adj.proof_image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No proof image")
    backend_root = Path(__file__).resolve().parent.parent.parent
    full = backend_root / adj.proof_image_path
    if not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proof file missing on disk")
    return FileResponse(full)


# ---------- Balance adjustment (admin) ----------

@router.post("/leads/{user_id}/balance_adjust", response_model=BalanceAdjustOut)
async def adjust_balance(
    user_id: str,
    data: BalanceAdjustIn,
    actor: AdminUser = Depends(get_current_admin),
):
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    before = float(user.balance)
    after = max(0.0, round(before + data.amount, 2))
    user.balance = after
    await user.save()

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
    await adj.insert()
    return _adj_out(adj)


@router.post("/transactions/{txn_id}/approve", response_model=BalanceAdjustOut)
async def approve_transaction(
    txn_id: str,
    actor: AdminUser = Depends(get_current_admin),
):
    adj = await BalanceAdjustment.get(txn_id)
    if not adj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    if adj.status != AdjustmentStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Transaction is already {adj.status.value}")

    user = await User.get(adj.user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    before = float(user.balance)
    after = max(0.0, round(before + adj.amount, 2))
    user.balance = after
    await user.save()

    adj.balance_before = round(before, 2)
    adj.balance_after = after
    adj.status = AdjustmentStatus.APPROVED
    adj.admin_id = actor.id
    adj.processed_at = datetime.utcnow()
    await adj.save()
    return _adj_out(adj)


class RejectReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


@router.post("/transactions/{txn_id}/reject", response_model=BalanceAdjustOut)
async def reject_transaction(
    txn_id: str,
    data: RejectReasonIn,
    actor: AdminUser = Depends(get_current_admin),
):
    adj = await BalanceAdjustment.get(txn_id)
    if not adj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    if adj.status != AdjustmentStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Transaction is already {adj.status.value}")

    adj.status = AdjustmentStatus.REJECTED
    adj.admin_id = actor.id
    adj.processed_at = datetime.utcnow()
    adj.reject_reason = data.reason.strip()
    await adj.save()
    return _adj_out(adj)


@router.get("/leads/{user_id}/adjustments", response_model=list[BalanceAdjustOut])
async def list_adjustments(
    user_id: str,
    _: AdminUser = Depends(get_current_admin),
):
    adjs = await BalanceAdjustment.find(
        BalanceAdjustment.user_id == PydanticObjectId(user_id)
    ).sort(-BalanceAdjustment.created_at).to_list()
    return [_adj_out(a) for a in adjs]


# ---------- Leads export ----------

@router.get("/leads")
async def export_leads(
    format: str = Query("csv", description="csv | json | xlsx"),
    _: AdminUser = Depends(get_current_admin),
):
    # Trade rollup per user
    trade_pipeline = [
        {"$match": {"status": {"$ne": "open"}}},
        {"$group": {
            "_id": "$user_id",
            "total_trades": {"$sum": 1},
            "wins": {"$sum": {"$cond": [{"$eq": ["$status", "won"]}, 1, 0]}},
            "losses": {"$sum": {"$cond": [{"$eq": ["$status", "lost"]}, 1, 0]}},
            "total_profit": {"$sum": "$profit"},
        }},
    ]
    trade_rows = await Trade.get_motor_collection().aggregate(trade_pipeline).to_list(None)
    trade_by_user = {str(r["_id"]): r for r in trade_rows}

    # Academy click rollup per user
    click_pipeline = [
        {"$sort": {"user_id": 1, "created_at": -1}},
        {"$group": {
            "_id": "$user_id",
            "clicks_total": {"$sum": 1},
            "last_click_at": {"$first": "$created_at"},
            "last_surface": {"$first": "$surface"},
        }},
    ]
    click_rows = await AcademyClick.get_motor_collection().aggregate(click_pipeline).to_list(None)
    click_by_user = {str(r["_id"]): r for r in click_rows}

    users = await User.find().sort(-User.created_at).to_list()
    rows = []
    for u in users:
        uid = str(u.id)
        tr = trade_by_user.get(uid, {})
        total_trades = int(tr.get("total_trades", 0))
        wins = int(tr.get("wins", 0))
        losses = int(tr.get("losses", 0))
        total_profit = float(tr.get("total_profit", 0.0))
        win_rate = round((wins / total_trades * 100), 2) if total_trades else 0.0

        cr = click_by_user.get(uid, {})
        clicks_total = int(cr.get("clicks_total", 0))
        last_click_at = cr["last_click_at"].isoformat() if cr.get("last_click_at") else ""
        last_click_surface = cr.get("last_surface", "")

        rows.append({
            "id": uid,
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
