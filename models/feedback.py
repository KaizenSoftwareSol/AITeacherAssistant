from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FeedbackFeatureArea(str, Enum):
    LECTURE_GENERATION = "LECTURE_GENERATION"
    RESULT_TRACKING = "RESULT_TRACKING"
    LECTURE_CREATION = "LECTURE_CREATION"
    ASSESSMENTS = "ASSESSMENTS"
    COURSES = "COURSES"
    NOTIFICATIONS = "NOTIFICATIONS"
    OTHER = "OTHER"


class FeedbackDifficultyLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKER = "BLOCKER"


class FeedbackStatus(str, Enum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESPONDED = "RESPONDED"
    CLOSED = "CLOSED"


class FeedbackAttachment(BaseModel):
    url: str
    path: str
    filename: str
    mimeType: str
    size: int


class FeedbackCreate(BaseModel):
    feature_area: FeedbackFeatureArea
    difficulty_level: FeedbackDifficultyLevel
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=5000)


class FeedbackUpdate(BaseModel):
    feature_area: Optional[FeedbackFeatureArea] = None
    difficulty_level: Optional[FeedbackDifficultyLevel] = None
    title: Optional[str] = Field(default=None, min_length=5, max_length=200)
    description: Optional[str] = Field(default=None, min_length=10, max_length=5000)


class FeedbackResponseCreate(BaseModel):
    response: str = Field(min_length=3, max_length=5000)
    status: FeedbackStatus = FeedbackStatus.RESPONDED


class FeedbackStatusUpdate(BaseModel):
    status: FeedbackStatus


class FeedbackRead(BaseModel):
    id: str
    user_id: str
    user_name: str
    user_role: str
    feature_area: FeedbackFeatureArea
    difficulty_level: FeedbackDifficultyLevel
    title: str
    description: str
    attachments: list[FeedbackAttachment] = []
    status: FeedbackStatus
    system_response: Optional[str] = None
    responded_by_user_id: Optional[str] = None
    responded_by_user_name: Optional[str] = None
    responded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class FeedbackListResponse(BaseModel):
    items: list[FeedbackRead]
    total: int
    page: int
    itemsPerPage: int


def map_feedback_record(record: dict[str, Any], user_name: str = "", responder_name: str = "") -> FeedbackRead:
    attachments = record.get("attachments") or []
    return FeedbackRead(
        id=str(record.get("uuid") or record.get("id")),
        user_id=str(record.get("user_id")),
        user_name=user_name,
        user_role=record.get("user_role"),
        feature_area=record.get("feature_area"),
        difficulty_level=record.get("difficulty_level"),
        title=record.get("title", ""),
        description=record.get("description", ""),
        attachments=[FeedbackAttachment(**a) for a in attachments if isinstance(a, dict)],
        status=record.get("status"),
        system_response=record.get("system_response"),
        responded_by_user_id=str(record.get("responded_by_user_id")) if record.get("responded_by_user_id") else None,
        responded_by_user_name=responder_name or None,
        responded_at=record.get("responded_at"),
        created_at=record.get("created_at"),
        updated_at=record.get("updated_at"),
    )
