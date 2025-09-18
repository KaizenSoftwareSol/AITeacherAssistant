# models/university.py

from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship


class University(SQLModel, table=True):
    """University entity."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    location: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    teachers: List["Teacher"] = Relationship(back_populates="university")
    students: List["Student"] = Relationship(back_populates="university")
    courses: List["Course"] = Relationship(back_populates="university")
    users: List["User"] = Relationship(back_populates="university")
