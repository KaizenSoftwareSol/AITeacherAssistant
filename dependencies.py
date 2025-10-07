from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from models.user import User, UserRole
from settings import settings
from utils.db import get_db

security = HTTPBearer()


class AuthDependency:
    @staticmethod
    async def get_current_user(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db=Depends(get_db),
    ) -> User:
        """
        Dependency to get the current authenticated user from the JWT token
        """
        # Standard header for 401 errors
        authenticate_header = {"WWW-Authenticate": "Bearer"}
        try:
            token = credentials.credentials
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )

            user_id: str = payload.get("sub")
            if user_id is None:
                # Raise HTTPException for invalid token
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials - Invalid token structure",
                    headers=authenticate_header,
                )

            # Get user from Supabase database
            # Note: user_id can be either UUID string or integer depending on database
            user_data = db.get_user_by_id(user_id)

            if not user_data:
                # Raise HTTPException for user not found
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,  # Often 401 or 404 depending on desired security feedback
                    detail="User not found",
                    headers=authenticate_header,
                )

            if not user_data.get("is_active", False):
                # Raise HTTPException for inactive user
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Inactive user",
                )

            # Convert dict to User object
            # Don't try to create full User object with relationships
            # Just create a basic user dict that we can work with
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

            # Load teacher profile if user is a teacher or admin
            if user.role in [UserRole.TEACHER, UserRole.ADMIN]:
                try:
                    # Query teacher profile by user_id
                    teacher_result = (
                        db.admin_client.table("teacher")
                        .select("*")
                        .eq("user_id", str(user.id))
                        .execute()
                    )

                    if teacher_result.data and len(teacher_result.data) > 0:
                        teacher_data = teacher_result.data[0]
                        # Create a simple teacher object (not full model with relationships)
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
                except Exception as e:
                    print(f"Warning: Could not load teacher profile: {e}")
                    import traceback

                    traceback.print_exc()
                    user.teacher_profile = None
            else:
                user.teacher_profile = None

            # Add user object to request state
            request.state.user = user
            return user

        except JWTError:  # Catch other JWT errors
            # Raise HTTPException for general token validation issues
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - Token error",
                headers=authenticate_header,
            )
        except Exception as e:
            # Log the detailed error for debugging
            print(f"Unexpected authentication error: {e}")  # Consider proper logging
            # Raise HTTPException for unexpected internal errors during auth
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
                # Raise HTTPException for insufficient permissions
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient Permissions",  # Keep message user-friendly
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

# Type hints for dependency injection (remain the same)
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
TeacherUser = Annotated[User, Depends(require_teacher)]
AnyUser = Annotated[User, Depends(require_user)]
