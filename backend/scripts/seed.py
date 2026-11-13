import asyncio
import os
import sys

# Ensure root is in sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy import select
from backend.app.core.security import get_password_hash
from backend.app.database.session import AsyncSessionLocal
import backend.app.database.models  # Register all models in registry
from backend.app.modules.identity.models import User, UserProfile
from backend.app.modules.institutions.models import Institution, InstitutionDepartment
from backend.app.modules.organizations.models import Department, Organization, OrganizationMember
from backend.app.modules.sources.models import Source


async def seed():
    # This script creates demo accounts with well-known passwords (including a superuser).
    from backend.app.core.config import settings
    if settings.is_production:
        raise SystemExit("Refusing to run the demo seed with ENVIRONMENT=production.")

    async with AsyncSessionLocal() as session:
        print("Starting database seeding...")

        # 1. Institutions: Bangladesh Bank
        bb_query = await session.execute(select(Institution).where(Institution.code == "BB"))
        bb = bb_query.scalar_one_or_none()
        if not bb:
            bb = Institution(
                code="BB",
                name="Bangladesh Bank",
                name_bn="বাংলাদেশ ব্যাংক",
                website_url="https://www.bb.org.bd",
                is_active=True
            )
            session.add(bb)
            await session.flush()
            print(" + Created Institution: Bangladesh Bank (BB)")

            # Departments
            depts = [
                ("BRPD", "Banking Regulation and Policy Department", "ব্যাংকিং প্রবিধান ও নীতি বিভাগ"),
                ("DOS", "Department of Off-site Supervision", "অফ-সাইট সুপারভিশন বিভাগ"),
                ("DBI", "Department of Banking Inspection", "ব্যাংকিং পরিদর্শন বিভাগ"),
                ("FEPD", "Foreign Exchange Policy Department", "বৈদেশিক মুদ্রা নীতি বিভাগ"),
                ("PSD", "Payment Systems Department", "পেমেন্ট সিস্টেম বিভাগ"),
                ("SFD", "Sustainable Finance Department", "সাসটেইনেবল ফাইন্যান্স ডিপার্টমেন্ট"),
            ]
            for code, name, name_bn in depts:
                d = InstitutionDepartment(
                    institution_id=bb.id,
                    code=code,
                    name=name,
                    name_bn=name_bn
                )
                session.add(d)
            print(f" + Created {len(depts)} Bangladesh Bank departments")

        # 2. Source: Bangladesh Bank Circular Portal
        source_query = await session.execute(select(Source).where(Source.name == "Bangladesh Bank Circular Portal"))
        source = source_query.scalar_one_or_none()
        if not source and bb:
            source = Source(
                institution_id=bb.id,
                name="Bangladesh Bank Circular Portal",
                source_type="WEB_CRAWLER",
                base_url="https://www.bb.org.bd/en/index.php/mediaroom/circular",
                config={
                    "request_interval_seconds": 3.0,
                    "max_pages": 5,
                    "target_departments": ["BRPD", "DOS", "FEPD", "PSD"]
                },
                is_active=True
            )
            session.add(source)
            print(" + Created Source: Bangladesh Bank Circular Portal")

        # 3. Superadmin User
        admin_email = "admin@regwatch.bd"
        admin_query = await session.execute(select(User).where(User.email == admin_email))
        admin = admin_query.scalar_one_or_none()
        if not admin:
            admin = User(
                email=admin_email,
                hashed_password=get_password_hash("AdminPassword123!"),
                full_name="System Administrator",
                phone_number="+8801700000000",
                is_active=True,
                is_superuser=True
            )
            session.add(admin)
            await session.flush()
            profile = UserProfile(user_id=admin.id, designation="Chief Platform Architect", preferences={})
            session.add(profile)
            print(f" + Created Superadmin: {admin_email} (Pass: AdminPassword123!)")

        # 4. Organization: ABC Bank PLC
        org_query = await session.execute(select(Organization).where(Organization.name == "ABC Bank PLC"))
        org = org_query.scalar_one_or_none()
        if not org:
            org = Organization(
                name="ABC Bank PLC",
                entity_type="COMMERCIAL_BANK",
                registration_number="C-12345/2020",
                license_number="BB-BRPD-LIC-9876",
                is_active=True
            )
            session.add(org)
            await session.flush()

            # Internal Bank Departments
            crm_dept = Department(organization_id=org.id, name="Credit Risk Management")
            trs_dept = Department(organization_id=org.id, name="Treasury & FX Operations")
            aml_dept = Department(organization_id=org.id, name="Anti-Money Laundering & Compliance")
            session.add_all([crm_dept, trs_dept, aml_dept])
            await session.flush()

            # Bank CCO User
            cco_email = "cco@abcbank.bd"
            cco = User(
                email=cco_email,
                hashed_password=get_password_hash("CCOPassword123!"),
                full_name="Mahmudur Rahman, CCO",
                phone_number="+8801800000000",
                is_active=True,
                is_superuser=False
            )
            session.add(cco)
            await session.flush()

            member = OrganizationMember(
                organization_id=org.id,
                user_id=cco.id,
                department_id=aml_dept.id,
                role="COMPLIANCE_HEAD",
                status="ACTIVE"
            )
            session.add(member)
            print(f" + Created Organization: ABC Bank PLC with CCO: {cco_email}")

        await session.commit()
        print(" Seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
