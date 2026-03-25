# models/ai_conversation.py
# AI conversation models - Temporarily disabled for dependency cleanup
# AI functionality will be restored soon!

# These models are commented out temporarily - will be restored when AI dependencies are added back

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.lecture import Lecture
    from models.user import User


class ConversationType(str, Enum):
    """Conversation type enumeration."""

    LECTURE_QA = "LECTURE_QA"
    ASSISTANT_CHAT = "ASSISTANT_CHAT"
    LIVE_SESSION = "LIVE_SESSION"


class MessageRole(str, Enum):
    """Message role enumeration."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class AIConversation(SQLModel, table=True):
    """AI conversation sessions for Q&A and chat."""

    __tablename__ = "ai_conversation"

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    user_id: int = Field(foreign_key="users.id")  # Integer FK for performance
    lecture_id: Optional[int] = Field(default=None, foreign_key="lecture.id")  # Integer FK for performance
    conversation_type: ConversationType
    session_id: str = Field(index=True)  # Unique session identifier
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="ai_conversations")
    lecture: "Lecture" = Relationship(back_populates="conversations")
    messages: List["ChatMessage"] = Relationship(back_populates="conversation")


class ChatMessage(SQLModel, table=True):
    """Individual chat messages within conversations."""

    __tablename__ = "chat_message"

    id: Optional[int] = Field(default=None, primary_key=True)  # Integer PK for performance
    uuid: Optional[str] = Field(default=None, unique=True, index=True)  # UUID for external APIs
    conversation_id: int = Field(foreign_key="ai_conversation.id")  # Integer FK for performance
    role: MessageRole
    content: str
    message_metadata: Optional[str] = None  # JSON metadata (tokens used, etc.)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    conversation: "AIConversation" = Relationship(back_populates="messages")
