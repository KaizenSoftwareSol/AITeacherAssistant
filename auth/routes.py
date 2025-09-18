# auth/routes.py

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from models.user import User
from auth.models import Token, UserCreate, UserRead
from auth.service import AuthService
from dependencies import get_current_user
from routes_config import auth_router
from utils.db import get_session

# Create router
router = APIRouter()


@router.post("/register", response_model=UserRead)
async def register(
    user_data: UserCreate,
    session: Session = Depends(get_session)
):
    """Register a new user."""
    try:
        user = await AuthService.create_user(session, user_data)
        return UserRead.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    """Login and get access token."""
    user = AuthService.authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    access_token_expires = timedelta(minutes=30)
    access_token = AuthService.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserRead)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Get current user information."""
    return UserRead.model_validate(current_user)


@router.put("/me", response_model=UserRead)
async def update_user_me(
    user_update: dict,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session)
):
    """Update current user information."""
    updated_user = AuthService.update_user(session, current_user.id, user_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserRead.model_validate(updated_user)


# Include the router in the auth_router
auth_router.include_router(router)
