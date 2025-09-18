# user/routes.py

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from models.user import User
from auth.models import UserRead
from dependencies import AdminUser, AnyUser, get_current_user
from routes_config import user_router
from utils.db import get_session

# Create router
router = APIRouter()


@router.get("/", response_model=List[UserRead])
async def read_users(
    current_user: Annotated[User, Depends(AdminUser)],
    session: Session = Depends(get_session),
    skip: int = 0,
    limit: int = 100
):
    """Get all users (admin only)."""
    from sqlmodel import select
    statement = select(User).offset(skip).limit(limit)
    users = session.exec(statement).all()
    return [UserRead.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserRead)
async def read_user(
    user_id: int,
    current_user: Annotated[User, Depends(AnyUser)],
    session: Session = Depends(get_session)
):
    """Get a specific user by ID."""
    from sqlmodel import select
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Users can only view their own profile unless they're admin
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return UserRead.model_validate(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: Annotated[User, Depends(AdminUser)],
    session: Session = Depends(get_session)
):
    """Delete a user (admin only)."""
    from auth.service import AuthService
    success = AuthService.delete_user(session, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return {"message": "User deleted successfully"}


# Include the router in the user_router
user_router.include_router(router)
