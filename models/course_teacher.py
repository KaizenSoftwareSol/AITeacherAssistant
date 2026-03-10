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

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    course_id: int = Field(foreign_key="course.id")  # Integer FK for performance
    teacher_id: int = Field(foreign_key="teacher.id")  # Integer FK for performance
    assigned_by: Optional[int] = Field(
        default=None, foreign_key="users.id"
    )  # Integer FK - admin who assigned
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)

    # Relationships
    course: "Course" = Relationship()
    teacher: "Teacher" = Relationship()
