# models/lecture.py

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.ai_conversation import AIConversation
    from models.analytics import LectureAnalytics
    from models.course import Course, Semester
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

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    title: str
    description: Optional[str] = None
    content: str  # Main lecture content/text
    chapter: Optional[str] = None  # Book chapter reference
    book_reference: Optional[str] = None  # Book name/reference
    lecture_type: LectureType
    status: LectureStatus = Field(default=LectureStatus.DRAFT)
    version: int = Field(default=1)  # Version control

    # Foreign keys
    course_id: str = Field(foreign_key="course.id")  # UUID
    semester_id: str = Field(foreign_key="semester.id")  # UUID
    teacher_id: str = Field(foreign_key="teacher.id")  # UUID

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None

    # Relationships
    course: Optional["Course"] = Relationship(back_populates="lectures")
    semester: Optional["Semester"] = Relationship(back_populates="lectures")
    teacher: Optional["Teacher"] = Relationship(back_populates="lectures")
    contents: List["LectureContent"] = Relationship(back_populates="lecture")
    conversations: List["AIConversation"] = Relationship(back_populates="lecture")
    analytics: List["LectureAnalytics"] = Relationship(back_populates="lecture")


class LectureContent(SQLModel, table=True):
    """File metadata for lecture materials stored in Supabase."""

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    lecture_id: str = Field(foreign_key="lecture.id")  # UUID
    file_name: str
    file_type: str  # pdf, pptx, docx, txt, etc.
    file_size: int  # in bytes
    storage_path: str  # Supabase storage path
    storage_bucket: str  # Supabase bucket name
    mime_type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    lecture: Optional["Lecture"] = Relationship(back_populates="contents")


# ==================== Request/Response Models ====================


class LectureGenerationRequest(SQLModel):
    """Request model for lecture generation from document."""

    document_id: str  # UUID of the source document
    course_id: str  # UUID of the course
    semester_id: str  # UUID of the semester
    title: str  # Title for the lecture
    description: str  # Description/overview from teacher


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
    content: str
    chapter: Optional[str] = None
    book_reference: Optional[str] = None
    lecture_type: LectureType
    status: LectureStatus
    version: int
    course_id: str  # UUID
    semester_id: str  # UUID
    teacher_id: str  # UUID
    created_at: datetime
    updated_at: datetime
    delivered_at: Optional[datetime] = None


class LectureUpdate(SQLModel):
    """Model for updating lecture data."""

    title: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    chapter: Optional[str] = None
    book_reference: Optional[str] = None
    status: Optional[LectureStatus] = None


class LectureDownloadResponse(SQLModel):
    """Response model for lecture download."""

    lecture_id: str
    title: str
    download_url: str
    file_name: str
    file_size: int
    created_at: str
