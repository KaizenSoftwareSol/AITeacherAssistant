# models/document.py

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.university import University
    from models.user import Teacher


class DocumentType(str, Enum):
    """Document types supported by the system."""

    PDF = "PDF"
    PPTX = "PPTX"
    DOCX = "DOCX"


class DocumentStatus(str, Enum):
    """Document processing status."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentBase(SQLModel):
    """Base document model with common fields."""

    title: str
    description: Optional[str] = None
    document_type: DocumentType
    file_size: Optional[int] = None  # in bytes
    file_path: str  # Path in Supabase storage
    content_json_path: str  # Path to parsed content JSON in storage
    status: DocumentStatus = DocumentStatus.UPLOADED
    document_metadata: Optional[str] = None  # Additional metadata as JSON string
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Document(DocumentBase, table=True):
    """Document model for database."""

    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    teacher_id: int = Field(foreign_key="teacher.id")  # Integer FK for performance
    university_id: int = Field(foreign_key="university.id")  # Integer FK for performance

    # Relationships
    teacher: "Teacher" = Relationship(back_populates="documents")
    university: "University" = Relationship(back_populates="documents")


class DocumentCreate(SQLModel):
    """Model for creating a new document."""

    title: str
    description: Optional[str] = None
    document_type: DocumentType
    file_size: Optional[int] = None
    file_path: str
    content_json_path: str
    document_metadata: Optional[str] = None


class DocumentRead(SQLModel):
    """Model for reading document data."""

    id: str  # UUID string
    title: str
    description: Optional[str] = None
    document_type: DocumentType
    file_size: Optional[int] = None
    file_path: str
    content_json_path: str
    status: DocumentStatus
    document_metadata: Optional[str] = None
    teacher_id: str  # UUID string
    university_id: str  # UUID string
    created_at: datetime
    updated_at: datetime


class DocumentUpdate(SQLModel):
    """Model for updating document data."""

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[DocumentStatus] = None
    document_metadata: Optional[str] = None
