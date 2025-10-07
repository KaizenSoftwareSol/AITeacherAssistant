# auth/routes.py

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from auth.models import Token, UserCreate, UserRead
from auth.service import AuthService
from dependencies import get_current_user
from models.user import User
from routes_config import auth_router
from utils.db import get_db

# Create router
router = APIRouter()


@router.post("/register", response_model=UserRead)
async def register(user_data: UserCreate, db=Depends(get_db)):
    """Register a new user."""
    try:
        user = await AuthService.create_user(db, user_data)
        return UserRead.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    """Login and get access token."""
    user = AuthService.authenticate_user(db, form_data.username, form_data.password)
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

    access_token_expires = timedelta(minutes=30)
    access_token = AuthService.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserRead)
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    """Get current user information."""
    # Convert SQLModel User to dict for Pydantic validation
    user_dict = {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "is_active": current_user.is_active,
        "role": current_user.role,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at,
    }
    return UserRead.model_validate(user_dict)


@router.put("/me", response_model=UserRead)
async def update_user_me(
    user_update: dict,
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """Update current user information."""
    updated_user = AuthService.update_user(db, current_user.id, user_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserRead.model_validate(updated_user)


# Include the router in the auth_router
auth_router.include_router(router)
