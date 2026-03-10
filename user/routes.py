# user/routes.py

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status

from auth.models import UserRead
from dependencies import AdminUser, AnyUser, get_current_user
from models.user import User
from routes_config import user_router
from utils.db import get_db
from utils.id_converter import IDConverter

# Create router
router = APIRouter()


@router.get("/", response_model=List[UserRead])
async def read_users(
    current_user: Annotated[User, Depends(AdminUser)],
    db=Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """Get all users (admin only)."""
    users_data = db.get_users(skip=skip, limit=limit)
    return [UserRead.model_validate(User(**user_data)) for user_data in users_data]


@router.get("/{user_id}", response_model=UserRead)
async def read_user(
    user_id: str, current_user: Annotated[User, Depends(AnyUser)], db=Depends(get_db)
):
    """Get a specific user by ID (UUID)."""
    user_data = db.get_user_by_id(user_id)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Users can only view their own profile unless they're admin
    # Compare UUIDs properly
    current_user_uuid = current_user.uuid if hasattr(current_user, "uuid") and current_user.uuid else str(current_user.id)
    if current_user.role != "admin" and current_user_uuid != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    return UserRead.model_validate(User(**user_data))


@router.delete("/{user_id}")
async def delete_user(
    user_id: str, current_user: Annotated[User, Depends(AdminUser)], db=Depends(get_db)
):
    """Delete a user (admin only). Accepts UUID string."""
    success = db.delete_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return {"message": "User deleted successfully"}


# Include the router in the user_router
user_router.include_router(router)
