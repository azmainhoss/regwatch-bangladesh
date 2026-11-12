import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.database.session import async_engine, get_async_db, AsyncSessionLocal
from backend.app.database.models import Base
from backend.app.modules.identity.router import router as auth_router
from backend.app.modules.institutions.router import router as institutions_router
from backend.app.modules.sources.router import router as sources_router
from backend.app.modules.documents.router import router as documents_router
from backend.app.modules.analysis.router import router as analysis_router
from backend.app.modules.research.router import router as research_router
from backend.app.modules.organizations.router import router as organizations_router
from backend.app.modules.compliance.router import router as compliance_router
from backend.app.workers.scheduler import monitoring_scheduler
from backend.app.modules.extraction.vision_jobs import vision_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    # In development/test mode, ensure tables are present
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schemas verified.")

    # Demo seed data is only loaded when explicitly requested, and never in production
    # (the fixture contains demo accounts with known passwords).
    if settings.SEED_ON_STARTUP and not settings.is_production:
        try:
            from backend.scripts.import_seed_data import import_seed
            async with AsyncSessionLocal() as session:
                await import_seed(session)
        except Exception as e:
            logger.warning(f"Auto-hydration skipped or failed: {e}")
    elif settings.SEED_ON_STARTUP:
        logger.warning("SEED_ON_STARTUP is ignored when ENVIRONMENT=production.")

    if settings.SCHEDULER_ENABLED:
        await monitoring_scheduler.start()
    else:
        logger.info("Source monitoring scheduler disabled in this process (SCHEDULER_ENABLED=false).")
    # Bangla and scanned pages are read from their image by a background job, never inside a request.
    run_vision = settings.SCHEDULER_ENABLED or settings.VISION_WORKER_ENABLED
    if run_vision:
        await vision_worker.start()
    yield
    logger.info("Shutting down application...")
    if settings.SCHEDULER_ENABLED:
        await monitoring_scheduler.stop()
    if run_vision:
        await vision_worker.stop()
    await async_engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Bangladesh Regulatory Intelligence and Compliance SaaS Platform API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["System"])
@app.get("/health", tags=["System"])
@app.get(f"{settings.API_V1_STR}/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": time.time()
    }


@app.get(f"{settings.API_V1_STR}/health/db", tags=["System"])
async def db_health_check(db: AsyncSession = Depends(get_async_db)):
    start_time = time.time()
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "status": "healthy",
            "database": "connected",
            "latency_ms": latency_ms
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "error",
            "detail": str(e)
        }


# Mount module routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(institutions_router, prefix=settings.API_V1_STR)
app.include_router(sources_router, prefix=settings.API_V1_STR)
app.include_router(analysis_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(research_router, prefix=settings.API_V1_STR)
app.include_router(organizations_router, prefix=settings.API_V1_STR)
app.include_router(compliance_router, prefix=settings.API_V1_STR)
