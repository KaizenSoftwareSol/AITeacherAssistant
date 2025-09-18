# models/user.py

from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from enum import Enum


class UserRole(str, Enum):
    """User roles in the system."""
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


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
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str
    university_id: Optional[int] = Field(default=None, foreign_key="university.id")
    
    # Relationships
    university: Optional["University"] = Relationship(back_populates="users")
    teacher_profile: Optional["Teacher"] = Relationship(back_populates="user")
    student_profile: Optional["Student"] = Relationship(back_populates="user")
    ai_conversations: List["AIConversation"] = Relationship(back_populates="user")


class Teacher(SQLModel, table=True):
    """Teacher profile with university association."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", unique=True)
    university_id: int = Field(foreign_key="university.id")
    department: Optional[str] = None
    specialization: Optional[str] = None
    voice_config: Optional[str] = None  # JSON config for ElevenLabs
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="teacher_profile")
    university: Optional["University"] = Relationship(back_populates="teachers")
    lectures: List["Lecture"] = Relationship(back_populates="teacher")


class Student(SQLModel, table=True):
    """Student profile with university association."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", unique=True)
    university_id: int = Field(foreign_key="university.id")
    student_id: str = Field(unique=True, index=True)  # University student ID
    year_of_study: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="student_profile")
    university: Optional["University"] = Relationship(back_populates="students")
    enrollments: List["Enrollment"] = Relationship(back_populates="student")
