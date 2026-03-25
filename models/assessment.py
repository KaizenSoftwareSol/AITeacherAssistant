# models/assessment.py

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.course import Course
    from models.lecture import Lecture
    from models.user import Student, Teacher


class AssessmentType(str, Enum):
    """Assessment type enumeration."""

    QUIZ = "QUIZ"
    ASSIGNMENT = "ASSIGNMENT"
    EXAM = "EXAM"
    PROJECT = "PROJECT"


class QuizMode(str, Enum):
    """Quiz mode enumeration - distinguishes practice from graded quizzes."""

    PRACTICE = "PRACTICE"  # AI-generated practice quizzes, no deadline
    TEST = "TEST"  # Teacher-created or AI-generated tests with deadlines


class DifficultyLevel(str, Enum):
    """Difficulty level for quizzes."""

    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class QuestionType(str, Enum):
    """Question type enumeration."""

    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_ANSWER = "SHORT_ANSWER"
    ESSAY = "ESSAY"
    FILL_IN_BLANK = "FILL_IN_BLANK"


class Assessment(SQLModel, table=True):
    """Assessment entity for quizzes, assignments, and exams."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    title: str
    description: Optional[str] = None
    assessment_type: AssessmentType
    course_id: int = Field(foreign_key="course.id")  # Integer FK for performance
    lecture_id: Optional[int] = Field(default=None, foreign_key="lecture.id")  # Integer FK for performance
    teacher_id: int = Field(foreign_key="teacher.id")  # Integer FK for performance

    # Assessment settings
    time_limit: Optional[int] = None  # in minutes
    max_attempts: int = Field(default=1)
    passing_score: float = Field(default=60.0)  # percentage
    is_published: bool = Field(default=False)

    # Quiz-specific settings (NEW)
    quiz_mode: str = Field(default="PRACTICE")  # PRACTICE or TEST
    difficulty: str = Field(default="MEDIUM")  # EASY, MEDIUM, HARD
    is_default: bool = Field(default=False)  # True for auto-generated practice quizzes
    show_leaderboard: bool = Field(default=True)  # Whether to show leaderboard for TEST quizzes

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    due_date: Optional[datetime] = None

    # Relationships
    course: "Course" = Relationship()
    lecture: "Lecture" = Relationship()
    teacher: "Teacher" = Relationship()
    questions: List["Question"] = Relationship(back_populates="assessment")
    submissions: List["AssessmentSubmission"] = Relationship(
        back_populates="assessment"
    )


class Question(SQLModel, table=True):
    """Individual questions within assessments."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    assessment_id: int = Field(foreign_key="assessment.id")  # Integer FK for performance
    question_text: str
    question_type: QuestionType
    points: float = Field(default=1.0)
    order: int = Field(default=0)

    # Question options (for multiple choice, etc.)
    options: Optional[str] = None  # JSON array of options
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    assessment: "Assessment" = Relationship(back_populates="questions")


class AssessmentSubmission(SQLModel, table=True):
    """Student submissions for assessments."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    assessment_id: int = Field(foreign_key="assessment.id")  # Integer FK for performance
    student_id: int = Field(foreign_key="student.id")  # Integer FK for performance

    # Submission data
    answers: str  # JSON object with question_id -> answer mapping
    score: Optional[float] = None
    max_score: Optional[float] = None
    attempt_number: int = Field(default=1)
    time_taken: Optional[int] = None  # in minutes

    # Status
    is_submitted: bool = Field(default=False)
    is_graded: bool = Field(default=False)

    # Timestamps
    started_at: datetime = Field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    graded_at: Optional[datetime] = None

    # Relationships
    assessment: "Assessment" = Relationship(back_populates="submissions")
    student: "Student" = Relationship()


class ResultViewRequestStatus(str, Enum):
    """Status for result view requests."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ResultViewRequest(SQLModel, table=True):
    """
    Student requests to view graded quiz results.
    
    Students submit a request to view their results for a specific graded quiz.
    Teachers can approve or reject these requests.
    Once approved, students can view their detailed results.
    """
    __tablename__ = "result_view_request"

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    assessment_id: int = Field(foreign_key="assessment.id")  # Integer FK - the graded quiz
    student_id: int = Field(foreign_key="student.id")  # Integer FK - student requesting
    teacher_id: int = Field(foreign_key="teacher.id")  # Integer FK - teacher who owns the quiz
    
    # Request details
    status: str = Field(default="PENDING")  # PENDING, APPROVED, REJECTED
    request_message: Optional[str] = None  # Optional message from student
    response_message: Optional[str] = None  # Optional message from teacher when approving/rejecting
    
    # Timestamps
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    responded_at: Optional[datetime] = None
    
    # Relationships
    assessment: "Assessment" = Relationship()
    student: "Student" = Relationship()
    teacher: "Teacher" = Relationship()
