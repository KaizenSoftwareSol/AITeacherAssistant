# models/course_teacher.py

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.course import Course
    from models.user import Teacher


class CourseTeacher(SQLModel, table=True):
    """Junction table for course-teacher assignments.
    
    Allows admins to assign courses to teachers.
    Teachers can be assigned to courses they didn't create.
    """

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    course_id: str = Field(foreign_key="course.id")  # UUID
    teacher_id: str = Field(foreign_key="teacher.id")  # UUID
    assigned_by: Optional[str] = Field(
        default=None, foreign_key="users.id"
    )  # UUID - admin who assigned
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)

    # Relationships
    course: Optional["Course"] = Relationship()
    teacher: Optional["Teacher"] = Relationship()
