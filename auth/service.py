# auth/service.py

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from auth.models import UserCreate
from models.user import User, UserRole
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
    def create_access_token(
        data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt

    @staticmethod
    async def create_user(db, user_create: UserCreate) -> User:
        """Create a new user."""
        # Check if user already exists
        existing_user = db.get_user_by_email(user_create.email)
        if existing_user:
            raise ValueError("User with this email already exists")

        # Check if username already exists
        users = db.get_records("users", {"username": user_create.username})
        if users:
            raise ValueError("User with this username already exists")

        # Create new user data
        hashed_password = AuthService.get_password_hash(user_create.password)
        user_data = {
            "email": user_create.email,
            "username": user_create.username,
            "hashed_password": hashed_password,
            "role": user_create.role.value,
            "is_active": True,
            "first_name": getattr(user_create, "first_name", ""),
            "last_name": getattr(user_create, "last_name", ""),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Create user in Supabase
        user_result = db.create_user(user_data)
        return User(**user_result)

    @staticmethod
    def authenticate_user(db, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password."""
        user_data = db.get_user_by_email(email)
        if not user_data:
            return None

        if not AuthService.verify_password(
            password, user_data.get("hashed_password", "")
        ):
            return None

        return User(**user_data)

    @staticmethod
    def get_user_by_id(db, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        user_data = db.get_user_by_id(user_id)
        if not user_data:
            return None
        return User(**user_data)

    @staticmethod
    def get_user_by_email(db, email: str) -> Optional[User]:
        """Get a user by email."""
        user_data = db.get_user_by_email(email)
        if not user_data:
            return None
        return User(**user_data)

    @staticmethod
    def update_user(db, user_id: int, user_update: dict) -> Optional[User]:
        """Update a user."""
        user_data = db.get_user_by_id(user_id)
        if not user_data:
            return None

        # Prepare update data
        update_data = {}
        for field, value in user_update.items():
            if value is not None:
                if field == "password":
                    update_data["hashed_password"] = AuthService.get_password_hash(
                        value
                    )
                else:
                    update_data[field] = value

        update_data["updated_at"] = datetime.utcnow().isoformat()

        # Update user in Supabase
        updated_user = db.update_user(user_id, update_data)
        if not updated_user:
            return None

        return User(**updated_user)

    @staticmethod
    def delete_user(db, user_id: int) -> bool:
        """Delete a user."""
        return db.delete_user(user_id)
