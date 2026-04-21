# models/lecture.py

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.ai_conversation import AIConversation
    from models.analytics import LectureAnalytics
    from models.course import Course, Semester
    from models.lecture_embedding import LectureChunk, LectureEmbedding
    from models.user import Teacher


class LectureStatus(str, Enum):
    """Lecture status enumeration."""

    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    DELIVERED = "DELIVERED"
    PUBLISHED = "PUBLISHED"  # Match actual database


class LectureType(str, Enum):
    """Lecture type enumeration."""

    AI_GENERATED = "AI_GENERATED"
    TEACHER_RECORDED = "TEACHER_RECORDED"
    LECTURE = "LECTURE"  # Match actual database


class Lecture(SQLModel, table=True):
    """Lecture entity for both AI-generated and teacher-recorded lectures."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    title: str
    description: Optional[str] = None
    learning_outcomes: Optional[str] = None  # Learning outcomes for students
    content: str  # Main lecture content/text
    summary: Optional[str] = None  # AI-generated summary for quick overview
    chapter: Optional[str] = None  # Book chapter reference
    book_reference: Optional[str] = None  # Book name/reference
    lecture_type: LectureType
    status: LectureStatus = Field(default=LectureStatus.DRAFT)
    version: int = Field(default=1)  # Version control
    has_embeddings: bool = Field(default=False)  # Whether embeddings exist for RAG

    # Foreign keys
    course_id: int = Field(foreign_key="course.id")  # Integer FK for performance
    semester_id: int = Field(foreign_key="semester.id")  # Integer FK for performance
    teacher_id: int = Field(foreign_key="teacher.id")  # Integer FK for performance
    document_id: Optional[int] = Field(default=None, foreign_key="documents.id")  # Integer FK - source document
    
    # Topic and numbering
    topic: Optional[str] = None  # Topic name for grouping (e.g., "CLUSTERING", "PREDICTION", "REGRESSION")
    lecture_number: Optional[int] = None  # Sequential number within topic (starts from 1)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None

    # Relationships
    course: "Course" = Relationship(back_populates="lectures")
    semester: "Semester" = Relationship(back_populates="lectures")
    teacher: "Teacher" = Relationship(back_populates="lectures")
    contents: List["LectureContent"] = Relationship(back_populates="lecture")
    conversations: List["AIConversation"] = Relationship(back_populates="lecture")
    analytics: List["LectureAnalytics"] = Relationship(back_populates="lecture")
    chunks: List["LectureChunk"] = Relationship(back_populates="lecture")
    embeddings: List["LectureEmbedding"] = Relationship()


class LectureContent(SQLModel, table=True):
    """File metadata for lecture materials stored in Supabase."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    lecture_id: int = Field(foreign_key="lecture.id")  # Integer FK for performance
    file_name: str
    file_type: str  # pdf, pptx, docx, txt, etc.
    file_size: int  # in bytes
    storage_path: str  # Supabase storage path
    storage_bucket: str  # Supabase bucket name
    mime_type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    lecture: "Lecture" = Relationship(back_populates="contents")


# ==================== Request/Response Models ====================


class LectureGenerationRequest(SQLModel):
    """Request model for lecture generation from document(s)."""

    # Support both single document (backward compatibility) and multiple documents
    document_id: Optional[str] = None  # UUID of a single source document (deprecated, use document_ids)
    document_ids: Optional[List[str]] = None  # List of UUIDs of source documents (PDF/PPTX)
    course_id: str  # UUID of the course
    semester_id: str  # UUID of the semester
    title: str  # Title for the lecture
    description: str  # Description/overview from teacher
    learning_outcomes: Optional[str] = None  # Learning outcomes for students
    # List of chapter names to include (None = all chapters) - applies to first document if multiple
    selected_chapters: Optional[List[str]] = None
    topic: Optional[str] = None  # Topic name for grouping (e.g., "CLUSTERING", "PREDICTION", "REGRESSION")
    # Optional extra sources to use transiently for generation (not persisted)
    extra_document_ids: Optional[List[str]] = None  # Existing ingested document IDs (must belong to teacher)
    extra_texts: Optional[List[str]] = None  # Raw text snippets to include transiently
    extra_file_urls: Optional[List[str]] = None  # Remote files (txt, pdf, docx) to fetch & parse transiently


class LectureGenerationResponse(SQLModel):
    """Response model for lecture generation."""

    lecture_id: str
    title: str
    description: str
    status: str
    pdf_storage_path: str
    pdf_filename: str
    content_length: int
    pdf_size: int
    created_at: str


class LectureRead(SQLModel):
    """Model for reading lecture data."""

    id: str  # UUID
    title: str
    description: Optional[str] = None
    learning_outcomes: Optional[str] = None
    content: str
    chapter: Optional[str] = None
    book_reference: Optional[str] = None
    lecture_type: LectureType
    status: LectureStatus
    version: int
    course_id: str  # UUID
    semester_id: str  # UUID
    teacher_id: str  # UUID
    topic: Optional[str] = None
    lecture_number: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    delivered_at: Optional[datetime] = None


class LectureUpdate(SQLModel):
    """Model for updating lecture data."""

    title: Optional[str] = None
    description: Optional[str] = None
    learning_outcomes: Optional[str] = None
    content: Optional[str] = None
    chapter: Optional[str] = None
    book_reference: Optional[str] = None
    status: Optional[LectureStatus] = None
    topic: Optional[str] = None
    lecture_number: Optional[int] = None


class LectureDownloadResponse(SQLModel):
    """Response model for lecture download."""

    lecture_id: str
    title: str
    download_url: Optional[str] = None
    file_name: str = "lecture.pdf"
    file_size: int = 0
    created_at: str
    lecture_content: Optional[str] = None
    has_pdf: bool = False


class DuplicateLectureInfo(SQLModel):
    """Information about a duplicate lecture."""

    lecture_id: str
    title: str
    description: Optional[str] = None
    learning_outcomes: Optional[str] = None
    status: str
    created_at: str
    download_url: Optional[str] = None  # May be None if PDF not available
    file_name: str
    file_size: int
    lecture_content: Optional[str] = None


class DuplicateCheckRequest(SQLModel):
    """Request model for checking duplicate lectures."""

    course_id: str | int  # Can be UUID string or integer ID
    semester_id: str | int  # Can be UUID string or integer ID
    title: str
    document_id: Optional[str | int] = None  # UUID of source document (deprecated, use document_ids)
    document_ids: Optional[List[str | int]] = None  # List of UUIDs or integer IDs of source documents (checks first document for duplicates)
    learning_outcomes: Optional[str] = None
    selected_chapters: Optional[List[str]] = None


class DuplicateCheckResponse(SQLModel):
    """Response model for duplicate check."""

    has_duplicate: bool
    duplicate_lecture: Optional[DuplicateLectureInfo] = None
    message: str
    suggested_title: Optional[str] = None  # Suggested versioned title when duplicate found (e.g., "Lecture Title (1)")


class LecturePlanGenerationResponse(SQLModel):
    """Response model for lecture plan generation."""

    lecture_id: str
    lecture_title: str
    plan: dict  # The comprehensive teaching plan
    message: str
    created_at: str


class LectureModifyRequest(SQLModel):
    """Request model for modifying a generated lecture."""

    title: Optional[str] = None  # New title for the lecture
    description: Optional[str] = None  # New description
    learning_outcomes: Optional[str] = None  # New learning outcomes
    content: Optional[str] = None  # Modified lecture content (will trigger PDF regeneration)
    topic: Optional[str] = None  # Topic for grouping
    lecture_number: Optional[int] = None  # Sequential number within topic
    regenerate_pdf: bool = False  # If True, regenerate PDF even if content unchanged


class LectureModifyResponse(SQLModel):
    """Response model for lecture modification."""

    lecture_id: str
    title: str
    description: Optional[str] = None
    learning_outcomes: Optional[str] = None
    status: str
    version: int
    pdf_regenerated: bool
    pdf_storage_path: Optional[str] = None
    updated_at: str
    message: str
