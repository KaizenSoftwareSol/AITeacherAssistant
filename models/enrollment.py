# models/enrollment.py

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.course import Course, Semester
    from models.user import Student


class Enrollment(SQLModel, table=True):
    """Student enrollment in courses."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    student_id: int = Field(foreign_key="student.id")  # Integer FK for performance
    course_id: int = Field(foreign_key="course.id")  # Integer FK for performance
    semester_id: int = Field(foreign_key="semester.id")  # Integer FK for performance
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)

    # Relationships
    student: "Student" = Relationship(back_populates="enrollments")
    course: "Course" = Relationship(back_populates="enrollments")
    semester: "Semester" = Relationship(back_populates="enrollments")
