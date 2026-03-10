# models/module.py

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.course import Course, Semester
    from models.university import University


class ModuleCourse(SQLModel, table=True):
    """Junction table linking modules to courses.

    A course can appear in multiple modules across different semesters.
    For example, 'Anatomy' can be in 'Urology' module in Sem 3
    and 'Cardiology' module in Sem 4.
    """

    __tablename__ = "module_course"

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    module_id: int = Field(foreign_key="module.id")  # Integer FK for performance
    course_id: int = Field(foreign_key="course.id")  # Integer FK for performance
    display_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Module(SQLModel, table=True):
    """Semester-specific module for MEDICAL universities.

    Hierarchy: Semester → Module → Courses
    Example: Semester 3 → Module "Urology" → Courses [Anatomy, Community Health]

    Only used for MEDICAL university type.
    """

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    name: str = Field(index=True)
    description: Optional[str] = None
    semester_id: int = Field(foreign_key="semester.id")  # Integer FK for performance
    university_id: int = Field(foreign_key="university.id")  # Integer FK for performance
    display_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    semester: "Semester" = Relationship(back_populates="modules")
    university: "University" = Relationship(back_populates="modules")
