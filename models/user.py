# models/user.py

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.ai_conversation import AIConversation
    from models.document import Document
    from models.enrollment import Enrollment
    from models.lecture import Lecture
    from models.university import University


class UserRole(str, Enum):
    """User roles in the system."""

    STUDENT = "STUDENT"  # Match database values
    TEACHER = "TEACHER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"  # System administrator for onboarding universities


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

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    hashed_password: str
    university_id: Optional[int] = Field(
        default=None, foreign_key="university.id"
    )  # Integer FK for performance

    # Relationships
    university: "University" = Relationship(back_populates="users")
    teacher_profile: "Teacher" = Relationship(back_populates="user")
    student_profile: "Student" = Relationship(back_populates="user")
    ai_conversations: List["AIConversation"] = Relationship(back_populates="user")


class Teacher(SQLModel, table=True):
    """Teacher profile with university association."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    user_id: int = Field(foreign_key="users.id", unique=True)  # Integer FK for performance
    university_id: int = Field(foreign_key="university.id")  # Integer FK for performance
    department: Optional[str] = None
    specialization: Optional[str] = None
    voice_config: Optional[str] = None  # JSON config for ElevenLabs
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="teacher_profile")
    university: "University" = Relationship(back_populates="teachers")
    lectures: List["Lecture"] = Relationship(back_populates="teacher")
    documents: List["Document"] = Relationship(back_populates="teacher")


class Student(SQLModel, table=True):
    """Student profile with university association."""

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    user_id: int = Field(foreign_key="users.id", unique=True)  # Integer FK for performance
    university_id: int = Field(foreign_key="university.id")  # Integer FK for performance
    student_id: str = Field(unique=True, index=True)  # University student ID
    year_of_study: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="student_profile")
    university: "University" = Relationship(back_populates="students")
    enrollments: List["Enrollment"] = Relationship(back_populates="student")
