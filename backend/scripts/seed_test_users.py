"""Test logins for local testing: one person per bank role, a second bank, and a user with no bank.

Run after `python -m backend.scripts.seed` (it needs ABC Bank PLC). Safe to run again.
Refuses to run when ENVIRONMENT=production. These passwords are for a local test database only.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy import select

from backend.app.core.security import get_password_hash
from backend.app.database.session import AsyncSessionLocal
import backend.app.database.models  # noqa: F401  (registers all models)
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.models import Department, Organization, OrganizationMember

ABC = "ABC Bank PLC"
XYZ = "XYZ Bank PLC"
CREDIT = "Credit Risk Management"
TREASURY = "Treasury & FX Operations"
AML = "Anti-Money Laundering & Compliance"

# email, password, full name, bank, role, department
USERS = [
    ("orgadmin@abcbank.bd", "OrgAdmin123!", "Farhana Akter (Bank admin)", ABC, "ORG_ADMIN", None),
    ("officer@abcbank.bd", "Officer123!", "Tanvir Hasan (Compliance officer)", ABC, "COMPLIANCE_OFFICER", AML),
    ("reviewer@abcbank.bd", "Reviewer123!", "Nusrat Jahan (Reviewer)", ABC, "REVIEWER", AML),
    ("creditlead@abcbank.bd", "CreditLead123!", "Rafiqul Islam (Credit dept lead)", ABC, "DEPARTMENT_LEAD", CREDIT),
    ("treasurylead@abcbank.bd", "TreasuryLead123!", "Sharmin Sultana (Treasury dept lead)", ABC, "DEPARTMENT_LEAD", TREASURY),
    ("analyst@abcbank.bd", "Analyst123!", "Imran Hossain (Analyst, Credit)", ABC, "ANALYST", CREDIT),
    ("auditor@abcbank.bd", "Auditor123!", "Shahana Begum (Auditor)", ABC, "AUDITOR", None),
    ("viewer@abcbank.bd", "Viewer123!", "Kamal Uddin (Viewer)", ABC, "VIEWER", None),
    ("admin@xyzbank.bd", "XyzAdmin123!", "Nadia Rahman (XYZ Bank admin)", XYZ, "ORG_ADMIN", None),
    ("tester2@example.com", "Password123!", "Tester Two (no bank)", None, None, None),
]

# department name -> email of its head
DEPT_HEADS = {CREDIT: "creditlead@abcbank.bd", TREASURY: "treasurylead@abcbank.bd"}


async def _org(session, name):
    org = (await session.execute(select(Organization).where(Organization.name == name))).scalar_one_or_none()
    if org is None and name == XYZ:
        org = Organization(name=XYZ, entity_type="COMMERCIAL_BANK", registration_number="C-67890/2021", is_active=True)
        session.add(org)
        await session.flush()
        session.add(Department(organization_id=org.id, name="Compliance"))
        await session.flush()
        print(f" + Created organization {XYZ}")
    return org


async def _dept(session, org, name):
    if org is None or name is None:
        return None
    return (await session.execute(
        select(Department).where(Department.organization_id == org.id, Department.name == name)
    )).scalar_one_or_none()


async def seed_test_users():
    from backend.app.core.config import settings
    if settings.is_production:
        raise SystemExit("Refusing to create test logins with ENVIRONMENT=production.")

    async with AsyncSessionLocal() as session:
        if await _org(session, ABC) is None:
            raise SystemExit("ABC Bank PLC not found. Run `python -m backend.scripts.seed` first.")

        by_email = {}
        for email, password, full_name, bank, role, dept_name in USERS:
            user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                user = User(email=email, hashed_password=get_password_hash(password), full_name=full_name,
                            is_active=True, is_superuser=False)
                session.add(user)
                await session.flush()
                print(f" + Created login {email}")
            else:
                # Keep the documented password working even if someone changed it while testing.
                user.hashed_password = get_password_hash(password)
                user.is_active = True
            by_email[email] = user

            if bank is None:
                continue
            org = await _org(session, bank)
            dept = await _dept(session, org, dept_name)
            member = (await session.execute(select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id
            ))).scalar_one_or_none()
            if member is None:
                session.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=role,
                                               department_id=dept.id if dept else None, status="ACTIVE"))
            else:
                member.role, member.status = role, "ACTIVE"
                member.department_id = dept.id if dept else None

        abc = await _org(session, ABC)
        for dept_name, email in DEPT_HEADS.items():
            dept = await _dept(session, abc, dept_name)
            if dept is not None:
                dept.head_user_id = by_email[email].id

        await session.commit()
        print(f" Test logins ready ({len(USERS)} people).")


if __name__ == "__main__":
    asyncio.run(seed_test_users())
