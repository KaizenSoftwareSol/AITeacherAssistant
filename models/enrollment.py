# models/enrollment.py

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from models.user import Student
    from models.course import Course, Semester


class Enrollment(SQLModel, table=True):
    """Student enrollment in courses."""
    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    student_id: str = Field(foreign_key="student.id")  # UUID
    course_id: str = Field(foreign_key="course.id")  # UUID
    semester_id: str = Field(foreign_key="semester.id")  # UUID
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
    
    # Relationships
    student: Optional["Student"] = Relationship(back_populates="enrollments")
    course: Optional["Course"] = Relationship(back_populates="enrollments")
    semester: Optional["Semester"] = Relationship(back_populates="enrollments")
