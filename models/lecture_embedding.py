# models/lecture_embedding.py

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.lecture import Lecture


class LectureChunk(SQLModel, table=True):
    """
    Stores chunked lecture content for RAG (Retrieval-Augmented Generation).
    Each lecture is split into smaller chunks for efficient semantic search.
    """

    __tablename__ = "lecture_chunk"

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    lecture_id: str = Field(foreign_key="lecture.id")  # UUID
    chunk_index: int = Field(default=0)  # Order of chunk in the lecture
    content: str  # The actual text content of this chunk
    chunk_type: str = Field(default="CONTENT")  # CONTENT, SUMMARY, HEADING, etc.
    tokens_count: int = Field(default=0)  # Number of tokens in this chunk
    chunk_metadata: Optional[str] = None  # JSON metadata (page numbers, section titles, etc.)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    lecture: Optional["Lecture"] = Relationship(back_populates="chunks")
    embedding: Optional["LectureEmbedding"] = Relationship(
        back_populates="chunk", sa_relationship_kwargs={"uselist": False}
    )


class LectureEmbedding(SQLModel, table=True):
    """
    Stores vector embeddings for lecture chunks to enable semantic search.
    Used for RAG-based chatbot responses.
    """

    __tablename__ = "lecture_embedding"

    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    lecture_id: str = Field(foreign_key="lecture.id")  # UUID
    chunk_id: Optional[str] = Field(default=None, foreign_key="lecture_chunk.id")  # UUID
    # Note: embedding is stored as a PostgreSQL vector type (requires pgvector extension)
    # In Python, we'll handle it as a list of floats
    # The actual vector column is defined in the database migration
    embedding_model: str = Field(
        default="text-embedding-3-small"
    )  # Model used to generate embedding
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    lecture: Optional["Lecture"] = Relationship(sa_relationship_kwargs={"overlaps": "embeddings"})
    chunk: Optional["LectureChunk"] = Relationship(back_populates="embedding")


# ==================== Request/Response Models ====================


class LectureChunkCreate(SQLModel):
    """Request model for creating a lecture chunk."""

    lecture_id: str
    chunk_index: int
    content: str
    chunk_type: str = "CONTENT"
    tokens_count: int = 0
    chunk_metadata: Optional[str] = None


class LectureChunkRead(SQLModel):
    """Response model for reading lecture chunk data."""

    id: str
    lecture_id: str
    chunk_index: int
    content: str
    chunk_type: str
    tokens_count: int
    chunk_metadata: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LectureEmbeddingCreate(SQLModel):
    """Request model for creating a lecture embedding."""

    lecture_id: str
    chunk_id: Optional[str] = None
    embedding: list[float]  # Vector will be stored as PostgreSQL vector type
    embedding_model: str = "text-embedding-3-small"


class LectureSearchRequest(SQLModel):
    """Request model for semantic search in lecture content."""

    lecture_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=20)  # Number of results to return


class LectureSearchResult(SQLModel):
    """Single search result from semantic search."""

    chunk_id: str
    chunk_content: str
    chunk_index: int
    similarity_score: float
    chunk_metadata: Optional[str] = None


class LectureSearchResponse(SQLModel):
    """Response model for semantic search results."""

    lecture_id: str
    query: str
    results: list[LectureSearchResult]
    total_results: int


class LectureSummaryRequest(SQLModel):
    """Request model for generating or retrieving lecture summary."""

    lecture_id: str
    regenerate: bool = Field(
        default=False, description="Force regenerate summary even if exists"
    )


class LectureSummaryResponse(SQLModel):
    """Response model for lecture summary."""

    lecture_id: str
    summary: str
    generated_at: datetime


class CourseEnrollmentByCodeRequest(SQLModel):
    """Request model for student enrollment using course code."""

    course_code: str  # e.g., "CS101"
    semester_id: Optional[str] = None  # If None, use current/latest semester


class StudentCourseInfo(SQLModel):
    """Information about a course for student display."""

    course_id: str
    course_code: str
    course_name: str
    course_description: Optional[str] = None
    teacher_name: str  # "FirstName LastName"
    display_name: str  # "CourseName - Teacher Name"
    enrolled_at: datetime
    total_lectures: int = 0
    published_lectures: int = 0


class StudentLectureInfo(SQLModel):
    """Information about a lecture for student display."""

    lecture_id: str
    title: str
    description: Optional[str] = None
    summary: Optional[str] = None
    chapter: Optional[str] = None
    status: str
    created_at: datetime
    has_embeddings: bool = False  # Whether RAG is available for this lecture


class StudentCourseLecturesResponse(SQLModel):
    """Response model for getting all lectures in a student's course."""

    course_info: StudentCourseInfo
    lectures: list[StudentLectureInfo]
    total_count: int


class QuizGenerationRequest(SQLModel):
    """Request model for generating a quiz from lecture content."""

    lecture_id: str
    num_questions: int = Field(default=10, ge=1, le=50)
    question_types: Optional[list[str]] = None  # e.g., ["MULTIPLE_CHOICE", "TRUE_FALSE"]
    difficulty: str = Field(default="MEDIUM")  # EASY, MEDIUM, HARD
    focus_areas: Optional[list[str]] = (
        None  # Specific topics/chunks to focus on (chunk_ids or keywords)
    )


class QuizResultForChat(SQLModel):
    """Model for adding quiz results to chat history."""

    assessment_id: str
    submission_id: str
    score: float
    max_score: float
    percentage: float
    weak_areas: list[str]  # Topics/concepts where student struggled
    time_taken: Optional[int] = None  # in minutes


class ChatMessageWithQuizResult(SQLModel):
    """Extended chat message model that includes quiz results."""

    role: str  # SYSTEM
    content: str  # Text summary of quiz results
    quiz_result: Optional[QuizResultForChat] = None

