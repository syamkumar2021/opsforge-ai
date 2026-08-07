import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import Request
from fastapi.responses import JSONResponse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.config import get_settings
from app.db import Base, engine

from app.mock_portal import mock_router

# Configure logging as early as possible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from app.browser_agent import browser_agent
    from app.execution_handler import handle_exception_event
    from app.kafka_client import kafka_client
    from app.auth import get_password_hash
    from app.models import User
    from sqlalchemy import select, func
    from app.db import AsyncSessionLocal, engine, Base

    # Startup: create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Bootstrap admin if no users exist
    async with AsyncSessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(User))
        if not count:
            admin = User(
                email="admin@opsforge.ai",
                hashed_password=get_password_hash("OpsForge@123"),
                full_name="OpsForge Admin",
                is_active=True,
                is_superuser=True,
            )
            db.add(admin)
            await db.commit()
            logger.info("Bootstrap admin created: admin@opsforge.ai / OpsForge@123")
        else:
            logger.info("Users already exist — skip admin bootstrap")

    await kafka_client.start()
    await browser_agent.start()
    await kafka_client.start_consumer(
        topic=settings.kafka_topic_exceptions,
        group_id=settings.kafka_consumer_group,
        handler=handle_exception_event,
    )
    logger.info(f"🚀 {settings.app_name} started successfully")

    yield

    await kafka_client.stop()
    await browser_agent.stop()
    await engine.dispose()
    logger.info(f"🛑 {settings.app_name} shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Autonomous Enterprise Operations Multi-Agent Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "Auth", "description": "Registration, login, and current user"},
        {"name": "ERP Orders", "description": "Feed, list, and reset simulated ERP order master data"},
        {"name": "Events", "description": "Exception event simulation"},
        {"name": "Executions", "description": "Investigation tracking, HITL approval, filters"},
        {"name": "Admin", "description": "Demo/test reset utilities"},
        {"name": "Health", "description": "Service health"},
    ],
)

app.include_router(mock_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "error": str(exc),
            "path": str(request.url),
        },
    )


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix=settings.api_prefix)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
    }