# auth/service.py

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from auth.models import UserCreate, UserRead
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

        # Determine university
        university_id = None
        if user_create.university_id:
            university = db.get_record_by_id("university", user_create.university_id)
            if not university:
                raise ValueError("Selected university was not found")
            university_id = university.get("id")
        elif user_create.university_name:
            university_name = user_create.university_name.strip()
            if not university_name:
                raise ValueError("University name cannot be empty")

            existing_universities = db.get_records(
                "university", {"name": university_name}
            )
            if existing_universities:
                university_id = existing_universities[0]["id"]
            else:
                new_university = {
                    "name": university_name,
                }
                if user_create.university_location:
                    new_university["location"] = user_create.university_location.strip()

                university_result = db.create_record("university", new_university)
                university_id = university_result.get("id")
        else:
            raise ValueError("University selection is required")

        if not university_id:
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

        user_id = user_result.get("id")

        # Create role-specific profiles
        if user_create.role == UserRole.TEACHER:
            teacher_payload = {
                "user_id": user_id,
                "university_id": university_id,
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
                "user_id": user_id,
                "university_id": university_id,
                "student_id": student_id,
            }

            if user_create.year_of_study is not None:
                student_payload["year_of_study"] = user_create.year_of_study

            db.create_record("student", student_payload)

        return User(**user_result)

    @staticmethod
    def to_user_read(db, user: User) -> UserRead:
        """Convert a User model to UserRead with profile enrichment."""

        user_dict = {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "role": user.role,
            "university_id": getattr(user, "university_id", None),
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
                    result = (
                        admin_client.table("teacher")
                        .select("department, specialization")
                        .eq("user_id", str(user.id))
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
                    result = (
                        admin_client.table("student")
                        .select("student_id, year_of_study")
                        .eq("user_id", str(user.id))
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
