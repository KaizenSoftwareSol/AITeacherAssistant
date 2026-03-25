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
from services.email_service import email_service


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
            from utils.id_converter import IDConverter
            
            notification_id = str(uuid4())
            
            # Convert user_id from UUID to integer if needed
            # Handle both UUID strings and integer strings/ints
            user_int_id = user_id
            if isinstance(user_id, str):
                if IDConverter.is_uuid(user_id):
                    user_int_id = await IDConverter.uuid_to_int(self.db, "users", user_id)
                    if not user_int_id:
                        logger.warning(f"Failed to convert user_id {user_id} to integer")
                        raise ValueError(f"Invalid user_id: {user_id}")
                else:
                    # Try to parse as integer
                    try:
                        user_int_id = int(user_id)
                    except (ValueError, TypeError):
                        logger.warning(f"user_id {user_id} is not a valid UUID or integer")
                        raise ValueError(f"Invalid user_id: {user_id}")
            elif isinstance(user_id, int):
                # Already an integer, use as-is
                user_int_id = user_id
            else:
                raise ValueError(f"Invalid user_id type: {type(user_id)}")
            
            # Convert related_entity_id from UUID to integer if needed
            related_entity_int_id = related_entity_id
            if related_entity_id and IDConverter.is_uuid(related_entity_id):
                # Determine the table name from related_entity_type
                table_name_map = {
                    "assessment": "assessment",
                    "lecture": "lecture",
                    "course": "course",
                    "document": "documents",
                    "result_request": "result_view_request",  # Map to correct table name
                }
                table_name = table_name_map.get(related_entity_type, related_entity_type)
                related_entity_int_id = await IDConverter.uuid_to_int(self.db, table_name, related_entity_id)
                if not related_entity_int_id:
                    logger.warning(f"Failed to convert related_entity_id {related_entity_id} to integer")
                    related_entity_int_id = None  # Set to None if conversion fails
            
            notification_data = {
                "id": notification_id,
                "user_id": user_int_id,  # Use integer ID
                "title": title,
                "description": description,
                "type": notification_type,
                "severity": severity,
                "is_read": False,
                "is_archived": False,
                "feature_type": feature_type,
                "related_entity_type": related_entity_type,
                "related_entity_id": related_entity_int_id,  # Use integer ID or None
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
            
            # Send email notification as well
            try:
                user_data = self.db.get_user_by_id(user_id, use_cache=False)
                if user_data:
                    user_email = user_data.get("email")
                    user_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or "User"
                    if user_email:
                        email_service.send_notification_email(
                            to_email=user_email,
                            to_name=user_name,
                            notification_title=title,
                            notification_description=description,
                            action_url=action_url
                        )
            except Exception as email_error:
                logger.warning(f"Failed to send email notification: {str(email_error)}")
            
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
            from utils.id_converter import IDConverter
            
            notifications = []
            for user_id in user_ids:
                notification_id = str(uuid4())
                
                # Convert user_id from UUID to integer if needed
                # Handle both UUID strings and integer strings/ints
                user_int_id = user_id
                if isinstance(user_id, str):
                    if IDConverter.is_uuid(user_id):
                        user_int_id = await IDConverter.uuid_to_int(self.db, "users", user_id)
                        if not user_int_id:
                            logger.warning(f"Failed to convert user_id {user_id} to integer, skipping notification")
                            continue
                    else:
                        # Try to parse as integer
                        try:
                            user_int_id = int(user_id)
                        except (ValueError, TypeError):
                            logger.warning(f"user_id {user_id} is not a valid UUID or integer, skipping notification")
                            continue
                elif isinstance(user_id, int):
                    # Already an integer, use as-is
                    user_int_id = user_id
                else:
                    logger.warning(f"Invalid user_id type {type(user_id)}, skipping notification")
                    continue
                
                # Convert related_entity_id from UUID to integer if needed
                related_entity_int_id = related_entity_id
                if related_entity_id and IDConverter.is_uuid(related_entity_id):
                    # Determine the table name from related_entity_type
                    table_name_map = {
                        "assessment": "assessment",
                        "lecture": "lecture",
                        "course": "course",
                        "document": "documents",
                    }
                    table_name = table_name_map.get(related_entity_type, related_entity_type)
                    related_entity_int_id = await IDConverter.uuid_to_int(self.db, table_name, related_entity_id)
                    if not related_entity_int_id:
                        logger.warning(f"Failed to convert related_entity_id {related_entity_id} to integer")
                        related_entity_int_id = None  # Set to None if conversion fails
                
                notifications.append({
                    "id": notification_id,
                    "user_id": user_int_id,  # Use integer ID
                    "title": title,
                    "description": description,
                    "type": notification_type,
                    "severity": severity,
                    "is_read": False,
                    "is_archived": False,
                    "feature_type": feature_type,
                    "related_entity_type": related_entity_type,
                    "related_entity_id": related_entity_int_id,  # Use integer ID or None
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
                
                # Send email notifications as well
                try:
                    # Get user emails for all user_ids
                    user_ids_list = list(set(user_ids))
                    users_result = (
                        self.db.admin_client
                        .table("users")
                        .select("id, email, first_name, last_name")
                        .in_("id", user_ids_list)
                        .execute()
                    )
                    
                    user_info_map = {}
                    for user in users_result.data or []:
                        user_info_map[user["id"]] = {
                            "email": user.get("email"),
                            "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "User"
                        }
                    
                    # Send emails
                    for notification in notifications:
                        user_id = notification["user_id"]
                        user_info = user_info_map.get(user_id)
                        if user_info and user_info["email"]:
                            email_service.send_notification_email(
                                to_email=user_info["email"],
                                to_name=user_info["name"],
                                notification_title=title,
                                notification_description=description,
                                action_url=action_url
                            )
                except Exception as email_error:
                    logger.warning(f"Failed to send bulk email notifications: {str(email_error)}")
                
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
        from services.cache_service import cache
        
        cache_key = f"unread_count:{user_id}"
        
        # Try cache first
        cached = cache.get("queries", cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT: unread_count for {user_id}")
            return cached
        
        # Query if not cached
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
            
            count = result.count or 0
            
            # Cache for 10 seconds
            try:
                cache.set("queries", count, cache_key, ttl=10)
            except Exception:
                pass  # If cache fails, continue anyway
            
            return count
            
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
        student_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify teacher when a student enrolls in their course."""
        notification = await self.create(
            user_id=teacher_user_id,
            title="New Student Enrolled",
            description=f"{student_name} enrolled in {course_name}",
            notification_type=NotificationType.STUDENT_ENROLLED,
            severity=NotificationSeverity.INFO,
            related_entity_type="course",
            related_entity_id=course_id,
            action_url=f"/teacher/courses/{course_id}",
        )
        
        # Send email notification
        try:
            from settings import settings
            from datetime import datetime
            
            teacher_data = self.db.get_user_by_id(teacher_user_id, use_cache=False)
            if teacher_data:
                teacher_email = teacher_data.get("email")
                teacher_name = f"{teacher_data.get('first_name', '')} {teacher_data.get('last_name', '')}".strip() or "Teacher"
                if teacher_email:
                    course_link = f"{settings.FRONTEND_URL}/teacher/courses/{course_id}"
                    enrollment_date = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p")
                    
                    email_service.send_student_enrolled_notification(
                        to_email=teacher_email,
                        teacher_name=teacher_name,
                        student_name=student_name,
                        student_id=student_id or "N/A",
                        course_name=course_name,
                        enrollment_date=enrollment_date,
                        course_link=course_link
                    )
        except Exception as email_error:
            logger.warning(f"Failed to send student enrolled email: {str(email_error)}")
        
        return notification
    
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
        course_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify teacher when a student submits a quiz."""
        notification = await self.create(
            user_id=teacher_user_id,
            title="Quiz Submitted",
            description=f"{student_name} submitted quiz '{quiz_title}'",
            notification_type=NotificationType.QUIZ_SUBMITTED,
            severity=NotificationSeverity.INFO,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url=f"/teacher/assessments/{assessment_id}",
        )
        
        # Send email notification
        try:
            from settings import settings
            from datetime import datetime
            
            teacher_data = self.db.get_user_by_id(teacher_user_id, use_cache=False)
            if teacher_data:
                teacher_email = teacher_data.get("email")
                teacher_name = f"{teacher_data.get('first_name', '')} {teacher_data.get('last_name', '')}".strip() or "Teacher"
                if teacher_email:
                    assessment_link = f"{settings.FRONTEND_URL}/teacher/assessments/{assessment_id}"
                    submission_date = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p")
                    
                    email_service.send_quiz_submitted_notification(
                        to_email=teacher_email,
                        teacher_name=teacher_name,
                        student_name=student_name,
                        quiz_title=quiz_title,
                        course_name=course_name or "Course",
                        submission_date=submission_date,
                        assessment_link=assessment_link
                    )
        except Exception as email_error:
            logger.warning(f"Failed to send quiz submitted email: {str(email_error)}")
        
        return notification
    
    async def notify_low_quiz_score(
        self,
        teacher_user_id: str,
        student_name: str,
        quiz_title: str,
        score_percentage: float,
        assessment_id: str,
        course_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify teacher when a student scores below passing on a quiz."""
        notification = await self.create(
            user_id=teacher_user_id,
            title="Student Needs Help",
            description=f"{student_name} scored {score_percentage:.0f}% on '{quiz_title}'",
            notification_type=NotificationType.LOW_QUIZ_SCORE,
            severity=NotificationSeverity.WARNING,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url=f"/teacher/assessments/{assessment_id}",
        )
        
        # Send email notification
        try:
            from settings import settings
            
            teacher_data = self.db.get_user_by_id(teacher_user_id, use_cache=False)
            if teacher_data:
                teacher_email = teacher_data.get("email")
                teacher_name = f"{teacher_data.get('first_name', '')} {teacher_data.get('last_name', '')}".strip() or "Teacher"
                if teacher_email:
                    assessment_link = f"{settings.FRONTEND_URL}/teacher/assessments/{assessment_id}"
                    
                    email_service.send_low_quiz_score_notification(
                        to_email=teacher_email,
                        teacher_name=teacher_name,
                        student_name=student_name,
                        quiz_title=quiz_title,
                        course_name=course_name or "Course",
                        score_percentage=score_percentage,
                        assessment_link=assessment_link
                    )
        except Exception as email_error:
            logger.warning(f"Failed to send low quiz score email: {str(email_error)}")
        
        return notification
    
    async def notify_result_request(
        self,
        teacher_user_id: str,
        student_name: str,
        quiz_title: str,
        request_id: str,
        course_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify teacher when a student requests to view results."""
        notification = await self.create(
            user_id=teacher_user_id,
            title="Result Request",
            description=f"{student_name} requested detailed results for '{quiz_title}'",
            notification_type=NotificationType.RESULT_REQUEST,
            severity=NotificationSeverity.WARNING,
            related_entity_type="result_view_request",  # Use correct table name
            related_entity_id=request_id,
            action_url=f"/teacher/result-requests",
        )
        
        # Send email notification
        try:
            from settings import settings
            from datetime import datetime
            
            teacher_data = self.db.get_user_by_id(teacher_user_id, use_cache=False)
            if teacher_data:
                teacher_email = teacher_data.get("email")
                teacher_name = f"{teacher_data.get('first_name', '')} {teacher_data.get('last_name', '')}".strip() or "Teacher"
                if teacher_email:
                    result_request_link = f"{settings.FRONTEND_URL}/teacher/result-requests"
                    request_date = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p")
                    
                    email_service.send_result_request_notification(
                        to_email=teacher_email,
                        teacher_name=teacher_name,
                        student_name=student_name,
                        quiz_title=quiz_title,
                        course_name=course_name or "Course",
                        request_date=request_date,
                        result_request_link=result_request_link
                    )
        except Exception as email_error:
            logger.warning(f"Failed to send result request email: {str(email_error)}")
        
        return notification
    
    async def notify_lecture_published(
        self,
        student_user_ids: List[str],
        lecture_title: str,
        course_name: str,
        lecture_id: str,
        course_id: Optional[str] = None,
        teacher_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Notify all enrolled students when a lecture is published."""
        notifications = await self.create_bulk(
            user_ids=student_user_ids,
            title="New Lecture Available",
            description=f"'{lecture_title}' is now available in {course_name}",
            notification_type=NotificationType.LECTURE_PUBLISHED,
            severity=NotificationSeverity.INFO,
            related_entity_type="lecture",
            related_entity_id=lecture_id,
            action_url=f"/student/lectures/{lecture_id}",
        )
        
        # Send email notifications with specific template
        try:
            from settings import settings
            from datetime import datetime
            from utils.id_converter import IDConverter
            
            # Get user info for emails
            users_result = (
                self.db.admin_client
                .table("users")
                .select("id, email, first_name, last_name")
                .in_("id", student_user_ids)
                .execute()
            )
            
            # Build lecture link with courseId query parameter
            if course_id:
                # Convert course_id to UUID if it's an integer
                course_id_uuid = course_id
                if not IDConverter.is_uuid(course_id):
                    course_id_uuid = await IDConverter.int_to_uuid(self.db, "course", course_id)
                    if not course_id_uuid:
                        course_id_uuid = course_id  # Fallback to original
                lecture_link = f"{settings.FRONTEND_URL}/student/lectures/{lecture_id}?courseId={course_id_uuid}"
            else:
                lecture_link = f"{settings.FRONTEND_URL}/student/lectures/{lecture_id}"
            
            published_date = datetime.utcnow().strftime("%B %d, %Y")
            
            for user in users_result.data or []:
                user_email = user.get("email")
                user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Student"
                if user_email:
                    email_service.send_lecture_published_notification(
                        to_email=user_email,
                        student_name=user_name,
                        lecture_title=lecture_title,
                        course_name=course_name,
                        teacher_name=teacher_name or "Your instructor",
                        lecture_link=lecture_link,
                        published_date=published_date
                    )
        except Exception as email_error:
            logger.warning(f"Failed to send lecture published emails: {str(email_error)}")
        
        return notifications
    
    async def notify_quiz_published(
        self,
        student_user_ids: List[str],
        quiz_title: str,
        due_date: Optional[str],
        assessment_id: str,
        course_name: Optional[str] = None,
        teacher_name: Optional[str] = None,
        max_points: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Notify all enrolled students when a quiz is published."""
        description = f"'{quiz_title}' is now available"
        if due_date:
            description += f". Due: {due_date}"
        
        notifications = await self.create_bulk(
            user_ids=student_user_ids,
            title="New Quiz Available",
            description=description,
            notification_type=NotificationType.QUIZ_PUBLISHED,
            severity=NotificationSeverity.INFO,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url="/student/assessments",
        )
        
        # Send email notifications with specific template
        try:
            from settings import settings
            
            # Get user info for emails
            users_result = (
                self.db.admin_client
                .table("users")
                .select("id, email, first_name, last_name")
                .in_("id", student_user_ids)
                .execute()
            )
            
            quiz_link = f"{settings.FRONTEND_URL}/student/assessments"
            
            for user in users_result.data or []:
                user_email = user.get("email")
                user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Student"
                if user_email:
                    email_service.send_quiz_published_notification(
                        to_email=user_email,
                        student_name=user_name,
                        quiz_title=quiz_title,
                        course_name=course_name or "Course",
                        teacher_name=teacher_name or "Your instructor",
                        due_date=due_date,
                        max_points=max_points,
                        quiz_link=quiz_link
                    )
        except Exception as email_error:
            logger.warning(f"Failed to send quiz published emails: {str(email_error)}")
        
        return notifications
    
    async def notify_result_approved(
        self,
        student_user_id: str,
        quiz_title: str,
        assessment_id: str,
        course_name: Optional[str] = None,
        teacher_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify student when their result request is approved."""
        notification = await self.create(
            user_id=student_user_id,
            title="Results Available",
            description=f"Your result request for '{quiz_title}' has been approved",
            notification_type=NotificationType.RESULT_APPROVED,
            severity=NotificationSeverity.SUCCESS,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
            action_url="/student/assessments",
        )
        
        # Send email notification
        try:
            from settings import settings
            
            student_data = self.db.get_user_by_id(student_user_id, use_cache=False)
            if student_data:
                student_email = student_data.get("email")
                student_name = f"{student_data.get('first_name', '')} {student_data.get('last_name', '')}".strip() or "Student"
                if student_email:
                    result_link = f"{settings.FRONTEND_URL}/student/assessments"
                    
                    email_service.send_result_approved_notification(
                        to_email=student_email,
                        student_name=student_name,
                        quiz_title=quiz_title,
                        course_name=course_name or "Course",
                        teacher_name=teacher_name or "Your instructor",
                        result_link=result_link
                    )
        except Exception as email_error:
            logger.warning(f"Failed to send result approved email: {str(email_error)}")
        
        return notification
    
    async def notify_result_rejected(
        self,
        student_user_id: str,
        quiz_title: str,
        reason: Optional[str],
        assessment_id: str,
        course_name: Optional[str] = None,
        teacher_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Notify student when their result request is rejected."""
        description = f"Your result request for '{quiz_title}' was declined"
        if reason:
            description += f": {reason}"
        
        notification = await self.create(
            user_id=student_user_id,
            title="Request Declined",
            description=description,
            notification_type=NotificationType.RESULT_REJECTED,
            severity=NotificationSeverity.WARNING,
            related_entity_type="assessment",
            related_entity_id=assessment_id,
        )
        
        # Send email notification
        try:
            from settings import settings
            
            student_data = self.db.get_user_by_id(student_user_id, use_cache=False)
            if student_data:
                student_email = student_data.get("email")
                student_name = f"{student_data.get('first_name', '')} {student_data.get('last_name', '')}".strip() or "Student"
                if student_email:
                    assessment_link = f"{settings.FRONTEND_URL}/student/assessments"
                    
                    email_service.send_result_rejected_notification(
                        to_email=student_email,
                        student_name=student_name,
                        quiz_title=quiz_title,
                        course_name=course_name or "Course",
                        teacher_name=teacher_name or "Your instructor",
                        reason=reason,
                        assessment_link=assessment_link
                    )
        except Exception as email_error:
            logger.warning(f"Failed to send result rejected email: {str(email_error)}")
        
        return notification
    
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

