# settings.py

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase Configuration (Required for all operations)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    
    # Authentication
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    JWT_ALGORITHM: str = "HS256"  # HMAC with SHA-256

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()

# AI API Keys - Temporarily disabled, will be restored soon!
# GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

