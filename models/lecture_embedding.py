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
    semester_name: Optional[str] = None  # Populated for MEDICAL universities
    modules: Optional[list] = None  # Populated for MEDICAL universities


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
    topic: Optional[str] = None  # Topic name for grouping
    lecture_number: Optional[int] = None  # Sequential number within topic
    content: Optional[str] = None  # Full lecture content for reading
    pdf_file_name: Optional[str] = None
    pdf_file_size: Optional[int] = None
    pdf_download_url: Optional[str] = None


class StudentCourseLecturesResponse(SQLModel):
    """Response model for getting all lectures in a student's course."""

    course_info: StudentCourseInfo
    lectures: list[StudentLectureInfo]  # Flat list for backward compatibility
    grouped_by_topic: Optional[dict[str, list[StudentLectureInfo]]] = None  # Lectures grouped by topic
    lectures_without_topic: Optional[list[StudentLectureInfo]] = None  # Lectures without topic
    total_count: int


class QuizGenerationRequest(SQLModel):
    """Request model for generating a quiz from lecture content."""

    lecture_id: Optional[str] = None  # Optional when lecture_id is in path parameter
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


# ==================== Test Quiz Models ====================


class TestQuizCreateRequest(SQLModel):
    """Request model for creating a test quiz (teacher)."""

    title: str
    description: Optional[str] = None
    lecture_id: str  # The lecture this quiz is based on
    difficulty: str = "MEDIUM"  # EASY, MEDIUM, HARD
    time_limit: Optional[int] = None  # in minutes
    max_attempts: int = 1
    passing_score: float = 60.0
    due_date: datetime  # Deadline for submission
    show_leaderboard: bool = True


class TestQuizAIGenerateRequest(SQLModel):
    """Request model for AI-generating questions for a test quiz."""

    num_questions: int = 10
    question_types: Optional[list[str]] = None  # e.g., ["MULTIPLE_CHOICE", "TRUE_FALSE"]
    focus_areas: Optional[list[str]] = None  # Specific topics to focus on


class ManualQuestionCreateRequest(SQLModel):
    """Request model for adding a manual question to a test quiz."""

    question_text: str
    question_type: str = "MULTIPLE_CHOICE"
    points: float = 1.0
    options: list[str]
    correct_answer: str
    explanation: Optional[str] = None


class TestQuizResponse(SQLModel):
    """Response model for a test quiz."""

    assessment_id: str
    title: str
    description: Optional[str] = None
    lecture_id: str
    lecture_title: Optional[str] = None
    difficulty: str
    quiz_mode: str = "TEST"
    time_limit: Optional[int] = None
    max_attempts: int
    passing_score: float
    due_date: datetime
    is_published: bool
    show_leaderboard: bool
    questions_count: int
    created_at: datetime
    is_overdue: bool = False


class StudentSubmissionSummary(SQLModel):
    """Summary of a student's submission for teacher view."""

    student_id: str
    student_name: str
    student_email: Optional[str] = None
    submission_id: Optional[str] = None
    score: Optional[float] = None
    max_score: Optional[float] = None
    percentage: Optional[float] = None
    attempt_number: int = 0
    submitted_at: Optional[datetime] = None
    time_taken: Optional[int] = None
    is_submitted: bool = False
    is_graded: bool = False
    rank: Optional[int] = None


class QuestionResultDetail(SQLModel):
    """Detailed result for a single question in a submission."""

    question_id: str
    question_text: str
    question_type: str
    points_possible: float
    points_earned: float
    student_answer: Optional[str] = None
    correct_answer: str
    is_correct: bool
    explanation: Optional[str] = None


class DetailedSubmissionResponse(SQLModel):
    """Detailed view of a student's submission for teacher review."""

    submission_id: str
    assessment_id: str
    assessment_title: str
    student_id: str
    student_name: str
    student_email: Optional[str] = None
    score: float
    max_score: float
    percentage: float
    correct_count: int
    total_questions: int
    attempt_number: int
    time_taken: Optional[int] = None
    started_at: datetime
    submitted_at: Optional[datetime] = None
    question_results: list[QuestionResultDetail]


class LeaderboardEntry(SQLModel):
    """Entry in the quiz leaderboard."""

    rank: int
    student_id: str
    student_name: str
    # Score and percentage are ONLY shown for teacher view
    score: Optional[float] = None
    percentage: Optional[float] = None
    submitted_at: Optional[datetime] = None


class LeaderboardResponse(SQLModel):
    """Response model for quiz leaderboard."""

    assessment_id: str
    assessment_title: str
    total_participants: int
    leaderboard: list[LeaderboardEntry]
    # Only for teacher view
    average_score: Optional[float] = None
    highest_score: Optional[float] = None
    lowest_score: Optional[float] = None


class StudentTestQuizInfo(SQLModel):
    """Test quiz information for student view."""

    assessment_id: str
    title: str
    description: Optional[str] = None
    lecture_id: str
    lecture_title: Optional[str] = None
    difficulty: str
    time_limit: Optional[int] = None
    max_attempts: int
    passing_score: float
    due_date: datetime
    is_overdue: bool = False
    questions_count: int
    my_attempts: int = 0
    my_best_score: Optional[float] = None
    can_attempt: bool = True  # False if overdue or max attempts reached
