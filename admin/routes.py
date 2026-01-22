# admin/routes.py
"""
Admin routes for Institute/Organization management.
Allows admins to manage teachers, students, and courses within their university.
"""

from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from admin.dependencies import require_admin
from admin.models import (
    BulkEnrollmentRequest,
    BulkEnrollmentResponse,
    BulkOperationResult,
    BulkSignupResponse,
    BulkStudentSignupRequest,
    CourseAssignmentRequest,
    CourseSummary,
    DashboardStats,
    EnrollmentSummary,
    StudentCreateRequest,
    StudentEnrollmentRequest,
    StudentSearchResponse,
    StudentSummary,
    TeacherCreateRequest,
    TeacherSummary,
)
from auth.models import UserCreate
from auth.service import AuthService
from logger import logger
from models.user import User, UserRole
from services.cache_service import cache
from utils.db import get_db
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


# ==================== Teacher Management Routes ====================


@router.get("/teachers", response_model=list[TeacherSummary])
async def list_teachers(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """
    List all teachers in the admin's university with their course and lecture counts.
    """
    _, university_id = admin_data

    try:
        # Get all teachers for this university
        teachers_result = (
            db.admin_client.table("teacher")
            .select("*, users!inner(*)")
            .eq("university_id", university_id)
            .range(skip, skip + limit - 1)
            .execute()
        )

        teachers = []
        for teacher_data in teachers_result.data or []:
            user_data = teacher_data.get("users", {})
            teacher_id = teacher_data["id"]
            user_id = teacher_data["user_id"]

            # Get courses for this teacher (via lectures)
            courses_result = (
                db.admin_client.table("lecture")
                .select("course_id, course!inner(id, name, code)")
                .eq("teacher_id", teacher_id)
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
            for course_id, course_info in course_details.items():
                enrollments_result = (
                    db.admin_client.table("enrollment")
                    .select("id", count="exact")
                    .eq("course_id", course_id)
                    .eq("is_active", True)
                    .execute()
                )
                enrollment_count = (
                    enrollments_result.count
                    if hasattr(enrollments_result, "count")
                    else len(enrollments_result.data or [])
                )

                # Count lectures for this course
                lectures_for_course = (
                    db.admin_client.table("lecture")
                    .select("id", count="exact")
                    .eq("course_id", course_id)
                    .eq("teacher_id", teacher_id)
                    .execute()
                )
                course_lecture_count = (
                    lectures_for_course.count
                    if hasattr(lectures_for_course, "count")
                    else len(lectures_for_course.data or [])
                )

                course_summaries.append(
                    CourseSummary(
                        course_id=course_info["id"],
                        course_name=course_info["name"],
                        course_code=course_info["code"],
                        total_lectures=course_lecture_count,
                        total_enrollments=enrollment_count,
                    )
                )

            teachers.append(
                TeacherSummary(
                    teacher_id=teacher_id,
                    user_id=user_id,
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

        return teachers

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
            from services.email_service import email_service
            from settings import settings
            
            activation_token = AuthService.create_activation_token(new_user.id)
            activation_link = f"{settings.FRONTEND_URL}/activate-account?token={activation_token}"
            
            teacher_name = f"{teacher_data.first_name} {teacher_data.last_name}".strip()
            email_service.send_activation_email(
                to_email=teacher_data.email,
                activation_link=activation_link,
                to_name=teacher_name
            )
            logger.info(f"Activation email sent to {teacher_data.email}")
        except Exception as email_error:
            logger.warning(f"Failed to send activation email: {str(email_error)}")

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


@router.get("/students", response_model=list[StudentSummary])
async def list_students(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """
    List all students in the admin's university with their enrollment information.
    """
    _, university_id = admin_data

    try:
        # Get all students for this university
        students_result = (
            db.admin_client.table("student")
            .select("*, users!inner(*)")
            .eq("university_id", university_id)
            .range(skip, skip + limit - 1)
            .execute()
        )

        students = []
        for student_data in students_result.data or []:
            user_data = student_data.get("users", {})
            student_db_id = student_data["id"]
            student_university_id = student_data["student_id"]  # University student ID

            # Get enrollments for this student
            enrollments = EnrollmentQueryHelper.get_student_enrollments(
                db, str(student_db_id)
            )

            enrollment_summaries = []
            for enrollment in enrollments:
                course = enrollment.get("course", {})
                semester = enrollment.get("semester", {})

                enrolled_at_str = enrollment.get("enrolled_at")
                from utils.datetime_helpers import parse_datetime_safe
                enrolled_at = parse_datetime_safe(enrolled_at_str)

                enrollment_summaries.append(
                    EnrollmentSummary(
                        enrollment_id=enrollment["id"],
                        course_id=course.get("id", ""),
                        course_name=course.get("name", ""),
                        course_code=course.get("code", ""),
                        semester_name=semester.get("name"),
                        enrolled_at=enrolled_at,
                        is_active=enrollment.get("is_active", True),
                    )
                )

            students.append(
                StudentSummary(
                    student_id=student_university_id,
                    user_id=student_data["user_id"],
                    first_name=user_data.get("first_name", ""),
                    last_name=user_data.get("last_name", ""),
                    email=user_data.get("email", ""),
                    year_of_study=student_data.get("year_of_study"),
                    total_enrollments=len(enrollment_summaries),
                    enrollments=enrollment_summaries,
                )
            )

        return students

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
        enrollments = EnrollmentQueryHelper.get_student_enrollments(
            db, str(student_db_id)
        )

        enrollment_summaries = []
        for enrollment in enrollments:
            course = enrollment.get("course", {})
            semester = enrollment.get("semester", {})

            enrolled_at_str = enrollment.get("enrolled_at")
            from utils.datetime_helpers import parse_datetime_safe
            enrolled_at = parse_datetime_safe(enrolled_at_str)

            enrollment_summaries.append(
                EnrollmentSummary(
                    enrollment_id=enrollment["id"],
                    course_id=course.get("id", ""),
                    course_name=course.get("name", ""),
                    course_code=course.get("code", ""),
                    semester_name=semester.get("name"),
                    enrolled_at=enrolled_at,
                    is_active=enrollment.get("is_active", True),
                )
            )

        student_summary = StudentSummary(
            student_id=student_data["student_id"],
            user_id=student_data["user_id"],
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
        # Check if student_id already exists in this university
        existing_student = db.get_records(
            "student",
            {
                "student_id": student_data.student_id,
                "university_id": university_id,
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

        # Create user using AuthService
        user_create = UserCreate(
            email=student_data.email,
            username=student_data.username,
            password=student_data.password,
            first_name=student_data.first_name,
            last_name=student_data.last_name,
            role=UserRole.STUDENT,
            university_id=university_id,
            student_id=student_data.student_id,
            year_of_study=student_data.year_of_study,
        )

        new_user = await AuthService.create_user(db, user_create)

        logger.info(
            f"Admin {admin_user.id} created student account "
            f"for {student_data.student_id}"
        )

        # Send activation email with one-time link in background (non-blocking)
        from services.email_service import email_service
        from settings import settings
        
        activation_token = AuthService.create_activation_token(new_user.id)
        activation_link = f"{settings.FRONTEND_URL}/activate-account?token={activation_token}"
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

        # Verify course belongs to this university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .eq("id", enrollment_request.course_id)
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

        # Verify semester belongs to this course
        semester_result = (
            db.admin_client.table("semester")
            .select("id, name")
            .eq("id", enrollment_request.semester_id)
            .eq("course_id", enrollment_request.course_id)
            .limit(1)
            .execute()
        )

        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found for this course",
            )

        # Check if already enrolled
        existing_enrollment = (
            db.admin_client.table("enrollment")
            .select("*")
            .eq("student_id", str(student_db_id))
            .eq("course_id", enrollment_request.course_id)
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
                    "semester_id": enrollment_request.semester_id,
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
        enrollment_data = {
            "id": str(uuid4()),
            "student_id": str(student_db_id),
            "course_id": enrollment_request.course_id,
            "semester_id": enrollment_request.semester_id,
            "enrolled_at": datetime.utcnow().isoformat(),
            "is_active": True,
        }

        result = db.admin_client.table("enrollment").insert(enrollment_data).execute()

        # Invalidate cache
        cache.invalidate_student(str(student_db_id))

        logger.info(
            f"Admin {admin_user.id} enrolled student "
            f"{enrollment_request.student_id} in course "
            f"{enrollment_request.course_id}"
        )

        # Send enrollment confirmation email in background (non-blocking)
        from services.email_service import email_service
        from settings import settings
        
        # Get student user info
        student_user_result = (
            db.admin_client.table("student")
            .select("user_id, users!inner(*)")
            .eq("id", str(student_db_id))
            .execute()
        )
        
        if student_user_result.data:
            student_user_data = student_user_result.data[0].get("users", {})
            student_email = student_user_data.get("email")
            student_name = f"{student_user_data.get('first_name', '')} {student_user_data.get('last_name', '')}".strip()
            
            # Get teacher name
            teacher_result = (
                db.admin_client.table("course")
                .select("teacher_id, teacher!inner(*, users!inner(*))")
                .eq("id", enrollment_request.course_id)
                .execute()
            )
            
            teacher_name = None
            if teacher_result.data:
                teacher_data = teacher_result.data[0].get("teacher", {})
                teacher_user_data = teacher_data.get("users", {})
                teacher_name = f"{teacher_user_data.get('first_name', '')} {teacher_user_data.get('last_name', '')}".strip()
            
            if student_email:
                dashboard_link = f"{settings.FRONTEND_URL}/student/dashboard"
                
                # Add email sending as background task (won't block the response)
                background_tasks.add_task(
                    email_service.send_enrollment_confirmation,
                    to_email=student_email,
                    student_name=student_name or "Student",
                    course_name=course["name"],
                    teacher_name=teacher_name,
                    dashboard_link=dashboard_link
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


@router.get("/courses/{course_id}/enrollments", response_model=list[StudentSummary])
async def get_course_enrollments(
    course_id: str,
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Get all students enrolled in a specific course.
    Only shows students from the admin's university.
    """
    _, university_id = admin_data

    try:
        # Verify course belongs to this university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .eq("id", course_id)
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
            .eq("course_id", course_id)
            .eq("is_active", True)
            .execute()
        )

        students = []
        for enrollment in enrollments_result.data or []:
            student_data = enrollment.get("student", {})
            user_data = student_data.get("users", {})
            student_db_id = student_data["id"]

            # Get all enrollments for this student
            all_enrollments = EnrollmentQueryHelper.get_student_enrollments(
                db, str(student_db_id)
            )

            enrollment_summaries = []
            for enr in all_enrollments:
                course_info = enr.get("course", {})
                semester = enr.get("semester", {})

                enrolled_at_str = enr.get("enrolled_at")
                from utils.datetime_helpers import parse_datetime_safe
                enrolled_at = parse_datetime_safe(enrolled_at_str)

                enrollment_summaries.append(
                    EnrollmentSummary(
                        enrollment_id=enr["id"],
                        course_id=course_info.get("id", ""),
                        course_name=course_info.get("name", ""),
                        course_code=course_info.get("code", ""),
                        semester_name=semester.get("name"),
                        enrolled_at=enrolled_at,
                        is_active=enr.get("is_active", True),
                    )
                )

            students.append(
                StudentSummary(
                    student_id=student_data.get("student_id", ""),
                    user_id=student_data.get("user_id", ""),
                    first_name=user_data.get("first_name", ""),
                    last_name=user_data.get("last_name", ""),
                    email=user_data.get("email", ""),
                    year_of_study=student_data.get("year_of_study"),
                    total_enrollments=len(enrollment_summaries),
                    enrollments=enrollment_summaries,
                )
            )

        return students

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching course enrollments: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching course enrollments",
        ) from e


# ==================== Course Management Routes ====================


@router.get("/courses", response_model=list[dict])
async def list_university_courses(
    admin_data: Annotated[tuple[User, str], Depends(require_admin)],
    db=Depends(get_db),
):
    """
    Get all courses in the admin's university.
    This endpoint is for admins to view all courses for filtering students by course.
    Returns courses with enrollment counts and basic information.
    """
    _, university_id = admin_data

    try:
        # Get all courses for this university
        courses = db.get_records(
            "course",
            filters={"university_id": university_id},
            skip=0,
            limit=1000,
            use_cache=True,
        )

        if not courses:
            return []

        course_ids = [c["id"] for c in courses]

        # Batch fetch enrollment counts for all courses
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

        # Enrich courses with enrollment counts
        enriched_courses = []
        for course in courses:
            course_id = course.get("id")
            enriched_courses.append(
                {
                    **course,
                    "total_enrollments": enrollment_counts.get(course_id, 0),
                }
            )

        return enriched_courses

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
        # Verify course belongs to admin's university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code, university_id")
            .eq("id", assignment_request.course_id)
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

        # Get teacher profile for the user
        teacher_result = (
            db.admin_client.table("teacher")
            .select("id, user_id, university_id")
            .eq("user_id", assignment_request.teacher_user_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not teacher_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher not found in your university",
            )

        teacher = teacher_result.data[0]
        teacher_id = teacher["id"]

        # Check if assignment already exists
        existing_assignment = (
            db.admin_client.table("course_teacher")
            .select("*")
            .eq("course_id", assignment_request.course_id)
            .eq("teacher_id", teacher_id)
            .execute()
        )

        if existing_assignment.data:
            assignment = existing_assignment.data[0]
            # Reactivate if inactive
            if not assignment.get("is_active"):
                db.admin_client.table("course_teacher").update({
                    "is_active": True,
                    "assigned_by": admin_user.id,
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

                return {
                    "message": "Course assignment reactivated successfully",
                    "assignment_id": assignment["id"],
                    "course_name": course["name"],
                    "course_code": course["code"],
                }
            else:
                return {
                    "message": "Course is already assigned to this teacher",
                    "assignment_id": assignment["id"],
                    "course_name": course["name"],
                    "course_code": course["code"],
                }

        # Create new assignment
        assignment_data = {
            "id": str(uuid4()),
            "course_id": assignment_request.course_id,
            "teacher_id": teacher_id,
            "assigned_by": admin_user.id,
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

            logger.info(
                f"Admin {admin_user.id} assigned course {assignment_request.course_id} "
                f"to teacher {teacher_id} (assignment_id: {assignment_id})"
            )

            return {
                "message": "Course assigned to teacher successfully",
                "assignment_id": assignment_id,
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
                    .eq("course_id", assignment_request.course_id)
                    .eq("teacher_id", teacher_id)
                    .execute()
                )
                
                if existing_check.data and len(existing_check.data) > 0:
                    existing = existing_check.data[0]
                    # If it exists but is inactive, reactivate it
                    if not existing.get("is_active"):
                        db.admin_client.table("course_teacher").update({
                            "is_active": True,
                            "assigned_by": admin_user.id,
                            "assigned_at": datetime.utcnow().isoformat(),
                        }).eq("id", existing["id"]).execute()
                        
                        cache.caches["courses"].delete_pattern(
                            f"courses:teacher_courses:{teacher_id}"
                        )
                        
                        logger.info(
                            f"Admin {admin_user.id} reactivated course assignment: "
                            f"course {assignment_request.course_id} -> teacher {teacher_id}"
                        )
                        
                        return {
                            "message": "Course assignment reactivated successfully",
                            "assignment_id": existing["id"],
                            "course_name": course["name"],
                            "course_code": course["code"],
                        }
                    else:
                        # Already active
                        return {
                            "message": "Course is already assigned to this teacher",
                            "assignment_id": existing["id"],
                            "course_name": course["name"],
                            "course_code": course["code"],
                        }
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating course assignment: {str(insert_error)}",
            ) from insert_error

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning course to teacher: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error assigning course to teacher",
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
        from services.email_service import email_service
        from settings import settings
        
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
                errors.append(f"Student {student_data.student_id}: {str(e)}")
            except Exception as e:
                logger.error(f"Error creating student {student_data.student_id}: {e!s}")
                failed_students.append({
                    "email": student_data.email,
                    "student_id": student_data.student_id,
                    "error": f"Internal error: {str(e)}"
                })
                errors.append(f"Student {student_data.student_id}: {str(e)}")
        
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
            detail=f"Error processing bulk signup: {str(e)}",
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
        # Verify course belongs to this university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code, university_id")
            .eq("id", bulk_request.course_id)
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
        
        # Verify semester belongs to this course
        semester_result = (
            db.admin_client.table("semester")
            .select("id, name, course_id")
            .eq("id", bulk_request.semester_id)
            .eq("course_id", bulk_request.course_id)
            .limit(1)
            .execute()
        )
        
        if not semester_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Semester not found for this course",
            )
        
        semester = semester_result.data[0]
        
        # Get teacher info for email
        teacher_result = (
            db.admin_client.table("course")
            .select("teacher_id, teacher!inner(*, users!inner(*))")
            .eq("id", bulk_request.course_id)
            .execute()
        )
        
        teacher_name = None
        if teacher_result.data:
            teacher_data = teacher_result.data[0].get("teacher", {})
            teacher_user_data = teacher_data.get("users", {})
            teacher_name = f"{teacher_user_data.get('first_name', '')} {teacher_user_data.get('last_name', '')}".strip()
        
        from services.email_service import email_service
        from settings import settings
        
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
                    .eq("course_id", bulk_request.course_id)
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
                            "semester_id": bulk_request.semester_id,
                            "enrolled_at": datetime.utcnow().isoformat(),
                        }).eq("id", enrollment["id"]).execute()
                        
                        cache.invalidate_student(str(student_db_id))
                        
                        enrollment_id = enrollment["id"]
                else:
                    # Create new enrollment
                    enrollment_data = {
                        "id": str(uuid4()),
                        "student_id": str(student_db_id),
                        "course_id": bulk_request.course_id,
                        "semester_id": bulk_request.semester_id,
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
                errors.append(f"Student {enrollment_item.student_id}: {str(e)}")
        
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
            detail=f"Error processing bulk enrollment: {str(e)}",
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

        # Verify user belongs to admin's university
        if user_data.get("university_id") != university_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete teachers from your own university",
            )

        # Verify teacher profile exists and belongs to this university
        teacher_result = (
            db.admin_client.table("teacher")
            .select("id, university_id")
            .eq("user_id", user_id)
            .eq("university_id", university_id)
            .limit(1)
            .execute()
        )

        if not teacher_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher profile not found",
            )

        # Delete the user (this will cascade delete the teacher profile)
        success = db.delete_user(user_id)
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

        # Verify user belongs to admin's university
        if user_data.get("university_id") != university_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete students from your own university",
            )

        # Verify student profile exists and belongs to this university
        student_result = (
            db.admin_client.table("student")
            .select("id, university_id, student_id")
            .eq("user_id", user_id)
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

        # Delete the user (this will cascade delete the student profile and enrollments)
        success = db.delete_user(user_id)
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


# Import and include the router in the admin_router from routes_config
# This import is at the end to avoid circular imports
from routes_config import admin_router as main_admin_router

main_admin_router.include_router(router)
