# notification/routes.py
"""
Notification API routes for the AITA platform.

These endpoints match the frontend's expected API contract for notifications.
Accessible to both Teachers and Students.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import get_current_user
from logger import logger
from models.user import User
from services.notification_service import NotificationService
from utils.db import get_db

router = APIRouter()


# ==================== GET /api/notifications ====================

@router.get("/")
async def get_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    type: Optional[int] = Query(None, description="Notification type filter"),
    isRead: Optional[int] = Query(None, description="0=all, 1=unread, 2=read"),
    isArchived: Optional[str] = Query(None, description="Archive filter"),
    featureType: Optional[int] = Query(None, description="Feature type filter"),
    userId: Optional[str] = Query(None, description="User ID filter (admin only)"),
    severity: Optional[int] = Query(None, description="Severity level (1-4)"),
    sortBy: str = Query("created_at", description="Sort field"),
    sortOrder: str = Query("desc", description="Sort order (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    itemsPerPage: int = Query(15, ge=1, le=100, description="Items per page"),
    db=Depends(get_db),
):
    """
    Fetch notifications for the current user with optional filters.
    
    Query Parameters:
    - type: Notification type filter (NotificationType enum value)
    - isRead: 0=all, 1=unread only, 2=read only
    - isArchived: Archive filter ('true'/'false')
    - featureType: Feature type filter
    - userId: User ID filter (admin only, ignored for regular users)
    - severity: Severity level (1-4)
    - sortBy: Field to sort by (default: 'created_at' or 'id')
    - sortOrder: 'asc' or 'desc'
    - page: Page number (1-indexed)
    - itemsPerPage: Number of items per page
    
    Returns paginated notifications matching the filters.
    """
    try:
        logger.info(f"Fetching notifications for user {current_user.id}")
        
        # Use the current user's ID unless admin and userId is specified
        target_user_id = str(current_user.id)
        
        # Parse isArchived string to bool
        is_archived_bool = None
        if isArchived is not None:
            if isArchived.lower() == 'true':
                is_archived_bool = True
            elif isArchived.lower() == 'false':
                is_archived_bool = False
        
        # Map sortBy to actual column names
        sort_field = sortBy
        if sortBy == "id":
            sort_field = "created_at"  # Sort by created_at when frontend asks for id
        
        notification_service = NotificationService(db)
        result = notification_service.get_notifications(
            user_id=target_user_id,
            notification_type=type,
            is_read=isRead,
            is_archived=is_archived_bool,
            feature_type=featureType,
            severity=severity,
            sort_by=sort_field,
            sort_order=sortOrder,
            page=page,
            items_per_page=itemsPerPage,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching notifications",
        )


# ==================== GET /api/notifications/unread-count ====================

@router.get("/unread-count")
async def get_unread_count(
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Get the count of unread notifications for the current user.
    
    Used for displaying badge count in the UI.
    
    Returns:
        { "count": <number> }
    """
    try:
        notification_service = NotificationService(db)
        count = notification_service.get_unread_count(str(current_user.id))
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting unread count",
        )


# ==================== PATCH /api/notifications/{notification_id}/read ====================

@router.patch("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Mark a specific notification as read.
    
    Only the owner of the notification can mark it as read.
    
    Returns:
        Success message and updated notification info.
    """
    try:
        logger.info(f"Marking notification {notification_id} as read for user {current_user.id}")
        
        notification_service = NotificationService(db)
        
        # Verify ownership and mark as read
        result = notification_service.mark_as_read(
            notification_id=notification_id,
            user_id=str(current_user.id),
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied",
            )
        
        return {
            "message": "Notification marked as read",
            "notification_id": notification_id,
            "is_read": True,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error marking notification as read",
        )


# ==================== PATCH /api/notifications/read-all ====================

@router.patch("/read-all")
async def mark_all_as_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Mark all notifications as read for the current user.
    
    Returns:
        Success message and count of notifications updated.
    """
    try:
        logger.info(f"Marking all notifications as read for user {current_user.id}")
        
        notification_service = NotificationService(db)
        count = notification_service.mark_all_as_read(str(current_user.id))
        
        return {
            "message": "All notifications marked as read",
            "count": count,
        }
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error marking all notifications as read",
        )


# ==================== PATCH /api/notifications/{notification_id}/archive ====================

@router.patch("/{notification_id}/archive")
async def archive_notification(
    notification_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Archive a specific notification.
    
    Archived notifications are typically hidden from the main list.
    Only the owner of the notification can archive it.
    
    Returns:
        Success message and updated notification info.
    """
    try:
        logger.info(f"Archiving notification {notification_id} for user {current_user.id}")
        
        notification_service = NotificationService(db)
        
        result = notification_service.archive_notification(
            notification_id=notification_id,
            user_id=str(current_user.id),
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied",
            )
        
        return {
            "message": "Notification archived",
            "notification_id": notification_id,
            "is_archived": True,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error archiving notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error archiving notification",
        )


# ==================== DELETE /api/notifications/{notification_id} ====================

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Delete a specific notification.
    
    Only the owner of the notification can delete it.
    This action is permanent and cannot be undone.
    
    Returns:
        Success message.
    """
    try:
        logger.info(f"Deleting notification {notification_id} for user {current_user.id}")
        
        notification_service = NotificationService(db)
        
        deleted = notification_service.delete_notification(
            notification_id=notification_id,
            user_id=str(current_user.id),
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied",
            )
        
        return {
            "message": "Notification deleted",
            "notification_id": notification_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting notification",
        )


# ==================== GET /api/notifications/{notification_id} ====================

@router.get("/{notification_id}")
async def get_notification(
    notification_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Get a specific notification by ID.
    
    Only the owner of the notification can view it.
    
    Returns:
        The notification details.
    """
    try:
        notification_service = NotificationService(db)
        
        notification = notification_service.get_notification_by_id(
            notification_id=notification_id,
            user_id=str(current_user.id),
        )
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied",
            )
        
        # Transform to frontend format
        return {
            "id": notification["id"],
            "title": notification["title"],
            "description": notification.get("description"),
            "type": notification["type"],
            "severity": notification.get("severity", 1),
            "isRead": notification.get("is_read", False),
            "isArchived": notification.get("is_archived", False),
            "createdOn": notification.get("created_at"),
            "companyKey": notification.get("company_key"),
            "relatedEntityType": notification.get("related_entity_type"),
            "relatedEntityId": notification.get("related_entity_id"),
            "actionUrl": notification.get("action_url"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting notification",
        )


# Include router in main application
from routes_config import notification_router as main_notification_router

main_notification_router.include_router(router)

