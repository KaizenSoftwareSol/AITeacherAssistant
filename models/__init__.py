# models/__init__.py

# Import all models for easy access
from .university import University
from .course import Course, Semester
from .user import User, Teacher, Student, UserRole
from .enrollment import Enrollment
from .lecture import Lecture, LectureContent, LectureStatus, LectureType
from .ai_conversation import AIConversation, ChatMessage, ConversationType, MessageRole
from .job_queue import JobQueue, JobStatus, JobType
from .analytics import LectureAnalytics, StudentEngagement, AIProcessingLog
from .assessment import Assessment, Question, AssessmentSubmission, AssessmentType, QuestionType
from .document import Document, DocumentType, DocumentStatus, DocumentCreate, DocumentRead, DocumentUpdate, WebsiteContent

# Export all models
__all__ = [
    # Core entities
    "University",
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
    "LectureStatus",
    "LectureType",
    
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
    "WebsiteContent",
]
