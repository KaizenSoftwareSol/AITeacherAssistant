# auth/models.py

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel

# Import from the new models structure
from models.user import User, UserRole


class UserCreate(BaseModel):
    """Model for creating a new user."""

    email: EmailStr
    username: str
    password: str
    first_name: str
    last_name: str
    role: UserRole = UserRole.STUDENT
    university_id: Optional[str] = None
    university_name: Optional[str] = None
    university_location: Optional[str] = None
    department: Optional[str] = None
    specialization: Optional[str] = None
    student_id: Optional[str] = None
    year_of_study: Optional[int] = None


class UserRead(BaseModel):
    """Model for reading user data (without sensitive info)."""

    id: str  # UUID string from Supabase
    email: str
    username: str
    first_name: str
    last_name: str
    is_active: bool
    role: UserRole
    university_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    department: Optional[str] = None
    specialization: Optional[str] = None
    student_id: Optional[str] = None
    year_of_study: Optional[int] = None


class UserUpdate(BaseModel):
    """Model for updating user data."""

    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None


class PasswordChangeRequest(BaseModel):
    """Model for changing password (requires old password)."""

    old_password: str
    new_password: str


class TokenPasswordChangeRequest(BaseModel):
    """Model for changing password using activation token (no old password required)."""

    token: str
    new_password: str


class Token(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str
    expires_in: int  # Seconds until token expires


class TokenData(BaseModel):
    """Token data model."""

    user_id: Optional[str] = None  # UUID string


class UniversityRead(BaseModel):
    """Model for exposing university data."""

    id: str
    name: str
    location: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
