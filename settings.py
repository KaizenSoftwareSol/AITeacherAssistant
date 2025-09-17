# settings.py

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SQLITE_DATABASE_URL: str = "sqlite:///./app.db"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    SECRET_KEY: str = "your-secret-key-here"  # In production, use a secure random key
    JWT_ALGORITHM: str = "HS256"  # HMAC with SHA-256


settings = Settings()

# AI API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

