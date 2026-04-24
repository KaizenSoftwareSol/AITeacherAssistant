# main.py

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse

from logger import logger
from routes_config import (admin_router, auth_router, course_router,
                           document_router, lecture_router, notification_router,
                           student_router, system_router, teacher_router,
                           user_router)
from services.cache_service import cache, periodic_cache_cleanup
from services.http_metrics import http_metrics
from services.response_cache import setup_cache_middleware
from services.performance_middleware import setup_performance_middleware
from services.request_id_middleware import setup_request_id_middleware
from utils.db import db
from utils.db import create_db_and_tables


# Background task reference
_cleanup_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    global _cleanup_task
    
    # Startup
    await create_db_and_tables()
    
    # Try to initialize Redis (optional, falls back to in-memory cache)
    await cache.try_init_redis()
    
    # Start background cache cleanup task
    _cleanup_task = asyncio.create_task(periodic_cache_cleanup(interval=300))
    logger.info("Cache cleanup background task started")
    
    yield
    
    # Shutdown
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    logger.info("Application shutdown complete")


allowed_origins = ["*"]


app = FastAPI(
    title="AI Teacher",
    description="AI Teacher - Intelligent Learning Platform",
    version="0.1.0",
    root_path="/api/v1",
    docs_url="/docs",
    openapi_url="/docs/openapi.json",
    redoc_url="/redocs",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add performance monitoring middleware
setup_cache_middleware(app)
setup_performance_middleware(app)
setup_request_id_middleware(app)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


router = APIRouter()


@router.get("/healthz")
def healthz(
    token: Annotated[str, Depends(oauth2_scheme)],
):
    """
    Health check endpoint.
    """
    logger.info("Health check endpoint was called.")
    try:
        logger.debug("Performing a task in healthz endpoint.")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error occurred in healthz endpoint: {e}")
        return {"status": "error"}


@router.get("/health")
def health():
    """
    Public health check endpoint (no auth required).
    """
    return {"status": "ok", "service": "ai-teacher-api"}


@router.get("/ready")
def ready():
    """
    Readiness probe for load testing and orchestration.
    """
    checks = {
        "supabase_client": db.client is not None,
        "supabase_admin_client": db.admin_client is not None,
        "cache_service": cache is not None,
    }
    ready_state = all(checks.values())
    return {
        "status": "ready" if ready_state else "not_ready",
        "checks": checks,
    }


@router.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """
    Prometheus-compatible HTTP metrics endpoint.
    """
    return PlainTextResponse(http_metrics.render_prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/cache/stats")
def get_cache_stats(
    token: Annotated[str, Depends(oauth2_scheme)],
):
    """
    Get cache statistics (admin only).
    
    Returns hit rates, sizes, and performance metrics for all cache regions.
    """
    return {
        "status": "ok",
        "cache_stats": cache.get_all_stats(),
    }


@router.post("/cache/cleanup")
def trigger_cache_cleanup(
    token: Annotated[str, Depends(oauth2_scheme)],
):
    """
    Trigger manual cache cleanup (admin only).
    
    Removes expired entries from all cache regions.
    """
    cleanup_stats = cache.cleanup_all()
    total_removed = sum(cleanup_stats.values())
    
    return {
        "status": "ok",
        "message": f"Removed {total_removed} expired entries",
        "details": cleanup_stats,
    }


@router.post("/cache/clear")
def clear_all_caches(
    token: Annotated[str, Depends(oauth2_scheme)],
):
    """
    Clear all caches (admin only).
    
    WARNING: This will clear all cached data and may temporarily increase load.
    """
    cache.clear_all()
    
    return {
        "status": "ok",
        "message": "All caches cleared",
    }


app.include_router(router)
app.include_router(auth_router, prefix="/auth")
app.include_router(user_router, prefix="/users")
app.include_router(course_router, prefix="/courses")
app.include_router(document_router, prefix="/documents")
app.include_router(lecture_router, prefix="/lectures")
app.include_router(student_router, prefix="/student")
app.include_router(teacher_router, prefix="/teacher")
app.include_router(notification_router, prefix="/notifications")
app.include_router(admin_router, prefix="/admin")
app.include_router(system_router, prefix="/system")