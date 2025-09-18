# models/ai_conversation.py

from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from enum import Enum


class ConversationType(str, Enum):
    """Conversation type enumeration."""
    LECTURE_QA = "lecture_qa"
    ASSISTANT_CHAT = "assistant_chat"
    LIVE_SESSION = "live_session"


class MessageRole(str, Enum):
    """Message role enumeration."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AIConversation(SQLModel, table=True):
    """AI conversation sessions for Q&A and chat."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    lecture_id: Optional[int] = Field(default=None, foreign_key="lecture.id")
    conversation_type: ConversationType
    session_id: str = Field(index=True)  # Unique session identifier
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="ai_conversations")
    lecture: Optional["Lecture"] = Relationship(back_populates="conversations")
    messages: List["ChatMessage"] = Relationship(back_populates="conversation")


class ChatMessage(SQLModel, table=True):
    """Individual chat messages within conversations."""
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="aiconversation.id")
    role: MessageRole
    content: str
    message_metadata: Optional[str] = None  # JSON metadata (tokens used, etc.)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    conversation: Optional["AIConversation"] = Relationship(back_populates="messages")
