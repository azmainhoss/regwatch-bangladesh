"""Production accounts: switch off the demo and test logins, create the real administrator and bank accounts.

The laptop database carries demo logins whose passwords are written in this repository (backend/scripts/seed.py,
seed_test_users.py) and leftover test accounts. None of them may sign in on the live site.

Usage (repo root, on the server as the app user, or locally before copying the database):
  .venv/bin/python backend/scripts/manage_accounts.py list
  .venv/bin/python backend/scripts/manage_accounts.py disable-demo [--yes]
  .venv/bin/python backend/scripts/manage_accounts.py create-admin --email you@yourdomain.com --name "Your Name"
  .venv/bin/python backend/scripts/manage_accounts.py create-bank-user --email cco@bank.com --name "Name" \\
        --bank "Bank PLC" [--role COMPLIANCE_HEAD]
  .venv/bin/python backend/scripts/manage_accounts.py reset-password --email someone@bank.com

A new or reset password is made here (random, 20 characters) and printed once; nothing else stores it.
disable-demo keeps the rows (registers, audit trail) but switches the logins off and scrambles their passwords.
"""
import argparse
import asyncio
import os
import re
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import backend.app.database.models  # noqa: E402,F401  (registers all models)
from sqlalchemy import select  # noqa: E402

from backend.app.core.security import get_password_hash  # noqa: E402
from backend.app.database.session import AsyncSessionLocal, async_engine  # noqa: E402
from backend.app.modules.identity.models import User  # noqa: E402
from backend.app.modules.organizations.models import Organization, OrganizationMember  # noqa: E402

# Logins created by the demo seed, the test-user seed and local test runs.
DEMO_EMAILS = {"admin@regwatch.bd"}
DEMO_DOMAINS = ("abcbank.bd", "xyzbank.bd", "example.com", "example.test", "regwatch-local.com", "regwatch.bd")
DEMO_PATTERNS = (re.compile(r"^(bench|asktest)[-\w]*@"),)
ROLES = ("ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER", "DEPARTMENT_LEAD", "REVIEWER", "ANALYST", "AUDITOR", "VIEWER")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def new_password() -> str:
    alphabet = string.ascii_letters + string.digits + "-_.!@#"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(20))
        if any(c.isdigit() for c in pw) and any(c.islower() for c in pw) and any(c.isupper() for c in pw):
            return pw


def is_demo(email: str) -> bool:
    e = email.lower()
    return e in DEMO_EMAILS or e.split("@")[-1] in DEMO_DOMAINS or any(p.match(e) for p in DEMO_PATTERNS)


async def cmd_list(_args) -> None:
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).order_by(User.email))).scalars().all()
        for u in users:
            flags = ["admin" if u.is_superuser else "", "ON" if u.is_active else "off", "demo/test" if is_demo(u.email) else ""]
            print(f"{u.email:45} {' '.join(f for f in flags if f)}")
        print(f"{len(users)} accounts")


async def cmd_disable_demo(args) -> None:
    async with AsyncSessionLocal() as db:
        users = [u for u in (await db.execute(select(User))).scalars().all() if is_demo(u.email) and u.is_active]
        for u in users:
            print(f"switch off: {u.email}{'  (administrator)' if u.is_superuser else ''}")
        if not users:
            print("No demo or test login is switched on.")
            return
        if not args.yes:
            print(f"Dry run: {len(users)} login(s) would be switched off. Run again with --yes.")
            return
        for u in users:
            u.is_active = False
            u.is_superuser = False
            u.hashed_password = get_password_hash(secrets.token_urlsafe(32))
        await db.commit()
        print(f"Switched off {len(users)} login(s).")
        left = (await db.execute(select(User).where(User.is_superuser.is_(True), User.is_active.is_(True)))).scalars().all()
        if not left:
            print("No active administrator is left: create one with create-admin.")


async def _upsert_user(db, email: str, name: str) -> tuple:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        sys.exit(f"Not an email address: {email}")
    if is_demo(email):
        sys.exit(f"{email} is a demo/test address; use a real one.")
    password = new_password()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name=name.strip(), hashed_password=get_password_hash(password), is_active=True)
        db.add(user)
        await db.flush()
    else:
        user.full_name = name.strip() or user.full_name
        user.hashed_password = get_password_hash(password)
        user.is_active = True
    return user, password


async def cmd_create_admin(args) -> None:
    async with AsyncSessionLocal() as db:
        user, password = await _upsert_user(db, args.email, args.name)
        user.is_superuser = True
        await db.commit()
    print(f"Administrator ready: {user.email}\nPassword (shown once; keep it in a password manager): {password}")


async def cmd_create_bank_user(args) -> None:
    if args.role not in ROLES:
        sys.exit(f"Role must be one of: {', '.join(ROLES)}")
    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organization).where(Organization.name == args.bank.strip()))).scalars().first()
        if org is None:
            org = Organization(name=args.bank.strip(), entity_type=args.bank_type, is_active=True)
            db.add(org)
            await db.flush()
            print(f"New bank: {org.name}")
        user, password = await _upsert_user(db, args.email, args.name)
        member = (await db.execute(select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id))).scalar_one_or_none()
        if member is None:
            db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=args.role, status="ACTIVE"))
        else:
            member.role, member.status = args.role, "ACTIVE"
        await db.commit()
    print(f"Bank user ready: {user.email} ({args.role}, {args.bank})\nPassword (shown once): {password}")


async def cmd_reset_password(args) -> None:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == args.email.strip().lower()))).scalar_one_or_none()
        if user is None:
            sys.exit("No such account.")
        if is_demo(user.email):
            sys.exit("That is a demo/test login; it stays switched off.")
        password = new_password()
        user.hashed_password = get_password_hash(password)
        await db.commit()
    print(f"New password for {user.email} (shown once): {password}")


def main() -> None:
    ap = argparse.ArgumentParser(description="RegWatch production accounts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    d = sub.add_parser("disable-demo")
    d.add_argument("--yes", action="store_true")
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--name", required=True)
    b = sub.add_parser("create-bank-user")
    b.add_argument("--email", required=True)
    b.add_argument("--name", required=True)
    b.add_argument("--bank", required=True)
    b.add_argument("--role", default="COMPLIANCE_HEAD")
    b.add_argument("--bank-type", default="COMMERCIAL_BANK")
    r = sub.add_parser("reset-password")
    r.add_argument("--email", required=True)
    args = ap.parse_args()

    async def run():
        try:
            await {"list": cmd_list, "disable-demo": cmd_disable_demo, "create-admin": cmd_create_admin,
                   "create-bank-user": cmd_create_bank_user, "reset-password": cmd_reset_password}[args.cmd](args)
        finally:
            await async_engine.dispose()
    asyncio.run(run())


if __name__ == "__main__":
    main()
