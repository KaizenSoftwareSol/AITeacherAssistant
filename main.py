# main.py

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles

from logger import logger
from routes_config import (auth_router, course_router, document_router,
                           lecture_router, student_router, user_router)
from utils.db import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


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


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


router = APIRouter()


@router.get("/healthz")
def healthz(
    token: Annotated[str, Depends(oauth2_scheme)],
):
    """
    Health check endpoint.
    """
    logger.info("Health check endpoint was called.")  # Log an info message
    try:
        logger.debug("Performing a task in healthz endpoint.")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error occurred in healthz endpoint: {e}")
        return {"status": "error"}


app.include_router(router)
app.include_router(auth_router, prefix="/auth")
app.include_router(user_router, prefix="/users")
app.include_router(course_router, prefix="/courses")
app.include_router(document_router, prefix="/documents")
app.include_router(lecture_router, prefix="/lectures")
app.include_router(student_router, prefix="/student")
