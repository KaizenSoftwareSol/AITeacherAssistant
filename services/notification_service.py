# services/notification_service.py
"""
Notification Service for the AITA platform.

Handles creation, retrieval, and management of notifications
for both teachers and students.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from logger import logger
from models.notification import (
    NotificationCreate,
    NotificationSeverity,
    NotificationType,
)


class NotificationService:
    """Service for managing notifications."""
    
    def __init__(self, db):
        """Initialize the notification service with a database instance."""
        self.db = db
    
    async def create(
        self,
        user_id: str,
        title: str,
        description: Optional[str] = None,
        notification_type: int = NotificationType.PENDING,
        severity: int = NotificationSeverity.INFO,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
        action_url: Optional[str] = None,
        company_key: Optional[str] = None,
        feature_type: int = 101,
    ) -> Dict[str, Any]:
        """
        Create a new notification.
        
        Args:
            user_id: UUID of the user to notify
            title: Notification title
            description: Optional detailed description
            notification_type: Type of notification (NotificationType enum)
            severity: Severity level (NotificationSeverity enum)
            related_entity_type: Type of related entity ('course', 'lecture', 'quiz', etc.)
            related_entity_id: UUID of the related entity
            action_url: Deep link URL for the notification
            company_key: Optional company/tenant key
            feature_type: Feature type for frontend categorization
            
        Returns:
            The created notification record
        """
        try:
            notification_id = str(uuid4())
            notification_data = {
                "id": notification_id,
                "user_id": str(user_id),
                "title": title,
                "description": description,
                "type": notification_type,
                "severity": severity,
                "is_read": False,
                "is_archived": False,
                "feature_type": feature_type,
                "related_entity_type": related_entity_type,
                "related_entity_id": str(related_entity_id) if related_entity_id else None,
                "action_url": action_url,
                "company_key": company_key,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            result = (
                self.db.admin_client
                .table("notification")
                .insert(notification_data)
                .execute()
            )
            
            logger.info(f"Created notification {notification_id} for user {user_id}: {title}")
            return result.data[0] if result.data else notification_data
            
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            raise
    
    async def create_bulk(
        self,
        user_ids: List[str],
        title: str,
        description: Optional[str] = None,
        notification_type: int = NotificationType.PENDING,
        severity: int = NotificationSeverity.INFO,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
        action_url: Optional[str] = None,
        company_key: Optional[str] = None,
        feature_type: int = 101,
    ) -> List[Dict[str, Any]]:
        """
        Create notifications for multiple users at once.
        
        Useful for broadcasting notifications to all enrolled students in a course.
        """
        try:
            notifications = []
            for user_id in user_ids:
                notification_id = str(uuid4())
                notifications.append({
                    "id": notification_id,
                    "user_id": str(user_id),
                    "title": title,
                    "description": description,
                    "type": notification_type,
                    "severity": severity,
                    "is_read": False,
                    "is_archived": False,
                    "feature_type": feature_type,
                    "related_entity_type": related_entity_type,
                    "related_entity_id": str(related_entity_id) if related_entity_id else None,
                    "action_url": action_url,
                    "company_key": company_key,
                    "created_at": datetime.utcnow().isoformat(),
                })
            
            if notifications:
                result = (
                    self.db.admin_client
                    .table("notification")
                    .insert(notifications)
                    .execute()
                )
                logger.info(f"Created {len(notifications)} notifications in bulk")
                return result.data
            
            return []
            
        except Exception as e:
            logger.error(f"Error creating bulk notifications: {str(e)}")
            raise
    
    def get_notifications(
        self,
        user_id: str,
        notification_type: Optional[int] = None,
        is_read: Optional[int] = None,  # 0=all, 1=unread, 2=read
        is_archived: Optional[bool] = None,
        feature_type: Optional[int] = None,
        severity: Optional[int] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        items_per_page: int = 15,
    ) -> Dict[str, Any]:
        """
        Get paginated notifications for a user with filters.
        
        Args:
            user_id: UUID of the user
            notification_type: Filter by notification type
            is_read: 0=all, 1=unread only, 2=read only
            is_archived: Filter by archive status
            feature_type: Filter by feature type
            severity: Filter by severity level
            sort_by: Field to sort by (default: created_at)
            sort_order: Sort direction ('asc' or 'desc')
            page: Page number (1-indexed)
            items_per_page: Number of items per page
            
        Returns:
            Dict with notifications list, total count, page, and items_per_page
        """
        try:
            # Build query
            query = (
                self.db.admin_client
                .table("notification")
                .select("*", count="exact")
                .eq("user_id", str(user_id))
            )
            
            # Apply filters
            if notification_type is not None:
                query = query.eq("type", notification_type)
            
            if is_read == 1:  # Unread only
                query = query.eq("is_read", False)
            elif is_read == 2:  # Read only
                query = query.eq("is_read", True)
            
            if is_archived is not None:
                query = query.eq("is_archived", is_archived)
            
            if feature_type is not None:
                query = query.eq("feature_type", feature_type)
            
            if severity is not None:
                query = query.eq("severity", severity)
            
            # Apply sorting
            desc = sort_order.lower() == "desc"
            query = query.order(sort_by, desc=desc)
            
            # Apply pagination
            offset = (page - 1) * items_per_page
            query = query.range(offset, offset + items_per_page - 1)
            
            # Execute query
            result = query.execute()
            
            # Transform to frontend format
            notifications = []
            for n in (result.data or []):
                notifications.append({
                    "id": n["id"],
                    "title": n["title"],
                    "description": n.get("description"),
                    "type": n["type"],
                    "severity": n.get("severity", 1),
                    "isRead": n.get("is_read", False),
                    "isArchived": n.get("is_archived", False),
                    "createdOn": n.get("created_at"),
                    "companyKey": n.get("company_key"),
                    # Navigation data
                    "relatedEntityType": n.get("related_entity_type"),
                    "relatedEntityId": n.get("related_entity_id"),
                    "actionUrl": n.get("action_url"),
                })
            
            return {
                "notifications": notifications,
                "total": result.count or 0,
                "page": page,
                "itemsPerPage": items_per_page,
            }
            
        except Exception as e:
            logger.error(f"Error getting notifications: {str(e)}")
            raise
    
    def get_notification_by_id(
        self,
        notification_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single notification by ID.
        
        Args:
            notification_id: UUID of the notification
            user_id: Optional user_id to verify ownership
            
        Returns:
            The notification record or None
        """
        try:
            query = (
                self.db.admin_client
                .table("notification")
                .select("*")
                .eq("id", notification_id)
            )
            
            if user_id:
                query = query.eq("user_id", str(user_id))
            
            result = query.execute()
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"Error getting notification {notification_id}: {str(e)}")
            return None
    
    def mark_as_read(
        self,
        notification_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Mark a notification as read.
        
        Args:
            notification_id: UUID of the notification
            user_id: UUID of the user (for ownership verification)
            
        Returns:
            The updated notification or None
        """
        try:
            result = (
                self.db.admin_client
                .table("notification")
                .update({
                    "is_read": True,
                    "read_at": datetime.utcnow().isoformat(),
                })
                .eq("id", notification_id)
                .eq("user_id", str(user_id))
                .execute()
            )
            
            if result.data:
                logger.info(f"Marked notification {notification_id} as read")
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            raise
    
    def mark_all_as_read(self, user_id: str) -> int:
        """
        Mark all notifications as read for a user.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            Number of notifications updated
        """
        try:
            result = (
                self.db.admin_client
                .table("notification")
                .update({
                    "is_read": True,
                    "read_at": datetime.utcnow().isoformat(),
                })
                .eq("user_id", str(user_id))
                .eq("is_read", False)
                .execute()
            )
            
            count = len(result.data) if result.data else 0
            logger.info(f"Marked {count} notifications as read for user {user_id}")
            return count
            
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {str(e)}")
            raise
    
    def archive_notification(
        self,
        notification_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Archive a notification.
        
        Args:
            notification_id: UUID of the notification
            user_id: UUID of the user (for ownership verification)
            
        Returns:
            The updated notification or None
        """
        try:
            result = (
                self.db.admin_client
                .table("notification")
                .update({"is_archived": True})
                .eq("id", notification_id)
                .eq("user_id", str(user_id))
                .execute()
            )
            
            if result.data:
                logger.info(f"Archived notification {notification_id}")
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error archiving notification: {str(e)}")
            raise
    
    def delete_notification(
        self,
        notification_id: str,
        user_id: str,
    ) -> bool:
        """
        Delete a notification.
        
        Args:
            notification_id: UUID of the notification
            user_id: UUID of the user (for ownership verification)
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            result = (
                self.db.admin_client
                .table("notification")
                .delete()
                .eq("id", notification_id)
                .eq("user_id", str(user_id))
                .execute()
            )
            
            deleted = len(result.data) > 0 if result.data else False
            if deleted:
                logger.info(f"Deleted notification {notification_id}")
            return deleted
            
        except Exception as e:
            logger.error(f"Error deleting notification: {str(e)}")
            raise
    
    def get_unread_count(self, user_id: str) -> int:
        """
        Get the count of unread notifications for a user.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            Count of unread notifications
        """
        try:
            result = (
                self.db.admin_client
                .table("notification")
                .select("id", count="exact")
                .eq("user_id", str(user_id))
                .eq("is_read", False)
                .eq("is_archived", False)
                .execute()
            )
            
            return result.count or 0
            
        except Exception as e:
            logger.error(f"Error getting unread count: {str(e)}")
            return 0
    
    # ==================== Convenience Methods for Specific Events ====================
    
    async def notify_student_enrolled(
        self,
        teacher_user_id: str,
        student_name: str,
        course_name: str,
        course_id: str,
    ) -> Dict[str, Any]:
        """Notify teacher when a student enrolls in their course."""
        return await self.create(
            user_id=teacher_user_id,
            title="New Student Enrolled",
            description=f"{student_name} enrolled in {course_name}",
            notification_type=NotificationType.STUDENT_ENROLLED,
            severity=NotificationSeverity.INFO,
            related_entity_type="course",
            related_entity_id=course_id,
            action_url=f"/teacher/courses/{course_id}",
        )
    
    async def notify_enrollment_confirmed(
        self,
        student_user_id: str,
        course_name: str,
        course_id: str,
    ) -> Dict[str, Any]:
        """Notify student when their enrollment is confirmed."""
        return await self.create(
            user_id=student_user_id,
            title="Enrollment Successful",
            description=f"You have enrolled in {course_name}",
            notification_type=NotificationType.ENROLLMENT_CONFIRMED,
            severity=NotificationSeverity.SUCCESS,
            related_entity_type="course",
            related_entity_id=course_id,
            action_url=f"/student/courses/{course_id}",
        )
    
    async def notify_quiz_submitted(
        self,
        teacher_user_id: str,
        student_name: str,
        quiz_title: str,
        assessment_id: str,
    ) -> Dict[str, Any]:
        """Notify teacher when a student submits a quiz."""
        return await self.create(
            user_id=teacher_user_id,
            title="Quiz Submitted",
            description=f"{student_name} submitted quiz '{quiz_title}'",
            notification_type=NotificationType.QUIZ_SUBMITTED,
            severity=NotificationSeverity.INFO,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url=f"/teacher/assessments/{assessment_id}",
        )
    
    async def notify_low_quiz_score(
        self,
        teacher_user_id: str,
        student_name: str,
        quiz_title: str,
        score_percentage: float,
        assessment_id: str,
    ) -> Dict[str, Any]:
        """Notify teacher when a student scores below passing on a quiz."""
        return await self.create(
            user_id=teacher_user_id,
            title="Student Needs Help",
            description=f"{student_name} scored {score_percentage:.0f}% on '{quiz_title}'",
            notification_type=NotificationType.LOW_QUIZ_SCORE,
            severity=NotificationSeverity.WARNING,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url=f"/teacher/assessments/{assessment_id}",
        )
    
    async def notify_result_request(
        self,
        teacher_user_id: str,
        student_name: str,
        quiz_title: str,
        request_id: str,
    ) -> Dict[str, Any]:
        """Notify teacher when a student requests to view results."""
        return await self.create(
            user_id=teacher_user_id,
            title="Result Request",
            description=f"{student_name} requested detailed results for '{quiz_title}'",
            notification_type=NotificationType.RESULT_REQUEST,
            severity=NotificationSeverity.WARNING,
            related_entity_type="result_request",
            related_entity_id=request_id,
            action_url=f"/teacher/result-requests",
        )
    
    async def notify_lecture_published(
        self,
        student_user_ids: List[str],
        lecture_title: str,
        course_name: str,
        lecture_id: str,
    ) -> List[Dict[str, Any]]:
        """Notify all enrolled students when a lecture is published."""
        return await self.create_bulk(
            user_ids=student_user_ids,
            title="New Lecture Available",
            description=f"'{lecture_title}' is now available in {course_name}",
            notification_type=NotificationType.LECTURE_PUBLISHED,
            severity=NotificationSeverity.INFO,
            related_entity_type="lecture",
            related_entity_id=lecture_id,
            action_url=f"/student/lectures/{lecture_id}",
        )
    
    async def notify_quiz_published(
        self,
        student_user_ids: List[str],
        quiz_title: str,
        due_date: Optional[str],
        assessment_id: str,
    ) -> List[Dict[str, Any]]:
        """Notify all enrolled students when a quiz is published."""
        description = f"'{quiz_title}' is now available"
        if due_date:
            description += f". Due: {due_date}"
        
        return await self.create_bulk(
            user_ids=student_user_ids,
            title="New Quiz Available",
            description=description,
            notification_type=NotificationType.QUIZ_PUBLISHED,
            severity=NotificationSeverity.INFO,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url="/student/assessments",
        )
    
    async def notify_result_approved(
        self,
        student_user_id: str,
        quiz_title: str,
        assessment_id: str,
    ) -> Dict[str, Any]:
        """Notify student when their result request is approved."""
        return await self.create(
            user_id=student_user_id,
            title="Results Available",
            description=f"Your result request for '{quiz_title}' has been approved",
            notification_type=NotificationType.RESULT_APPROVED,
            severity=NotificationSeverity.SUCCESS,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url="/student/assessments",
        )
    
    async def notify_result_rejected(
        self,
        student_user_id: str,
        quiz_title: str,
        reason: Optional[str],
        assessment_id: str,
    ) -> Dict[str, Any]:
        """Notify student when their result request is rejected."""
        description = f"Your result request for '{quiz_title}' was declined"
        if reason:
            description += f": {reason}"
        
        return await self.create(
            user_id=student_user_id,
            title="Request Declined",
            description=description,
            notification_type=NotificationType.RESULT_REJECTED,
            severity=NotificationSeverity.WARNING,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
        )
    
    async def notify_quiz_deadline_reminder(
        self,
        student_user_id: str,
        quiz_title: str,
        assessment_id: str,
    ) -> Dict[str, Any]:
        """Notify student when a quiz deadline is approaching (24h)."""
        return await self.create(
            user_id=student_user_id,
            title="Quiz Deadline Reminder",
            description=f"'{quiz_title}' is due in 24 hours",
            notification_type=NotificationType.QUIZ_DEADLINE_REMINDER,
            severity=NotificationSeverity.WARNING,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url="/student/assessments",
        )

