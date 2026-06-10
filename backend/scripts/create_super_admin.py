"""
Create (or reset) a SUPER ADMIN directly in MongoDB.

Use this when the admin bootstrap UI can't be used — e.g. admins already exist
(bootstrap is locked), or you've lost access. It bypasses the bootstrap secret
entirely by writing straight to the database.

Run it ON THE SERVER, where MongoDB is reachable and .env.local points at the
right database:

    cd ~/Binary-Trade/backend
    venv/bin/python scripts/create_super_admin.py

Credentials come from ADMIN_EMAIL / ADMIN_PASSWORD env vars if set, otherwise
you're prompted. The password is hashed with the app's own bcrypt; the plaintext
is never stored or printed. If the email already exists it's promoted to
super_admin and its password reset; otherwise a new super_admin is created.
"""
import asyncio
import getpass
import os
import sys

# Allow running as `venv/bin/python scripts/create_super_admin.py` from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings                       # noqa: E402
from app.models.db import AdminRole, AdminUser        # noqa: E402
from app.services.auth import hash_password           # noqa: E402
from app.services.db import init_db                   # noqa: E402


async def main() -> None:
    email = (os.environ.get("ADMIN_EMAIL") or input("Super-admin email: ")).strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("New password (min 10 chars): ")

    if not email or "@" not in email:
        print("ERROR: a valid email is required.")
        sys.exit(1)
    if len(password) < 10:
        print("ERROR: password must be at least 10 characters.")
        sys.exit(1)

    print(f"Connecting to {settings.DATABASE_NAME} …")
    await init_db()

    existing = await AdminUser.find_one(AdminUser.email == email)
    if existing:
        existing.password_hash = hash_password(password)
        existing.role = AdminRole.SUPER_ADMIN
        await existing.save()
        print(f"Updated '{email}' -> role=super_admin, password reset.")
    else:
        await AdminUser(
            email=email,
            password_hash=hash_password(password),
            role=AdminRole.SUPER_ADMIN,
        ).insert()
        print(f"Created new super_admin '{email}'.")

    total = await AdminUser.find().count()
    print(f"Done. Total admin accounts now: {total}")
    print("Log in at /admin with this email + the password you just set.")


if __name__ == "__main__":
    asyncio.run(main())
