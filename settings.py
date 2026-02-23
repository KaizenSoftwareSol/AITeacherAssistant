# settings.py

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase Configuration (Required for all operations)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # Authentication
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 1 day
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    JWT_ALGORITHM: str = "HS256"  # HMAC with SHA-256

    # AI API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    # GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    
    # Cache Configuration (Optional)
    # Set REDIS_URL for distributed caching, otherwise uses in-memory LRU cache
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    
    # Cache TTL defaults (in seconds)
    CACHE_TTL_AUTH: int = int(os.getenv("CACHE_TTL_AUTH", "1440"))  # 1 day
    CACHE_TTL_USER: int = int(os.getenv("CACHE_TTL_USER", "1440"))   # 1 day
    CACHE_TTL_COURSE: int = int(os.getenv("CACHE_TTL_COURSE", "1440"))  # 1 day
    CACHE_TTL_LECTURE: int = int(os.getenv("CACHE_TTL_LECTURE", "1440"))  # 1 day
    
    # Cache size limits
    CACHE_MAX_SIZE: int = int(os.getenv("CACHE_MAX_SIZE", "10000"))
    
    # Email Configuration
    # Email service type: "smtp" or "sendgrid" (default: "smtp" for local, "sendgrid" for Render)
    EMAIL_SERVICE_TYPE: str = os.getenv("EMAIL_SERVICE_TYPE", "smtp")
    
    # SMTP Configuration (for local development)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    
    # SendGrid API Configuration (for Render/production)
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    
    # Common email settings
    SMTP_SENDER_EMAIL: str = os.getenv("SMTP_SENDER_EMAIL", "aitaedu.org@gmail.com")
    SMTP_SENDER_NAME: str = os.getenv("SMTP_SENDER_NAME", "AITA Platform")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()
