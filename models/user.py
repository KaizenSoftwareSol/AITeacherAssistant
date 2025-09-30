# models/user.py

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from enum import Enum

if TYPE_CHECKING:
    from models.university import University
    from models.ai_conversation import AIConversation
    from models.lecture import Lecture
    from models.document import Document
    from models.enrollment import Enrollment


class UserRole(str, Enum):
    """User roles in the system."""
    STUDENT = "STUDENT"  # Match database values
    TEACHER = "TEACHER"
    ADMIN = "ADMIN"


class UserBase(SQLModel):
    """Base user model with common fields."""
    email: str = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True)
    first_name: str
    last_name: str
    is_active: bool = Field(default=True)
    role: UserRole
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class User(UserBase, table=True):
    """User model for database."""
    id: Optional[str] = Field(default=None, primary_key=True)  # UUID string
    hashed_password: str
    university_id: Optional[str] = Field(default=None, foreign_key="university.id")  # UUID string
    
    # Relationships
    university: Optional["University"] = Relationship(back_populates="users")
    teacher_profile: Optional["Teacher"] = Relationship(back_populates="user")
    student_profile: Optional["Student"] = Relationship(back_populates="user")
    ai_conversations: List["AIConversation"] = Relationship(back_populates="user")


class Teacher(SQLModel, table=True):
    """Teacher profile with university association."""
    id: Optional[str] = Field(default=None, primary_key=True)  # UUID string
    user_id: str = Field(foreign_key="user.id", unique=True)  # UUID string
    university_id: str = Field(foreign_key="university.id")  # UUID string
    department: Optional[str] = None
    specialization: Optional[str] = None
    voice_config: Optional[str] = None  # JSON config for ElevenLabs
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="teacher_profile")
    university: Optional["University"] = Relationship(back_populates="teachers")
    lectures: List["Lecture"] = Relationship(back_populates="teacher")
    documents: List["Document"] = Relationship(back_populates="teacher")


class Student(SQLModel, table=True):
    """Student profile with university association."""
    id: Optional[str] = Field(default=None, primary_key=True)  # UUID string
    user_id: str = Field(foreign_key="user.id", unique=True)  # UUID string
    university_id: str = Field(foreign_key="university.id")  # UUID string
    student_id: str = Field(unique=True, index=True)  # University student ID
    year_of_study: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="student_profile")
    university: Optional["University"] = Relationship(back_populates="students")
    enrollments: List["Enrollment"] = Relationship(back_populates="student")
