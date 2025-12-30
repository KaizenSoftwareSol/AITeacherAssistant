# models/notification.py
"""
Notification model for the AITA platform.

Notifications keep Teachers and Students informed about important events
such as enrollments, quiz submissions, lecture publications, and result requests.
"""

from datetime import datetime
from enum import IntEnum
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


class NotificationSeverity(IntEnum):
    """Notification severity levels."""
    INFO = 1        # General information
    SUCCESS = 2     # Positive actions completed
    WARNING = 3     # Requires attention
    DANGER = 4      # Urgent/critical alerts


class NotificationType(IntEnum):
    """Notification type enumeration."""
    STUDENT_ENROLLED = 1
    PENDING = 2
    QUIZ_SUBMITTED = 3
    RESULT_REQUEST = 4
    LECTURE_PUBLISHED = 5
    QUIZ_PUBLISHED = 6
    RESULT_APPROVED = 7
    RESULT_REJECTED = 8
    NEW_ASSESSMENT_AVAILABLE = 9
    COURSE_UPDATE = 10
    QUIZ_DEADLINE_REMINDER = 11
    QUIZ_RESULTS_READY = 12
    LOW_QUIZ_SCORE = 13
    ENROLLMENT_CONFIRMED = 14


class Notification(SQLModel, table=True):
    """Notification entity for system notifications."""
    
    __tablename__ = "notification"
    
    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    user_id: str = Field(foreign_key="users.id")  # UUID - recipient of the notification
    title: str = Field(max_length=255)
    description: Optional[str] = None
    type: int  # NotificationType enum value
    severity: int = Field(default=1)  # NotificationSeverity enum value
    is_read: bool = Field(default=False)
    is_archived: bool = Field(default=False)
    feature_type: int = Field(default=101)  # For frontend categorization
    
    # Related entity info for deep linking
    related_entity_type: Optional[str] = None  # 'course', 'lecture', 'quiz', etc.
    related_entity_id: Optional[str] = None  # UUID of related entity
    action_url: Optional[str] = None  # Deep link URL
    
    # Additional metadata
    company_key: Optional[str] = None  # For multi-tenant support
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    read_at: Optional[datetime] = None


# ==================== Pydantic Models for API ====================


class NotificationCreate(BaseModel):
    """Schema for creating a notification."""
    user_id: str
    title: str
    description: Optional[str] = None
    type: int
    severity: int = NotificationSeverity.INFO
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    action_url: Optional[str] = None
    company_key: Optional[str] = None
    feature_type: int = 101


class NotificationRead(BaseModel):
    """Schema for reading a notification."""
    id: str
    title: str
    description: Optional[str]
    type: int
    severity: int
    isRead: bool  # Frontend expects camelCase
    isArchived: bool  # Frontend expects camelCase
    createdOn: datetime  # Frontend expects createdOn not created_at
    companyKey: Optional[str] = None
    
    class Config:
        from_attributes = True


class NotificationUpdate(BaseModel):
    """Schema for updating a notification."""
    is_read: Optional[bool] = None
    is_archived: Optional[bool] = None


class NotificationListResponse(BaseModel):
    """Paginated response for notification list."""
    notifications: list[NotificationRead]
    total: int
    page: int
    itemsPerPage: int


class UnreadCountResponse(BaseModel):
    """Response for unread notification count."""
    count: int

