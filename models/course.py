# models/course.py

from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship


class Course(SQLModel, table=True):
    """Course/Subject entity with curriculum."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    code: str = Field(unique=True, index=True)  # e.g., "CS101"
    description: Optional[str] = None
    curriculum_content: Optional[str] = None  # Full curriculum text
    university_id: int = Field(foreign_key="university.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    university: Optional["University"] = Relationship(back_populates="courses")
    semesters: List["Semester"] = Relationship(back_populates="course")
    enrollments: List["Enrollment"] = Relationship(back_populates="course")
    lectures: List["Lecture"] = Relationship(back_populates="course")


class Semester(SQLModel, table=True):
    """Academic semester/period."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str  # e.g., "Fall 2024", "Spring 2025"
    start_date: datetime
    end_date: datetime
    course_id: int = Field(foreign_key="course.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    course: Optional["Course"] = Relationship(back_populates="semesters")
    lectures: List["Lecture"] = Relationship(back_populates="semester")
    enrollments: List["Enrollment"] = Relationship(back_populates="semester")
