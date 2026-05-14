# admin/routes.py
"""
Admin routes for Institute/Organization management.
Allows admins to manage teachers, students, and courses within their university.
"""

from datetime import datetime, timedelta
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, status, UploadFile

from admin.dependencies import require_admin
from admin.models import (
    ActivityLogEntry,
    ActivityLogResponse,
    AIChatUsageStats,
    AIChatUsageSummary,
    BulkEnrollmentRequest,
    BulkEnrollmentResponse,
    BulkOperationResult,
    BulkSignupResponse,
    BulkStudentSignupRequest,
    CourseAssignmentRequest,
    CourseSummary,
    DashboardStats,
    EnrollmentSummary,
    LogoDeleteResponse,
    LogoGetResponse,
    LogoUploadResponse,
    SemesterCreateRequest,
    SemesterResponse,
    SemesterUpdateRequest,
    StudentCreateRequest,
    StudentEnrollmentRequest,
    StudentSearchResponse,
    StudentSummary,
    TeacherCreateRequest,
    TeacherSummary,
)
from auth.models import UserCreate
from auth.service import AuthService
from dependencies import get_current_user
from logger import logger
from models.user import User, UserRole
from services.branding_service import BrandingService
from services.cache_service import cache
from services.email_service import email_service
from settings import settings
from urllib.parse import urlparse
from utils.db import get_db
from utils.datetime_helpers import parse_datetime_safe
from utils.id_converter import IDConverter
from utils.query_helpers import EnrollmentQueryHelper

router = APIRouter()


# ==================== Dashboard Routes ====================


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Get dashboard statistics for the admin's university.
    Returns total counts of teachers, students, courses, and lectures.
    """
    _, university_id = admin_data

    try:
        # Check cache
        cache_key = f"admin_stats:{university_id}"
        cached_stats = cache.get("queries", cache_key)
        if cached_stats is not None:
            return DashboardStats(**cached_stats)

        # Get total teachers
        teachers_result = (
            db.admin_client.table("teacher")
            .select("id", count="exact")
            .eq("university_id", university_id)
            .execute()
        )
        total_teachers = (
            teachers_result.count
            if hasattr(teachers_result, "count")
            else len(teachers_result.data or [])
        )

        # Get total students
        students_result = (
            db.admin_client.table("student")
            .select("id", count="exact")
            .eq("university_id", university_id)
            .execute()
        )
        total_students = (
            students_result.count
            if hasattr(students_result, "count")
            else len(students_result.data or [])
        )

        # Get total courses
        courses_result = (
            db.admin_client.table("course")
            .select("id", count="exact")
            .eq("university_id", university_id)
            .execute()
        )
        total_courses = (
            courses_result.count
            if hasattr(courses_result, "count")
            else len(courses_result.data or [])
        )

        # Get total lectures (via courses)
        course_ids = [c["id"] for c in (courses_result.data or [])]
        lectures_result = (
            db.admin_client.table("lecture")
            .select("id", count="exact")
            .in_("course_id", course_ids)
            .execute()
        )
        total_lectures = (
            lectures_result.count
            if hasattr(lectures_result, "count")
            else len(lectures_result.data or [])
        )

        stats = {
            "total_teachers": total_teachers,
            "total_students": total_students,
            "total_courses": total_courses,
            "total_lectures": total_lectures,
        }

        # Cache for 5 minutes
        cache.set("queries", stats, cache_key, ttl=300)

        return DashboardStats(**stats)

    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching dashboard statistics",
        ) from e


_TEACHER_ACTIVITY_TYPES = frozenset({
    "LOGIN", "GENERATE_LECTURE", "GENERATE_LEARNING_MATERIALS",
    "DELETE_LECTURE", "PUBLISH_LECTURE",
})
_STUDENT_ACTIVITY_TYPES = frozenset({
    "STUDENT_LOGIN", "STUDENT_TAKE_ASSESSMENT", "STUDENT_TAKE_QUIZ",
    "STUDENT_CHAT", "STUDENT_DOWNLOAD", "STUDENT_GENERATE_QUIZ",
})


@router.get("/activity-log", response_model=ActivityLogResponse)
async def get_activity_log(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    user_type: str = Query("teacher", description="teacher | student"),
    teacher_id: Optional[str] = Query(None, description="Filter by teacher integer ID (teacher view only)"),
    activity_type: Optional[str] = Query(None, description="Filter by specific activity type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    Return paginated activity log for the admin's university.

    Set user_type=teacher (default) for teacher events or user_type=student
    for student events. Each row captures who acted, what they did, and when.
    """
    try:
        current_user, university_id_str = admin_data
        university_id = int(university_id_str)

        is_student_view = user_type.lower() == "student"
        allowed_types = (
            _STUDENT_ACTIVITY_TYPES if is_student_view
            else _TEACHER_ACTIVITY_TYPES
        )

        # Build base query filtered only by university first
        base_q = (
            db.get_admin_client()
            .table("teacher_activity_log")
            .select("*", count="exact")
            .eq("university_id", university_id)
            .order("created_at", desc=True)
        )

        # Apply activity-type filter using OR conditions (more reliable than .in_() for text columns)
        type_or = ",".join(f"activity_type.eq.{t}" for t in sorted(allowed_types))
        query = base_q.or_(type_or)

        if teacher_id and not is_student_view:
            query = query.eq("teacher_id", int(teacher_id))

        if activity_type:
            at = activity_type.upper()
            if at in allowed_types:
                query = query.eq("activity_type", at)

        offset = (page - 1) * page_size
        query = query.range(offset, offset + page_size - 1)

        result = query.execute()
        rows = result.data or []
        total = result.count or 0

        logger.info(
            f"[ActivityLog] query university={university_id} user_type={user_type} "
            f"rows={len(rows)} total={total}"
        )

        # Fallback: if the OR filter returned nothing, re-query without the
        # activity_type constraint so we can at least surface raw rows for
        # debugging and avoid a completely blank page.
        if not rows:
            fallback = (
                db.get_admin_client()
                .table("teacher_activity_log")
                .select("*", count="exact")
                .eq("university_id", university_id)
                .order("created_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            raw_rows = fallback.data or []
            if raw_rows:
                logger.warning(
                    f"[ActivityLog] OR filter returned 0 rows but fallback found {len(raw_rows)}. "
                    f"activity_types in DB: {list({r.get('activity_type') for r in raw_rows})}"
                )
                # Show the fallback rows — mismatched types will still render
                rows = raw_rows
                total = fallback.count or len(raw_rows)

        # Batch-enrich with user names / emails
        user_ids = list({r["user_id"] for r in rows if r.get("user_id")})
        user_map: dict = {}
        if user_ids:
            users_result = (
                db.get_admin_client()
                .table("users")
                .select("id, first_name, last_name, email")
                .in_("id", user_ids)
                .execute()
            )
            for u in (users_result.data or []):
                user_map[u["id"]] = u

        items = []
        for r in rows:
            uid = r.get("user_id")
            u = user_map.get(uid, {})
            first = u.get("first_name", "")
            last = u.get("last_name", "")
            full_name = f"{first} {last}".strip() or None
            email = u.get("email")

            items.append(
                ActivityLogEntry(
                    id=r["id"],
                    user_id=uid,
                    university_id=r.get("university_id"),
                    activity_type=r["activity_type"],
                    lecture_id=r.get("lecture_id"),
                    lecture_name=r.get("lecture_name"),
                    metadata=r.get("metadata"),
                    created_at=r["created_at"],
                    # Teacher fields
                    teacher_id=r.get("teacher_id") if not is_student_view else None,
                    teacher_name=full_name if not is_student_view else None,
                    teacher_email=email if not is_student_view else None,
                    # Student fields
                    student_id=r.get("student_id") if is_student_view else None,
                    student_name=full_name if is_student_view else None,
                    student_email=email if is_student_view else None,
                )
            )

        total_pages = max(1, -(-total // page_size))
        return ActivityLogResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

    except Exception as e:
        logger.error(f"Error fetching activity log: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching activity log",
        ) from e


@router.get("/ai-chat/usage", response_model=AIChatUsageStats)
async def get_ai_chat_usage(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Get AI chat usage statistics for all students in the admin's university.
    Shows daily message counts, limits, and usage patterns.
    """
    _, university_id = admin_data
    
    try:
        # Convert university_id to integer if needed
        university_int_id = await IDConverter.uuid_to_int(db, "university", university_id) if IDConverter.is_uuid(university_id) else university_id
        if not university_int_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="University not found",
            )
        
        # Get all students in this university
        students_result = (
            db.admin_client.table("student")
            .select("id, user_id, university_id")
            .eq("university_id", university_int_id)
            .execute()
        )
        
        if not students_result.data:
            return AIChatUsageStats(
                total_students=0,
                students_with_usage=0,
                total_messages_today=0,
                total_messages_all_time=0,
                students_at_limit=0,
                daily_limit=20,
                usage_by_student=[],
            )
        
        # Get user IDs for all students
        student_user_ids = [student["user_id"] for student in students_result.data]
        
        # Get today's date range (UTC)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        daily_limit = 20
        
        # Get all conversations for these students
        conversations_result = (
            db.admin_client.table("ai_conversation")
            .select("id, user_id")
            .in_("user_id", student_user_ids)
            .execute()
        )
        
        # Group conversations by user_id
        user_conversations = {}
        for conv in conversations_result.data:
            user_id = conv["user_id"]
            if user_id not in user_conversations:
                user_conversations[user_id] = []
            user_conversations[user_id].append(conv["id"])
        
        # Get all messages for these conversations
        all_conversation_ids = [conv["id"] for conv in conversations_result.data] if conversations_result.data else []
        
        # Count messages today and all-time per user
        usage_by_student = []
        total_messages_today = 0
        total_messages_all_time = 0
        students_at_limit = 0
        
        for student in students_result.data:
            user_id = student["user_id"]
            student_int_id = student["id"]
            
            # Get student user details
            user_result = (
                db.admin_client.table("users")
                .select("id, email, first_name, last_name")
                .eq("id", user_id)
                .execute()
            )
            
            if not user_result.data:
                continue
            
            user_data = user_result.data[0]
            conversation_ids = user_conversations.get(user_id, [])
            
            # Count messages today
            messages_today = 0
            if conversation_ids:
                messages_today_result = (
                    db.admin_client.table("chat_message")
                    .select("id", count="exact")
                    .in_("conversation_id", conversation_ids)
                    .eq("role", "USER")
                    .gte("created_at", today_start.isoformat())
                    .lt("created_at", today_end.isoformat())
                    .execute()
                )
                if hasattr(messages_today_result, "count") and messages_today_result.count is not None:
                    messages_today = messages_today_result.count
                else:
                    messages_today = len(messages_today_result.data) if messages_today_result.data else 0
            
            # Count all-time messages
            total_messages = 0
            if conversation_ids:
                all_messages_result = (
                    db.admin_client.table("chat_message")
                    .select("id", count="exact")
                    .in_("conversation_id", conversation_ids)
                    .eq("role", "USER")
                    .execute()
                )
                if hasattr(all_messages_result, "count") and all_messages_result.count is not None:
                    total_messages = all_messages_result.count
                else:
                    total_messages = len(all_messages_result.data) if all_messages_result.data else 0
            
            # Convert IDs to UUIDs for response
            user_uuid = await IDConverter.int_to_uuid(db, "users", user_id) if isinstance(user_id, int) else user_id
            student_uuid = await IDConverter.int_to_uuid(db, "student", student_int_id) if isinstance(student_int_id, int) else student_int_id
            
            remaining = max(0, daily_limit - messages_today)
            if messages_today >= daily_limit:
                students_at_limit += 1
            
            total_messages_today += messages_today
            total_messages_all_time += total_messages
            
            usage_by_student.append(
                AIChatUsageSummary(
                    user_id=user_uuid,
                    student_id=student_uuid,
                    email=user_data.get("email", ""),
                    first_name=user_data.get("first_name", ""),
                    last_name=user_data.get("last_name", ""),
                    messages_today=messages_today,
                    daily_limit=daily_limit,
                    remaining=remaining,
                    reset_at=today_end,
                    total_conversations=len(conversation_ids),
                    total_messages_all_time=total_messages,
                )
            )
        
        students_with_usage = len([s for s in usage_by_student if s.total_messages_all_time > 0])
        
        return AIChatUsageStats(
            total_students=len(students_result.data),
            students_with_usage=students_with_usage,
            total_messages_today=total_messages_today,
            total_messages_all_time=total_messages_all_time,
            students_at_limit=students_at_limit,
            daily_limit=daily_limit,
            usage_by_student=usage_by_student,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching AI chat usage stats: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching AI chat usage statistics",
        ) from e


# ==================== Teacher Management Routes ====================


@router.get("/teachers")
async def list_teachers(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: str = Query(None, description="Search by name, email, department"),
    department: str = Query(None, description="Filter by department"),
    sort_by: str = Query("first_name", description="Sort by: first_name, last_name, email, department, total_courses"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
):
    """
    List all teachers in the admin's university with pagination and filtering.
    
    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - search: Search by name, email, or department (case-insensitive)
    - department: Filter by department
    - sort_by: Sort field (default: first_name)
    - sort_order: asc or desc (default: asc)
    """
    _, university_id = admin_data

    try:
        # Convert university_id UUID to integer for database query
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="University not found",
                )
        
        # Get all teachers for this university using integer ID
        teachers_query = (
            db.admin_client.table("teacher")
            .select("*, users!inner(*)")
            .eq("university_id", university_int_id)
        )
        
        # Apply department filter at DB level
        if department:
            teachers_query = teachers_query.eq("department", department)
        
        teachers_result = teachers_query.execute()

        all_teachers_data = teachers_result.data or []
        
        # Apply search filter in Python (across multiple fields)
        if search:
            search_lower = search.lower()
            filtered = []
            for td in all_teachers_data:
                ud = td.get("users", {})
                if (
                    search_lower in ud.get("first_name", "").lower()
                    or search_lower in ud.get("last_name", "").lower()
                    or search_lower in ud.get("email", "").lower()
                    or search_lower in (td.get("department") or "").lower()
                    or search_lower in (td.get("specialization") or "").lower()
                    or search_lower in f"{ud.get('first_name', '')} {ud.get('last_name', '')}".lower()
                ):
                    filtered.append(td)
            all_teachers_data = filtered
        
        # Sort
        sort_desc = sort_order.lower() == "desc"
        sort_key_map = {
            "first_name": lambda td: (td.get("users", {}).get("first_name") or "").lower(),
            "last_name": lambda td: (td.get("users", {}).get("last_name") or "").lower(),
            "email": lambda td: (td.get("users", {}).get("email") or "").lower(),
            "department": lambda td: (td.get("department") or "").lower(),
        }
        sort_fn = sort_key_map.get(sort_by, sort_key_map["first_name"])
        all_teachers_data.sort(key=sort_fn, reverse=sort_desc)
        
        # Calculate pagination
        total = len(all_teachers_data)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = all_teachers_data[start:end]
        
        teachers = []
        for teacher_data in page_data:
            user_data = teacher_data.get("users", {})
            teacher_id_int = teacher_data["id"]  # Integer ID from database
            user_id_int = teacher_data["user_id"]  # Integer ID from database
            
            # Convert integer IDs to UUIDs for API response
            teacher_id_uuid = await IDConverter.int_to_uuid(db, "teacher", teacher_id_int) if teacher_id_int else None
            if not teacher_id_uuid:
                teacher_id_uuid = str(teacher_id_int)  # Fallback
            
            user_id_uuid = await IDConverter.int_to_uuid(db, "users", user_id_int) if user_id_int else None
            if not user_id_uuid:
                user_id_uuid = str(user_id_int)  # Fallback

            # Get courses for this teacher (via lectures) using integer teacher_id
            courses_result = (
                db.admin_client.table("lecture")
                .select("course_id, course!inner(id, name, code)")
                .eq("teacher_id", teacher_id_int)  # Use integer ID for query
                .execute()
            )

            # Count unique courses and lectures
            course_ids = set()
            lecture_count = 0
            course_details = {}

            for lecture in courses_result.data or []:
                course_id = lecture.get("course_id")
                if course_id:
                    course_ids.add(course_id)
                    lecture_count += 1
                    if course_id not in course_details:
                        course_info = lecture.get("course", {})
                        course_details[course_id] = {
                            "id": course_info.get("id"),
                            "name": course_info.get("name"),
                            "code": course_info.get("code"),
                        }

            # Get enrollment counts for each course
            course_summaries = []
            for course_id_int, course_info in course_details.items():
                # Convert course_id to UUID for API response
                course_id_uuid = await IDConverter.int_to_uuid(db, "course", course_id_int) if course_id_int else None
                if not course_id_uuid:
                    course_id_uuid = str(course_id_int)  # Fallback
                
                enrollments_result = (
                    db.admin_client.table("enrollment")
                    .select("id", count="exact")
                    .eq("course_id", course_id_int)  # Use integer ID for query
                    .eq("is_active", True)
                    .execute()
                )
                enrollment_count = (
                    enrollments_result.count
                    if hasattr(enrollments_result, "count")
                    else len(enrollments_result.data or [])
                )

                # Count lectures for this course using integer IDs
                lectures_for_course = (
                    db.admin_client.table("lecture")
                    .select("id", count="exact")
                    .eq("course_id", course_id_int)  # Use integer ID
                    .eq("teacher_id", teacher_id_int)  # Use integer ID
                    .execute()
                )
                course_lecture_count = (
                    lectures_for_course.count
                    if hasattr(lectures_for_course, "count")
                    else len(lectures_for_course.data or [])
                )

                course_summaries.append(
                    CourseSummary(
                        course_id=course_id_uuid,  # Use UUID for API
                        course_name=course_info["name"],
                        course_code=course_info["code"],
                        total_lectures=course_lecture_count,
                        total_enrollments=enrollment_count,
                    )
                )

            teachers.append(
                TeacherSummary(
                    teacher_id=teacher_id_uuid,  # Use UUID for API
                    user_id=user_id_uuid,  # Use UUID for API
                    first_name=user_data.get("first_name", ""),
                    last_name=user_data.get("last_name", ""),
                    email=user_data.get("email", ""),
                    department=teacher_data.get("department"),
                    specialization=teacher_data.get("specialization"),
                    total_courses=len(course_ids),
                    total_lectures=lecture_count,
                    courses=course_summaries,
                )
            )

        return {
            "items": teachers,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing teachers: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching teachers",
        ) from e


@router.post("/teachers/create", status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_data: TeacherCreateRequest,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Create a new teacher account in the admin's university.
    Admin can sign up teachers and share credentials with them.
    """
    admin_user, university_id = admin_data

    try:
        # Check if email or username already exists
        existing_user = db.get_user_by_email(teacher_data.email, use_cache=False)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists",
            )

        existing_users = db.get_records(
            "users", {"username": teacher_data.username}, use_cache=False
        )
        if existing_users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

        # Create user using AuthService
        user_create = UserCreate(
            email=teacher_data.email,
            username=teacher_data.username,
            password=teacher_data.password,
            first_name=teacher_data.first_name,
            last_name=teacher_data.last_name,
            role=UserRole.TEACHER,
            university_id=university_id,
            department=teacher_data.department,
            specialization=teacher_data.specialization,
        )

        new_user = await AuthService.create_user(db, user_create)

        logger.info(
            f"Admin {admin_user.id} created teacher account "
            f"for {teacher_data.email}"
        )

        # Send activation email with one-time link
        try:
            activation_token = AuthService.create_activation_token(new_user.id)
            activation_link = (
                f"{settings.FRONTEND_URL}/activate-account?token={activation_token}"
            )
            
            teacher_name = f"{teacher_data.first_name} {teacher_data.last_name}".strip()
            email_service.send_activation_email(
                to_email=teacher_data.email,
                activation_link=activation_link,
                to_name=teacher_name
            )
            logger.info(f"Activation email sent to {teacher_data.email}")
        except Exception as email_error:
            logger.warning(f"Failed to send activation email: {email_error!s}")

        return {
            "message": "Teacher account created successfully",
            "user_id": new_user.id,
            "email": teacher_data.email,
            "username": teacher_data.username,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating teacher: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating teacher account",
        ) from e


# ==================== Student Management Routes ====================


@router.get("/students")
async def list_students(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: str = Query(None, description="Search by name, email, or student ID"),
    year_of_study: int = Query(None, description="Filter by year of study"),
    course_id: str = Query(None, description="Filter by enrolled course ID"),
    sort_by: str = Query("first_name", description="Sort by: first_name, last_name, email, student_id, year_of_study, created_at"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
):
    """
    List all students in the admin's university with pagination and filtering.
    
    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - search: Search by name, email, or student ID (case-insensitive)
    - year_of_study: Filter by year of study
    - course_id: Filter by enrolled course ID (UUID)
    - sort_by: Sort field (default: first_name)
    - sort_order: asc or desc (default: asc)
    """
    _, university_id = admin_data

    try:
        # First get total count for pagination metadata
        count_query = (
            db.admin_client.table("student")
            .select("id", count="exact")
            .eq("university_id", university_id)
        )
        count_result = count_query.execute()
        
        # Get all students for this university (we filter in Python for search)
        students_query = (
            db.admin_client.table("student")
            .select("*, users!inner(*)")
            .eq("university_id", university_id)
        )
        
        # Apply year_of_study filter at DB level
        if year_of_study is not None:
            students_query = students_query.eq("year_of_study", year_of_study)
        
        students_result = students_query.execute()
        all_students_data = students_result.data or []
        
        # Apply search filter in Python (across multiple fields)
        if search:
            search_lower = search.lower()
            filtered = []
            for sd in all_students_data:
                ud = sd.get("users", {})
                if (
                    search_lower in ud.get("first_name", "").lower()
                    or search_lower in ud.get("last_name", "").lower()
                    or search_lower in ud.get("email", "").lower()
                    or search_lower in sd.get("student_id", "").lower()
                    or search_lower in f"{ud.get('first_name', '')} {ud.get('last_name', '')}".lower()
                ):
                    filtered.append(sd)
            all_students_data = filtered
        
        # Apply course_id filter if specified
        enrolled_student_ids = None
        if course_id:
            course_int_id = course_id
            if IDConverter.is_uuid(course_id):
                course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
            if course_int_id:
                enrollments_for_course = (
                    db.admin_client.table("enrollment")
                    .select("student_id")
                    .eq("course_id", course_int_id)
                    .eq("is_active", True)
                    .execute()
                )
                enrolled_student_ids = set(
                    e["student_id"] for e in (enrollments_for_course.data or [])
                )
                all_students_data = [
                    sd for sd in all_students_data
                    if sd["id"] in enrolled_student_ids
                ]
        
        # Sort
        sort_desc = sort_order.lower() == "desc"
        sort_key_map = {
            "first_name": lambda sd: (sd.get("users", {}).get("first_name") or "").lower(),
            "last_name": lambda sd: (sd.get("users", {}).get("last_name") or "").lower(),
            "email": lambda sd: (sd.get("users", {}).get("email") or "").lower(),
            "student_id": lambda sd: (sd.get("student_id") or "").lower(),
            "year_of_study": lambda sd: sd.get("year_of_study") or 0,
            "created_at": lambda sd: sd.get("users", {}).get("created_at") or "",
        }
        sort_fn = sort_key_map.get(sort_by, sort_key_map["first_name"])
        all_students_data.sort(key=sort_fn, reverse=sort_desc)
        
        # Calculate pagination
        total = len(all_students_data)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = all_students_data[start:end]
        
        # Build student summaries for this page only
        students = []
        for student_data in page_data:
            user_data = student_data.get("users", {})
            student_db_id = student_data["id"]
            student_university_id = student_data["student_id"]  # University student ID

            # Get enrollments for this student
            enrollments = await EnrollmentQueryHelper.get_student_enrollments(
                db, str(student_db_id)
            )

            enrollment_summaries = []
            for enrollment in enrollments:
                course = enrollment.get("course", {})
                semester = enrollment.get("semester", {})

                enrolled_at_str = enrollment.get("enrolled_at")
                enrolled_at = parse_datetime_safe(enrolled_at_str)

                # Convert integer IDs to UUIDs for API response
                enrollment_id_uuid = await IDConverter.int_to_uuid(db, "enrollment", enrollment["id"])
                if not enrollment_id_uuid:
                    enrollment_id_uuid = str(enrollment["id"])  # Fallback
                
                course_id_uuid = await IDConverter.int_to_uuid(db, "course", course.get("id")) if course.get("id") else ""
                if course.get("id") and not course_id_uuid:
                    course_id_uuid = str(course.get("id"))  # Fallback

                enrollment_summaries.append(
                    EnrollmentSummary(
                        enrollment_id=enrollment_id_uuid,
                        course_id=course_id_uuid,
                        course_name=course.get("name", ""),
                        course_code=course.get("code", ""),
                        semester_name=semester.get("name"),
                        enrolled_at=enrolled_at,
                        is_active=enrollment.get("is_active", True),
                    )
                )

            # Convert user_id from integer to UUID for API response
            user_id_uuid = await IDConverter.int_to_uuid(db, "users", student_data["user_id"])
            if not user_id_uuid:
                user_id_uuid = str(student_data["user_id"])  # Fallback
            
            students.append(
                StudentSummary(
                    student_id=student_university_id,
                    user_id=user_id_uuid,
                    first_name=user_data.get("first_name", ""),
                    last_name=user_data.get("last_name", ""),
                    email=user_data.get("email", ""),
                    year_of_study=student_data.get("year_of_study"),
                    total_enrollments=len(enrollment_summaries),
                    enrollments=enrollment_summaries,
                )
            )

        return {
            "items": students,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing students: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching students",
        ) from e


@router.get("/students/search/{student_id}", response_model=StudentSearchResponse)
async def search_student_by_id(
    student_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Search for a student by their university student ID.
    Returns student details with all their enrollments.
    """
    _, university_id = admin_data

    try:
        # Search for student by student_id (university student ID)
        # within this university
        student_result = (
            db.admin_client.table("student")
            .select("*, users!inner(*)")
            .eq("student_id", student_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not student_result.data:
            return StudentSearchResponse(student=None, found=False)

        student_data = student_result.data[0]
        user_data = student_data.get("users", {})
        student_db_id = student_data["id"]

        # Get enrollments for this student
        enrollments = await EnrollmentQueryHelper.get_student_enrollments(
            db, str(student_db_id)
        )

        enrollment_summaries = []
        for enrollment in enrollments:
            course = enrollment.get("course", {})
            semester = enrollment.get("semester", {})

            enrolled_at_str = enrollment.get("enrolled_at")
            enrolled_at = parse_datetime_safe(enrolled_at_str)

            # Convert integer IDs to UUIDs for API response
            enrollment_id_uuid = await IDConverter.int_to_uuid(db, "enrollment", enrollment["id"])
            if not enrollment_id_uuid:
                enrollment_id_uuid = str(enrollment["id"])  # Fallback
            
            course_id_uuid = await IDConverter.int_to_uuid(db, "course", course.get("id")) if course.get("id") else ""
            if course.get("id") and not course_id_uuid:
                course_id_uuid = str(course.get("id"))  # Fallback

            enrollment_summaries.append(
                EnrollmentSummary(
                    enrollment_id=enrollment_id_uuid,
                    course_id=course_id_uuid,
                    course_name=course.get("name", ""),
                    course_code=course.get("code", ""),
                    semester_name=semester.get("name"),
                    enrolled_at=enrolled_at,
                    is_active=enrollment.get("is_active", True),
                )
            )

        # Convert user_id from integer to UUID for API response
        user_id_uuid = await IDConverter.int_to_uuid(db, "users", student_data["user_id"])
        if not user_id_uuid:
            user_id_uuid = str(student_data["user_id"])  # Fallback
        
        student_summary = StudentSummary(
            student_id=student_data["student_id"],
            user_id=user_id_uuid,
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name", ""),
            email=user_data.get("email", ""),
            year_of_study=student_data.get("year_of_study"),
            total_enrollments=len(enrollment_summaries),
            enrollments=enrollment_summaries,
        )

        return StudentSearchResponse(student=student_summary, found=True)

    except Exception as e:
        logger.error(f"Error searching student: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error searching for student",
        ) from e


@router.post("/students/create", status_code=status.HTTP_201_CREATED)
async def create_student(
    student_data: StudentCreateRequest,
    background_tasks: BackgroundTasks,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Create a new student account in the admin's university.
    Admin can sign up students and share credentials with them.
    """
    admin_user, university_id = admin_data

    try:
        # Convert university_id from UUID to integer if needed
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid university ID",
                )
        elif isinstance(university_id, str):
            try:
                university_int_id = int(university_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid university ID format",
                )
        
        # Check if student_id already exists in this university using integer ID
        existing_student = db.get_records(
            "student",
            {
                "student_id": student_data.student_id,
                "university_id": university_int_id,  # Use integer ID
            },
        )
        if existing_student:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Student with ID '{student_data.student_id}' "
                    "already exists in your university"
                ),
            )

        # Create user using AuthService - pass UUID string for compatibility
        # AuthService will convert it to integer internally
        user_create = UserCreate(
            email=student_data.email,
            username=student_data.username,
            password=student_data.password,
            first_name=student_data.first_name,
            last_name=student_data.last_name,
            role=UserRole.STUDENT,
            university_id=university_id,  # Pass UUID string - AuthService handles conversion
            student_id=student_data.student_id,
            year_of_study=student_data.year_of_study,
        )

        new_user = await AuthService.create_user(db, user_create)

        logger.info(
            f"Admin {admin_user.id} created student account "
            f"for {student_data.student_id}"
        )

        # Send activation email with one-time link in background (non-blocking)
        activation_token = AuthService.create_activation_token(new_user.id)
        activation_link = (
            f"{settings.FRONTEND_URL}/activate-account?token={activation_token}"
        )
        student_name = f"{student_data.first_name} {student_data.last_name}".strip()
        
        # Add email sending as background task (won't block the response)
        background_tasks.add_task(
            email_service.send_activation_email,
            to_email=student_data.email,
            activation_link=activation_link,
            to_name=student_name
        )

        return {
            "message": "Student account created successfully",
            "user_id": new_user.id,
            "student_id": student_data.student_id,
            "email": student_data.email,
            "username": student_data.username,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Error creating student: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating student account",
        ) from e


# ==================== Enrollment Management Routes ====================


@router.post("/enrollments/create", status_code=status.HTTP_201_CREATED)
async def enroll_student_in_course(
    enrollment_request: StudentEnrollmentRequest,
    background_tasks: BackgroundTasks,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Enroll a student in a course.
    Admin can enroll students from their university in any course from their university.
    """
    admin_user, university_id = admin_data

    try:
        # Find student by university student_id within this university
        student_result = (
            db.admin_client.table("student")
            .select("id")
            .eq("student_id", enrollment_request.student_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not student_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Student with ID '{enrollment_request.student_id}' "
                    "not found in your university"
                ),
            )

        student_db_id = student_result.data[0]["id"]

        # Convert course_id and semester_id from UUIDs to integer IDs if needed
        course_int_id = enrollment_request.course_id
        if IDConverter.is_uuid(enrollment_request.course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", enrollment_request.course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found in your university",
                )

        semester_int_id = enrollment_request.semester_id
        if IDConverter.is_uuid(enrollment_request.semester_id):
            semester_int_id = await IDConverter.uuid_to_int(db, "semester", enrollment_request.semester_id)
            if not semester_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Semester not found in your university",
                )

        # Verify course belongs to this university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .eq("id", course_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found in your university",
            )

        course = course_result.data[0]

        # Verify semester belongs to this university (university-level semesters)
        semester_result = (
            db.admin_client.table("semester")
            .select("id, name, university_id")
            .eq("id", semester_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found in your university",
            )

        # Check if already enrolled
        existing_enrollment = (
            db.admin_client.table("enrollment")
            .select("*")
            .eq("student_id", student_db_id)  # Use integer ID directly
            .eq("course_id", course_int_id)
            .execute()
        )

        if existing_enrollment.data and len(existing_enrollment.data) > 0:
            enrollment = existing_enrollment.data[0]
            if enrollment.get("is_active"):
                return {
                    "message": "Student is already enrolled in this course",
                    "enrollment_id": enrollment["id"],
                    "course_name": course["name"],
                    "course_code": course["code"],
                }
            else:
                # Reactivate the enrollment
                db.admin_client.table("enrollment").update({
                    "is_active": True,
                    "semester_id": semester_int_id,
                    "enrolled_at": datetime.utcnow().isoformat(),
                }).eq("id", enrollment["id"]).execute()

                # Invalidate cache
                cache.invalidate_student(str(student_db_id))

                return {
                    "message": "Student re-enrolled in course successfully",
                    "enrollment_id": enrollment["id"],
                    "course_name": course["name"],
                    "course_code": course["code"],
                }

        # Create new enrollment
        # Note: Don't set 'id' - let database auto-generate integer ID
        enrollment_data = {
            "student_id": student_db_id,  # Use integer ID directly
            "course_id": course_int_id,
            "semester_id": semester_int_id,
            "enrolled_at": datetime.utcnow().isoformat(),
            "is_active": True,
        }

        result = db.admin_client.table("enrollment").insert(enrollment_data).execute()

        # Invalidate cache
        cache.invalidate_student(str(student_db_id))  # Cache uses string keys

        logger.info(
            f"Admin {admin_user.id} enrolled student "
            f"{enrollment_request.student_id} in course "
            f"{enrollment_request.course_id}"
        )

        # Send enrollment confirmation email in background (non-blocking)
        # Get student user info
        student_user_result = (
            db.admin_client.table("student")
            .select("user_id, users!inner(*)")
            .eq("id", student_db_id)  # Use integer ID directly
            .execute()
        )
        
        if student_user_result.data:
            student_user_data = student_user_result.data[0].get("users", {})
            student_email = student_user_data.get("email")
            student_name = f"{student_user_data.get('first_name', '')} {student_user_data.get('last_name', '')}".strip()
            
            # Get teacher name from course_teacher junction table or created_by_teacher_id
            teacher_name = None
            
            # First, try to get teacher from course_teacher table
            course_teacher_result = (
                db.admin_client.table("course_teacher")
                .select("teacher_id")
                .eq("course_id", course_int_id)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            
            teacher_id = None
            if course_teacher_result.data:
                teacher_id = course_teacher_result.data[0].get("teacher_id")
            
            # If no teacher from course_teacher, try created_by_teacher_id
            if not teacher_id:
                course_result = (
                    db.admin_client.table("course")
                    .select("created_by_teacher_id")
                    .eq("id", course_int_id)
                    .execute()
                )
                if course_result.data:
                    teacher_id = course_result.data[0].get("created_by_teacher_id")
            
            # Get teacher user info if we found a teacher_id
            if teacher_id:
                teacher_result = (
                    db.admin_client.table("teacher")
                    .select("user_id, users!inner(first_name, last_name)")
                    .eq("id", teacher_id)
                    .execute()
                )
                if teacher_result.data:
                    teacher_data = teacher_result.data[0]
                    teacher_user_data = teacher_data.get("users", {})
                    teacher_name = f"{teacher_user_data.get('first_name', '')} {teacher_user_data.get('last_name', '')}".strip()
            
            if student_email:
                # Get course UUID for the link (use original course_id if it's a UUID, otherwise convert)
                course_id_for_link = enrollment_request.course_id
                if not IDConverter.is_uuid(course_id_for_link):
                    # Convert int ID to UUID for the link
                    course_id_for_link = await IDConverter.int_to_uuid(db, "course", course_int_id)
                    if not course_id_for_link:
                        course_id_for_link = enrollment_request.course_id  # Fallback to original
                
                course_link = f"{settings.FRONTEND_URL}/student/courses/{course_id_for_link}"
                
                # Add email sending as background task (won't block the response)
                background_tasks.add_task(
                    email_service.send_enrollment_confirmation,
                    to_email=student_email,
                    student_name=student_name or "Student",
                    course_name=course["name"],
                    teacher_name=teacher_name,
                    dashboard_link=course_link
                )

        return {
            "message": "Student enrolled in course successfully",
            "enrollment_id": result.data[0]["id"],
            "course_name": course["name"],
            "course_code": course["code"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enrolling student: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing enrollment",
        ) from e


@router.get("/courses/{course_id}/enrollments")
async def get_course_enrollments(
    course_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: str = Query(None, description="Search by student name, email, or student ID"),
    sort_by: str = Query("first_name", description="Sort by: first_name, last_name, email, student_id"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
):
    """
    Get all students enrolled in a specific course with pagination.
    Only shows students from the admin's university.
    
    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - search: Search by student name, email, or student ID
    - sort_by: Sort field (default: first_name)
    - sort_order: asc or desc (default: asc)
    """
    _, university_id = admin_data

    try:
        # Convert UUID to integer ID if needed
        course_int_id = course_id
        if IDConverter.is_uuid(course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found in your university",
                )

        # Verify course belongs to this university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .eq("id", course_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found in your university",
            )

        # Get enrollments with student info
        enrollments_result = (
            db.admin_client.table("enrollment")
            .select("*, student!inner(*, users!inner(*))")
            .eq("course_id", course_int_id)
            .eq("is_active", True)
            .execute()
        )

        all_enrollment_data = enrollments_result.data or []
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            filtered = []
            for enr in all_enrollment_data:
                sd = enr.get("student", {})
                ud = sd.get("users", {})
                if (
                    search_lower in ud.get("first_name", "").lower()
                    or search_lower in ud.get("last_name", "").lower()
                    or search_lower in ud.get("email", "").lower()
                    or search_lower in sd.get("student_id", "").lower()
                    or search_lower in f"{ud.get('first_name', '')} {ud.get('last_name', '')}".lower()
                ):
                    filtered.append(enr)
            all_enrollment_data = filtered
        
        # Sort
        sort_desc = sort_order.lower() == "desc"
        sort_key_map = {
            "first_name": lambda e: (e.get("student", {}).get("users", {}).get("first_name") or "").lower(),
            "last_name": lambda e: (e.get("student", {}).get("users", {}).get("last_name") or "").lower(),
            "email": lambda e: (e.get("student", {}).get("users", {}).get("email") or "").lower(),
            "student_id": lambda e: (e.get("student", {}).get("student_id") or "").lower(),
        }
        sort_fn = sort_key_map.get(sort_by, sort_key_map["first_name"])
        all_enrollment_data.sort(key=sort_fn, reverse=sort_desc)
        
        # Calculate pagination
        total = len(all_enrollment_data)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = all_enrollment_data[start:end]

        students = []
        for enrollment in page_data:
            student_data = enrollment.get("student", {})
            user_data = student_data.get("users", {})
            student_db_id = student_data["id"]

            # Get all enrollments for this student
            all_enrollments = await EnrollmentQueryHelper.get_student_enrollments(
                db, str(student_db_id)
            )

            enrollment_summaries = []
            for enr in all_enrollments:
                course_info = enr.get("course", {})
                semester = enr.get("semester", {})

                enrolled_at_str = enr.get("enrolled_at")
                enrolled_at = parse_datetime_safe(enrolled_at_str)

                # Convert integer IDs to UUIDs for API response
                enrollment_id_uuid = await IDConverter.int_to_uuid(db, "enrollment", enr["id"])
                if not enrollment_id_uuid:
                    enrollment_id_uuid = str(enr["id"])  # Fallback
                
                course_id_uuid = await IDConverter.int_to_uuid(db, "course", course_info.get("id")) if course_info.get("id") else ""
                if course_info.get("id") and not course_id_uuid:
                    course_id_uuid = str(course_info.get("id"))  # Fallback

                enrollment_summaries.append(
                    EnrollmentSummary(
                        enrollment_id=enrollment_id_uuid,
                        course_id=course_id_uuid,
                        course_name=course_info.get("name", ""),
                        course_code=course_info.get("code", ""),
                        semester_name=semester.get("name"),
                        enrolled_at=enrolled_at,
                        is_active=enr.get("is_active", True),
                    )
                )

            # Convert user_id from integer to UUID for API response
            user_id_raw = student_data.get("user_id", "")
            user_id_uuid = ""
            if user_id_raw:
                user_id_uuid = await IDConverter.int_to_uuid(db, "users", user_id_raw)
                if not user_id_uuid:
                    user_id_uuid = str(user_id_raw)  # Fallback
            
            students.append(
                StudentSummary(
                    student_id=student_data.get("student_id", ""),
                    user_id=user_id_uuid,
                    first_name=user_data.get("first_name", ""),
                    last_name=user_data.get("last_name", ""),
                    email=user_data.get("email", ""),
                    year_of_study=student_data.get("year_of_study"),
                    total_enrollments=len(enrollment_summaries),
                    enrollments=enrollment_summaries,
                )
            )

        return {
            "items": students,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching course enrollments: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching course enrollments",
        ) from e


# ==================== Course Management Routes ====================


@router.get("/courses")
async def list_university_courses(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: str = Query(None, description="Search by course name or code"),
    sort_by: str = Query("name", description="Sort by: name, code, created_at, total_enrollments"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
):
    """
    Get all courses in the admin's university with pagination.
    
    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - search: Search by course name or code (case-insensitive)
    - sort_by: Sort field (default: name)
    - sort_order: asc or desc (default: asc)
    """
    _, university_id = admin_data

    try:
        # Convert university_id UUID to integer for database query
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="University not found",
                )
        
        # Get all courses for this university using integer ID
        courses_result = (
            db.admin_client.table("course")
            .select("*")
            .eq("university_id", university_int_id)
            .execute()
        )
        courses_raw = courses_result.data if courses_result.data else []

        if not courses_raw:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 1,
                "has_next": False,
                "has_previous": False,
            }
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            courses_raw = [
                c for c in courses_raw
                if search_lower in (c.get("name") or "").lower()
                or search_lower in (c.get("code") or "").lower()
            ]

        # Extract integer course IDs for enrollment query
        course_ids = [c["id"] for c in courses_raw]  # These are integer IDs

        # Batch fetch enrollment counts for all courses using integer IDs
        enrollments_result = (
            db.admin_client.table("enrollment")
            .select("course_id")
            .in_("course_id", course_ids)
            .eq("is_active", True)
            .execute()
        )

        enrollment_counts = {}
        for e in enrollments_result.data or []:
            cid = e.get("course_id")
            enrollment_counts[cid] = enrollment_counts.get(cid, 0) + 1
        
        # Sort
        sort_desc = sort_order.lower() == "desc"
        if sort_by == "total_enrollments":
            courses_raw.sort(key=lambda c: enrollment_counts.get(c["id"], 0), reverse=sort_desc)
        else:
            sort_key_map = {
                "name": lambda c: (c.get("name") or "").lower(),
                "code": lambda c: (c.get("code") or "").lower(),
                "created_at": lambda c: c.get("created_at") or "",
            }
            sort_fn = sort_key_map.get(sort_by, sort_key_map["name"])
            courses_raw.sort(key=sort_fn, reverse=sort_desc)
        
        # Calculate pagination
        total = len(courses_raw)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = courses_raw[start:end]

        # Enrich courses with enrollment counts and convert IDs to UUIDs
        enriched_courses = []
        for course in page_data:
            course_id_int = course.get("id")
            # Convert integer course_id to UUID for API response
            course_id_uuid = await IDConverter.int_to_uuid(db, "course", course_id_int) if course_id_int else None
            if not course_id_uuid:
                course_id_uuid = course.get("uuid") or str(course_id_int)  # Use existing uuid or fallback
            
            # Convert all IDs in course dict to UUIDs
            course_dict = dict(course)
            course_dict["id"] = course_id_uuid
            if "uuid" not in course_dict:
                course_dict["uuid"] = course_id_uuid
            
            enriched_courses.append(
                {
                    **course_dict,
                    "total_enrollments": enrollment_counts.get(course_id_int, 0),
                }
            )

        return {
            "items": enriched_courses,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching university courses: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching courses",
        ) from e


# ==================== Course Assignment Routes ====================


@router.post("/courses/assign", status_code=status.HTTP_201_CREATED)
async def assign_course_to_teacher(
    assignment_request: CourseAssignmentRequest,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Assign a course to a teacher.
    Admin can assign courses from their university to teachers in their university.
    """
    admin_user, university_id = admin_data

    try:
        # Convert course_id from UUID to integer ID if needed
        course_int_id = assignment_request.course_id
        if IDConverter.is_uuid(assignment_request.course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", assignment_request.course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found in your university",
                )

        # Verify course belongs to admin's university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code, university_id")
            .eq("id", course_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found in your university",
            )

        course = course_result.data[0]

        # Convert teacher_user_id from UUID to integer if needed
        teacher_user_int_id = assignment_request.teacher_user_id
        if IDConverter.is_uuid(assignment_request.teacher_user_id):
            teacher_user_int_id = await IDConverter.uuid_to_int(db, "users", assignment_request.teacher_user_id)
            if not teacher_user_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Teacher user not found",
                )
        
        # Convert university_id UUID to integer for query
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="University not found",
                )
        
        # Get teacher profile for the user using integer IDs
        teacher_result = (
            db.admin_client.table("teacher")
            .select("id, user_id, university_id")
            .eq("user_id", teacher_user_int_id)  # Use integer ID
            .eq("university_id", university_int_id)  # Use integer ID
            .limit(1)
            .execute()
        )

        if not teacher_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found in your university",
            )

        teacher = teacher_result.data[0]
        teacher_id = teacher["id"]  # Already an integer

        # Convert admin_user.id from UUID to integer for assigned_by
        admin_user_int_id = admin_user.id
        if IDConverter.is_uuid(admin_user.id):
            admin_user_int_id = await IDConverter.uuid_to_int(db, "users", admin_user.id)
            if not admin_user_int_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Admin user ID conversion failed",
                )

        # Check if assignment already exists
        existing_assignment = (
            db.admin_client.table("course_teacher")
            .select("*")
            .eq("course_id", course_int_id)
            .eq("teacher_id", teacher_id)
            .execute()
        )

        if existing_assignment.data:
            assignment = existing_assignment.data[0]
            # Reactivate if inactive
            if not assignment.get("is_active"):
                db.admin_client.table("course_teacher").update({
                    "is_active": True,
                    "assigned_by": admin_user_int_id,  # Use integer ID
                    "assigned_at": datetime.utcnow().isoformat(),
                }).eq("id", assignment["id"]).execute()

                # Invalidate cache
                cache.caches["courses"].delete_pattern(
                    f"courses:teacher_courses:{teacher_id}"
                )

                logger.info(
                    f"Admin {admin_user.id} reactivated course assignment: "
                    f"course {assignment_request.course_id} -> teacher {teacher_id}"
                )

                # Convert assignment ID to UUID for response
                assignment_id_uuid = await IDConverter.int_to_uuid(db, "course_teacher", assignment["id"]) if assignment.get("id") else None
                if not assignment_id_uuid:
                    assignment_id_uuid = assignment.get("uuid") or str(assignment["id"])
                
                return {
                    "message": "Course assignment reactivated successfully",
                    "assignment_id": assignment_id_uuid,  # Use UUID for API
                    "course_name": course["name"],
                    "course_code": course["code"],
                }
            else:
                # Convert assignment ID to UUID for response
                assignment_id_uuid = await IDConverter.int_to_uuid(db, "course_teacher", assignment["id"]) if assignment.get("id") else None
                if not assignment_id_uuid:
                    assignment_id_uuid = assignment.get("uuid") or str(assignment["id"])
                
                return {
                    "message": "Course is already assigned to this teacher",
                    "assignment_id": assignment_id_uuid,  # Use UUID for API
                    "course_name": course["name"],
                    "course_code": course["code"],
                }

        # Create new assignment
        # Don't set 'id' - let database auto-generate integer PK
        # Generate UUID for external API compatibility
        assignment_data = {
            "uuid": str(uuid4()),  # UUID for external APIs
            "course_id": course_int_id,  # Integer FK
            "teacher_id": teacher_id,  # Integer FK
            "assigned_by": admin_user_int_id,  # Integer FK
            "assigned_at": datetime.utcnow().isoformat(),
            "is_active": True,
        }

        try:
            result = (
                db.admin_client.table("course_teacher")
                .insert(assignment_data)
                .execute()
            )
            
            # Verify the insert actually succeeded
            if not result.data or len(result.data) == 0:
                logger.error(
                    f"Failed to create course assignment: Insert returned no data. "
                    f"Course: {assignment_request.course_id}, Teacher: {teacher_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create course assignment. The assignment may already exist or there was a database error.",
                )
            
            assignment_id = result.data[0].get("id")
            if not assignment_id:
                logger.error(
                    f"Failed to create course assignment: No ID returned. "
                    f"Course: {assignment_request.course_id}, Teacher: {teacher_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create course assignment. No assignment ID was returned.",
                )
            
            # Verify the assignment was actually created by querying it back
            verify_result = (
                db.admin_client.table("course_teacher")
                .select("id, is_active")
                .eq("id", assignment_id)
                .execute()
            )
            
            if not verify_result.data or len(verify_result.data) == 0:
                logger.error(
                    f"Course assignment was not persisted: Assignment ID {assignment_id} not found after insert. "
                    f"Course: {assignment_request.course_id}, Teacher: {teacher_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Course assignment was not saved. Please try again.",
                )
            
            # Invalidate cache
            cache.caches["courses"].delete_pattern(
                f"courses:teacher_courses:{teacher_id}"
            )

            # Convert assignment ID to UUID for API response
            assignment_id_uuid = await IDConverter.int_to_uuid(db, "course_teacher", assignment_id) if assignment_id else None
            if not assignment_id_uuid:
                # Try to get UUID from the result data
                assignment_id_uuid = result.data[0].get("uuid") or str(assignment_id)
            
            logger.info(
                f"Admin {admin_user.id} assigned course {assignment_request.course_id} "
                f"to teacher {teacher_id} (assignment_id: {assignment_id_uuid})"
            )

            return {
                "message": "Course assigned to teacher successfully",
                "assignment_id": assignment_id_uuid,  # Use UUID for API
                "course_name": course["name"],
                "course_code": course["code"],
            }
            
        except HTTPException:
            raise
        except Exception as insert_error:
            logger.error(
                f"Error inserting course assignment: {insert_error!s}. "
                f"Course: {assignment_request.course_id}, Teacher: {teacher_id}, "
                f"Data: {assignment_data}"
            )
            # Check if it's a unique constraint violation
            error_str = str(insert_error).lower()
            if "unique" in error_str or "duplicate" in error_str:
                # Try to get the existing assignment
                existing_check = (
                    db.admin_client.table("course_teacher")
                    .select("*")
                    .eq("course_id", course_int_id)
                    .eq("teacher_id", teacher_id)
                    .execute()
                )
                
                if existing_check.data and len(existing_check.data) > 0:
                    existing = existing_check.data[0]
                    # If it exists but is inactive, reactivate it
                    if not existing.get("is_active"):
                        db.admin_client.table("course_teacher").update({
                            "is_active": True,
                            "assigned_by": admin_user_int_id,  # Use integer ID
                            "assigned_at": datetime.utcnow().isoformat(),
                        }).eq("id", existing["id"]).execute()
                        
                        cache.caches["courses"].delete_pattern(
                            f"courses:teacher_courses:{teacher_id}"
                        )
                        
                        # Convert assignment ID to UUID for response
                        existing_id_uuid = await IDConverter.int_to_uuid(db, "course_teacher", existing["id"]) if existing.get("id") else None
                        if not existing_id_uuid:
                            existing_id_uuid = existing.get("uuid") or str(existing["id"])
                        
                        logger.info(
                            f"Admin {admin_user.id} reactivated course assignment: "
                            f"course {assignment_request.course_id} -> teacher {teacher_id}"
                        )
                        
                        return {
                            "message": "Course assignment reactivated successfully",
                            "assignment_id": existing_id_uuid,  # Use UUID for API
                            "course_name": course["name"],
                            "course_code": course["code"],
                        }
                    else:
                        # Already active - convert ID to UUID for response
                        existing_id_uuid = await IDConverter.int_to_uuid(db, "course_teacher", existing["id"]) if existing.get("id") else None
                        if not existing_id_uuid:
                            existing_id_uuid = existing.get("uuid") or str(existing["id"])
                        
                        return {
                            "message": "Course is already assigned to this teacher",
                            "assignment_id": existing_id_uuid,  # Use UUID for API
                            "course_name": course["name"],
                            "course_code": course["code"],
                        }
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating course assignment: {insert_error!s}",
            ) from insert_error

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning course to teacher: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error assigning course to teacher",
        ) from e


# ==================== Semester Management Routes ====================


@router.post("/semesters", status_code=status.HTTP_201_CREATED, response_model=SemesterResponse)
async def create_semester(
    semester_request: SemesterCreateRequest,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Create a new semester for the admin's university.
    Semesters are managed at the university level and can be used across multiple courses.
    """
    admin_user, university_id = admin_data

    try:
        # Validate dates
        if semester_request.end_date < semester_request.start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be after start date",
            )

        # Check if semester name already exists in this university
        existing_semester = (
            db.admin_client.table("semester")
            .select("id, name")
            .eq("university_id", university_id)
            .eq("name", semester_request.name)
            .limit(1)
            .execute()
        )

        if existing_semester.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Semester '{semester_request.name}' already exists in your university",
            )

        # Create semester
        semester_data = {
            "id": str(uuid4()),
            "name": semester_request.name,
            "start_date": semester_request.start_date.isoformat(),
            "end_date": semester_request.end_date.isoformat(),
            "university_id": university_id,
            "course_id": None,  # University-level semester, not tied to specific course
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        result = (
            db.admin_client.table("semester")
            .insert(semester_data)
            .execute()
        )

        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create semester",
            )

        created_semester = result.data[0]

        # Auto-create a "Default Module" for the new semester
        try:
            db.admin_client.table("module").insert({
                "id": str(uuid4()),
                "name": "Default Module",
                "university_id": university_id,
                "semester_id": created_semester["id"],
                "display_order": 1,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }).execute()
        except Exception as mod_err:
            logger.warning(f"Failed to auto-create default module for semester {created_semester['id']}: {mod_err}")

        logger.info(
            f"Admin {admin_user.id} created semester '{semester_request.name}' "
            f"for university {university_id}"
        )

        # Convert integer IDs to UUIDs for API response
        semester_id_uuid = await IDConverter.int_to_uuid(db, "semester", created_semester["id"])
        if not semester_id_uuid:
            semester_id_uuid = str(created_semester["id"])  # Fallback
        
        university_id_uuid = await IDConverter.int_to_uuid(db, "university", created_semester["university_id"])
        if not university_id_uuid:
            university_id_uuid = str(created_semester["university_id"])  # Fallback
        
        course_id_uuid = None
        if created_semester.get("course_id"):
            course_id_uuid = await IDConverter.int_to_uuid(db, "course", created_semester["course_id"])
            if not course_id_uuid:
                course_id_uuid = str(created_semester["course_id"])  # Fallback

        return SemesterResponse(
            id=semester_id_uuid,
            name=created_semester["name"],
            start_date=parse_datetime_safe(created_semester["start_date"]),
            end_date=parse_datetime_safe(created_semester["end_date"]),
            university_id=university_id_uuid,
            course_id=course_id_uuid,
            module_count=1,
            created_at=parse_datetime_safe(created_semester["created_at"]),
            updated_at=parse_datetime_safe(created_semester["updated_at"]),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating semester: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating semester",
        ) from e


@router.get("/semesters")
async def list_semesters(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: str = Query(None, description="Search by semester name"),
    sort_by: str = Query("start_date", description="Sort by: name, start_date, end_date, created_at"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
):
    """
    Get all semesters for the admin's university.
    Returns university-level semesters that can be used across courses.
    """
    _, university_id = admin_data

    try:
        # Get all semesters for this university (university-level semesters)
        # Filter for semesters where university_id is set and course_id is NULL
        semesters_result = (
            db.admin_client.table("semester")
            .select("*")
            .eq("university_id", university_id)
            .is_("course_id", "null")  # Only university-level semesters
            .order("start_date", desc=True)
            .execute()
        )
        
        # Fallback: if .is_() doesn't work, filter in Python
        # This ensures we only return university-level semesters
        all_semesters_data = semesters_result.data or []
        all_semesters_data = [
            s for s in all_semesters_data
            if s.get("course_id") is None
        ]
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            all_semesters_data = [
                s for s in all_semesters_data
                if search_lower in (s.get("name") or "").lower()
            ]
        
        # Sort
        sort_desc = sort_order.lower() == "desc"
        sort_key_map = {
            "name": lambda s: (s.get("name") or "").lower(),
            "start_date": lambda s: s.get("start_date") or "",
            "end_date": lambda s: s.get("end_date") or "",
            "created_at": lambda s: s.get("created_at") or "",
        }
        sort_fn = sort_key_map.get(sort_by, sort_key_map["start_date"])
        all_semesters_data.sort(key=sort_fn, reverse=sort_desc)
        
        # Calculate pagination
        total = len(all_semesters_data)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = all_semesters_data[start:end]

        # Batch-fetch module counts per semester
        module_counts = {}
        modules_result = (
            db.admin_client.table("module")
            .select("id, semester_id")
            .eq("university_id", university_id)
            .execute()
        )
        for mod in (modules_result.data or []):
            sid = mod["semester_id"]
            module_counts[sid] = module_counts.get(sid, 0) + 1

        semesters = []
        for semester in page_data:
            # Convert integer IDs to UUIDs for API response
            semester_id_uuid = await IDConverter.int_to_uuid(db, "semester", semester["id"])
            if not semester_id_uuid:
                semester_id_uuid = str(semester["id"])  # Fallback
            
            university_id_uuid = await IDConverter.int_to_uuid(db, "university", semester["university_id"])
            if not university_id_uuid:
                university_id_uuid = str(semester["university_id"])  # Fallback
            
            course_id_uuid = None
            if semester.get("course_id"):
                course_id_uuid = await IDConverter.int_to_uuid(db, "course", semester["course_id"])
                if not course_id_uuid:
                    course_id_uuid = str(semester["course_id"])  # Fallback
            
            semesters.append(
                SemesterResponse(
                    id=semester_id_uuid,
                    name=semester["name"],
                    start_date=parse_datetime_safe(semester["start_date"]),
                    end_date=parse_datetime_safe(semester["end_date"]),
                    university_id=university_id_uuid,
                    course_id=course_id_uuid,
                    module_count=module_counts.get(semester["id"], 0),
                    created_at=parse_datetime_safe(semester["created_at"]),
                    updated_at=parse_datetime_safe(semester["updated_at"]),
                )
            )

        return {
            "items": semesters,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    except Exception as e:
        logger.error(f"Error fetching semesters: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching semesters",
        ) from e


@router.get("/semesters/{semester_id}", response_model=SemesterResponse)
async def get_semester(
    semester_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Get a specific semester by ID.
    """
    _, university_id = admin_data

    try:
        semester_result = (
            db.admin_client.table("semester")
            .select("*")
            .eq("id", semester_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found in your university",
            )

        semester = semester_result.data[0]

        # Convert integer IDs to UUIDs for API response
        semester_id_uuid = await IDConverter.int_to_uuid(db, "semester", semester["id"])
        if not semester_id_uuid:
            semester_id_uuid = str(semester["id"])  # Fallback
        
        university_id_uuid = await IDConverter.int_to_uuid(db, "university", semester["university_id"])
        if not university_id_uuid:
            university_id_uuid = str(semester["university_id"])  # Fallback
        
        course_id_uuid = None
        if semester.get("course_id"):
            course_id_uuid = await IDConverter.int_to_uuid(db, "course", semester["course_id"])
            if not course_id_uuid:
                course_id_uuid = str(semester["course_id"])  # Fallback

        return SemesterResponse(
            id=semester_id_uuid,
            name=semester["name"],
            start_date=parse_datetime_safe(semester["start_date"]),
            end_date=parse_datetime_safe(semester["end_date"]),
            university_id=university_id_uuid,
            course_id=course_id_uuid,
            created_at=parse_datetime_safe(semester["created_at"]),
            updated_at=parse_datetime_safe(semester["updated_at"]),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching semester: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching semester",
        ) from e


@router.put("/semesters/{semester_id}", response_model=SemesterResponse)
async def update_semester(
    semester_id: str,
    semester_request: SemesterUpdateRequest,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Update a semester.
    """
    admin_user, university_id = admin_data

    try:
        # Convert UUID to integer ID if needed
        semester_int_id = semester_id
        if IDConverter.is_uuid(semester_id):
            semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id)
            if not semester_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Semester not found in your university",
                )

        # Verify semester exists and belongs to this university
        semester_result = (
            db.admin_client.table("semester")
            .select("*")
            .eq("id", semester_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found in your university",
            )

        current_semester = semester_result.data[0]

        # Build update data
        update_data = {"updated_at": datetime.utcnow().isoformat()}

        if semester_request.name is not None:
            # Check if new name conflicts with existing semester
            if semester_request.name != current_semester["name"]:
                existing_check = (
                    db.admin_client.table("semester")
                    .select("id")
                    .eq("university_id", university_id)
                    .eq("name", semester_request.name)
                    .neq("id", semester_id)
                    .limit(1)
                    .execute()
                )
                if existing_check.data:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Semester '{semester_request.name}' already exists in your university",
                    )
            update_data["name"] = semester_request.name

        if semester_request.start_date is not None:
            update_data["start_date"] = semester_request.start_date.isoformat()

        if semester_request.end_date is not None:
            update_data["end_date"] = semester_request.end_date.isoformat()

        # Validate dates if both are being updated
        start_date = (
            parse_datetime_safe(update_data.get("start_date"))
            if "start_date" in update_data
            else parse_datetime_safe(current_semester["start_date"])
        )
        end_date = (
            parse_datetime_safe(update_data.get("end_date"))
            if "end_date" in update_data
            else parse_datetime_safe(current_semester["end_date"])
        )

        if end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be after start date",
            )

        # Update semester
        result = (
            db.admin_client.table("semester")
            .update(update_data)
            .eq("id", semester_int_id)
            .execute()
        )

        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update semester",
            )

        updated_semester = result.data[0]

        logger.info(
            f"Admin {admin_user.id} updated semester {semester_id} "
            f"in university {university_id}"
        )

        # Convert integer IDs to UUIDs for API response
        semester_id_uuid = await IDConverter.int_to_uuid(db, "semester", updated_semester["id"])
        if not semester_id_uuid:
            semester_id_uuid = str(updated_semester["id"])  # Fallback
        
        university_id_uuid = await IDConverter.int_to_uuid(db, "university", updated_semester["university_id"])
        if not university_id_uuid:
            university_id_uuid = str(updated_semester["university_id"])  # Fallback
        
        course_id_uuid = None
        if updated_semester.get("course_id"):
            course_id_uuid = await IDConverter.int_to_uuid(db, "course", updated_semester["course_id"])
            if not course_id_uuid:
                course_id_uuid = str(updated_semester["course_id"])  # Fallback

        return SemesterResponse(
            id=semester_id_uuid,
            name=updated_semester["name"],
            start_date=parse_datetime_safe(updated_semester["start_date"]),
            end_date=parse_datetime_safe(updated_semester["end_date"]),
            university_id=university_id_uuid,
            course_id=course_id_uuid,
            created_at=parse_datetime_safe(updated_semester["created_at"]),
            updated_at=parse_datetime_safe(updated_semester["updated_at"]),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating semester: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating semester",
        ) from e


@router.delete("/semesters/{semester_id}")
async def delete_semester(
    semester_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Delete a semester.
    Only allowed if the semester is not used in any enrollments.
    """
    admin_user, university_id = admin_data

    try:
        # Convert UUID to integer ID if needed
        semester_int_id = semester_id
        if IDConverter.is_uuid(semester_id):
            semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id)
            if not semester_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Semester not found in your university",
                )

        # Verify semester exists and belongs to this university
        semester_result = (
            db.admin_client.table("semester")
            .select("*")
            .eq("id", semester_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found in your university",
            )

        # Check if semester is used in any enrollments
        enrollments_check = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("semester_id", semester_int_id)
            .limit(1)
            .execute()
        )

        if enrollments_check.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete semester that is used in enrollments. Deactivate enrollments first.",
            )

        # Delete semester
        db.admin_client.table("semester").delete().eq("id", semester_int_id).execute()

        logger.info(
            f"Admin {admin_user.id} deleted semester {semester_id} "
            f"from university {university_id}"
        )

        return {"message": "Semester deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting semester: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting semester",
        ) from e


# ==================== Bulk Operations Routes ====================


@router.post("/students/bulk-signup", status_code=status.HTTP_201_CREATED, response_model=BulkSignupResponse)
async def bulk_student_signup(
    bulk_request: BulkStudentSignupRequest,
    background_tasks: BackgroundTasks,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Bulk create student accounts and send activation links via email.
    Admin can create multiple students at once and send them activation emails.
    """
    admin_user, university_id = admin_data
    
    created_students = []
    failed_students = []
    errors = []
    
    try:
        for student_data in bulk_request.students:
            try:
                # Check if student_id already exists in this university
                existing_student = db.get_records(
                    "student",
                    {
                        "student_id": student_data.student_id,
                        "university_id": university_id,
                    },
                )
                if existing_student:
                    failed_students.append({
                        "email": student_data.email,
                        "student_id": student_data.student_id,
                        "error": f"Student with ID '{student_data.student_id}' already exists"
                    })
                    errors.append(f"Student {student_data.student_id}: Already exists")
                    continue
                
                # Check if email already exists
                existing_user = db.get_user_by_email(student_data.email)
                if existing_user:
                    failed_students.append({
                        "email": student_data.email,
                        "student_id": student_data.student_id,
                        "error": f"Email '{student_data.email}' already exists"
                    })
                    errors.append(f"Student {student_data.student_id}: Email already exists")
                    continue
                
                # Create user using AuthService
                user_create = UserCreate(
                    email=student_data.email,
                    username=student_data.username,
                    password=bulk_request.default_password,
                    first_name=student_data.first_name,
                    last_name=student_data.last_name,
                    role=UserRole.STUDENT,
                    university_id=university_id,
                    student_id=student_data.student_id,
                    year_of_study=student_data.year_of_study,
                )
                
                new_user = await AuthService.create_user(db, user_create)
                
                # Generate activation token and link
                activation_token = AuthService.create_activation_token(new_user.id)
                activation_link = f"{settings.FRONTEND_URL}/activate-account?token={activation_token}"
                
                # Send activation email in background (non-blocking)
                student_name = f"{student_data.first_name} {student_data.last_name}".strip()
                background_tasks.add_task(
                    email_service.send_bulk_signup_email,
                    to_email=student_data.email,
                    activation_link=activation_link,
                    to_name=student_name,
                    student_id=student_data.student_id,
                    temporary_password=bulk_request.default_password
                )
                
                created_students.append({
                    "user_id": new_user.id,
                    "email": student_data.email,
                    "student_id": student_data.student_id,
                    "username": student_data.username,
                    "email_sent": True  # Queued for sending in background
                })
                
                logger.info(
                    f"Admin {admin_user.id} created student {student_data.student_id} "
                    f"via bulk signup for {student_data.email}"
                )
                
            except ValueError as e:
                failed_students.append({
                    "email": student_data.email,
                    "student_id": student_data.student_id,
                    "error": str(e)
                })
                errors.append(f"Student {student_data.student_id}: {e!s}")
            except Exception as e:
                logger.error(f"Error creating student {student_data.student_id}: {e!s}")
                failed_students.append({
                    "email": student_data.email,
                    "student_id": student_data.student_id,
                    "error": f"Internal error: {e!s}"
                })
                errors.append(f"Student {student_data.student_id}: {e!s}")
        
        result = BulkOperationResult(
            total=len(bulk_request.students),
            successful=len(created_students),
            failed=len(failed_students),
            errors=errors
        )
        
        return BulkSignupResponse(
            result=result,
            created_students=created_students,
            failed_students=failed_students
        )
        
    except Exception as e:
        logger.error(f"Error in bulk student signup: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing bulk signup: {e!s}",
        ) from e


@router.post("/enrollments/bulk-enroll", status_code=status.HTTP_201_CREATED, response_model=BulkEnrollmentResponse)
async def bulk_student_enrollment(
    bulk_request: BulkEnrollmentRequest,
    background_tasks: BackgroundTasks,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Bulk enroll students in a course and send enrollment links via email.
    Admin can enroll multiple students at once and send them enrollment emails.
    """
    admin_user, university_id = admin_data
    
    enrolled_students = []
    failed_students = []
    errors = []
    
    try:
        # Convert course_id and semester_id from UUIDs to integer IDs if needed
        course_int_id = bulk_request.course_id
        if IDConverter.is_uuid(bulk_request.course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", bulk_request.course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found in your university",
                )

        semester_int_id = bulk_request.semester_id
        if IDConverter.is_uuid(bulk_request.semester_id):
            semester_int_id = await IDConverter.uuid_to_int(db, "semester", bulk_request.semester_id)
            if not semester_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Semester not found in your university",
                )

        # Verify course belongs to this university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code, university_id")
            .eq("id", course_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )
        
        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found in your university",
            )
        
        course = course_result.data[0]
        
        # Verify semester belongs to this university (university-level semesters)
        semester_result = (
            db.admin_client.table("semester")
            .select("id, name, university_id")
            .eq("id", semester_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found in your university",
            )
        
        semester = semester_result.data[0]
        
        # Get teacher info for email
        teacher_result = (
            db.admin_client.table("course")
            .select("teacher_id, teacher!inner(*, users!inner(*))")
            .eq("id", course_int_id)
            .execute()
        )
        
        teacher_name = None
        if teacher_result.data:
            teacher_data = teacher_result.data[0].get("teacher", {})
            teacher_user_data = teacher_data.get("users", {})
            teacher_name = f"{teacher_user_data.get('first_name', '')} {teacher_user_data.get('last_name', '')}".strip()
        
        for enrollment_item in bulk_request.students:
            try:
                # Find student by university student_id within this university
                student_result = (
                    db.admin_client.table("student")
                    .select("id, student_id, user_id, users!inner(*)")
                    .eq("student_id", enrollment_item.student_id)
                    .eq("university_id", university_id)
                    .limit(1)
                    .execute()
                )
                
                if not student_result.data:
                    failed_students.append({
                        "student_id": enrollment_item.student_id,
                        "error": f"Student with ID '{enrollment_item.student_id}' not found in your university"
                    })
                    errors.append(f"Student {enrollment_item.student_id}: Not found")
                    continue
                
                student_data = student_result.data[0]
                student_db_id = student_data["id"]
                user_data = student_data.get("users", {})
                student_email = enrollment_item.email or user_data.get("email")
                
                if not student_email:
                    failed_students.append({
                        "student_id": enrollment_item.student_id,
                        "error": "Student email not found"
                    })
                    errors.append(f"Student {enrollment_item.student_id}: Email not found")
                    continue
                
                # Check if already enrolled
                existing_enrollment = (
                    db.admin_client.table("enrollment")
                    .select("*")
                    .eq("student_id", str(student_db_id))
                    .eq("course_id", course_int_id)
                    .execute()
                )
                
                if existing_enrollment.data and len(existing_enrollment.data) > 0:
                    enrollment = existing_enrollment.data[0]
                    if enrollment.get("is_active"):
                        # Already enrolled, skip but don't count as failed
                        enrolled_students.append({
                            "student_id": enrollment_item.student_id,
                            "email": student_email,
                            "enrollment_id": enrollment["id"],
                            "status": "already_enrolled"
                        })
                        continue
                    else:
                        # Reactivate the enrollment
                        db.admin_client.table("enrollment").update({
                            "is_active": True,
                            "semester_id": semester_int_id,
                            "enrolled_at": datetime.utcnow().isoformat(),
                        }).eq("id", enrollment["id"]).execute()
                        
                        cache.invalidate_student(str(student_db_id))
                        
                        enrollment_id = enrollment["id"]
                else:
                    # Create new enrollment
                    enrollment_data = {
                        "id": str(uuid4()),
                        "student_id": str(student_db_id),
                        "course_id": course_int_id,
                        "semester_id": semester_int_id,
                        "enrolled_at": datetime.utcnow().isoformat(),
                        "is_active": True,
                    }
                    
                    result = db.admin_client.table("enrollment").insert(enrollment_data).execute()
                    enrollment_id = result.data[0]["id"]
                    
                    # Invalidate cache
                    cache.invalidate_student(str(student_db_id))
                
                # Generate enrollment token and link
                enrollment_token = AuthService.create_enrollment_token(
                    student_id=str(student_db_id),
                    course_id=bulk_request.course_id,
                    semester_id=bulk_request.semester_id
                )
                enrollment_link = f"{settings.FRONTEND_URL}/enroll?token={enrollment_token}"
                
                # Send enrollment email in background (non-blocking)
                student_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or "Student"
                background_tasks.add_task(
                    email_service.send_bulk_enrollment_email,
                    to_email=student_email,
                    enrollment_link=enrollment_link,
                    student_name=student_name,
                    course_name=course["name"],
                    teacher_name=teacher_name,
                    semester_name=semester.get("name")
                )
                
                enrolled_students.append({
                    "student_id": enrollment_item.student_id,
                    "email": student_email,
                    "enrollment_id": enrollment_id,
                    "email_sent": True  # Queued for sending in background
                })
                
                logger.info(
                    f"Admin {admin_user.id} enrolled student {enrollment_item.student_id} "
                    f"in course {bulk_request.course_id} via bulk enrollment"
                )
                
            except Exception as e:
                logger.error(f"Error enrolling student {enrollment_item.student_id}: {e!s}")
                failed_students.append({
                    "student_id": enrollment_item.student_id,
                    "error": str(e)
                })
                errors.append(f"Student {enrollment_item.student_id}: {e!s}")
        
        result = BulkOperationResult(
            total=len(bulk_request.students),
            successful=len(enrolled_students),
            failed=len(failed_students),
            errors=errors
        )
        
        return BulkEnrollmentResponse(
            result=result,
            enrolled_students=enrolled_students,
            failed_students=failed_students
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk enrollment: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing bulk enrollment: {e!s}",
        ) from e


# ==================== Module Management Routes ====================


@router.post("/modules", status_code=status.HTTP_201_CREATED)
async def create_module(
    request: dict,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Create a module within a semester.
    Hierarchy: Semester → Module → Courses

    Request body: { "name": "Urology", "description": "...", "semester_id": "uuid", "display_order": 0 }
    """
    admin_user, university_id = admin_data

    try:
        name = (request.get("name") or "").strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Module name is required",
            )

        semester_id = request.get("semester_id")
        if not semester_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="semester_id is required",
            )

        # Convert UUID to integer ID if needed
        semester_int_id = semester_id
        if IDConverter.is_uuid(semester_id):
            semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id)
            if not semester_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Semester not found in your university",
                )

        # Verify semester belongs to this university
        semester_result = (
            db.admin_client.table("semester")
            .select("id")
            .eq("id", semester_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )
        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found in your university",
            )

        # Check for duplicate module name in this semester
        existing = (
            db.admin_client.table("module")
            .select("id")
            .eq("semester_id", semester_int_id)
            .eq("name", name)
            .limit(1)
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Module '{name}' already exists in this semester",
            )

        module_data = {
            "id": str(uuid4()),
            "name": name,
            "description": (request.get("description") or "").strip() or None,
            "semester_id": semester_id,
            "university_id": university_id,
            "display_order": request.get("display_order", 0),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        result = db.admin_client.table("module").insert(module_data).execute()

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create module",
            )

        logger.info(f"Admin {admin_user.id} created module '{name}' in semester {semester_id}")
        return result.data[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating module: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating module",
        ) from e


@router.get("/modules")
async def list_modules(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    semester_id: str | None = None,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: str = Query(None, description="Search by module name"),
    sort_by: str = Query("display_order", description="Sort by: name, display_order, created_at"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
):
    """
    List all modules for the admin's university with pagination.
    Optional filter: ?semester_id= to get modules for a specific semester.
    Each module includes its courses.
    """
    _, university_id = admin_data

    try:
        query = (
            db.admin_client.table("module")
            .select("*")
            .eq("university_id", university_id)
        )
        if semester_id:
            # Convert UUID to integer ID if needed
            semester_int_id = semester_id
            if IDConverter.is_uuid(semester_id):
                semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id)
                if semester_int_id:
                    query = query.eq("semester_id", semester_int_id)
            else:
                query = query.eq("semester_id", semester_id)

        modules_result = query.order("display_order").order("created_at").execute()
        
        all_modules_data = modules_result.data or []
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            all_modules_data = [
                m for m in all_modules_data
                if search_lower in (m.get("name") or "").lower()
            ]
        
        # Sort
        sort_desc = sort_order.lower() == "desc"
        sort_key_map = {
            "name": lambda m: (m.get("name") or "").lower(),
            "display_order": lambda m: m.get("display_order") or 0,
            "created_at": lambda m: m.get("created_at") or "",
        }
        sort_fn = sort_key_map.get(sort_by, sort_key_map["display_order"])
        all_modules_data.sort(key=sort_fn, reverse=sort_desc)
        
        # Calculate pagination
        total = len(all_modules_data)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = all_modules_data[start:end]

        modules = []
        for module in page_data:
            # Get courses for this module
            courses_result = (
                db.admin_client.table("module_course")
                .select("course_id, display_order, course!inner(id, name, code)")
                .eq("module_id", module["id"])
                .order("display_order")
                .execute()
            )

            courses = []
            for mc in courses_result.data or []:
                course = mc.get("course", {})
                courses.append({
                    "course_id": course.get("id"),
                    "course_name": course.get("name"),
                    "course_code": course.get("code"),
                    "display_order": mc.get("display_order", 0),
                })

            modules.append({**module, "courses": courses})

        return {
            "items": modules,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    except Exception as e:
        logger.error(f"Error listing modules: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching modules",
        ) from e


@router.get("/modules/{module_id}", response_model=dict)
async def get_module(
    module_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """Get a specific module with its courses."""
    _, university_id = admin_data

    try:
        module_result = (
            db.admin_client.table("module")
            .select("*")
            .eq("id", module_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not module_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found",
            )

        module = module_result.data[0]

        # Convert UUID to integer ID if needed
        module_int_id = module_id
        if IDConverter.is_uuid(module_id):
            module_int_id = await IDConverter.uuid_to_int(db, "module", module_id)
            if not module_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Module not found",
                )

        # Get courses
        courses_result = (
            db.admin_client.table("module_course")
            .select("course_id, display_order, course!inner(id, name, code, description)")
            .eq("module_id", module_int_id)
            .order("display_order")
            .execute()
        )

        courses = []
        for mc in courses_result.data or []:
            course = mc.get("course", {})
            courses.append({
                "course_id": course.get("id"),
                "course_name": course.get("name"),
                "course_code": course.get("code"),
                "course_description": course.get("description"),
                "display_order": mc.get("display_order", 0),
            })

        return {**module, "courses": courses}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching module: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching module",
        ) from e


@router.put("/modules/{module_id}", response_model=dict)
async def update_module(
    module_id: str,
    request: dict,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """Update a module's name, description, or display_order."""
    admin_user, university_id = admin_data

    try:
        # Convert UUID to integer ID if needed
        module_int_id = module_id
        if IDConverter.is_uuid(module_id):
            module_int_id = await IDConverter.uuid_to_int(db, "module", module_id)
            if not module_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Module not found",
                )

        # Verify module exists
        module_result = (
            db.admin_client.table("module")
            .select("*")
            .eq("id", module_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not module_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found",
            )

        update_data = {"updated_at": datetime.utcnow().isoformat()}

        if request.get("name"):
            update_data["name"] = request["name"].strip()
        if "description" in request:
            update_data["description"] = (
                (request.get("description") or "").strip() or None
            )
        if "display_order" in request:
            update_data["display_order"] = request["display_order"]

        result = (
            db.admin_client.table("module")
            .update(update_data)
            .eq("id", module_int_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update module",
            )

        logger.info(f"Admin {admin_user.id} updated module {module_id}")
        return result.data[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating module: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating module",
        ) from e


@router.delete("/modules/{module_id}")
async def delete_module(
    module_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Delete a module. This removes the module and its course associations,
    but does NOT delete the courses themselves.
    """
    admin_user, university_id = admin_data

    try:
        # Convert UUID to integer ID if needed
        module_int_id = module_id
        if IDConverter.is_uuid(module_id):
            module_int_id = await IDConverter.uuid_to_int(db, "module", module_id)
            if not module_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Module not found",
                )

        module_result = (
            db.admin_client.table("module")
            .select("id, name")
            .eq("id", module_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not module_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found",
            )

        module_name = module_result.data[0]["name"]

        # Delete module (module_course entries cascade-delete via FK)
        db.admin_client.table("module").delete().eq("id", module_int_id).execute()

        logger.info(f"Admin {admin_user.id} deleted module '{module_name}' ({module_id})")
        return {"message": f"Module '{module_name}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting module: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting module",
        ) from e


@router.post("/modules/{module_id}/courses")
async def assign_courses_to_module(
    module_id: str,
    request: dict,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Assign courses to a module.
    Request body: { "course_ids": ["uuid1", "uuid2"] }
    """
    admin_user, university_id = admin_data

    try:
        # Convert UUID to integer ID if needed
        module_int_id = module_id
        if IDConverter.is_uuid(module_id):
            module_int_id = await IDConverter.uuid_to_int(db, "module", module_id)
            if not module_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Module not found",
                )

        # Verify module exists
        module_result = (
            db.admin_client.table("module")
            .select("id, name")
            .eq("id", module_int_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not module_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found",
            )

        course_ids = request.get("course_ids", [])
        if not course_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="course_ids list is required",
            )

        # Convert course_ids from UUIDs to integer IDs if needed (before verification query)
        course_int_ids = []
        for course_id in course_ids:
            if IDConverter.is_uuid(course_id):
                course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
                if course_int_id:
                    course_int_ids.append(course_int_id)
            else:
                course_int_ids.append(course_id)

        # Verify all courses belong to this university
        courses_result = (
            db.admin_client.table("course")
            .select("id, name")
            .in_("id", course_int_ids)
            .eq("university_id", university_id)
            .execute()
        )

        found_ids = {c["id"] for c in (courses_result.data or [])}
        # Compare with integer IDs for missing check
        missing = set(course_int_ids) - found_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Courses not found in your university: {list(missing)}",
            )

        # Get existing assignments to avoid duplicates
        existing_result = (
            db.admin_client.table("module_course")
            .select("course_id")
            .eq("module_id", module_int_id)
            .in_("course_id", course_int_ids)
            .execute()
        )
        existing_ids = {mc["course_id"] for mc in (existing_result.data or [])}

        # Insert new assignments
        new_assignments = []
        for course_int_id in course_int_ids:
            if course_int_id not in existing_ids:
                new_assignments.append({
                    "id": str(uuid4()),
                    "module_id": module_int_id,
                    "course_id": course_int_id,
                    "display_order": 0,
                    "created_at": datetime.utcnow().isoformat(),
                })

        if new_assignments:
            db.admin_client.table("module_course").insert(new_assignments).execute()

        logger.info(
            f"Admin {admin_user.id} assigned {len(new_assignments)} courses to module {module_id} "
            f"({len(existing_ids)} already assigned)"
        )

        return {
            "message": f"Assigned {len(new_assignments)} courses to module",
            "newly_assigned": len(new_assignments),
            "already_assigned": len(existing_ids),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning courses to module: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error assigning courses to module",
        ) from e


@router.delete("/modules/{module_id}/courses/{course_id}")
async def remove_course_from_module(
    module_id: str,
    course_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """Remove a course from a module. Does NOT delete the course."""
    admin_user, university_id = admin_data

    try:
        # Verify module belongs to this university
        module_result = (
            db.admin_client.table("module")
            .select("id")
            .eq("id", module_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not module_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found",
            )

        # Delete the junction entry
        db.admin_client.table("module_course").delete().eq(
            "module_id", module_id
        ).eq("course_id", course_id).execute()

        logger.info(f"Admin {admin_user.id} removed course {course_id} from module {module_id}")
        return {"message": "Course removed from module"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing course from module: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error removing course from module",
        ) from e


@router.get("/semesters/{semester_id}/modules", response_model=list[dict])
async def get_semester_modules(
    semester_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Get all modules for a specific semester, each with its courses.
    Used by frontend to display the Semester → Module → Course hierarchy.
    """
    _, university_id = admin_data

    try:
        # Convert UUID to integer ID if needed
        semester_int_id = semester_id
        if IDConverter.is_uuid(semester_id):
            semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id)
            if not semester_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Semester not found",
                )
        
        # Convert university_id to integer if needed
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid university ID",
                )

        # Verify semester belongs to this university using integer IDs
        semester_result = (
            db.admin_client.table("semester")
            .select("id, name")
            .eq("id", semester_int_id)  # Use integer ID
            .eq("university_id", university_int_id)  # Use integer ID
            .limit(1)
            .execute()
        )

        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found in your university",
            )

        # Get modules for this semester using integer ID
        modules_result = (
            db.admin_client.table("module")
            .select("*")
            .eq("semester_id", semester_int_id)  # Use integer ID
            .order("display_order")
            .order("created_at")
            .execute()
        )

        modules = []
        for module in modules_result.data or []:
            # Convert module_id to integer for query
            module_int_id = module["id"]
            
            # Get courses for this module
            courses_result = (
                db.admin_client.table("module_course")
                .select("course_id, display_order, course!inner(id, name, code, description)")
                .eq("module_id", module_int_id)  # Use integer ID
                .order("display_order")
                .execute()
            )

            courses = []
            for mc in courses_result.data or []:
                course = mc.get("course", {})
                # Convert course integer ID to UUID for API response
                course_id_uuid = await IDConverter.int_to_uuid(db, "course", course.get("id")) if course.get("id") else None
                if course.get("id") and not course_id_uuid:
                    course_id_uuid = str(course.get("id"))  # Fallback
                
                courses.append({
                    "id": course_id_uuid if course_id_uuid else course.get("id"),
                    "name": course.get("name"),
                    "code": course.get("code"),
                    "description": course.get("description"),
                    "display_order": mc.get("display_order", 0),
                })

            # Convert module integer ID to UUID for API response
            module_id_uuid = await IDConverter.int_to_uuid(db, "module", module["id"])
            if not module_id_uuid:
                module_id_uuid = str(module["id"])  # Fallback
            
            # Convert semester_id to UUID for API response
            semester_id_uuid = await IDConverter.int_to_uuid(db, "semester", module.get("semester_id")) if module.get("semester_id") else None
            if module.get("semester_id") and not semester_id_uuid:
                semester_id_uuid = str(module.get("semester_id"))  # Fallback

            modules.append({
                "id": module_id_uuid,
                "name": module.get("name"),
                "description": module.get("description"),
                "semester_id": semester_id_uuid if semester_id_uuid else module.get("semester_id"),
                "display_order": module.get("display_order", 0),
                "created_at": module.get("created_at"),
                "updated_at": module.get("updated_at"),
                "courses": courses,
                "course_count": len(courses),
            })

        return modules

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching semester modules: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching semester modules",
        ) from e


# ==================== Delete Management Routes ====================


@router.delete("/teachers/{user_id}")
async def delete_teacher(
    user_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Delete a teacher from the admin's university.
    This will delete the user account and cascade delete the teacher profile.
    """
    _, university_id = admin_data

    try:
        # Get user to verify they exist
        user_data = db.get_user_by_id(user_id, use_cache=False)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Verify user is a teacher
        if user_data.get("role") != UserRole.TEACHER.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not a teacher",
            )

        # Verify user belongs to admin's university (compare as strings — university_id
        # from require_admin is always a string, DB value may be int or str)
        if str(user_data.get("university_id")) != str(university_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete teachers from your own university",
            )

        # Resolve integer PK from the looked-up user (user_id from the route is a UUID)
        int_user_id = user_data.get("id")

        # Verify teacher profile exists and belongs to this university
        teacher_result = (
            db.admin_client.table("teacher")
            .select("id, university_id")
            .eq("user_id", int_user_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not teacher_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher profile not found",
            )

        success = db.delete_user(int_user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete teacher",
            )

        logger.info(
            f"Admin {admin_data[0].id} deleted teacher {user_id} "
            f"from university {university_id}"
        )

        return {"message": "Teacher deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting teacher: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting teacher",
        ) from e


@router.delete("/students/{user_id}")
async def delete_student(
    user_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Delete a student from the admin's university.
    This will delete the user account and cascade delete the student profile.
    """
    _, university_id = admin_data

    try:
        # Get user to verify they exist
        user_data = db.get_user_by_id(user_id, use_cache=False)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Verify user is a student
        if user_data.get("role") != UserRole.STUDENT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not a student",
            )

        # Verify user belongs to admin's university (compare as strings — university_id
        # from require_admin is always a string, DB value may be int or str)
        if str(user_data.get("university_id")) != str(university_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete students from your own university",
            )

        # Resolve integer PK from the looked-up user (user_id from the route is a UUID)
        int_user_id = user_data.get("id")

        # Verify student profile exists and belongs to this university
        student_result = (
            db.admin_client.table("student")
            .select("id, university_id, student_id")
            .eq("user_id", int_user_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not student_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student profile not found",
            )

        student_info = student_result.data[0]

        success = db.delete_user(int_user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete student",
            )

        logger.info(
            f"Admin {admin_data[0].id} deleted student {user_id} "
            f"(student_id: {student_info.get('student_id')}) "
            f"from university {university_id}"
        )

        return {
            "message": "Student deleted successfully",
            "student_id": student_info.get("student_id"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting student: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting student",
        ) from e


@router.post("/students/{user_id}/resend-activation")
async def resend_student_activation(
    user_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """Resend activation email to a student so they can set up their account."""
    _, university_id = admin_data

    try:
        user_data = db.get_user_by_id(user_id, use_cache=False)
        if not user_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if user_data.get("role") != UserRole.STUDENT.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not a student")
        if str(user_data.get("university_id")) != str(university_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only manage students from your own university")

        int_user_id = user_data.get("id")
        activation_token = AuthService.create_activation_token(str(int_user_id))
        activation_link = f"{settings.FRONTEND_URL}/activate-account?token={activation_token}"

        email = user_data.get("email")
        name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or None

        sent = email_service.send_activation_email(email, activation_link, name)
        if not sent:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send activation email")

        logger.info(f"Admin resent activation email to student {user_id} ({email})")
        return {"message": "Activation email sent successfully", "email": email}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending activation for student {user_id}: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send activation email",
        ) from e


@router.post("/students/{user_id}/reset-password")
async def reset_student_password(
    user_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """Send a password reset link to a student via email."""
    _, university_id = admin_data

    try:
        user_data = db.get_user_by_id(user_id, use_cache=False)
        if not user_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if user_data.get("role") != UserRole.STUDENT.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not a student")
        if str(user_data.get("university_id")) != str(university_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only manage students from your own university")

        int_user_id = user_data.get("id")
        activation_token = AuthService.create_activation_token(str(int_user_id))
        activation_link = f"{settings.FRONTEND_URL}/activate-account?token={activation_token}"

        email = user_data.get("email")
        name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or None

        sent = email_service.send_password_reset_email(email, activation_link, name)
        if not sent:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send password reset email")

        logger.info(f"Admin sent password reset email to student {user_id} ({email})")
        return {"message": "Password reset email sent successfully", "email": email}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending password reset for student {user_id}: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send password reset email",
        ) from e


# ==================== Branding Routes ====================


@router.post(
    "/branding/logo",
    response_model=LogoUploadResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_institute_logo(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """
    Upload a logo for the admin's university/institute.
    This logo will be displayed in the sidebar replacing the default AITA logo.
    
    Accepts: PNG, JPG, JPEG, SVG, WEBP
    Max size: 5MB
    """
    admin_user, university_id = admin_data

    try:
        # Get existing logo URL from database (for cleanup)
        existing_university = (
            db.admin_client.table("university")
            .select("logo_url")
            .eq("id", university_id)
            .limit(1)
            .execute()
        )
        existing_logo_url = None
        if existing_university.data and existing_university.data[0].get("logo_url"):
            existing_logo_url = existing_university.data[0]["logo_url"]

        # Upload new logo (this will delete the old one)
        logo_url = await BrandingService.upload_logo(university_id, file, existing_logo_url)

        # Update university record with new logo URL
        update_result = (
            db.admin_client.table("university")
            .update({"logo_url": logo_url, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", university_id)
            .execute()
        )

        if not update_result.data:
            logger.warning(
                f"Logo uploaded but failed to update university record for {university_id}"
            )

        logger.info(
            f"Admin {admin_user.id} uploaded logo for university {university_id}"
        )

        # Extract path from URL for response
        logo_path = None
        if logo_url:
            # Extract path from public URL (e.g., extract from full URL)
            try:
                parsed = urlparse(logo_url)
                logo_path = parsed.path.lstrip("/")
            except Exception:
                pass

        return LogoUploadResponse(
            message="Logo uploaded successfully",
            logo_url=logo_url,
            logo_path=logo_path,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading logo: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error uploading logo",
        ) from e


@router.get("/branding/logo", response_model=LogoGetResponse)
async def get_institute_logo(
    current_user: Annotated[User, Depends(get_current_user)],
    db=Depends(get_db),
):
    """
    Get the current logo for the user's university/institute.
    Returns the logo URL if a custom logo exists, or null if using default.
    
    This endpoint can be accessed by all authenticated users (not just admins)
    to display the logo in the sidebar. The logo is scoped to the user's university.
    """
    # Get university_id from user
    university_id = current_user.university_id
    if not university_id:
        # If user has no university, return no logo
        return LogoGetResponse(
            logo_url=None,
            has_custom_logo=False,
            default_logo_url=None,
        )

    try:
        # Convert UUID to integer ID if needed
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                university_int_id = university_id  # Fallback

        # Get university record
        university_result = (
            db.admin_client.table("university")
            .select("logo_url")
            .eq("id", university_int_id)
            .limit(1)
            .execute()
        )

        logo_url = None
        if university_result.data and university_result.data[0].get("logo_url"):
            logo_url = university_result.data[0]["logo_url"]

        # Default logo URL (can be configured in settings)
        default_logo_url = None  # Frontend should handle default logo display

        return LogoGetResponse(
            logo_url=logo_url,
            has_custom_logo=logo_url is not None,
            default_logo_url=default_logo_url,
        )

    except Exception as e:
        logger.error(f"Error fetching logo: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching logo",
        ) from e


@router.delete("/branding/logo", response_model=LogoDeleteResponse)
async def delete_institute_logo(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Delete the custom logo for the admin's university/institute.
    This will restore the default AITA logo.
    """
    admin_user, university_id = admin_data

    try:
        # Delete logo file from storage
        await BrandingService.delete_logo(university_id)

        # Convert UUID to integer ID if needed
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                university_int_id = university_id  # Fallback

        # Update university record to remove logo URL
        update_result = (
            db.admin_client.table("university")
            .update({"logo_url": None, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", university_int_id)
            .execute()
        )

        if not update_result.data:
            logger.warning(
                f"Logo deleted but failed to update university record for {university_id}"
            )

        logger.info(
            f"Admin {admin_user.id} deleted logo for university {university_id}"
        )

        return LogoDeleteResponse(
            message="Logo removed successfully, default logo restored"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting logo: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting logo",
        ) from e


# Import and include the router in the admin_router from routes_config
# This import is at the end to avoid circular imports
from routes_config import admin_router as main_admin_router

main_admin_router.include_router(router)
