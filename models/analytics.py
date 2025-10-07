# models/analytics.py

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.lecture import Lecture


class LectureAnalytics(SQLModel, table=True):
    """Analytics for lecture performance and engagement."""

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    lecture_id: str = Field(foreign_key="lecture.id")  # UUID

    # Engagement metrics
    total_views: int = Field(default=0)
    unique_viewers: int = Field(default=0)
    average_watch_time: float = Field(default=0.0)  # in minutes
    completion_rate: float = Field(default=0.0)  # percentage

    # Q&A metrics
    total_questions: int = Field(default=0)
    questions_answered: int = Field(default=0)
    average_response_time: float = Field(default=0.0)  # in seconds

    # Content metrics
    content_length: int = Field(default=0)  # in characters
    slides_count: int = Field(default=0)
    audio_duration: float = Field(default=0.0)  # in minutes

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    lecture: Optional["Lecture"] = Relationship(back_populates="analytics")


class StudentEngagement(SQLModel, table=True):
    """Student engagement tracking."""

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    student_id: str = Field(foreign_key="student.id")  # UUID
    lecture_id: str = Field(foreign_key="lecture.id")  # UUID

    # Engagement data
    watch_time: float = Field(default=0.0)  # in minutes
    questions_asked: int = Field(default=0)
    questions_answered: int = Field(default=0)
    completion_percentage: float = Field(default=0.0)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AIProcessingLog(SQLModel, table=True):
    """Logs for AI processing operations."""

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    job_id: Optional[str] = Field(default=None, foreign_key="jobqueue.id")  # UUID
    operation_type: str  # e.g., "lecture_generation", "rag_indexing"

    # Processing details
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    processing_time: float = Field(default=0.0)  # in seconds
    cost: float = Field(default=0.0)  # in USD

    # Status
    status: str  # success, error, warning
    error_message: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
