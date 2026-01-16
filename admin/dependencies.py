# admin/dependencies.py

from typing import Annotated

from fastapi import Depends, HTTPException, status

from dependencies import get_current_user
from models.user import User, UserRole
from utils.db import get_db


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
) -> tuple[User, str]:
    """
    Dependency to ensure the current user is an admin and belongs to a university.
    Returns (user, university_id) tuple.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    
    if not current_user.university_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin user must be associated with a university",
        )
    
    return current_user, str(current_user.university_id)
