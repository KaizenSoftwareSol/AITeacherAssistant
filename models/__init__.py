# models/__init__.py

# Import all models for easy access
from .ai_conversation import (AIConversation, ChatMessage, ConversationType,
                              MessageRole)
from .analytics import AIProcessingLog, LectureAnalytics, StudentEngagement
from .assessment import (Assessment, AssessmentSubmission, AssessmentType,
                         Question, QuestionType)
from .course import Course, Semester
from .module import Module, ModuleCourse
from .document import (Document, DocumentCreate, DocumentRead, DocumentStatus,
                       DocumentType, DocumentUpdate)
from .enrollment import Enrollment
from .job_queue import JobQueue, JobStatus, JobType
from .lecture import (Lecture, LectureContent, LectureDownloadResponse,
                      LectureGenerationRequest, LectureGenerationResponse,
                      LectureRead, LectureStatus, LectureType, LectureUpdate)
from .lecture_embedding import LectureChunk, LectureEmbedding
from .notification import (Notification, NotificationCreate,
                           NotificationListResponse, NotificationRead,
                           NotificationSeverity, NotificationType,
                           NotificationUpdate, UnreadCountResponse)
from .university import University, UniversityType
from .user import Student, Teacher, User, UserRole

# Export all models
__all__ = [
    # Core entities
    "University",
    "UniversityType",
    "Module",
    "ModuleCourse",
    "Course",
    "Semester",
    "User",
    "Teacher",
    "Student",
    "UserRole",
    "Enrollment",
    # Lecture system
    "Lecture",
    "LectureContent",
    "LectureChunk",
    "LectureEmbedding",
    "LectureStatus",
    "LectureType",
    "LectureGenerationRequest",
    "LectureGenerationResponse",
    "LectureRead",
    "LectureUpdate",
    "LectureDownloadResponse",
    # AI & Chat
    "AIConversation",
    "ChatMessage",
    "ConversationType",
    "MessageRole",
    # Job processing
    "JobQueue",
    "JobStatus",
    "JobType",
    # Analytics
    "LectureAnalytics",
    "StudentEngagement",
    "AIProcessingLog",
    # Assessment
    "Assessment",
    "Question",
    "AssessmentSubmission",
    "AssessmentType",
    "QuestionType",
    # Document management
    "Document",
    "DocumentType",
    "DocumentStatus",
    "DocumentCreate",
    "DocumentRead",
    "DocumentUpdate",
    # Notifications
    "Notification",
    "NotificationType",
    "NotificationSeverity",
    "NotificationCreate",
    "NotificationRead",
    "NotificationUpdate",
    "NotificationListResponse",
    "UnreadCountResponse",
]
