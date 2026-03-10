# models/university.py

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.course import Course
    from models.document import Document
    from models.module import Module
    from models.user import Student, Teacher, User


class UniversityType(str, Enum):
    """University type. Modules are only used for MEDICAL."""

    MEDICAL = "MEDICAL"
    ENGINEERING = "ENGINEERING"
    LAW = "LAW"
    BUSINESS = "BUSINESS"
    ARTS = "ARTS"
    GENERAL = "GENERAL"


class University(SQLModel, table=True):
    """University entity."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    name: str = Field(index=True)
    location: Optional[str] = None
    type: str = Field(default="GENERAL")  # MEDICAL, ENGINEERING, LAW, BUSINESS, ARTS, GENERAL
    logo_url: Optional[str] = None  # Logo URL for branding
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    teachers: List["Teacher"] = Relationship(back_populates="university")
    students: List["Student"] = Relationship(back_populates="university")
    courses: List["Course"] = Relationship(back_populates="university")
    users: List["User"] = Relationship(back_populates="university")
    documents: List["Document"] = Relationship(back_populates="university")
    modules: List["Module"] = Relationship(back_populates="university")
