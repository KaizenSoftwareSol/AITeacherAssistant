# models/university.py

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from models.user import Teacher, Student, User
    from models.course import Course
    from models.document import Document


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
