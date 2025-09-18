# models/job_queue.py

from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
from enum import Enum


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Job type enumeration."""
    LECTURE_GENERATION = "lecture_generation"
    CURRICULUM_PROCESSING = "curriculum_processing"
    AUDIO_GENERATION = "audio_generation"
    PPT_GENERATION = "ppt_generation"
    RAG_INDEXING = "rag_indexing"


class JobQueue(SQLModel, table=True):
    """Job queue for async processing."""
    id: Optional[int] = Field(default=None, primary_key=True)
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
