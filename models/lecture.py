# models/lecture.py

from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from enum import Enum


class LectureStatus(str, Enum):
    """Lecture status enumeration."""
    DRAFT = "draft"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    DELIVERED = "delivered"


class LectureType(str, Enum):
    """Lecture type enumeration."""
    AI_GENERATED = "ai_generated"
    TEACHER_RECORDED = "teacher_recorded"


class Lecture(SQLModel, table=True):
    """Lecture entity for both AI-generated and teacher-recorded lectures."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None
    content: str  # Main lecture content/text
    chapter: Optional[str] = None  # Book chapter reference
    book_reference: Optional[str] = None  # Book name/reference
    lecture_type: LectureType
    status: LectureStatus = Field(default=LectureStatus.DRAFT)
    version: int = Field(default=1)  # Version control
    
    # Foreign keys
    course_id: int = Field(foreign_key="course.id")
    semester_id: int = Field(foreign_key="semester.id")
    teacher_id: int = Field(foreign_key="teacher.id")
    
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
    id: Optional[int] = Field(default=None, primary_key=True)
    lecture_id: int = Field(foreign_key="lecture.id")
    file_name: str
    file_type: str  # pdf, pptx, docx, txt, etc.
    file_size: int  # in bytes
    storage_path: str  # Supabase storage path
    storage_bucket: str  # Supabase bucket name
    mime_type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    lecture: Optional["Lecture"] = Relationship(back_populates="contents")
