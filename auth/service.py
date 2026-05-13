# auth/service.py

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from auth.models import UserCreate, UserRead
from models.user import User, UserRole
from settings import settings

# Import all models to ensure relationships are properly initialized
# This prevents SQLAlchemy relationship errors when creating User objects
try:
    from models.lecture_embedding import LectureChunk, LectureEmbedding  # noqa: F401
except ImportError:
    pass  # Models may not be needed for user creation

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=10)


class AuthService:
    """Authentication service for user management and JWT operations."""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
        """Verify a password without blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, pwd_context.verify, plain_password, hashed_password)

    @staticmethod
    async def authenticate_user_async(db, email: str, password: str) -> Optional["User"]:
        """Authenticate a user without blocking the event loop during bcrypt."""
        user_data = db.get_user_by_email(email.lower())
        if not user_data:
            return None
        if not await AuthService.verify_password_async(password, user_data.get("hashed_password", "")):
            return None
        return User(**user_data)

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
    def create_activation_token(user_id: str) -> str:
        """
        Create a one-time activation token for password setup.
        
        Token expires in 14 days and includes user_id and purpose.
        """
        expires_delta = timedelta(days=14)
        data = {
            "sub": str(user_id),
            "purpose": "activation",
            "type": "activation_token"
        }
        return AuthService.create_access_token(data, expires_delta=expires_delta)
    
    @staticmethod
    def verify_activation_token(token: str) -> Optional[str]:
        """
        Verify and extract user_id from activation token.
        
        Returns:
            user_id if token is valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
            # Verify token purpose
            if payload.get("purpose") != "activation" or payload.get("type") != "activation_token":
                return None
            user_id: str = payload.get("sub")
            return user_id
        except JWTError:
            return None
    
    @staticmethod
    def create_enrollment_token(student_id: str, course_id: str, semester_id: str) -> str:
        """
        Create a one-time enrollment token for course enrollment.
        
        Token expires in 30 days and includes student_id, course_id, and semester_id.
        """
        expires_delta = timedelta(days=30)
        data = {
            "student_id": str(student_id),
            "course_id": str(course_id),
            "semester_id": str(semester_id),
            "purpose": "enrollment",
            "type": "enrollment_token"
        }
        return AuthService.create_access_token(data, expires_delta=expires_delta)
    
    @staticmethod
    def verify_enrollment_token(token: str) -> Optional[dict]:
        """
        Verify and extract enrollment data from token.
        
        Returns:
            dict with student_id, course_id, semester_id if token is valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
            # Verify token purpose
            if payload.get("purpose") != "enrollment" or payload.get("type") != "enrollment_token":
                return None
            return {
                "student_id": payload.get("student_id"),
                "course_id": payload.get("course_id"),
                "semester_id": payload.get("semester_id")
            }
        except JWTError:
            return None

    @staticmethod
    async def create_user(db, user_create: UserCreate) -> User:
        """Create a new user."""
        # Normalize email to lowercase
        user_create.email = user_create.email.lower()

        # Check if user already exists
        existing_user = db.get_user_by_email(user_create.email)
        if existing_user:
            raise ValueError("User with this email already exists")

        # Check if username already exists
        users = db.get_records("users", {"username": user_create.username})
        if users:
            raise ValueError("User with this username already exists")

        # Determine university (not required for SYSTEM users)
        university_id = None
        if user_create.role == UserRole.SYSTEM:
            # System users don't belong to any university
            university_id = None
        elif user_create.university_id:
            # Convert UUID to integer ID if needed, then query for integer ID
            from utils.id_converter import IDConverter
            university_int_id = user_create.university_id
            if IDConverter.is_uuid(user_create.university_id):
                university_int_id = await IDConverter.uuid_to_int(db, "university", user_create.university_id)
                if not university_int_id:
                    raise ValueError("Selected university was not found")
            
            # Query university directly to get integer ID
            university_result = (
                db.get_admin_client().table("university")
                .select("id")
                .eq("id", university_int_id)
                .execute()
            )
            if not university_result.data:
                raise ValueError("Selected university was not found")
            university_id = university_result.data[0]["id"]  # Integer ID for FK
        elif user_create.university_name:
            university_name = user_create.university_name.strip()
            if not university_name:
                raise ValueError("University name cannot be empty")

            # Query directly to get integer ID
            existing_universities_result = (
                db.get_admin_client().table("university")
                .select("id")
                .eq("name", university_name)
                .execute()
            )
            if existing_universities_result.data:
                university_id = existing_universities_result.data[0]["id"]  # Integer ID
            else:
                new_university = {
                    "name": university_name,
                }
                if user_create.university_location:
                    new_university["location"] = user_create.university_location.strip()

                university_result = db.get_admin_client().table("university").insert(new_university).execute()
                if not university_result.data:
                    raise ValueError("Failed to create university")
                university_id = university_result.data[0]["id"]  # Integer ID from database
        else:
            raise ValueError("University selection is required")

        # Only validate university_id for non-SYSTEM users
        if user_create.role != UserRole.SYSTEM and not university_id:
            raise ValueError("Unable to resolve university for the new user")

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
            "university_id": university_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Create user in Supabase
        user_result = db.create_user(user_data)
        if not user_result:
            raise ValueError("Failed to create user")

        # db.create_user returns UUID in 'id' field for API compatibility
        # We need integer ID for foreign keys
        user_id_uuid = user_result.get("id")
        user_id = user_result.get("id")
        
        # Convert UUID to integer ID if needed
        if isinstance(user_id, str):
            from utils.id_converter import IDConverter
            if IDConverter.is_uuid(user_id):
                user_id = await IDConverter.uuid_to_int(db, "users", user_id)
                if not user_id:
                    raise ValueError("Failed to convert user UUID to integer ID")
            else:
                try:
                    user_id = int(user_id)
                except ValueError:
                    raise ValueError(f"Invalid user_id format: {user_id}")

        # Create role-specific profiles
        if user_create.role == UserRole.TEACHER:
            teacher_payload = {
                "user_id": user_id,  # Integer FK
                "university_id": university_id,  # Integer FK
            }
            if user_create.department:
                teacher_payload["department"] = user_create.department.strip()
            if user_create.specialization:
                teacher_payload["specialization"] = user_create.specialization.strip()

            db.create_record("teacher", teacher_payload)

        elif user_create.role == UserRole.STUDENT:
            if not user_create.student_id:
                raise ValueError("Student ID is required for student signup")

            student_id = user_create.student_id.strip()
            if not student_id:
                raise ValueError("Student ID cannot be empty")

            existing_student = db.get_records(
                "student", {"student_id": student_id}
            )
            if existing_student:
                raise ValueError("A student with this student ID already exists")

            student_payload = {
                "user_id": user_id,  # Integer FK
                "university_id": university_id,  # Integer FK
                "student_id": student_id,
            }

            if user_create.year_of_study is not None:
                student_payload["year_of_study"] = user_create.year_of_study

            db.create_record("student", student_payload)

        # Create User object without triggering full relationship initialization
        # This avoids SQLAlchemy relationship errors when models aren't fully loaded
        # Parse datetime strings if they exist
        from utils.datetime_helpers import parse_datetime_safe
        
        created_at_val = user_result.get("created_at")
        created_at_parsed = parse_datetime_safe(created_at_val)
        
        updated_at_val = user_result.get("updated_at")
        updated_at_parsed = parse_datetime_safe(updated_at_val)
        
        # Create User with minimal initialization to avoid relationship errors
        user = User(
            id=user_result.get("id"),
            email=user_result.get("email"),
            username=user_result.get("username"),
            first_name=user_result.get("first_name", ""),
            last_name=user_result.get("last_name", ""),
            is_active=user_result.get("is_active", True),
            role=UserRole(user_result.get("role")),
            hashed_password=user_result.get("hashed_password", ""),
            university_id=user_result.get("university_id"),
            created_at=created_at_parsed,
            updated_at=updated_at_parsed,
        )
        
        return user

    @staticmethod
    def to_user_read(db, user: User) -> UserRead:
        """Convert a User model to UserRead with profile enrichment."""

        # Use UUID for external API responses (not integer ID)
        user_uuid = user.uuid if hasattr(user, "uuid") and user.uuid else str(user.id)
        
        # Convert university_id to UUID if it's an integer
        university_id_value = getattr(user, "university_id", None)
        university_uuid = None
        if university_id_value is not None:
            # If it's an integer, we need to get the UUID from the university table
            # For now, return as string (will be converted to UUID after migration)
            # After migration, we'll need to query the university table to get UUID
            university_uuid = str(university_id_value)  # Temporary - will be UUID after migration
        
        user_dict = {
            "id": user_uuid,  # Return UUID, not integer ID
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "role": user.role,
            "university_id": university_uuid,  # Will be UUID after migration
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "department": None,
            "specialization": None,
            "student_id": None,
            "year_of_study": None,
        }

        # Teacher details
        teacher_profile = getattr(user, "teacher_profile", None)
        if teacher_profile:
            user_dict["department"] = getattr(teacher_profile, "department", None)
            user_dict["specialization"] = getattr(
                teacher_profile, "specialization", None
            )
        elif user.role in [UserRole.TEACHER, UserRole.ADMIN]:
            try:
                admin_client = getattr(db, "admin_client", None)
                if admin_client:
                    # Use integer ID for database query (after migration)
                    user_id_for_query = user.id if isinstance(user.id, int) else int(user.id) if str(user.id).isdigit() else user.id
                    result = (
                        admin_client.table("teacher")
                        .select("department, specialization")
                        .eq("user_id", user_id_for_query)
                        .limit(1)
                        .execute()
                    )
                    if result.data:
                        teacher_data = result.data[0]
                        user_dict["department"] = teacher_data.get("department")
                        user_dict["specialization"] = teacher_data.get(
                            "specialization"
                        )
            except Exception:
                pass

        # Student details
        student_profile = getattr(user, "student_profile", None)
        if student_profile:
            user_dict["student_id"] = getattr(student_profile, "student_id", None)
            user_dict["year_of_study"] = getattr(
                student_profile, "year_of_study", None
            )
        elif user.role == UserRole.STUDENT:
            try:
                admin_client = getattr(db, "admin_client", None)
                if admin_client:
                    # Use integer ID for database query (after migration)
                    user_id_for_query = user.id if isinstance(user.id, int) else int(user.id) if str(user.id).isdigit() else user.id
                    result = (
                        admin_client.table("student")
                        .select("student_id, year_of_study")
                        .eq("user_id", user_id_for_query)
                        .limit(1)
                        .execute()
                    )
                    if result.data:
                        student_data = result.data[0]
                        user_dict["student_id"] = student_data.get("student_id")
                        user_dict["year_of_study"] = student_data.get("year_of_study")
            except Exception:
                pass

        return UserRead.model_validate(user_dict)

    @staticmethod
    def authenticate_user(db, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password."""
        user_data = db.get_user_by_email(email.lower())
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
