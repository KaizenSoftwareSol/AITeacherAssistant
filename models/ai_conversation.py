# models/ai_conversation.py
# AI conversation models - Temporarily disabled for dependency cleanup
# AI functionality will be restored soon!

# These models are commented out temporarily - will be restored when AI dependencies are added back

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from enum import Enum

if TYPE_CHECKING:
    from models.user import User
    from models.lecture import Lecture


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
    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    user_id: str = Field(foreign_key="user.id")  # UUID
    lecture_id: Optional[str] = Field(default=None, foreign_key="lecture.id")  # UUID
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
    id: Optional[str] = Field(default=None, primary_key=True)  # UUID
    conversation_id: str = Field(foreign_key="aiconversation.id")  # UUID
    role: MessageRole
    content: str
    message_metadata: Optional[str] = None  # JSON metadata (tokens used, etc.)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    conversation: Optional["AIConversation"] = Relationship(back_populates="messages")
