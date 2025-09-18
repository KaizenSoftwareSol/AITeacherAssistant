# auth/service.py

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from models.user import User, UserRole
from auth.models import UserCreate
from settings import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Authentication service for user management and JWT operations."""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    async def create_user(session: Session, user_create: UserCreate) -> User:
        """Create a new user."""
        # Check if user already exists
        existing_user = session.exec(
            select(User).where(User.email == user_create.email)
        ).first()
        if existing_user:
            raise ValueError("User with this email already exists")
        
        existing_username = session.exec(
            select(User).where(User.username == user_create.username)
        ).first()
        if existing_username:
            raise ValueError("User with this username already exists")
        
        # Create new user
        hashed_password = AuthService.get_password_hash(user_create.password)
        user = User(
            email=user_create.email,
            username=user_create.username,
            hashed_password=hashed_password,
            role=user_create.role,
            is_active=True
        )
        
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    
    @staticmethod
    def authenticate_user(session: Session, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password."""
        user = session.exec(select(User).where(User.email == email)).first()
        if not user:
            return None
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        return user
    
    @staticmethod
    def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        return session.exec(select(User).where(User.id == user_id)).first()
    
    @staticmethod
    def get_user_by_email(session: Session, email: str) -> Optional[User]:
        """Get a user by email."""
        return session.exec(select(User).where(User.email == email)).first()
    
    @staticmethod
    def update_user(session: Session, user_id: int, user_update: dict) -> Optional[User]:
        """Update a user."""
        user = session.exec(select(User).where(User.id == user_id)).first()
        if not user:
            return None
        
        for field, value in user_update.items():
            if hasattr(user, field) and value is not None:
                if field == "password":
                    setattr(user, "hashed_password", AuthService.get_password_hash(value))
                else:
                    setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    
    @staticmethod
    def delete_user(session: Session, user_id: int) -> bool:
        """Delete a user."""
        user = session.exec(select(User).where(User.id == user_id)).first()
        if not user:
            return False
        
        session.delete(user)
        session.commit()
        return True
