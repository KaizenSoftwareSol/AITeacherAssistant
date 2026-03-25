# models/job_queue.py

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    """Job status enumeration."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(str, Enum):
    """Job type enumeration."""

    LECTURE_GENERATION = "LECTURE_GENERATION"
    CURRICULUM_PROCESSING = "CURRICULUM_PROCESSING"
    AUDIO_GENERATION = "AUDIO_GENERATION"
    PPT_GENERATION = "PPT_GENERATION"
    RAG_INDEXING = "RAG_INDEXING"


class JobQueue(SQLModel, table=True):
    """Job queue for async processing."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    job_type: JobType
    status: JobStatus = Field(default=JobStatus.PENDING)
    priority: int = Field(default=0)  # Higher number = higher priority

    # Job data
    payload: str  # JSON payload with job parameters
    result: Optional[str] = None  # JSON result data
    error_message: Optional[str] = None

    # Processing info
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
