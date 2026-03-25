from typing import Annotated, Union

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from models.user import User, UserRole
from services.cache_service import cache, cached
from settings import settings
from utils.db import get_db

security = HTTPBearer()


def _get_cached_user_by_id(db, user_id: Union[int, str]) -> dict | None:
    """Get user by ID with caching (handles both integer IDs and UUID strings)."""
    # Determine if it's a UUID or integer ID
    if isinstance(user_id, str):
        # Check if it's a UUID (contains hyphens) or an integer string
        if "-" in user_id or len(user_id) > 10:
            # Likely a UUID - use UUID string as cache key
            cache_key = f"user_by_uuid:{user_id}"
        else:
            # Try to parse as integer
            try:
                user_id = int(user_id)
                cache_key = f"user_by_id:{user_id}"
            except ValueError:
                # Not a valid integer, treat as UUID
                cache_key = f"user_by_uuid:{user_id}"
    else:
        # Integer ID
        cache_key = f"user_by_id:{user_id}"
    
    # Check cache first
    cached_user = cache.get("users", cache_key)
    if cached_user is not None:
        return cached_user
    
    # Fetch from database (db.get_user_by_id handles both UUIDs and integer IDs)
    user_data = db.get_user_by_id(user_id)
    
    # Cache the result (even None to prevent repeated lookups)
    if user_data:
        cache.set("users", user_data, cache_key, ttl=60)
    
    return user_data


def _get_cached_teacher_profile(db, user_id: Union[int, str]) -> dict | None:
    """Get teacher profile by user_id with caching (uses integer ID)."""
    # Convert to integer if needed
    user_id_int = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else user_id
    cache_key = f"teacher_by_user:{user_id_int}"
    
    # Check cache first
    cached_teacher = cache.get("teachers", cache_key)
    if cached_teacher is not None:
        return cached_teacher if cached_teacher != "__NONE__" else None
    
    # Fetch from database
    try:
        teacher_result = (
            db.admin_client.table("teacher")
            .select("*")
            .eq("user_id", user_id_int)
            .execute()
        )
        
        if teacher_result.data and len(teacher_result.data) > 0:
            teacher_data = teacher_result.data[0]
            cache.set("teachers", teacher_data, cache_key, ttl=300)
            return teacher_data
        else:
            # Cache the absence to avoid repeated lookups
            cache.set("teachers", "__NONE__", cache_key, ttl=300)
            return None
    except Exception as e:
        print(f"Warning: Could not load teacher profile: {e}")
        return None


class AuthDependency:
    @staticmethod
    async def get_current_user(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db=Depends(get_db),
    ) -> User:
        """
        Dependency to get the current authenticated user from the JWT token.
        Uses caching for improved performance.
        """
        # Standard header for 401 errors
        authenticate_header = {"WWW-Authenticate": "Bearer"}
        try:
            token = credentials.credentials
            
            # Check if we have a cached user for this token
            token_hash = hash(token) % 10**8  # Simple hash for cache key
            cached_result = cache.get("auth", "token", token_hash)
            if cached_result is not None:
                user = cached_result
                request.state.user = user
                return user
            
            # Decode token
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )

            user_id: str = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials - Invalid token structure",
                    headers=authenticate_header,
                )

            # Get user from cache or database
            user_data = _get_cached_user_by_id(db, user_id)

            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers=authenticate_header,
                )

            if not user_data.get("is_active", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Inactive user",
                )

            # Convert dict to User object
            from models.user import Teacher

            # Create basic user object
            user_dict = {
                "id": user_data.get("id"),
                "email": user_data.get("email"),
                "username": user_data.get("username"),
                "first_name": user_data.get("first_name", ""),
                "last_name": user_data.get("last_name", ""),
                "is_active": user_data.get("is_active", True),
                "role": UserRole(user_data.get("role")),
                "created_at": user_data.get("created_at"),
                "updated_at": user_data.get("updated_at"),
                "university_id": user_data.get("university_id"),
                "hashed_password": user_data.get("hashed_password", ""),
            }

            # Create user object without relationships initially
            user = User(**user_dict)

            # Load teacher profile if user is a teacher or admin (cached)
            if user.role in [UserRole.TEACHER, UserRole.ADMIN]:
                teacher_data = _get_cached_teacher_profile(db, user.id)
                
                if teacher_data:
                    teacher_dict = {
                        "id": teacher_data.get("id"),
                        "user_id": teacher_data.get("user_id"),
                        "university_id": teacher_data.get("university_id"),
                        "department": teacher_data.get("department"),
                        "specialization": teacher_data.get("specialization"),
                        "voice_config": teacher_data.get("voice_config"),
                        "created_at": teacher_data.get("created_at"),
                        "updated_at": teacher_data.get("updated_at"),
                    }
                    user.teacher_profile = Teacher(**teacher_dict)
                else:
                    user.teacher_profile = None
            else:
                user.teacher_profile = None

            # Cache the complete user object for this token (5 min TTL)
            cache.set("auth", user, "token", token_hash, ttl=300)

            # Add user object to request state
            request.state.user = user
            return user

        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - Token error",
                headers=authenticate_header,
            )
        except HTTPException:
            raise
        except Exception as e:
            print(f"Unexpected authentication error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during authentication",
            )

    @staticmethod
    def check_roles(allowed_roles: list[UserRole]):
        """
        Dependency factory for role-based access control
        """

        async def role_checker(
            user: User = Depends(AuthDependency.get_current_user),
        ) -> User:
            if user.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient Permissions",
                )
            return user

        return role_checker


# Common dependencies (remain the same)
get_current_user = AuthDependency.get_current_user
require_admin = AuthDependency.check_roles([UserRole.ADMIN])
require_teacher = AuthDependency.check_roles([UserRole.TEACHER, UserRole.ADMIN])
require_user = AuthDependency.check_roles(
    [UserRole.STUDENT, UserRole.TEACHER, UserRole.ADMIN]
)
require_system = AuthDependency.check_roles([UserRole.SYSTEM])

# Type hints for dependency injection (remain the same)
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
TeacherUser = Annotated[User, Depends(require_teacher)]
AnyUser = Annotated[User, Depends(require_user)]
SystemUser = Annotated[User, Depends(require_system)]