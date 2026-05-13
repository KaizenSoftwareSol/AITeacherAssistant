# auth/routes.py

import time
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import ExpiredSignatureError, JWTError, jwt

from auth.models import (
    PasswordChangeRequest,
    TokenPasswordChangeRequest,
    Token,
    UserCreate,
    UserRead,
    UniversityRead,
)
from auth.service import AuthService
from dependencies import get_current_user
from models.user import User
from routes_config import auth_router
from settings import settings
from utils.db import get_db

# Create router
router = APIRouter()


@router.post("/register", response_model=UserRead)
async def register(user_data: UserCreate, db=Depends(get_db)):
    """Register a new user."""
    try:
        user = await AuthService.create_user(db, user_data)
        return AuthService.to_user_read(db, user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    """Login and get access token."""
    user = await AuthService.authenticate_user_async(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # Use UUID for token security (not integer ID)
    user_uuid = user.uuid if hasattr(user, "uuid") and user.uuid else str(user.id)
    access_token = AuthService.create_access_token(
        data={"sub": user_uuid}, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": int(access_token_expires.total_seconds()),
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    db=Depends(get_db),
):
    """
    Refresh the access token.

    Accepts a valid OR recently-expired token (up to 7 days past expiry).
    Returns a new access token with a fresh expiry.
    The frontend should call this on 401 errors to silently renew the session.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )

    token = auth_header.split(" ", 1)[1]

    # Try decoding normally first, then allow expired tokens within grace period
    user_id = None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
    except ExpiredSignatureError:
        # Token expired — decode WITHOUT verifying expiry to extract user_id
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        user_id = payload.get("sub")

        # Check grace period: only allow refresh within 7 days of expiry
        exp = payload.get("exp", 0)
        grace_period = 7 * 24 * 60 * 60  # 7 days in seconds
        if time.time() - exp > grace_period:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired beyond refresh grace period. Please log in again.",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token — no user ID",
        )

    # Verify user still exists and is active
    from dependencies import _get_cached_user_by_id
    user_data = _get_cached_user_by_id(db, user_id)
    if not user_data or not user_data.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Issue fresh token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_token = AuthService.create_access_token(
        data={"sub": user_id}, expires_delta=access_token_expires
    )
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": int(access_token_expires.total_seconds()),
    }


@router.get("/me", response_model=UserRead)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """Get current user information."""
    return AuthService.to_user_read(db, current_user)


@router.put("/me", response_model=UserRead)
async def update_user_me(
    user_update: dict,
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Update current user information.
    
    Note: To change password, use /auth/change-password endpoint instead
    for better security (requires old password verification).
    """
    # Prevent password changes through this endpoint
    if "password" in user_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /auth/change-password endpoint to change your password",
        )
    
    updated_user = AuthService.update_user(db, current_user.id, user_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserRead.model_validate(updated_user)


@router.post("/change-password")
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Change user password.
    
    Requires the old password for verification.
    Available for all authenticated users (students, teachers, admins).
    """
    # Get current user data with password hash
    user_data = db.get_user_by_id(current_user.id, use_cache=False)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    
    # Verify old password
    hashed_password = user_data.get("hashed_password", "")
    if not AuthService.verify_password(password_data.old_password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password",
        )
    
    # Validate new password (basic validation)
    min_password_length = 6
    if (
        not password_data.new_password
        or len(password_data.new_password) < min_password_length
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"New password must be at least {min_password_length} "
                "characters long"
            ),
        )
    
    # Check if new password is same as old password
    if AuthService.verify_password(password_data.new_password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from old password",
        )
    
    # Update password (AuthService.update_user expects "password" field)
    updated_user = AuthService.update_user(
        db, current_user.id, {"password": password_data.new_password}
    )
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password",
        )
    
    return {"message": "Password changed successfully"}


@router.post("/activate-account")
async def activate_account_with_token(
    password_data: TokenPasswordChangeRequest,
    db=Depends(get_db),
):
    """
    Activate account and set password using activation token.
    
    This endpoint is used when a user clicks the activation link sent via email.
    The token is a JWT that contains the user_id and expires in 14 days.
    """
    # Verify token and get user_id
    user_id = AuthService.verify_activation_token(password_data.token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired activation token",
        )
    
    # Get user data
    user_data = db.get_user_by_id(user_id, use_cache=False)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Validate new password
    min_password_length = 6
    if (
        not password_data.new_password
        or len(password_data.new_password) < min_password_length
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Password must be at least {min_password_length} "
                "characters long"
            ),
        )
    
    # Update password
    updated_user = AuthService.update_user(
        db, user_id, {"password": password_data.new_password}
    )
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set password",
        )
    
    return {
        "message": "Account activated and password set successfully",
        "user_id": user_id,
        "email": user_data.get("email"),
    }


@router.get("/universities", response_model=list[UniversityRead])
async def list_universities(db=Depends(get_db), skip: int = 0, limit: int = 100):
    """List available universities for signup."""
    try:
        universities = db.get_records(
            "university",
            skip=skip,
            limit=min(limit, 500),
        )
        return universities
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load universities: {e!s}",
        ) from e


# Include the router in the auth_router
auth_router.include_router(router)
