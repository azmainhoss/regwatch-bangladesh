from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.app.core.config import settings

# Async Engine for FastAPI async handlers
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

async_engine = create_async_engine(
    db_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if "sqlite" in db_url else {}
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Sync Engine for Alembic migrations and synchronous CLI tools
sync_url = settings.SYNC_DATABASE_URL or settings.DATABASE_URL
if sync_url.startswith("postgresql+asyncpg://"):
    sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
elif sync_url.startswith("postgres://"):
    sync_url = sync_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif sync_url.startswith("postgresql://") and "+psycopg2" not in sync_url:
    sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)
elif sync_url.startswith("sqlite+aiosqlite://"):
    sync_url = sync_url.replace("sqlite+aiosqlite://", "sqlite://", 1)

sync_engine = create_engine(
    sync_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if "sqlite" in sync_url else {}
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db() -> Generator[Session, None, None]:
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
