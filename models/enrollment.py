# models/enrollment.py

from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship


class Enrollment(SQLModel, table=True):
    """Student enrollment in courses."""
    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id")
    course_id: int = Field(foreign_key="course.id")
    semester_id: int = Field(foreign_key="semester.id")
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
    
    # Relationships
    student: Optional["Student"] = Relationship(back_populates="enrollments")
    course: Optional["Course"] = Relationship(back_populates="enrollments")
    semester: Optional["Semester"] = Relationship(back_populates="enrollments")
