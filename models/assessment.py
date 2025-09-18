# models/assessment.py

from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from enum import Enum


class AssessmentType(str, Enum):
    """Assessment type enumeration."""
    QUIZ = "quiz"
    ASSIGNMENT = "assignment"
    EXAM = "exam"
    PROJECT = "project"


class QuestionType(str, Enum):
    """Question type enumeration."""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    FILL_IN_BLANK = "fill_in_blank"


class Assessment(SQLModel, table=True):
    """Assessment entity for quizzes, assignments, and exams."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None
    assessment_type: AssessmentType
    course_id: int = Field(foreign_key="course.id")
    lecture_id: Optional[int] = Field(default=None, foreign_key="lecture.id")
    teacher_id: int = Field(foreign_key="teacher.id")
    
    # Assessment settings
    time_limit: Optional[int] = None  # in minutes
    max_attempts: int = Field(default=1)
    passing_score: float = Field(default=60.0)  # percentage
    is_published: bool = Field(default=False)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    due_date: Optional[datetime] = None
    
    # Relationships
    course: Optional["Course"] = Relationship()
    lecture: Optional["Lecture"] = Relationship()
    teacher: Optional["Teacher"] = Relationship()
    questions: List["Question"] = Relationship(back_populates="assessment")
    submissions: List["AssessmentSubmission"] = Relationship(back_populates="assessment")


class Question(SQLModel, table=True):
    """Individual questions within assessments."""
    id: Optional[int] = Field(default=None, primary_key=True)
    assessment_id: int = Field(foreign_key="assessment.id")
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
    assessment: Optional["Assessment"] = Relationship(back_populates="questions")


class AssessmentSubmission(SQLModel, table=True):
    """Student submissions for assessments."""
    id: Optional[int] = Field(default=None, primary_key=True)
    assessment_id: int = Field(foreign_key="assessment.id")
    student_id: int = Field(foreign_key="student.id")
    
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
    assessment: Optional["Assessment"] = Relationship(back_populates="submissions")
    student: Optional["Student"] = Relationship()
