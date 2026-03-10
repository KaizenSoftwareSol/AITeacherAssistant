# models/flashcard.py

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.lecture import Lecture


class Flashcard(SQLModel, table=True):
    """Flashcard entity for quick review and study."""

    id: int | None = Field(default=None, primary_key=True)  # Integer PK
    uuid: str | None = Field(
        default=None, unique=True, index=True
    )  # UUID for external APIs
    lecture_id: int = Field(foreign_key="lecture.id")  # Integer FK
    question: str
    answer: str
    order_index: int = Field(default=0)
    difficulty: str = Field(default="MEDIUM")  # EASY, MEDIUM, HARD
    topic: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    lecture: Optional["Lecture"] = Relationship()
