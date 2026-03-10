# models/course.py

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.enrollment import Enrollment
    from models.lecture import Lecture
    from models.module import Module
    from models.university import University


class Course(SQLModel, table=True):
    """Course/Subject entity with curriculum."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    name: str = Field(index=True)
    code: str = Field(unique=True, index=True)  # e.g., "CS101"
    description: Optional[str] = None
    curriculum_content: Optional[str] = None  # Full curriculum text
    university_id: int = Field(foreign_key="university.id")  # Integer FK for performance
    created_by_teacher_id: Optional[int] = Field(
        default=None, foreign_key="teacher.id"
    )  # Integer FK for performance
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    university: "University" = Relationship(back_populates="courses")
    semesters: List["Semester"] = Relationship(back_populates="course")
    enrollments: List["Enrollment"] = Relationship(back_populates="course")
    lectures: List["Lecture"] = Relationship(back_populates="course")


class Semester(SQLModel, table=True):
    """Academic semester/period.
    
    Can be either:
    - University-level: university_id set, course_id is None (managed by admin, shared across courses)
    - Course-level: course_id set, university_id is None (legacy, tied to specific course)
    """

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    name: str  # e.g., "Fall 2024", "Spring 2025"
    start_date: datetime
    end_date: datetime
    university_id: Optional[int] = Field(default=None, foreign_key="university.id")  # Integer FK - for university-level semesters
    course_id: Optional[int] = Field(default=None, foreign_key="course.id")  # Integer FK - for course-level semesters (legacy)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    course: "Course" = Relationship(back_populates="semesters")
    lectures: List["Lecture"] = Relationship(back_populates="semester")
    enrollments: List["Enrollment"] = Relationship(back_populates="semester")
    modules: List["Module"] = Relationship(back_populates="semester")
