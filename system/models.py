# system/models.py

from typing import Optional

from pydantic import BaseModel, EmailStr


class UniversityCreateRequest(BaseModel):
    """Request model for creating a university."""

    name: str
    location: Optional[str] = None
    type: Optional[str] = "GENERAL"  # MEDICAL, ENGINEERING, LAW, BUSINESS, ARTS, GENERAL


class UniversityResponse(BaseModel):
    """Response model for university data."""

    id: str
    name: str
    location: Optional[str] = None
    type: str = "GENERAL"
    created_at: str
    updated_at: str


class AdminCreateRequest(BaseModel):
    """Request model for creating an admin user for a university."""

    email: EmailStr


class AdminCreateResponse(BaseModel):
    """Response model for admin user creation."""

    user_id: str
    email: str
    username: str
    password: str  # Generated password to share
    university_id: str
    university_name: str
    message: str


class AdminSummary(BaseModel):
    """Summary of an admin user."""

    user_id: str
    email: str
    username: str
    first_name: str
    last_name: str
    university_id: str
    university_name: str
    is_active: bool
    created_at: str


class UniversityDetail(BaseModel):
    """Detailed university information with admin count."""

    id: str
    name: str
    location: Optional[str] = None
    type: str = "GENERAL"
    created_at: str
    updated_at: str
    admin_count: int
    admin_users: list[AdminSummary] = []
