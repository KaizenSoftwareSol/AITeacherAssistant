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

    # AI API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    # GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    
    # Cache Configuration (Optional)
    # Set REDIS_URL for distributed caching, otherwise uses in-memory LRU cache
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    
    # Cache TTL defaults (in seconds)
    CACHE_TTL_AUTH: int = int(os.getenv("CACHE_TTL_AUTH", "600"))  # 10 min
    CACHE_TTL_USER: int = int(os.getenv("CACHE_TTL_USER", "120"))   # 2 min
    CACHE_TTL_COURSE: int = int(os.getenv("CACHE_TTL_COURSE", "600"))  # 10 min
    CACHE_TTL_LECTURE: int = int(os.getenv("CACHE_TTL_LECTURE", "300"))  # 5 min
    
    # Cache size limits
    CACHE_MAX_SIZE: int = int(os.getenv("CACHE_MAX_SIZE", "1000"))

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()
