# models/document_assignment.py

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.course import Course
    from models.document import Document


class DocumentAssignment(SQLModel, table=True):
    """Junction table linking documents to courses."""

    __tablename__ = "document_assignment"

    id: int | None = Field(
        default=None, primary_key=True
    )  # Integer PK for performance
    uuid: str | None = Field(
        default=None, unique=True, index=True
    )  # UUID for external APIs
    document_id: int = Field(foreign_key="documents.id")  # Integer FK
    course_id: int = Field(foreign_key="course.id")  # Integer FK
    topic: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    document: Optional["Document"] = Relationship()
    course: Optional["Course"] = Relationship()
