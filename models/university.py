# models/university.py

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.course import Course
    from models.document import Document
    from models.user import Student, Teacher, User


class University(SQLModel, table=True):
    """University entity."""

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID string
    name: str = Field(index=True)
    location: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    teachers: List["Teacher"] = Relationship(back_populates="university")
    students: List["Student"] = Relationship(back_populates="university")
    courses: List["Course"] = Relationship(back_populates="university")
    users: List["User"] = Relationship(back_populates="university")
    documents: List["Document"] = Relationship(back_populates="university")
