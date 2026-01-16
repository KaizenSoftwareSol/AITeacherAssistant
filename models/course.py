# models/course.py

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.enrollment import Enrollment
    from models.lecture import Lecture
    from models.university import University


class Course(SQLModel, table=True):
    """Course/Subject entity with curriculum."""

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    name: str = Field(index=True)
    code: str = Field(unique=True, index=True)  # e.g., "CS101"
    description: Optional[str] = None
    curriculum_content: Optional[str] = None  # Full curriculum text
    university_id: str = Field(foreign_key="university.id")  # UUID
    created_by_teacher_id: Optional[str] = Field(
        default=None, foreign_key="teacher.id"
    )  # UUID - teacher who created the course
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    university: Optional["University"] = Relationship(back_populates="courses")
    semesters: List["Semester"] = Relationship(back_populates="course")
    enrollments: List["Enrollment"] = Relationship(back_populates="course")
    lectures: List["Lecture"] = Relationship(back_populates="course")


class Semester(SQLModel, table=True):
    """Academic semester/period."""

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    name: str  # e.g., "Fall 2024", "Spring 2025"
    start_date: datetime
    end_date: datetime
    course_id: str = Field(foreign_key="course.id")  # UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    course: Optional["Course"] = Relationship(back_populates="semesters")
    lectures: List["Lecture"] = Relationship(back_populates="semester")
    enrollments: List["Enrollment"] = Relationship(back_populates="semester")
