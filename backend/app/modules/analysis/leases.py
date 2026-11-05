from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import logger
from backend.app.modules.analysis.models import AnalysisLease


class AnalysisLeaseManager:
    """
    Durable database-backed distributed lease manager for document analysis jobs.
    Ensures:
    1. Atomic lease acquisition across multiple workers and processes.
    2. Prevention of duplicate processing runs.
    3. Heartbeat lease extension during long analyses.
    4. Safe recovery of stale locks after worker crash or termination.
    5. Token-validated release preventing race conditions.
    """

    DEFAULT_LEASE_DURATION_SECONDS = 120  # 2 minutes default lease duration

    @classmethod
    async def acquire_lease(
        cls,
        db: AsyncSession,
        document_id: UUID,
        worker_id: str,
        lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS
    ) -> str:
        """
        Attempts to acquire an exclusive analysis lease on a document.
        Returns the unique lease_token string if acquired.
        Raises ValueError if the document is actively leased by another live worker.
        """
        now = datetime.now(timezone.utc)
        stmt = select(AnalysisLease).where(AnalysisLease.document_id == document_id)
        result = await db.execute(stmt)
        existing_lease = result.scalar_one_or_none()

        if existing_lease:
            # Ensure timezone-aware comparison
            expires_at = existing_lease.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            # Check if active and unexpired
            if existing_lease.status == "ACTIVE" and expires_at and expires_at > now:
                # Same worker reentrancy
                if existing_lease.owner_worker_id == worker_id:
                    existing_lease.expires_at = now + timedelta(seconds=lease_duration_seconds)
                    existing_lease.heartbeat_at = now
                    await db.commit()
                    return existing_lease.lease_token

                remaining = int((expires_at - now).total_seconds())
                logger.warning(
                    f"Lock collision on document {document_id}: already leased to {existing_lease.owner_worker_id} "
                    f"for another {remaining}s."
                )
                raise ValueError(
                    f"Document analysis is currently locked by worker '{existing_lease.owner_worker_id}'. "
                    f"Active lease valid for another {remaining}s. Duplicate execution prevented."
                )

            # Stale lock recovery
            logger.warning(
                f"Recovering stale or expired lease on document {document_id}. "
                f"Previous owner: '{existing_lease.owner_worker_id}', expired at: {expires_at}"
            )
            new_token = uuid4().hex
            existing_lease.owner_worker_id = worker_id
            existing_lease.lease_token = new_token
            existing_lease.acquired_at = now
            existing_lease.expires_at = now + timedelta(seconds=lease_duration_seconds)
            existing_lease.heartbeat_at = now
            existing_lease.status = "ACTIVE"
            await db.commit()
            return new_token

        # Brand new lease
        new_token = uuid4().hex
        lease = AnalysisLease(
            document_id=document_id,
            owner_worker_id=worker_id,
            lease_token=new_token,
            acquired_at=now,
            expires_at=now + timedelta(seconds=lease_duration_seconds),
            heartbeat_at=now,
            status="ACTIVE"
        )
        db.add(lease)
        await db.commit()
        logger.info(f"Worker '{worker_id}' acquired analysis lease for document {document_id} (token={new_token[:8]}...)")
        return new_token

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        document_id: UUID,
        lease_token: str,
        extension_seconds: int = DEFAULT_LEASE_DURATION_SECONDS
    ) -> bool:
        """
        Extends lease expiration (heartbeat) during long-running processing.
        Returns True if renewed, False if token mismatch or lease not found.
        """
        now = datetime.now(timezone.utc)
        stmt = select(AnalysisLease).where(
            AnalysisLease.document_id == document_id,
            AnalysisLease.lease_token == lease_token,
            AnalysisLease.status == "ACTIVE"
        )
        result = await db.execute(stmt)
        lease = result.scalar_one_or_none()

        if not lease:
            logger.error(f"Cannot renew lease for document {document_id}: token mismatch or lease not active.")
            return False

        lease.expires_at = now + timedelta(seconds=extension_seconds)
        lease.heartbeat_at = now
        await db.commit()
        return True

    @classmethod
    async def release_lease(
        cls,
        db: AsyncSession,
        document_id: UUID,
        lease_token: str,
        status: str = "RELEASED"
    ) -> bool:
        """
        Releases an analysis lease upon job completion or termination.
        Verifies lease_token ownership before mutating status.
        """
        stmt = select(AnalysisLease).where(
            AnalysisLease.document_id == document_id,
            AnalysisLease.lease_token == lease_token
        )
        result = await db.execute(stmt)
        lease = result.scalar_one_or_none()

        if not lease:
            logger.warning(f"Release skipped for document {document_id}: lease record not found with token {lease_token[:8]}...")
            return False

        lease.status = status
        lease.expires_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"Analysis lease for document {document_id} released with status '{status}'")
        return True

    @classmethod
    async def get_lease(
        cls,
        db: AsyncSession,
        document_id: UUID
    ) -> Optional[AnalysisLease]:
        stmt = select(AnalysisLease).where(AnalysisLease.document_id == document_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
