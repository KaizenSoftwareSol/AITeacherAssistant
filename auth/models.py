# auth/models.py

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel

# Import from the new models structure
from models.user import User, UserRole


class UserCreate(BaseModel):
    """Model for creating a new user."""
    email: str
    username: str
    password: str
    role: UserRole = UserRole.STUDENT


class UserRead(BaseModel):
    """Model for reading user data (without sensitive info)."""
    id: str  # UUID string from Supabase
    email: str
    username: str
    first_name: str
    last_name: str
    is_active: bool
    role: UserRole
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    """Model for updating user data."""
    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Token data model."""
    user_id: Optional[str] = None  # UUID string
