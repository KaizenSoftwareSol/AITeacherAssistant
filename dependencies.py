from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlmodel import Session, select

from auth.models import User, UserRole
from settings import Settings
from utils.db import get_session

settings = Settings()
security = HTTPBearer()


class AuthDependency:
    @staticmethod
    async def get_current_user(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        session: Session = Depends(get_session),
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

            # Get user from database
            statement = select(User).where(User.id == int(user_id))
            user = session.exec(statement).first()

            if not user:
                # Raise HTTPException for user not found
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,  # Often 401 or 404 depending on desired security feedback
                    detail="User not found",
                    headers=authenticate_header,
                )

            if not user.is_active:
                # Raise HTTPException for inactive user
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Inactive user",
                )

            # Add user object to request state
            request.state.user = user
            print(user)
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
require_manager = AuthDependency.check_roles([UserRole.MANAGER, UserRole.ADMIN])
require_user = AuthDependency.check_roles(
    [UserRole.USER, UserRole.MANAGER, UserRole.ADMIN]
)

# Type hints for dependency injection (remain the same)
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
ManagerUser = Annotated[User, Depends(require_manager)]
AnyUser = Annotated[User, Depends(require_user)]

