# settings.py

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase Database Configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    
    # Database URL for SQLModel (using Supabase PostgreSQL)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # Authentication
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    JWT_ALGORITHM: str = "HS256"  # HMAC with SHA-256

    class Config:
        env_file = ".env"


settings = Settings()

# AI API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

