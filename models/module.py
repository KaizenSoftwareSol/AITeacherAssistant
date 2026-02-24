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

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    module_id: str = Field(foreign_key="module.id")
    course_id: str = Field(foreign_key="course.id")
    display_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Module(SQLModel, table=True):
    """Semester-specific module for MEDICAL universities.

    Hierarchy: Semester → Module → Courses
    Example: Semester 3 → Module "Urology" → Courses [Anatomy, Community Health]

    Only used for MEDICAL university type.
    """

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    name: str = Field(index=True)
    description: Optional[str] = None
    semester_id: str = Field(foreign_key="semester.id")
    university_id: str = Field(foreign_key="university.id")
    display_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    semester: Optional["Semester"] = Relationship(back_populates="modules")
    university: Optional["University"] = Relationship(back_populates="modules")
