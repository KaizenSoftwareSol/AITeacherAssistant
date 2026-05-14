# student/routes.py
"""
Student-facing API routes for course enrollment, lecture viewing, 
chatbot interaction, and quiz generation.

Optimized with caching for improved performance.
"""

import json
from datetime import datetime, timedelta
from typing import Annotated, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from dependencies import get_current_user
from logger import logger
from models.ai_conversation import AIConversation, ChatMessage, ConversationType, MessageRole
from models.assessment import Assessment, AssessmentSubmission, AssessmentType, Question
from models.course import Course
from models.enrollment import Enrollment
from models.lecture import Lecture, LectureStatus
from models.lecture_embedding import (
    ChatMessageWithQuizResult,
    CourseEnrollmentByCodeRequest,
    LectureSearchRequest,
    LectureSearchResponse,
    LectureSummaryRequest,
    LectureSummaryResponse,
    QuizGenerationRequest,
    QuizResultForChat,
    StudentCourseInfo,
    StudentCourseLecturesResponse,
    StudentLectureInfo
)
from models.user import Student, User, UserRole
from services.cache_service import cache
from services.embedding_service import EmbeddingService
from services.notification_service import NotificationService
from services.quiz_service import QuizService
from services.rag_service import RAGService
from utils.db import get_db
from utils.query_helpers import (
    CourseQueryHelper,
    EnrollmentQueryHelper,
    LectureQueryHelper,
    StudentQueryHelper,
    AssessmentQueryHelper,
    FlashcardQueryHelper,
    TeacherQueryHelper,
    verify_student_enrollment,
    get_lecture_if_enrolled,
)
from utils.id_converter import IDConverter
from supabase_config import supabase

router = APIRouter()


# ==================== Dependencies ====================


async def require_student(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> tuple[User, Student]:
    """
    Dependency to ensure the user is a student and fetch their student profile.
    Uses caching for improved performance.
    """
    if user.role not in [UserRole.STUDENT, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only accessible to students",
        )
    
    # Get student profile with caching
    try:
        # Use UUID for external lookups, but query helpers will convert to integer ID
        user_uuid = user.uuid if hasattr(user, "uuid") and user.uuid else str(user.id)
        student_data = await StudentQueryHelper.get_student_profile(db, user_uuid)
        
        if not student_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student profile not found. Please contact administrator.",
            )
        
        student = Student(**student_data)
        return user, student
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching student profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching student profile",
        )


# ==================== Course Enrollment Routes ====================


@router.post("/enroll-by-token", status_code=status.HTTP_201_CREATED)
async def enroll_by_token(
    token: str = Query(..., description="Enrollment token from email link"),
    user_student: Annotated[tuple[User, Student], Depends(require_student)] = None,
    db=Depends(get_db),
):
    """
    Enroll a student in a course using an enrollment token from email.
    
    Students click the enrollment link sent via email to automatically enroll.
    This creates an enrollment record linking the student to the course.
    """
    user, student = user_student
    
    try:
        from auth.service import AuthService
        
        # Verify enrollment token
        enrollment_data = AuthService.verify_enrollment_token(token)
        if not enrollment_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired enrollment token",
            )
        
        token_student_id = enrollment_data.get("student_id")
        course_id = enrollment_data.get("course_id")
        semester_id = enrollment_data.get("semester_id")
        
        # Verify the token is for this student
        if str(student.id) != token_student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This enrollment link is not for your account",
            )
        
        # Convert UUIDs to integer IDs if needed
        course_int_id = course_id
        semester_int_id = semester_id
        if IDConverter.is_uuid(course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )
        if IDConverter.is_uuid(semester_id):
            semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id)
            if not semester_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Semester not found",
                )
        
        # Verify course exists and belongs to student's university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code, university_id")
            .eq("id", course_int_id)
            .eq("university_id", str(student.university_id))
            .limit(1)
            .execute()
        )
        
        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        
        course = course_result.data[0]
        
        # Verify semester belongs to this course
        semester_result = (
            db.admin_client.table("semester")
            .select("id, name, course_id")
            .eq("id", semester_int_id)
            .eq("course_id", course_int_id)
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
            .eq("student_id", str(student.id))
            .eq("course_id", course_int_id)
            .execute()
        )
        
        if existing_enrollment.data and len(existing_enrollment.data) > 0:
            enrollment = existing_enrollment.data[0]
            if enrollment.get("is_active"):
                return {
                    "message": "Already enrolled in this course",
                    "course_name": course["name"],
                    "course_code": course["code"],
                    "enrollment_id": enrollment["id"],
                }
            else:
                # Reactivate the enrollment
                # semester_int_id is already defined earlier in the function
                db.admin_client.table("enrollment").update({
                    "is_active": True,
                    "semester_id": semester_int_id,
                    "enrolled_at": datetime.utcnow().isoformat(),
                }).eq("id", enrollment["id"]).execute()
                
                cache.invalidate_student(str(student.id))
                
                return {
                    "message": "Re-enrolled in course successfully",
                    "course_name": course["name"],
                    "course_code": course["code"],
                    "enrollment_id": enrollment["id"],
                }
        
        # Create new enrollment
        enrollment_data = {
            "student_id": str(student.id),
            "course_id": course_int_id,
            "semester_id": semester_int_id,
            "enrolled_at": datetime.utcnow().isoformat(),
            "is_active": True,
        }
        
        result = db.admin_client.table("enrollment").insert(enrollment_data).execute()
        
        # Invalidate enrollment caches for this student
        cache.invalidate_student(str(student.id))
        
        logger.info(f"Student {student.id} successfully enrolled in course {course_id} via token")
        
        # Send notifications
        notification_service = NotificationService(db)
        
        # Get student's full name for notification
        student_name = f"{user.first_name} {user.last_name}".strip() or "A student"
        
        # Get teacher info to send notification
        try:
            # Find lectures for this course to get teacher_id
            # Use course_int_id which was already converted
            lecture_result = (
                db.admin_client.table("lecture")
                .select("teacher_id")
                .eq("course_id", course_int_id)
                .limit(1)
                .execute()
            )
            
            if lecture_result.data:
                teacher_id = lecture_result.data[0]["teacher_id"]
                # Get teacher's user_id
                teacher_result = (
                    db.admin_client.table("teacher")
                    .select("user_id")
                    .eq("id", teacher_id)
                    .execute()
                )
                
                if teacher_result.data:
                    teacher_user_id = teacher_result.data[0]["user_id"]
                    # Notify teacher about new enrollment
                    await notification_service.notify_student_enrolled(
                        teacher_user_id=teacher_user_id,
                        student_name=student_name,
                        course_name=course["name"],
                        course_id=course_id,
                    )
        except Exception as notify_error:
            # Don't fail enrollment if notification fails
            logger.warning(f"Failed to send teacher notification: {notify_error}")
        
        # Notify student about successful enrollment
        try:
            await notification_service.notify_enrollment_confirmed(
                student_user_id=str(user.id),
                course_name=course["name"],
                course_id=course_id,
            )
        except Exception as notify_error:
            logger.warning(f"Failed to send student notification: {notify_error}")
        
        return {
            "message": "Successfully enrolled in course",
            "course_name": course["name"],
            "course_code": course["code"],
            "enrollment_id": result.data[0]["id"],
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enrolling student by token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing enrollment",
        ) from e


@router.post("/enroll", status_code=status.HTTP_201_CREATED)
async def enroll_in_course(
    request: CourseEnrollmentByCodeRequest,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Enroll a student in a course using the course code provided by the teacher.
    
    Students enter the course code they received from their teacher in person.
    This creates an enrollment record linking the student to the course.
    """
    user, student = user_student
    
    try:
        logger.info(f"Student {student.id} attempting to enroll in course code: {request.course_code}")
        
        # Find the course by code (cached)
        course = await CourseQueryHelper.get_course_by_code(
            db, request.course_code, str(student.university_id)
        )
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Course with code '{request.course_code}' not found at your university",
            )
        
        course_id = course["id"]
        
        # Convert course_id to integer if needed (from query helper might return UUID)
        course_int_id = course_id
        if IDConverter.is_uuid(course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
            if not course_int_id:
                course_int_id = course_id  # Fallback
        
        # Check if already enrolled
        existing_enrollment = (
            db.admin_client.table("enrollment")
            .select("*")
            .eq("student_id", str(student.id))
            .eq("course_id", course_int_id)
            .execute()
        )
        
        if existing_enrollment.data and len(existing_enrollment.data) > 0:
            enrollment = existing_enrollment.data[0]
            if enrollment.get("is_active"):
                return {
                    "message": "Already enrolled in this course",
                    "course_name": course["name"],
                    "course_code": course["code"],
                    "enrollment_id": enrollment["id"],
                }
            else:
                # Reactivate the enrollment
                db.admin_client.table("enrollment").update({
                    "is_active": True,
                    "enrolled_at": datetime.utcnow().isoformat()
                }).eq("id", enrollment["id"]).execute()
                
                return {
                    "message": "Re-enrolled in course successfully",
                    "course_name": course["name"],
                    "course_code": course["code"],
                    "enrollment_id": enrollment["id"],
                }
        
        # Get the semester (use provided or get latest)
        semester_id = request.semester_id
        semester_int_id = None
        if semester_id:
            # Convert semester_id to integer if needed
            if IDConverter.is_uuid(semester_id):
                semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id)
                if not semester_int_id:
                    semester_int_id = semester_id  # Fallback
            else:
                semester_int_id = semester_id
        else:
            # 1. Try course-level semester (legacy)
            semester_result = (
                db.admin_client.table("semester")
                .select("*")
                .eq("course_id", course_int_id)
                .order("start_date", desc=True)
                .limit(1)
                .execute()
            )

            if semester_result.data:
                semester_id = semester_result.data[0]["id"]
                semester_int_id = semester_id
            else:
                # 2. Fall back to the most recent university-level semester
                uni_semester_result = (
                    db.admin_client.table("semester")
                    .select("*")
                    .eq("university_id", student.university_id)
                    .is_("course_id", "null")
                    .order("start_date", desc=True)
                    .limit(1)
                    .execute()
                )

                if uni_semester_result.data:
                    semester_id = uni_semester_result.data[0]["id"]
                    semester_int_id = semester_id
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No active semester found for this course. Please contact your instructor.",
                    )
        
        # Create enrollment
        enrollment_data = {
            "student_id": str(student.id),
            "course_id": course_int_id,
            "semester_id": semester_int_id,
            "enrolled_at": datetime.utcnow().isoformat(),
            "is_active": True,
        }
        
        result = db.admin_client.table("enrollment").insert(enrollment_data).execute()
        
        # Invalidate enrollment caches for this student
        cache.invalidate_student(str(student.id))
        
        logger.info(f"Student {student.id} successfully enrolled in course {course_id}")
        
        # Send notifications
        notification_service = NotificationService(db)
        
        # Get student's full name for notification
        student_name = f"{user.first_name} {user.last_name}".strip() or "A student"
        
        # Get teacher info to send notification
        try:
            # Find lectures for this course to get teacher_id
            lecture_result = (
                db.admin_client.table("lecture")
                .select("teacher_id")
                .eq("course_id", course_int_id)
                .limit(1)
                .execute()
            )
            
            if lecture_result.data:
                teacher_id = lecture_result.data[0]["teacher_id"]
                # Get teacher's user_id
                teacher_result = (
                    db.admin_client.table("teacher")
                    .select("user_id")
                    .eq("id", teacher_id)
                    .execute()
                )
                
                if teacher_result.data:
                    teacher_user_id = teacher_result.data[0]["user_id"]
                    # Notify teacher about new enrollment
                    await notification_service.notify_student_enrolled(
                        teacher_user_id=teacher_user_id,
                        student_name=student_name,
                        course_name=course["name"],
                        course_id=course_id,
                    )
        except Exception as notify_error:
            # Don't fail enrollment if notification fails
            logger.warning(f"Failed to send teacher notification: {notify_error}")
        
        # Notify student about successful enrollment
        try:
            await notification_service.notify_enrollment_confirmed(
                student_user_id=str(user.id),
                course_name=course["name"],
                course_id=course_id,
            )
        except Exception as notify_error:
            logger.warning(f"Failed to send student notification: {notify_error}")
        
        return {
            "message": "Successfully enrolled in course",
            "course_name": course["name"],
            "course_code": course["code"],
            "enrollment_id": result.data[0]["id"],
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enrolling student in course: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing enrollment",
        )


@router.get("/my-courses", response_model=dict)
async def get_my_courses(
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get all courses the student is enrolled in.
    
    Returns course information including teacher name and lecture counts.
    Format: "Course Name - Teacher Name"
    
    Optimized with caching and batch queries.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching courses for student {student.id}")
        
        # Check cache first for the entire response
        cache_key = f"my_courses:{student.id}"
        cached_courses = cache.get("enrollments", cache_key)
        if cached_courses is not None:
            return cached_courses
        
        # Get all active enrollments for this student (cached)
        student_uuid = student.uuid if hasattr(student, "uuid") and student.uuid else str(student.id)
        enrollments = await EnrollmentQueryHelper.get_student_enrollments(db, student_uuid)
        
        if not enrollments:
            logger.info(f"No enrollments found for student {student.id}")
            uni = db.get_record_by_id("university", student.university_id)
            uni_type = uni.get("type", "GENERAL") if uni else "GENERAL"
            return {"university_type": uni_type, "courses": []}
        
        # Collect all course IDs for batch queries
        course_ids = [e.get("course", {}).get("id") for e in enrollments if e.get("course", {}).get("id")]
        
        # Batch fetch all lectures for all courses at once
        all_lectures_result = (
            db.admin_client.table("lecture")
            .select("id, status, teacher_id, course_id")
            .in_("course_id", course_ids)
            .execute()
        )
        
        # Group lectures by course_id
        lectures_by_course = {}
        teacher_ids = set()
        for lec in (all_lectures_result.data or []):
            cid = lec.get("course_id")
            if cid not in lectures_by_course:
                lectures_by_course[cid] = []
            lectures_by_course[cid].append(lec)
            if lec.get("teacher_id"):
                teacher_ids.add(lec["teacher_id"])
        
        # Batch fetch all teacher names at once
        teacher_names = {}
        if teacher_ids:
            teachers_result = (
                db.admin_client.table("teacher")
                .select("id, users(first_name, last_name)")
                .in_("id", list(teacher_ids))
                .execute()
            )
            for t in (teachers_result.data or []):
                user_data = t.get("users", {})
                if user_data:
                    name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
                    teacher_names[t["id"]] = name or "Unknown Teacher"
        
        courses = []
        for enrollment in enrollments:
            course = enrollment.get("course", {})
            course_id_int = course.get("id")
            
            if not course_id_int:
                continue
            
            # Convert integer course_id to UUID for API response
            course_id_uuid = None
            if isinstance(course_id_int, int):
                course_id_uuid = await IDConverter.int_to_uuid(db, "course", course_id_int)
            elif isinstance(course_id_int, str):
                if IDConverter.is_uuid(course_id_int):
                    course_id_uuid = course_id_int
                else:
                    # Try to convert string to int then to UUID
                    try:
                        course_id_int = int(course_id_int)
                        course_id_uuid = await IDConverter.int_to_uuid(db, "course", course_id_int)
                    except ValueError:
                        course_id_uuid = course_id_int  # Fallback
            
            if not course_id_uuid:
                course_id_uuid = str(course_id_int)  # Final fallback
            
            course_lectures = lectures_by_course.get(course_id_int, [])
            total_lectures = len(course_lectures)
            published_lectures = sum(
                1 for l in course_lectures
                if l.get("status") in ["PUBLISHED", "DELIVERED"]
            )
            
            # Get teacher name from first lecture
            teacher_name = "Unknown Teacher"
            if course_lectures:
                teacher_id = course_lectures[0].get("teacher_id")
                if teacher_id:
                    teacher_name = teacher_names.get(teacher_id, "Unknown Teacher")
            
            course_info = StudentCourseInfo(
                course_id=course_id_uuid,  # Use UUID string for API
                course_code=course.get("code", "N/A"),
                course_name=course.get("name", "Unnamed Course"),
                course_description=course.get("description"),
                teacher_name=teacher_name,
                display_name=f"{course.get('name', 'Unnamed Course')} - {teacher_name}",
                enrolled_at=enrollment.get("enrolled_at"),
                total_lectures=total_lectures,
                published_lectures=published_lectures,
            )
            courses.append(course_info)

        # Get university type
        university = db.get_record_by_id("university", student.university_id)
        university_type = university.get("type", "GENERAL") if university else "GENERAL"

        # Convert to dicts for the wrapper response
        courses_data = [c.dict() for c in courses]

        # Enrich with module + semester info
        if course_ids:
            # Map course_id → enrollment semester_id
            enrollment_semesters = {}
            for enrollment in enrollments:
                cid = enrollment.get("course", {}).get("id")
                sid = enrollment.get("semester_id")
                if cid and sid:
                    enrollment_semesters[cid] = sid

            all_semester_ids = list(set(enrollment_semesters.values()))

            # Batch fetch semester names
            semester_names = {}
            if all_semester_ids:
                semesters_result = (
                    db.admin_client.table("semester")
                    .select("id, name")
                    .in_("id", all_semester_ids)
                    .execute()
                )
                semester_names = {s["id"]: s["name"] for s in (semesters_result.data or [])}

            # Batch fetch modules for these semesters
            modules_by_id = {}
            all_module_ids = []
            if all_semester_ids:
                modules_result = (
                    db.admin_client.table("module")
                    .select("id, name, semester_id, display_order")
                    .in_("semester_id", all_semester_ids)
                    .execute()
                )
                modules_by_id = {m["id"]: m for m in (modules_result.data or [])}
                all_module_ids = list(modules_by_id.keys())

            # Batch fetch module_course for these modules + courses
            course_modules = {}
            if all_module_ids:
                mc_result = (
                    db.admin_client.table("module_course")
                    .select("course_id, module_id")
                    .in_("module_id", all_module_ids)
                    .in_("course_id", course_ids)
                    .execute()
                )
                for mc in (mc_result.data or []):
                    cid = mc["course_id"]
                    mid = mc["module_id"]
                    mod = modules_by_id.get(mid, {})
                    # Only include if module's semester matches enrollment semester
                    if mod.get("semester_id") == enrollment_semesters.get(cid):
                        course_modules.setdefault(cid, []).append({
                            "module_id": mid,
                            "module_name": mod.get("name"),
                            "module_display_order": mod.get("display_order", 0),
                            "semester_id": mod.get("semester_id"),
                        })

            # Attach module + semester info to each course
            # Note: courses_data has UUID course_id, but enrollment_semesters and course_modules use integer IDs
            # We need to map UUID back to integer for lookup
            course_uuid_to_int = {}
            for enrollment in enrollments:
                course = enrollment.get("course", {})
                course_id_int = course.get("id")
                if course_id_int:
                    # Convert to UUID to match courses_data
                    if isinstance(course_id_int, int):
                        course_id_uuid = await IDConverter.int_to_uuid(db, "course", course_id_int)
                        if course_id_uuid:
                            course_uuid_to_int[course_id_uuid] = course_id_int
            
            for cd in courses_data:
                course_id_uuid = cd.get("course_id")
                course_id_int = course_uuid_to_int.get(course_id_uuid)
                if course_id_int:
                    cd["semester_name"] = semester_names.get(enrollment_semesters.get(course_id_int, ""))
                    # Convert module and semester IDs to UUIDs
                    modules = course_modules.get(course_id_int, [])
                    converted_modules = []
                    for mod in modules:
                        module_id_int = mod.get("module_id")
                        semester_id_int = mod.get("semester_id")
                        
                        # Convert module_id to UUID
                        module_id_uuid = None
                        if isinstance(module_id_int, int):
                            module_id_uuid = await IDConverter.int_to_uuid(db, "module", module_id_int)
                        if not module_id_uuid:
                            module_id_uuid = str(module_id_int) if module_id_int else None
                        
                        # Convert semester_id to UUID
                        semester_id_uuid = None
                        if isinstance(semester_id_int, int):
                            semester_id_uuid = await IDConverter.int_to_uuid(db, "semester", semester_id_int)
                        if not semester_id_uuid:
                            semester_id_uuid = str(semester_id_int) if semester_id_int else None
                        
                        converted_modules.append({
                            "module_id": module_id_uuid,
                            "module_name": mod.get("module_name"),
                            "module_display_order": mod.get("module_display_order", 0),
                            "semester_id": semester_id_uuid,
                            "semester_name": semester_names.get(semester_id_int, ""),
                        })
                    cd["modules"] = converted_modules
                else:
                    cd["semester_name"] = None
                    cd["modules"] = []

        # Wrap response
        result = {"university_type": university_type, "courses": courses_data}

        # Cache the result for 2 minutes
        cache.set("enrollments", result, cache_key, ttl=120)

        logger.info(f"Found {len(courses_data)} courses for student {student.id}")
        return result
    
    except Exception as e:
        logger.error(f"Error fetching student courses: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching courses",
        )


@router.get("/courses/{course_id}/lectures", response_model=StudentCourseLecturesResponse)
async def get_course_lectures(
    course_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get all published lectures for a specific course.
    
    Students can only see published/delivered lectures for courses they're enrolled in.
    Optimized with caching.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching lectures for course {course_id}, student {student.id}")
        
        # Convert UUID to integer ID if needed
        course_int_id = course_id
        if IDConverter.is_uuid(course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )
        
        # Check cache first
        cache_key = f"course_lectures:{course_id}:{student.id}"
        cached_response = cache.get("lectures", cache_key)
        if cached_response is not None:
            return cached_response
        
        # Verify student is enrolled in this course (cached)
        student_uuid = student.uuid if hasattr(student, "uuid") and student.uuid else str(student.id)
        enrollment = await EnrollmentQueryHelper.check_enrollment(db, student_uuid, course_id)
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Get course information (cached)
        course = await CourseQueryHelper.get_course_with_cache(db, course_id)
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        
        # Get all published lectures for this course (cached)
        lectures_data = await LectureQueryHelper.get_course_lectures(
            db, course_id, status_filter=["PUBLISHED", "DELIVERED"]
        )
        
        # Get teacher name from first lecture if available
        teacher_name = "Unknown Teacher"
        if lectures_data:
            teacher_id = None
            # Try to get teacher_id from lectures
            for lec in lectures_data:
                if lec.get("teacher_id"):
                    teacher_id = lec.get("teacher_id")
                    break
            
            if not teacher_id:
                # Fallback: query for teacher_id
                first_lecture = (
                    db.admin_client.table("lecture")
                    .select("teacher_id")
                    .eq("course_id", course_int_id)
                    .limit(1)
                    .execute()
                )
                if first_lecture.data:
                    teacher_id = first_lecture.data[0].get("teacher_id")
            
            if teacher_id:
                teacher_name = await TeacherQueryHelper.get_teacher_name(db, teacher_id)
        
        # Batch fetch lecture_content for PDFs
        lecture_id_list = [row["id"] for row in lectures_data]
        content_by_lecture_id = {}
        if lecture_id_list:
            lc_result = (
                db.admin_client.table("lecture_content")
                .select("lecture_id, file_name, file_size, storage_bucket, storage_path")
                .in_("lecture_id", lecture_id_list)
                .execute()
            )
            for row in lc_result.data or []:
                # keep the first record per lecture
                lid = row.get("lecture_id")
                if lid and lid not in content_by_lecture_id:
                    content_by_lecture_id[lid] = row

        # Build lecture list with content and pdf info
        lectures = []
        for lecture_data in lectures_data:
            # Convert integer ID to UUID for API response
            lecture_uuid = await IDConverter.int_to_uuid(db, "lecture", lecture_data["id"]) if lecture_data.get("id") else None
            
            pdf_file_name = None
            pdf_file_size = None
            pdf_download_url = None
            lc = content_by_lecture_id.get(lecture_data["id"])
            if lc:
                pdf_file_name = lc.get("file_name")
                pdf_file_size = lc.get("file_size")
                storage_bucket = lc.get("storage_bucket")
                storage_path = lc.get("storage_path")
                try:
                    if storage_bucket and storage_path:
                        bucket = supabase.get_storage_bucket(storage_bucket)
                        pdf_download_url = bucket.get_public_url(storage_path)
                except Exception as e:
                    logger.warning(f"Could not get public URL for lecture {lecture_data['id']}: {e}")

            lecture_info = StudentLectureInfo(
                lecture_id=lecture_uuid or str(lecture_data["id"]),  # Use UUID if available
                title=lecture_data["title"],
                description=lecture_data.get("description"),
                summary=lecture_data.get("summary"),
                chapter=lecture_data.get("chapter"),
                status=lecture_data["status"],
                created_at=lecture_data["created_at"],
                has_embeddings=lecture_data.get("has_embeddings", False),
                topic=lecture_data.get("topic"),
                lecture_number=lecture_data.get("lecture_number"),
                content=lecture_data.get("content"),
                pdf_file_name=pdf_file_name,
                pdf_file_size=pdf_file_size,
                pdf_download_url=pdf_download_url,
                published_at=lecture_data.get("updated_at") or lecture_data.get("created_at"),
            )
            lectures.append(lecture_info)
        
        # Group lectures by topic for response
        lectures_by_topic = {}
        lectures_without_topic = []
        
        for lec in lectures:
            topic = getattr(lec, "topic", None)
            if topic:
                if topic not in lectures_by_topic:
                    lectures_by_topic[topic] = []
                lectures_by_topic[topic].append(lec)
            else:
                lectures_without_topic.append(lec)
        
        # Sort lectures within each topic by lecture_number
        for topic in lectures_by_topic:
            lectures_by_topic[topic].sort(
                key=lambda x: (getattr(x, "lecture_number", None) or 0, x.created_at or datetime.min)
            )
        
        # Sort topics alphabetically
        sorted_topics = sorted(lectures_by_topic.keys())
        grouped_dict = {topic: lectures_by_topic[topic] for topic in sorted_topics}
        
        # Build response
        # Convert integer course_id to UUID for API response
        course_id_int = course["id"]
        course_id_uuid = None
        if isinstance(course_id_int, int):
            course_id_uuid = await IDConverter.int_to_uuid(db, "course", course_id_int)
        elif isinstance(course_id_int, str):
            if IDConverter.is_uuid(course_id_int):
                course_id_uuid = course_id_int
            else:
                try:
                    course_id_int = int(course_id_int)
                    course_id_uuid = await IDConverter.int_to_uuid(db, "course", course_id_int)
                except ValueError:
                    course_id_uuid = course_id_int
        
        if not course_id_uuid:
            course_id_uuid = str(course_id_int)  # Fallback
        
        course_info = StudentCourseInfo(
            course_id=course_id_uuid,  # Use UUID string for API
            course_code=course["code"],
            course_name=course["name"],
            course_description=course.get("description"),
            teacher_name=teacher_name,
            display_name=f"{course['name']} - {teacher_name}",
            enrolled_at=enrollment.get("enrolled_at"),
            total_lectures=len(lectures),
            published_lectures=len(lectures),
        )
        
        response = StudentCourseLecturesResponse(
            course_info=course_info,
            lectures=lectures,  # Keep flat list for backward compatibility
            grouped_by_topic=grouped_dict if grouped_dict else None,
            lectures_without_topic=lectures_without_topic if lectures_without_topic else None,
            total_count=len(lectures),
        )
        
        # Cache the response for 3 minutes
        cache.set("lectures", response, cache_key, ttl=180)
        
        logger.info(f"Found {len(lectures)} lectures for course {course_id}")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching course lectures: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching lectures",
        )


# ==================== Lecture & Chatbot Routes ====================


@router.get("/lectures/{lecture_id}/summary", response_model=LectureSummaryResponse)
async def get_lecture_summary(
    lecture_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    regenerate: bool = False,
    db=Depends(get_db),
):
    """
    Get or generate a summary for a lecture.
    
    This is the first thing shown to students when they open a lecture.
    If summary doesn't exist, it will be generated using AI.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching summary for lecture {lecture_id}, student {student.id}")
        
        # Get lecture and verify access
        # Convert UUID to integer ID for database query
        lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id) if IDConverter.is_uuid(lecture_id) else lecture_id
        if not lecture_int_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )
        
        lecture_result = (
            db.get_admin_client().table("lecture")
            .select("*, course!inner(id)")
            .eq("id", lecture_int_id)
            .in_("status", ["PUBLISHED", "DELIVERED"])
            .execute()
        )
        
        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or not published",
            )
        
        lecture = lecture_result.data[0]
        course_id = lecture["course"]["id"]
        # Ensure course_id is an integer (from database result, should already be int after migration)
        course_int_id = course_id if isinstance(course_id, int) else course_id
        
        # Verify enrollment - convert student_id to integer
        student_int_id = student.id if isinstance(student.id, int) else await IDConverter.uuid_to_int(db, "student", str(student.id))
        if not student_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get student ID",
            )
        
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", student_int_id)  # Use integer ID
            .eq("course_id", course_int_id)  # Use integer ID
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check if summary exists and regenerate flag is not set
        if lecture.get("summary") and not regenerate:
            return LectureSummaryResponse(
                lecture_id=lecture_id,
                summary=lecture["summary"],
                generated_at=lecture.get("updated_at", lecture["created_at"]),
            )
        
        # Generate summary using AI
        from services.summary_service import SummaryService
        
        summary_service = SummaryService()
        summary = await summary_service.generate_lecture_summary(lecture["content"])
        
        # Update lecture with summary
        db.admin_client.table("lecture").update({
            "summary": summary,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", lecture_int_id).execute()
        
        logger.info(f"Generated summary for lecture {lecture_id}")
        
        return LectureSummaryResponse(
            lecture_id=lecture_id,
            summary=summary,
            generated_at=datetime.utcnow(),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching/generating lecture summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating lecture summary",
        )


@router.post("/lectures/{lecture_id}/generate-embeddings")
async def generate_lecture_embeddings(
    lecture_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Generate embeddings for a lecture to enable RAG-based chatbot.
    
    This endpoint allows students to generate embeddings on-demand when they
    want to use the chatbot feature. Embeddings are only generated once and
    reused for all future chat sessions.
    """
    user, student = user_student
    
    try:
        logger.info(f"Embedding generation request for lecture {lecture_id}, student {student.id}")
        
        # Convert UUID to integer ID if needed
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found or not published",
                )
        
        # Verify lecture access and enrollment
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, title, content, has_embeddings, course_id")
            .eq("id", lecture_int_id)
            .in_("status", ["PUBLISHED", "DELIVERED"])
            .execute()
        )
        
        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or not published",
            )
        
        lecture = lecture_result.data[0]
        course_id = lecture["course_id"]
        
        # course_id from database should be integer already, but verify
        course_int_id = course_id if isinstance(course_id, int) else course_id
        
        # Verify student is enrolled in the course
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("*")
            .eq("student_id", str(student.id))
            .eq("course_id", course_int_id)
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check if embeddings already exist
        if lecture.get("has_embeddings"):
            return {
                "status": "already_exists",
                "message": "Embeddings already exist for this lecture",
                "lecture_id": lecture_id,
                "has_embeddings": True,
            }
        
        # Generate embeddings
        from services.embedding_service import EmbeddingService
        
        embedding_service = EmbeddingService(db)
        
        logger.info(f"Generating embeddings for lecture {lecture_id}...")
        result = await embedding_service.generate_embeddings_for_lecture(
            lecture_id=lecture_id,
            lecture_content=lecture["content"]
        )
        
        logger.info(
            f"Generated {result['chunks_created']} chunks and "
            f"{result['embeddings_created']} embeddings for lecture {lecture_id}"
        )
        
        return {
            "status": "success",
            "message": "Embeddings generated successfully! You can now chat with the lecture.",
            "lecture_id": lecture_id,
            "chunks_created": result["chunks_created"],
            "embeddings_created": result["embeddings_created"],
            "has_embeddings": True,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating embeddings for lecture {lecture_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating embeddings: {str(e)}",
        )


@router.post("/lectures/{lecture_id}/chat")
async def chat_with_lecture(
    lecture_id: str,
    message: dict,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    session_id: Optional[str] = None,
    db=Depends(get_db),
):
    """
    Chat with the AI about a specific lecture using RAG.
    
    The chatbot uses semantic search to find relevant chunks from the lecture
    and provides contextual answers based on the lecture content.
    
    NOTE: Embeddings must be generated first using the /generate-embeddings endpoint.
    """
    user, student = user_student
    
    try:
        user_message = message.get("content", "").strip()
        if not user_message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message content is required",
            )
        
        # Get integer user_id for rate limiting check
        user_int_id = user.id if isinstance(user.id, int) else await IDConverter.uuid_to_int(db, "users", str(user.id))
        if not user_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get user ID",
            )
        
        # Rate limiting: Check daily message count (20 messages per day)
        # Count USER role messages sent today (UTC) - Database-backed (persistent across restarts)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        # Optimized: Count messages directly via join instead of two queries
        # This query counts USER messages for this user sent today
        messages_result = (
            db.admin_client.table("chat_message")
            .select("id", count="exact")
            .eq("role", "USER")
            .gte("created_at", today_start.isoformat())
            .lt("created_at", today_end.isoformat())
            .execute()
        )
        
        # Filter to only this user's messages by checking conversation ownership
        # We need to get conversation IDs first, then count messages
        user_conversations = (
            db.admin_client.table("ai_conversation")
            .select("id")
            .eq("user_id", user_int_id)
            .execute()
        )
        
        conversation_ids = [conv["id"] for conv in user_conversations.data] if user_conversations.data else []
        
        # Count USER messages sent today for this user's conversations
        messages_today = 0
        if conversation_ids:
            messages_result = (
                db.admin_client.table("chat_message")
                .select("id", count="exact")
                .in_("conversation_id", conversation_ids)
                .eq("role", "USER")
                .gte("created_at", today_start.isoformat())
                .lt("created_at", today_end.isoformat())
                .execute()
            )
            # Use count if available, otherwise count data
            if hasattr(messages_result, "count") and messages_result.count is not None:
                messages_today = messages_result.count
            else:
                messages_today = len(messages_result.data) if messages_result.data else 0
        
        # Daily limit: 20 messages per day
        daily_message_limit = 20
        
        if messages_today >= daily_message_limit:
            # Calculate when the limit resets (next day at midnight UTC)
            reset_time = today_end
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"You have reached the daily limit of {daily_message_limit} messages. Please try again tomorrow.",
                    "limit": daily_message_limit,
                    "used": messages_today,
                    "remaining": 0,
                    "reset_at": reset_time.isoformat(),
                },
            )
        
        logger.info(f"Chat request for lecture {lecture_id}, student {student.id} (Messages today: {messages_today}/{daily_message_limit})")
        
        # Verify lecture access (same as summary endpoint)
        # Convert UUID to integer ID for database query
        lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id) if IDConverter.is_uuid(lecture_id) else lecture_id
        if not lecture_int_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )
        
        lecture_result = (
            db.get_admin_client().table("lecture")
            .select("*, course!inner(id)")
            .eq("id", lecture_int_id)
            .in_("status", ["PUBLISHED", "DELIVERED"])
            .execute()
        )
        
        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )
        
        lecture = lecture_result.data[0]
        course_id = lecture["course"]["id"]
        # Ensure course_id is an integer (from database result, should already be int after migration)
        course_int_id = course_id if isinstance(course_id, int) else course_id
        
        # Verify enrollment - convert student_id to integer
        student_int_id = student.id if isinstance(student.id, int) else await IDConverter.uuid_to_int(db, "student", str(student.id))
        if not student_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get student ID",
            )
        
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", student_int_id)  # Use integer ID
            .eq("course_id", course_int_id)  # Use integer ID
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Convert UUID to integer ID if needed
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )
        
        # Get or create conversation
        # If session_id is provided, try to use that conversation
        # Otherwise, look for the latest conversation for this user+lecture in the last 24h
        conversation_result = None
        conversation_record = None
        conversation_int_id = None
        conversation_uuid = None
        
        if session_id:
            # Try to find conversation by session_id
            conversation_result = (
                db.admin_client.table("ai_conversation")
                .select("*")
                .eq("session_id", session_id)
                .eq("user_id", user_int_id)  # Use integer ID (already obtained above)
                .eq("lecture_id", lecture_int_id)  # Use integer ID
                .execute()
            )
        
        # If no session_id or conversation not found, look for latest conversation in last 24h
        if not conversation_result or not conversation_result.data:
            # Look for the most recent conversation for this user+lecture in the last 24 hours
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            recent_conversations = (
                db.admin_client.table("ai_conversation")
                .select("*")
                .eq("user_id", user_int_id)
                .eq("lecture_id", lecture_int_id)
                .gte("created_at", cutoff_time.isoformat())
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            
            if recent_conversations.data:
                conversation_result = recent_conversations
                conversation_record = recent_conversations.data[0]
                conversation_int_id = conversation_record["id"]
                conversation_uuid = conversation_record.get("uuid")
                if not conversation_uuid:
                    conversation_uuid = await IDConverter.int_to_uuid(db, "ai_conversation", conversation_int_id) if isinstance(conversation_int_id, int) else str(conversation_int_id)
                # Use the existing session_id from the found conversation
                session_id = conversation_record.get("session_id") or str(uuid4())
        
        # If still no conversation found, create a new one
        if not conversation_result or not conversation_result.data:
            if not session_id:
                session_id = str(uuid4())
            
            # Create new conversation with integer IDs
            conversation_uuid = str(uuid4())
            conversation_data = {
                "uuid": conversation_uuid,  # Store UUID for external use
                "user_id": user_int_id,  # Integer FK
                "lecture_id": lecture_int_id,  # Integer FK
                "conversation_type": "LECTURE_QA",
                "session_id": session_id,
                "title": f"Chat about {lecture['title'][:50]}",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            conversation_result = db.admin_client.table("ai_conversation").insert(conversation_data).execute()
            conversation_record = conversation_result.data[0]
            conversation_int_id = conversation_record["id"]  # Integer ID from database
            conversation_uuid = conversation_record.get("uuid") or conversation_uuid
        else:
            # Use existing conversation
            if not conversation_record:
                conversation_record = conversation_result.data[0]
            conversation_int_id = conversation_record["id"]  # Integer ID from database
            conversation_uuid = conversation_record.get("uuid")
            if not conversation_uuid:
                conversation_uuid = await IDConverter.int_to_uuid(db, "ai_conversation", conversation_int_id) if isinstance(conversation_int_id, int) else str(conversation_int_id)
        
        # Save user message with integer conversation_id
        user_msg_uuid = str(uuid4())
        user_msg_data = {
            "uuid": user_msg_uuid,  # Store UUID for external use
            "conversation_id": conversation_int_id,  # Integer FK
            "role": "USER",
            "content": user_message,
            "created_at": datetime.utcnow().isoformat(),
        }
        db.admin_client.table("chat_message").insert(user_msg_data).execute()
        
        # Use RAG service to get response
        rag_service = RAGService(db)
        response = await rag_service.generate_response(
            lecture_id=lecture_id,  # UUID string for external use
            query=user_message,
            conversation_id=conversation_int_id,  # Pass integer ID for internal database queries
        )
        
        # Save assistant message with integer conversation_id
        assistant_msg_uuid = str(uuid4())
        assistant_msg_data = {
            "uuid": assistant_msg_uuid,  # Store UUID for external use
            "conversation_id": conversation_int_id,  # Integer FK
            "role": "ASSISTANT",
            "content": response["answer"],
            "message_metadata": json.dumps({
                "sources": response.get("sources", []),
                "similarity_scores": response.get("similarity_scores", []),
            }),
            "created_at": datetime.utcnow().isoformat(),
        }
        db.admin_client.table("chat_message").insert(assistant_msg_data).execute()
        
        logger.info(f"Chat response generated for lecture {lecture_id}")
        
        # Calculate remaining messages for today
        remaining_messages = daily_message_limit - (messages_today + 1)  # +1 because we just sent a message
        
        return {
            "session_id": session_id,
            "conversation_id": conversation_uuid,  # Return UUID for API
            "response": response["answer"],
            "sources": response.get("sources", []),
            "rate_limit": {
                "limit": daily_message_limit,
                "used": messages_today + 1,
                "remaining": remaining_messages,
                "reset_at": today_end.isoformat(),
            },
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat request: {str(e)}",
        )


# ==================== Flashcard Routes ====================


@router.get("/lectures/{lecture_id}/flashcards")
async def get_lecture_flashcards(
    lecture_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get flashcards for a lecture.
    
    Returns the pre-generated flashcards that were created when the lecture was published.
    Students can use these for quick review and study.
    Optimized with caching.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching flashcards for lecture {lecture_id}, student {student.id}")
        
        # Check cache for the full response
        cache_key = f"flashcards_response:{lecture_id}"
        cached_response = cache.get("flashcards", cache_key)
        if cached_response is not None:
            # Still need to verify enrollment (but this is cached too)
            lecture = await LectureQueryHelper.get_published_lecture(db, lecture_id)
            if lecture:
                course_id = lecture.get("course", {}).get("id") or lecture.get("course_id")
                student_uuid = student.uuid if hasattr(student, "uuid") and student.uuid else str(student.id)
                if course_id and await verify_student_enrollment(db, student_uuid, course_id):
                    return cached_response
        
        # Verify lecture access and enrollment (cached)
        student_uuid = student.uuid if hasattr(student, "uuid") and student.uuid else str(student.id)
        lecture, error = await get_lecture_if_enrolled(db, lecture_id, student_uuid, published_only=True)
        
        if error:
            status_code = status.HTTP_403_FORBIDDEN if "not enrolled" in error else status.HTTP_404_NOT_FOUND
            raise HTTPException(status_code=status_code, detail=error)
        
        course_id = lecture.get("course", {}).get("id") or lecture.get("course_id")
        
        # Get flashcards for this lecture (cached)
        flashcards_data = await FlashcardQueryHelper.get_lecture_flashcards(db, lecture_id)
        
        if not flashcards_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No flashcards available for this lecture yet. They may still be generating.",
            )
        
        flashcards = []
        for card in flashcards_data:
            # Convert integer ID to UUID for API response
            card_uuid = await IDConverter.int_to_uuid(db, "flashcard", card["id"]) if card.get("id") else None
            flashcards.append({
                "id": card_uuid or str(card["id"]),  # Use UUID if available, fallback to string
                "question": card["question"],
                "answer": card["answer"],
                "difficulty": card.get("difficulty", "MEDIUM"),
                "topic": card.get("topic", "General"),
                "order_index": card.get("order_index", 0),
            })
        
        # Group by difficulty for stats
        difficulties = {}
        topics = {}
        for card in flashcards:
            diff = card["difficulty"]
            topic = card["topic"]
            difficulties[diff] = difficulties.get(diff, 0) + 1
            topics[topic] = topics.get(topic, 0) + 1
        
        response = {
            "lecture_id": lecture_id,
            "lecture_title": lecture.get("title"),
            "total_flashcards": len(flashcards),
            "by_difficulty": difficulties,
            "by_topic": topics,
            "flashcards": flashcards,
        }
        
        # Cache the response for 10 minutes
        cache.set("flashcards", response, cache_key, ttl=600)
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching flashcards: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching flashcards: {str(e)}",
        )


# ==================== Quiz Routes ====================


@router.get("/lectures/{lecture_id}/quiz")
async def get_lecture_quiz(
    lecture_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get the saved/default quiz for a lecture.
    
    Returns the pre-generated quiz that was created when the lecture was published.
    This is the same quiz for all students.
    Optimized with caching.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching saved quiz for lecture {lecture_id}, student {student.id}")
        
        # Check cache for the quiz response
        cache_key = f"quiz_response:{lecture_id}"
        cached_response = cache.get("assessments", cache_key)
        
        # Verify access first (cached operations)
        student_uuid = student.uuid if hasattr(student, "uuid") and student.uuid else str(student.id)
        lecture, error = await get_lecture_if_enrolled(db, lecture_id, student_uuid, published_only=True)
        
        if error:
            status_code = status.HTTP_403_FORBIDDEN if "not enrolled" in error else status.HTTP_404_NOT_FOUND
            raise HTTPException(status_code=status_code, detail=error)
        
        # Return cached response if available (after access verification)
        if cached_response is not None:
            return cached_response
        
        course_id = lecture.get("course", {}).get("id") or lecture.get("course_id")
        
        # Get default quiz for this lecture (cached)
        assessment = await AssessmentQueryHelper.get_default_assessment(db, lecture_id)
        
        if not assessment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No quiz available for this lecture yet. It may still be generating.",
            )
        
        # Get questions (cached)
        questions_data = await AssessmentQueryHelper.get_assessment_questions(db, assessment["id"])
        
        # Convert assessment integer ID to UUID for response
        assessment_uuid = await IDConverter.int_to_uuid(db, "assessment", assessment["id"]) if assessment.get("id") else None
        
        questions = []
        for q in questions_data:
            # Convert question integer ID to UUID for response
            question_uuid = await IDConverter.int_to_uuid(db, "question", q["id"]) if q.get("id") else None
            questions.append({
                "question_id": question_uuid or str(q["id"]),  # Use UUID if available
                "question_text": q["question_text"],
                "question_type": q["question_type"],
                "points": q.get("points", 1.0),
                "options": json.loads(q.get("options", "[]")) if isinstance(q.get("options"), str) else q.get("options", []),
                "explanation": q.get("explanation"),
            })
        
        response = {
            "assessment_id": assessment_uuid or str(assessment["id"]),  # Use UUID if available
            "title": assessment["title"],
            "description": assessment.get("description"),
            "num_questions": len(questions),
            "time_limit": assessment.get("time_limit", 30),
            "max_attempts": assessment.get("max_attempts", 3),
            "passing_score": assessment.get("passing_score", 60.0),
            "is_default": True,
            "questions": questions,
        }
        
        # Cache the response for 5 minutes
        cache.set("assessments", response, cache_key, ttl=300)
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching quiz: {str(e)}",
        )


@router.post("/lectures/{lecture_id}/generate-quiz")
async def generate_quiz(
    lecture_id: str,
    request: QuizGenerationRequest,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Generate a NEW temporary quiz from lecture content using AI.
    
    This creates a fresh quiz that is NOT saved to the database.
    Use this for practice or to get different questions.
    
    Note: Use GET /lectures/{lecture_id}/quiz to get the saved/default quiz instead.
    """
    user, student = user_student
    
    try:
        logger.info(f"Generating temporary quiz for lecture {lecture_id}, student {student.id}")
        
        # Verify lecture access
        # Convert UUID to integer ID for database query
        lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id) if IDConverter.is_uuid(lecture_id) else lecture_id
        if not lecture_int_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )
        
        lecture_result = (
            db.get_admin_client().table("lecture")
            .select("*, course!inner(id, name), teacher!inner(id)")
            .eq("id", lecture_int_id)
            .in_("status", ["PUBLISHED", "DELIVERED"])
            .execute()
        )
        
        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )
        
        lecture = lecture_result.data[0]
        course_id = lecture["course"]["id"]
        teacher_id = lecture["teacher"]["id"]
        # Ensure course_id is an integer (from database result, should already be int after migration)
        course_int_id = course_id if isinstance(course_id, int) else course_id
        
        # Verify enrollment - convert student_id to integer
        student_int_id = student.id if isinstance(student.id, int) else await IDConverter.uuid_to_int(db, "student", str(student.id))
        if not student_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get student ID",
            )
        
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", student_int_id)  # Use integer ID
            .eq("course_id", course_int_id)  # Use integer ID
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Generate quiz using AI (temporary, not saved)
        quiz_service = QuizService(db)
        quiz_data = await quiz_service.generate_quiz_from_lecture(
            lecture_id=lecture_id,
            lecture_content=lecture["content"],
            num_questions=request.num_questions,
            question_types=request.question_types,
            difficulty=request.difficulty,
            focus_areas=request.focus_areas,
        )
        
        # Return quiz without saving to database (temporary)
        logger.info(f"Generated temporary quiz with {len(quiz_data['questions'])} questions")
        
        return {
            "assessment_id": None,  # No ID since it's not saved
            "title": f"Practice Quiz: {lecture['title']}",
            "description": "Temporary quiz for practice (not saved)",
            "num_questions": len(quiz_data["questions"]),
            "time_limit": 30,
            "is_temporary": True,
            "questions": quiz_data["questions"],
            "note": "This is a practice quiz. Results will not be recorded."
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating quiz: {str(e)}",
        )


@router.post("/assessments/{assessment_id}/submit")
async def submit_quiz(
    assessment_id: str,
    submission: dict,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Submit quiz answers and get results.
    
    The results are automatically added to the chat history so the chatbot
    can focus on topics the student struggled with.
    """
    user, student = user_student
    
    try:
        logger.info(f"Submitting quiz {assessment_id} for student {student.id}")
        
        # Get assessment and questions
        # Convert UUID to integer ID for database query
        assessment_int_id = await IDConverter.uuid_to_int(db, "assessment", assessment_id) if IDConverter.is_uuid(assessment_id) else assessment_id
        if not assessment_int_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found",
            )
        
        assessment_result = (
            db.get_admin_client().table("assessment")
            .select("*, lecture!inner(id, course_id)")
            .eq("id", assessment_int_id)
            .execute()
        )
        
        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found",
            )
        
        assessment = assessment_result.data[0]
        lecture_id = assessment["lecture"]["id"]
        course_id = assessment["lecture"]["course_id"]
        # Ensure course_id is an integer (from database result, should already be int after migration)
        course_int_id = course_id if isinstance(course_id, int) else course_id
        
        # Verify enrollment - convert student_id to integer
        student_int_id = student.id if isinstance(student.id, int) else await IDConverter.uuid_to_int(db, "student", str(student.id))
        if not student_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get student ID",
            )
        
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", student_int_id)  # Use integer ID
            .eq("course_id", course_int_id)  # Use integer ID
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Get questions
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_int_id)
            .order("order_index")
            .execute()
        )
        
        questions = questions_result.data
        
        # Convert question integer IDs to UUIDs for matching with frontend answers
        # Frontend sends UUIDs as keys in student_answers
        questions_with_uuids = []
        for q in questions:
            question_uuid = await IDConverter.int_to_uuid(db, "question", q["id"]) if q.get("id") else None
            q_with_uuid = q.copy()
            # Store UUID for matching with student_answers keys
            q_with_uuid["uuid"] = question_uuid or str(q["id"])
            questions_with_uuids.append(q_with_uuid)
        
        # Grade the submission
        quiz_service = QuizService(db)
        grading_result = quiz_service.grade_submission(
            questions=questions_with_uuids,
            student_answers=submission.get("answers", {}),
        )
        
        # Create submission record with integer IDs
        submission_uuid = str(uuid4())
        student_int_id = student.id if isinstance(student.id, int) else await IDConverter.uuid_to_int(db, "student", str(student.id))
        if not student_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get student ID",
            )
        
        submission_data = {
            "uuid": submission_uuid,  # Store UUID for external use
            "assessment_id": assessment_int_id,  # Integer FK
            "student_id": student_int_id,  # Integer FK
            "answers": json.dumps(submission.get("answers", {})),
            "score": grading_result["score"],
            "max_score": grading_result["max_score"],
            "attempt_number": 1,  # TODO: Track actual attempt number
            "time_taken": submission.get("time_taken"),
            "is_submitted": True,
            "is_graded": True,
            "started_at": submission.get("started_at", datetime.utcnow().isoformat()),
            "submitted_at": datetime.utcnow().isoformat(),
            "graded_at": datetime.utcnow().isoformat(),
        }
        submission_result = db.admin_client.table("assessment_submission").insert(submission_data).execute()
        # Get the UUID from the inserted record (or use the one we generated)
        submission_id = submission_uuid
        if submission_result.data and len(submission_result.data) > 0:
            submission_id = submission_result.data[0].get("uuid") or submission_uuid
        
        # Calculate percentage and weak areas
        percentage = (grading_result["score"] / grading_result["max_score"]) * 100 if grading_result["max_score"] > 0 else 0
        weak_areas = [item["topic"] for item in grading_result.get("weak_areas", [])]
        
        logger.info(f"Graded quiz {assessment_id} - Score: {grading_result['score']}/{grading_result['max_score']}")
        
        return {
            "submission_id": submission_id,
            "score": grading_result["score"],
            "max_score": grading_result["max_score"],
            "percentage": percentage,
            "correct_count": grading_result["correct_count"],
            "total_questions": grading_result["total_questions"],
            "weak_areas": weak_areas,
            "question_results": grading_result.get("question_results", []),
            "passed": percentage >= assessment.get("passing_score", 60.0),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting quiz: {str(e)}",
        )


@router.get("/lectures/{lecture_id}/chat-history")
async def get_chat_history(
    lecture_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    hours: Optional[int] = Query(None, description="Get messages from last N hours (default: 24)"),
    since: Optional[str] = Query(None, description="Get messages since ISO timestamp (e.g., 2026-03-12T10:00:00Z)"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=200, description="Messages per page (default: 50, max: 200)"),
    db=Depends(get_db),
):
    """
    Get chat history for a lecture conversation with pagination.
    
    Returns messages from all conversations for the authenticated user and lecture.
    Scoped by user+lecture, not session ID, so it persists across re-logins.
    Messages are ordered chronologically (oldest first within a page).
    
    Query Parameters:
    - hours: Get messages from last N hours (default: 24)
    - since: Get messages since ISO timestamp (overrides hours if provided)
    - page: Page number (default: 1). Page 1 = most recent messages
    - page_size: Messages per page (default: 50, max: 200)
    
    Returns paginated messages with: id (uuid), role, content, created_at, conversation_id
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching chat history for lecture {lecture_id}, student {student.id}")
        
        # Get integer user_id for query
        user_int_id = user.id if isinstance(user.id, int) else await IDConverter.uuid_to_int(db, "users", str(user.id))
        if not user_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get user ID",
            )
        
        # Convert UUID to integer ID if needed
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )
        
        # Calculate time filter
        if since:
            # Parse ISO timestamp
            try:
                since_datetime = datetime.fromisoformat(since.replace('Z', '+00:00'))
                if since_datetime.tzinfo is None:
                    since_datetime = since_datetime.replace(tzinfo=datetime.now().astimezone().tzinfo)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid 'since' timestamp format. Use ISO format (e.g., 2026-03-12T10:00:00Z)",
                )
            cutoff_time = since_datetime
        else:
            # Default to 24 hours if not specified
            hours_back = hours if hours is not None else 24
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        # Get all conversations for this user+lecture
        conversations_result = (
            db.admin_client.table("ai_conversation")
            .select("id, uuid, session_id, created_at")
            .eq("user_id", user_int_id)
            .eq("lecture_id", lecture_int_id)
            .gte("created_at", cutoff_time.isoformat())
            .execute()
        )
        
        empty_response = {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 1,
            "has_next": False,
            "has_previous": False,
        }
        
        if not conversations_result.data:
            return empty_response
        
        # Get all conversation IDs
        conversation_ids = [conv["id"] for conv in conversations_result.data]
        
        # Get all messages from these conversations
        messages_result = (
            db.admin_client.table("chat_message")
            .select("id, uuid, conversation_id, role, content, created_at")
            .in_("conversation_id", conversation_ids)
            .gte("created_at", cutoff_time.isoformat())
            .order("created_at", desc=True)  # Newest first for pagination
            .execute()
        )
        
        if not messages_result.data:
            return empty_response
        
        all_messages_data = messages_result.data
        
        # Calculate pagination
        total = len(all_messages_data)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = all_messages_data[start:end]
        
        # Reverse page_data so messages within a page are chronological (oldest first)
        page_data.reverse()
        
        # Build response with UUIDs
        messages = []
        for msg in page_data:
            # Convert conversation_id to UUID
            conv_id_int = msg["conversation_id"]
            conv_record = next((c for c in conversations_result.data if c["id"] == conv_id_int), None)
            conversation_uuid = conv_record.get("uuid") if conv_record else None
            if not conversation_uuid and conv_record:
                conversation_uuid = await IDConverter.int_to_uuid(db, "ai_conversation", conv_id_int) if isinstance(conv_id_int, int) else conv_id_int
            
            # Convert message id to UUID
            message_uuid = msg.get("uuid")
            if not message_uuid:
                message_uuid = await IDConverter.int_to_uuid(db, "chat_message", msg["id"]) if isinstance(msg["id"], int) else msg["id"]
            
            messages.append({
                "id": message_uuid,
                "role": msg["role"],
                "content": msg["content"],
                "created_at": msg["created_at"],
                "conversation_id": conversation_uuid or str(conv_id_int),
            })
        
        return {
            "items": messages,
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
        logger.error(f"Error fetching chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching chat history",
        )


# ==================== Test Quiz Routes ====================


@router.get("/courses/{course_id}/test-quizzes")
async def get_test_quizzes(
    course_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get all published test quizzes for a course.
    
    Shows test quizzes with deadlines that the student can attempt.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching test quizzes for course {course_id}, student {student.id}")
        
        # Convert UUID to integer ID if needed
        course_int_id = course_id
        if IDConverter.is_uuid(course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )
        
        # Verify enrollment - convert student_id to integer
        student_int_id = student.id if isinstance(student.id, int) else await IDConverter.uuid_to_int(db, "student", str(student.id))
        if not student_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get student ID",
            )
        
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", student_int_id)  # Use integer ID
            .eq("course_id", course_int_id)  # Use integer ID
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Get published test quizzes
        assessments_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(id, title)")
            .eq("course_id", course_int_id)
            .eq("quiz_mode", "TEST")
            .eq("is_published", True)
            .order("due_date", desc=False)
            .execute()
        )
        
        # Get student's submissions for these quizzes
        assessment_ids = [a["id"] for a in (assessments_result.data or [])]
        
        submissions_by_assessment = {}
        if assessment_ids:
            submissions_result = (
                db.admin_client.table("assessment_submission")
                .select("assessment_id, score, max_score, is_submitted")
                .eq("student_id", str(student.id))
                .in_("assessment_id", assessment_ids)
                .execute()
            )
            
            for sub in (submissions_result.data or []):
                aid = sub["assessment_id"]
                if aid not in submissions_by_assessment:
                    submissions_by_assessment[aid] = []
                submissions_by_assessment[aid].append(sub)
        
        # Batch get question counts for all assessments
        question_counts = {}
        if assessment_ids:
            questions_result = (
                db.admin_client.table("question")
                .select("assessment_id")
                .in_("assessment_id", assessment_ids)
                .execute()
            )
            for q in (questions_result.data or []):
                aid = q["assessment_id"]
                question_counts[aid] = question_counts.get(aid, 0) + 1
        
        quizzes = []
        for a in (assessments_result.data or []):
            # Check if overdue
            due_date = a.get("due_date")
            is_overdue = False
            if due_date:
                try:
                    due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    is_overdue = datetime.utcnow() > due_dt.replace(tzinfo=None)
                except:
                    pass
            
            # Calculate student's attempts and best score
            my_submissions = submissions_by_assessment.get(a["id"], [])
            my_attempts = len([s for s in my_submissions if s.get("is_submitted")])
            my_best_score = None
            if my_submissions:
                scores = [s.get("score") for s in my_submissions if s.get("score") is not None]
                if scores:
                    my_best_score = max(scores)
            
            # Check if can attempt
            can_attempt = not is_overdue and my_attempts < a.get("max_attempts", 1)
            
            quizzes.append({
                "assessment_id": a["id"],
                "title": a["title"],
                "description": a.get("description"),
                "lecture_id": a["lecture"]["id"],
                "lecture_title": a["lecture"]["title"],
                "difficulty": a.get("difficulty", "MEDIUM"),
                "time_limit": a.get("time_limit"),
                "max_attempts": a.get("max_attempts", 1),
                "passing_score": a.get("passing_score", 60.0),
                "due_date": due_date,
                "is_overdue": is_overdue,
                "show_leaderboard": a.get("show_leaderboard", True),
                "questions_count": question_counts.get(a["id"], 0),
                "my_attempts": my_attempts,
                "my_best_score": my_best_score,
                "can_attempt": can_attempt,
            })
        
        return {
            "course_id": course_id,
            "test_quizzes": quizzes,
            "total_count": len(quizzes),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching test quizzes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching test quizzes",
        )


@router.get("/test-quizzes/{assessment_id}")
async def get_test_quiz_details(
    assessment_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get details of a test quiz for attempting.
    
    Returns quiz questions (without correct answers) if the student can attempt it.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching test quiz {assessment_id} for student {student.id}")
        
        # Convert UUID to integer ID if needed
        assessment_int_id = assessment_id
        if IDConverter.is_uuid(assessment_id):
            assessment_int_id = await IDConverter.uuid_to_int(db, "assessment", assessment_id)
            if not assessment_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test quiz not found or not published",
                )
        
        # Get assessment
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(id, course_id)")
            .eq("id", assessment_int_id)
            .eq("quiz_mode", "TEST")
            .eq("is_published", True)
            .execute()
        )
        
        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test quiz not found or not published",
            )
        
        assessment = assessment_result.data[0]
        course_id = assessment["lecture"]["course_id"]
        
        # Verify enrollment
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", str(student.id))
            .eq("course_id", course_id)
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check if overdue
        due_date = assessment.get("due_date")
        is_overdue = False
        if due_date:
            try:
                due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                is_overdue = datetime.utcnow() > due_dt.replace(tzinfo=None)
            except:
                pass
        
        # Check attempts
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("id, is_submitted")
            .eq("assessment_id", assessment_id)
            .eq("student_id", str(student.id))
            .execute()
        )
        
        my_attempts = len([s for s in (submissions_result.data or []) if s.get("is_submitted")])
        max_attempts = assessment.get("max_attempts", 1)
        
        can_attempt = not is_overdue and my_attempts < max_attempts
        
        if not can_attempt:
            reason = "Quiz deadline has passed" if is_overdue else f"Maximum attempts ({max_attempts}) reached"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot attempt this quiz: {reason}",
            )
        
        # Get questions (without correct answers)
        questions_result = (
            db.admin_client.table("question")
            .select("id, question_text, question_type, points, order_index, options")
            .eq("assessment_id", assessment_int_id)
            .order("order_index")
            .execute()
        )
        
        questions = []
        for q in (questions_result.data or []):
            questions.append({
                "question_id": q["id"],
                "question_text": q["question_text"],
                "question_type": q.get("question_type", "MULTIPLE_CHOICE"),
                "points": q.get("points", 1.0),
                "options": json.loads(q.get("options", "[]")),
            })
        
        return {
            "assessment_id": assessment_id,
            "title": assessment["title"],
            "description": assessment.get("description"),
            "difficulty": assessment.get("difficulty", "MEDIUM"),
            "time_limit": assessment.get("time_limit"),
            "max_attempts": max_attempts,
            "passing_score": assessment.get("passing_score", 60.0),
            "due_date": due_date,
            "is_overdue": is_overdue,
            "my_attempts": my_attempts,
            "attempts_remaining": max_attempts - my_attempts,
            "questions_count": len(questions),
            "questions": questions,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching test quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching test quiz",
        )


@router.post("/test-quizzes/{assessment_id}/submit")
async def submit_test_quiz(
    assessment_id: str,
    submission: dict,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Submit answers for a test quiz.
    
    Validates deadline and attempt limits before accepting the submission.
    Returns grading results.
    """
    user, student = user_student
    
    try:
        logger.info(f"Submitting test quiz {assessment_id} for student {student.id}")
        
        # Convert UUID to integer ID if needed
        assessment_int_id = assessment_id
        if IDConverter.is_uuid(assessment_id):
            assessment_int_id = await IDConverter.uuid_to_int(db, "assessment", assessment_id)
            if not assessment_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test quiz not found",
                )
        
        # Get assessment
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(id, course_id)")
            .eq("id", assessment_int_id)
            .eq("quiz_mode", "TEST")
            .eq("is_published", True)
            .execute()
        )
        
        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test quiz not found",
            )
        
        assessment = assessment_result.data[0]
        course_id = assessment["lecture"]["course_id"]
        lecture_id = assessment["lecture"]["id"]
        
        # Verify enrollment
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", str(student.id))
            .eq("course_id", course_id)
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check deadline
        due_date = assessment.get("due_date")
        if due_date:
            try:
                due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                if datetime.utcnow() > due_dt.replace(tzinfo=None):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Quiz deadline has passed",
                    )
            except HTTPException:
                raise
            except:
                pass
        
        # Check attempts
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("id, is_submitted")
            .eq("assessment_id", assessment_int_id)
            .eq("student_id", str(student.id))
            .execute()
        )
        
        my_attempts = len([s for s in (submissions_result.data or []) if s.get("is_submitted")])
        max_attempts = assessment.get("max_attempts", 1)
        
        if my_attempts >= max_attempts:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Maximum attempts ({max_attempts}) reached",
            )
        
        # Get questions
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_int_id)
            .order("order_index")
            .execute()
        )
        
        questions = questions_result.data
        
        # Convert question integer IDs to UUIDs for matching with frontend answers
        # Frontend sends UUIDs as keys in student_answers
        questions_with_uuids = []
        for q in questions:
            question_uuid = await IDConverter.int_to_uuid(db, "question", q["id"]) if q.get("id") else None
            q_with_uuid = q.copy()
            # Store UUID for matching with student_answers keys
            q_with_uuid["uuid"] = question_uuid or str(q["id"])
            questions_with_uuids.append(q_with_uuid)
        
        # Grade the submission
        quiz_service = QuizService(db)
        grading_result = quiz_service.grade_submission(
            questions=questions_with_uuids,
            student_answers=submission.get("answers", {}),
        )
        
        # Create submission record with integer IDs
        submission_uuid = str(uuid4())
        student_int_id = student.id if isinstance(student.id, int) else await IDConverter.uuid_to_int(db, "student", str(student.id))
        if not student_int_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get student ID",
            )
        
        submission_data = {
            "uuid": submission_uuid,  # Store UUID for external use
            "assessment_id": assessment_int_id,  # Integer FK
            "student_id": student_int_id,  # Integer FK
            "answers": json.dumps(submission.get("answers", {})),
            "score": grading_result["score"],
            "max_score": grading_result["max_score"],
            "attempt_number": my_attempts + 1,
            "time_taken": submission.get("time_taken"),
            "is_submitted": True,
            "is_graded": True,
            "started_at": submission.get("started_at", datetime.utcnow().isoformat()),
            "submitted_at": datetime.utcnow().isoformat(),
            "graded_at": datetime.utcnow().isoformat(),
        }
        submission_result = db.admin_client.table("assessment_submission").insert(submission_data).execute()
        # Get the UUID from the inserted record (or use the one we generated)
        submission_id = submission_uuid
        if submission_result.data and len(submission_result.data) > 0:
            submission_id = submission_result.data[0].get("uuid") or submission_uuid
        
        percentage = (grading_result["score"] / grading_result["max_score"]) * 100 if grading_result["max_score"] > 0 else 0
        passed = percentage >= assessment.get("passing_score", 60.0)
        
        logger.info(f"Graded test quiz {assessment_id} - Score: {grading_result['score']}/{grading_result['max_score']}")
        
        # Send notifications to teacher
        try:
            notification_service = NotificationService(db)
            student_name = f"{user.first_name} {user.last_name}".strip() or "A student"
            
            # Get teacher's user_id from assessment
            teacher_result = (
                db.admin_client.table("teacher")
                .select("user_id")
                .eq("id", assessment.get("teacher_id"))
                .execute()
            )
            
            if teacher_result.data:
                teacher_user_id = teacher_result.data[0]["user_id"]
                
                # Notify teacher about quiz submission
                await notification_service.notify_quiz_submitted(
                    teacher_user_id=teacher_user_id,
                    student_name=student_name,
                    quiz_title=assessment.get("title", "Quiz"),
                    assessment_id=assessment_id,
                )
                
                # If score is below passing, send additional alert
                passing_score = assessment.get("passing_score", 60.0)
                if percentage < passing_score:
                    await notification_service.notify_low_quiz_score(
                        teacher_user_id=teacher_user_id,
                        student_name=student_name,
                        quiz_title=assessment.get("title", "Quiz"),
                        score_percentage=percentage,
                        assessment_id=assessment_id,
                    )
        except Exception as notify_error:
            logger.warning(f"Failed to send quiz submission notification: {notify_error}")
        
        return {
            "submission_id": submission_id,
            "score": grading_result["score"],
            "max_score": grading_result["max_score"],
            "percentage": percentage,
            "correct_count": grading_result["correct_count"],
            "total_questions": grading_result["total_questions"],
            "passed": passed,
            "attempt_number": my_attempts + 1,
            "attempts_remaining": max_attempts - (my_attempts + 1),
            "question_results": grading_result.get("question_results", []),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting test quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting quiz: {str(e)}",
        )


@router.get("/test-quizzes/{assessment_id}/leaderboard")
async def get_quiz_leaderboard(
    assessment_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get the leaderboard for a test quiz (student view).
    
    Shows only student names and ranks - NO SCORES to protect student confidence.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching leaderboard for quiz {assessment_id}, student {student.id}")
        
        # Convert UUID to integer ID if needed
        assessment_int_id = assessment_id
        if IDConverter.is_uuid(assessment_id):
            assessment_int_id = await IDConverter.uuid_to_int(db, "assessment", assessment_id)
            if not assessment_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assessment not found",
                )
        
        # Get assessment
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title, show_leaderboard, lecture!inner(course_id)")
            .eq("id", assessment_int_id)
            .eq("quiz_mode", "TEST")
            .eq("is_published", True)
            .execute()
        )
        
        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test quiz not found",
            )
        
        assessment = assessment_result.data[0]
        course_id = assessment["lecture"]["course_id"]
        
        # Verify enrollment
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", str(student.id))
            .eq("course_id", course_id)
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check if leaderboard is enabled
        if not assessment.get("show_leaderboard", True):
            return {
                "assessment_id": assessment_id,
                "assessment_title": assessment["title"],
                "leaderboard_enabled": False,
                "message": "Leaderboard is not available for this quiz",
                "leaderboard": [],
            }
        
        # Get submissions ordered by score
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("student_id, score, max_score")
            .eq("assessment_id", assessment_id)
            .eq("is_submitted", True)
            .order("score", desc=True)
            .execute()
        )
        
        # Get best score per student
        best_by_student = {}
        for sub in (submissions_result.data or []):
            sid = sub["student_id"]
            if sid not in best_by_student or (sub.get("score") or 0) > (best_by_student[sid].get("score") or 0):
                best_by_student[sid] = sub
        
        if not best_by_student:
            return {
                "assessment_id": assessment_id,
                "assessment_title": assessment["title"],
                "leaderboard_enabled": True,
                "total_participants": 0,
                "my_rank": None,
                "leaderboard": [],
            }
        
        # Get student details
        student_ids = list(best_by_student.keys())
        students_result = (
            db.admin_client.table("student")
            .select("id, user_id")
            .in_("id", student_ids)
            .execute()
        )
        student_user_map = {s["id"]: s["user_id"] for s in (students_result.data or [])}
        
        user_ids = list(student_user_map.values())
        users_result = (
            db.admin_client.table("users")
            .select("id, first_name, last_name")
            .in_("id", user_ids)
            .execute()
        )
        user_map = {u["id"]: u for u in (users_result.data or [])}
        
        # Build leaderboard - NAMES AND RANKS ONLY (no scores for students)
        sorted_entries = sorted(
            best_by_student.items(),
            key=lambda x: (x[1].get("score") or 0),
            reverse=True
        )
        
        leaderboard = []
        my_rank = None
        
        for rank, (sid, sub) in enumerate(sorted_entries, 1):
            user_id = student_user_map.get(sid)
            u = user_map.get(user_id, {})
            
            # Check if this is the current student
            if sid == str(student.id):
                my_rank = rank
            
            leaderboard.append({
                "rank": rank,
                "student_name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "Anonymous",
                # NO SCORES shown to students
            })
        
        return {
            "assessment_id": assessment_id,
            "assessment_title": assessment["title"],
            "leaderboard_enabled": True,
            "total_participants": len(leaderboard),
            "my_rank": my_rank,
            "leaderboard": leaderboard,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching leaderboard",
        )


# ==================== Result View Request Routes ====================


class ResultViewRequestCreate(BaseModel):
    """Request body for creating a result view request."""
    message: Optional[str] = None  # Optional message to teacher


@router.post("/test-quizzes/{assessment_id}/request-results")
async def request_quiz_results(
    assessment_id: str,
    request: Optional[ResultViewRequestCreate] = None,
    user_student: Annotated[tuple[User, Student], Depends(require_student)] = None,
    db=Depends(get_db),
):
    """
    Request to view results of a graded quiz.
    
    Students can request access to see their detailed results for a graded quiz.
    The teacher must approve the request before the student can view results.
    
    Returns the request status.
    """
    user, student = user_student
    
    try:
        logger.info(f"Student {student.id} requesting results for assessment {assessment_id}")
        
        # Convert UUID to integer ID if needed
        assessment_int_id = assessment_id
        if IDConverter.is_uuid(assessment_id):
            assessment_int_id = await IDConverter.uuid_to_int(db, "assessment", assessment_id)
            if not assessment_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Graded quiz not found",
                )
        
        # Get the assessment and verify it's a graded quiz (TEST mode)
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title, teacher_id, course_id, quiz_mode, lecture!inner(course_id)")
            .eq("id", assessment_int_id)
            .eq("quiz_mode", "TEST")
            .eq("is_published", True)
            .execute()
        )
        
        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Graded quiz not found",
            )
        
        assessment = assessment_result.data[0]
        course_id = assessment["lecture"]["course_id"]
        teacher_id = assessment["teacher_id"]
        # Ensure course_id is an integer (from database result, should already be int after migration)
        course_int_id = course_id if isinstance(course_id, int) else course_id
        
        # Convert student.id to integer if needed
        student_int_id = student.id
        if IDConverter.is_uuid(student.id):
            student_int_id = await IDConverter.uuid_to_int(db, "student", student.id)
            if not student_int_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Student ID conversion failed",
                )
        
        # Verify student is enrolled in the course using integer IDs
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id")
            .eq("student_id", student_int_id)  # Use integer ID
            .eq("course_id", course_int_id)
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Verify student has submitted the quiz using integer IDs
        submission_result = (
            db.admin_client.table("assessment_submission")
            .select("id")
            .eq("assessment_id", assessment_int_id)  # Use integer ID
            .eq("student_id", student_int_id)  # Use integer ID
            .eq("is_submitted", True)
            .execute()
        )
        
        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must submit the quiz before requesting results",
            )
        
        # Check if request already exists using integer IDs
        existing_request = (
            db.admin_client.table("result_view_request")
            .select("id, status, requested_at, responded_at, response_message")
            .eq("assessment_id", assessment_int_id)  # Use integer ID
            .eq("student_id", student_int_id)  # Use integer ID
            .execute()
        )
        
        if existing_request.data:
            req = existing_request.data[0]
            return {
                "message": f"Request already exists with status: {req['status']}",
                "request_id": req["id"],
                "status": req["status"],
                "requested_at": req["requested_at"],
                "responded_at": req.get("responded_at"),
                "response_message": req.get("response_message"),
            }
        
        # Ensure teacher_id is an integer
        teacher_int_id = teacher_id
        if IDConverter.is_uuid(teacher_id):
            teacher_int_id = await IDConverter.uuid_to_int(db, "teacher", teacher_id)
            if not teacher_int_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Teacher ID conversion failed",
                )
        
        # Create new request using integer IDs
        # Don't set 'id' - let database auto-generate integer PK
        # Generate UUID for external API compatibility
        request_uuid = str(uuid4())
        request_data = {
            "uuid": request_uuid,  # UUID for external APIs
            "assessment_id": assessment_int_id,  # Use integer ID
            "student_id": student_int_id,  # Use integer ID
            "teacher_id": teacher_int_id,  # Use integer ID
            "status": "PENDING",
            "request_message": request.message if request else None,
            "requested_at": datetime.utcnow().isoformat(),
        }
        
        result = db.admin_client.table("result_view_request").insert(request_data).execute()
        
        # Get the created request ID (integer) and convert to UUID for response
        if result.data:
            request_id_int = result.data[0].get("id")
            request_id = await IDConverter.int_to_uuid(db, "result_view_request", request_id_int) if request_id_int else None
            if not request_id:
                request_id = result.data[0].get("uuid") or request_uuid
        else:
            request_id = request_uuid
        
        logger.info(f"Created result view request {request_id} for student {student.id}")
        
        # Notify teacher about the result request
        try:
            notification_service = NotificationService(db)
            student_name = f"{user.first_name} {user.last_name}".strip() or "A student"
            
            # Get teacher's user_id using integer teacher_id
            teacher_result = (
                db.admin_client.table("teacher")
                .select("user_id")
                .eq("id", teacher_int_id)  # Use integer ID
                .execute()
            )
            
            if teacher_result.data:
                teacher_user_id = teacher_result.data[0]["user_id"]
                    # Convert teacher_user_id to UUID string if it's an integer
                # The notification service will handle the conversion back to integer
                if teacher_user_id:
                    # If it's an integer, convert to UUID for the API
                    if isinstance(teacher_user_id, int):
                        teacher_user_id_uuid = await IDConverter.int_to_uuid(db, "users", teacher_user_id)
                        if not teacher_user_id_uuid:
                            teacher_user_id_uuid = str(teacher_user_id)  # Fallback
                    else:
                        teacher_user_id_uuid = str(teacher_user_id)
                    
                    await notification_service.notify_result_request(
                        teacher_user_id=teacher_user_id_uuid,
                        student_name=student_name,
                        quiz_title=assessment["title"],
                        request_id=request_id,  # Already a UUID string
                    )
        except Exception as notify_error:
            logger.warning(f"Failed to send result request notification: {notify_error}")
        
        return {
            "message": "Result view request submitted successfully. Waiting for teacher approval.",
            "request_id": request_id,
            "assessment_id": assessment_id,
            "assessment_title": assessment["title"],
            "status": "PENDING",
            "requested_at": request_data["requested_at"],
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating result view request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error submitting result view request",
        )


@router.get("/my-result-requests")
async def get_my_result_requests(
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    status_filter: Optional[str] = None,
    db=Depends(get_db),
):
    """
    Get all result view requests submitted by the student.
    
    Optionally filter by status: PENDING, APPROVED, REJECTED
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching result requests for student {student.id}")
        
        query = (
            db.admin_client.table("result_view_request")
            .select("*, assessment!inner(id, title, quiz_mode, lecture!inner(title))")
            .eq("student_id", str(student.id))
            .order("requested_at", desc=True)
        )
        
        if status_filter and status_filter.upper() in ["PENDING", "APPROVED", "REJECTED"]:
            query = query.eq("status", status_filter.upper())
        
        result = query.execute()
        
        requests = []
        for req in (result.data or []):
            requests.append({
                "request_id": req["id"],
                "assessment_id": req["assessment_id"],
                "assessment_title": req["assessment"]["title"],
                "lecture_title": req["assessment"]["lecture"]["title"],
                "status": req["status"],
                "request_message": req.get("request_message"),
                "response_message": req.get("response_message"),
                "requested_at": req["requested_at"],
                "responded_at": req.get("responded_at"),
            })
        
        return {
            "total_count": len(requests),
            "requests": requests,
        }
    
    except Exception as e:
        logger.error(f"Error fetching result requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching result requests",
        )


@router.get("/test-quizzes/{assessment_id}/my-results")
async def get_my_quiz_results(
    assessment_id: str,
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get detailed results for a graded quiz (if approved by teacher).
    
    Returns full question-by-question breakdown with:
    - Your answers
    - Correct answers
    - Explanations
    - Points earned per question
    
    Only accessible if the teacher has approved your result view request.
    """
    user, student = user_student
    
    try:
        logger.info(f"Student {student.id} viewing results for assessment {assessment_id}")
        
        # Check if student has an approved request
        request_result = (
            db.admin_client.table("result_view_request")
            .select("id, status")
            .eq("assessment_id", assessment_id)
            .eq("student_id", str(student.id))
            .execute()
        )
        
        if not request_result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must request access to view results first. Use POST /test-quizzes/{assessment_id}/request-results",
            )
        
        req = request_result.data[0]
        
        if req["status"] == "PENDING":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your request is pending teacher approval",
            )
        
        if req["status"] == "REJECTED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your request to view results was rejected by the teacher",
            )
        
        # Request is APPROVED - get the full results
        
        # Convert UUID to integer ID if needed
        assessment_int_id = assessment_id
        if IDConverter.is_uuid(assessment_id):
            assessment_int_id = await IDConverter.uuid_to_int(db, "assessment", assessment_id)
            if not assessment_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assessment not found",
                )
        
        # Get assessment details
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title, passing_score, lecture!inner(id, title, course_id)")
            .eq("id", assessment_int_id)
            .execute()
        )
        
        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found",
            )
        
        assessment = assessment_result.data[0]
        
        # Get student's submission(s) - get the best one
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("*")
            .eq("assessment_id", assessment_id)
            .eq("student_id", str(student.id))
            .eq("is_submitted", True)
            .order("score", desc=True)
            .execute()
        )
        
        if not submissions_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No submission found",
            )
        
        best_submission = submissions_result.data[0]
        student_answers = json.loads(best_submission.get("answers", "{}"))
        
        # Get all questions with correct answers
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_id)
            .order("order_index")
            .execute()
        )
        
        # Build detailed results
        question_results = []
        for q in (questions_result.data or []):
            question_id = q["id"]
            # Match by int id or string id (JSON keys are always strings)
            student_answer = student_answers.get(question_id) or student_answers.get(str(question_id))
            correct_answer = q.get("correct_answer")
            is_correct = student_answer == correct_answer if student_answer else False
            
            question_results.append({
                "question_id": question_id,
                "question_text": q["question_text"],
                "question_type": q.get("question_type", "MULTIPLE_CHOICE"),
                "options": json.loads(q.get("options", "[]")),
                "your_answer": student_answer,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
                "points_possible": q.get("points", 1.0),
                "points_earned": q.get("points", 1.0) if is_correct else 0,
                "explanation": q.get("explanation"),
            })
        
        # Calculate statistics
        total_correct = sum(1 for q in question_results if q["is_correct"])
        total_questions = len(question_results)
        percentage = (best_submission["score"] / best_submission["max_score"] * 100) if best_submission.get("max_score") else 0
        passed = percentage >= assessment.get("passing_score", 60.0)
        
        return {
            "assessment_id": assessment_id,
            "assessment_title": assessment["title"],
            "lecture_title": assessment["lecture"]["title"],
            "submission_id": best_submission["id"],
            "score": best_submission["score"],
            "max_score": best_submission["max_score"],
            "percentage": round(percentage, 2),
            "passing_score": assessment.get("passing_score", 60.0),
            "passed": passed,
            "correct_count": total_correct,
            "total_questions": total_questions,
            "attempt_number": best_submission.get("attempt_number", 1),
            "submitted_at": best_submission.get("submitted_at"),
            "time_taken": best_submission.get("time_taken"),
            "question_results": question_results,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quiz results: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching quiz results",
        )


# ==================== ALL ASSESSMENTS ENDPOINT ====================


@router.get("/assessments/all")
async def get_all_student_assessments(
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get ALL available quizzes across ALL enrolled courses for a student.
    
    Returns quizzes from all published lectures in all courses the student is enrolled in.
    Includes submission history and completion status.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching all assessments for student {student.id}")
        
        # Get all active enrollments
        enrollments_result = (
            db.admin_client.table("enrollment")
            .select("course_id")
            .eq("student_id", str(student.id))
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollments_result.data:
            return {
                "student_id": str(student.id),
                "total_quizzes": 0,
                "completed_quizzes": 0,
                "pending_quizzes": 0,
                "quizzes": [],
                "by_course": {},
            }
        
        course_ids = [e["course_id"] for e in enrollments_result.data]
        
        # Get all courses info
        courses_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .in_("id", course_ids)
            .execute()
        )
        course_map = {c["id"]: c for c in (courses_result.data or [])}
        
        # Get all published lectures for these courses
        lectures_result = (
            db.admin_client.table("lecture")
            .select("id, title, course_id, topic, lecture_number")
            .in_("course_id", course_ids)
            .in_("status", ["PUBLISHED", "DELIVERED"])
            .execute()
        )
        
        if not lectures_result.data:
            return {
                "student_id": str(student.id),
                "total_quizzes": 0,
                "completed_quizzes": 0,
                "pending_quizzes": 0,
                "quizzes": [],
                "by_course": {},
            }
        
        lecture_ids = [l["id"] for l in lectures_result.data]
        lecture_map = {l["id"]: l for l in lectures_result.data}
        
        # Get all GRADED TEST assessments (is_default=False means graded test, not practice quiz)
        assessments_result = (
            db.admin_client.table("assessment")
            .select("id, lecture_id, title, description, time_limit, passing_score, created_at, show_leaderboard, due_date, max_attempts")
            .in_("lecture_id", lecture_ids)
            .eq("is_default", False)
            .execute()
        )
        
        if not assessments_result.data:
            return {
                "student_id": str(student.id),
                "total_quizzes": 0,
                "completed_quizzes": 0,
                "pending_quizzes": 0,
                "quizzes": [],
                "by_course": {},
            }
        
        assessment_ids = [a["id"] for a in assessments_result.data]
        
        # Get question counts for each assessment
        questions_result = (
            db.admin_client.table("question")
            .select("assessment_id")
            .in_("assessment_id", assessment_ids)
            .execute()
        )
        question_counts = {}
        for q in (questions_result.data or []):
            aid = q["assessment_id"]
            question_counts[aid] = question_counts.get(aid, 0) + 1
        
        # Get all submissions by this student
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("assessment_id, score, max_score, submitted_at, attempt_number")
            .eq("student_id", str(student.id))
            .in_("assessment_id", assessment_ids)
            .order("submitted_at", desc=True)
            .execute()
        )
        
        # Group submissions by assessment (get best score)
        submissions_by_assessment = {}
        for sub in (submissions_result.data or []):
            aid = sub["assessment_id"]
            if aid not in submissions_by_assessment:
                submissions_by_assessment[aid] = sub
            else:
                # Keep the one with higher score
                existing = submissions_by_assessment[aid]
                if sub["score"] > existing["score"]:
                    submissions_by_assessment[aid] = sub
        
        # Build quizzes list
        quizzes = []
        by_course = {}
        completed_count = 0
        
        for assessment in assessments_result.data:
            lecture = lecture_map.get(assessment["lecture_id"], {})
            course = course_map.get(lecture.get("course_id"), {})
            submission = submissions_by_assessment.get(assessment["id"])
            
            is_completed = submission is not None
            if is_completed:
                completed_count += 1
            
            # Calculate is_overdue based on due_date
            due_date = assessment.get("due_date")
            is_overdue = False
            if due_date:
                try:
                    due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    is_overdue = datetime.utcnow() > due_dt.replace(tzinfo=None)
                except:
                    pass
            
            quiz_info = {
                "assessment_id": assessment["id"],
                "title": assessment["title"],
                "description": assessment.get("description"),
                "lecture_id": assessment["lecture_id"],
                "lecture_title": lecture.get("title"),
                "lecture_topic": lecture.get("topic"),
                "lecture_number": lecture.get("lecture_number"),
                "course_id": lecture.get("course_id"),
                "course_name": course.get("name"),
                "course_code": course.get("code"),
                "questions_count": question_counts.get(assessment["id"], 0),
                "time_limit": assessment.get("time_limit", 30),
                "passing_score": assessment.get("passing_score", 60.0),
                "created_at": assessment.get("created_at"),
                "is_completed": is_completed,
                "best_score": submission["score"] if submission else None,
                "max_score": submission["max_score"] if submission else None,
                "best_percentage": round((submission["score"] / submission["max_score"]) * 100, 1) if submission and submission["max_score"] else None,
                "passed": (submission["score"] / submission["max_score"] * 100) >= assessment.get("passing_score", 60.0) if submission and submission["max_score"] else None,
                "last_attempt_at": submission["submitted_at"] if submission else None,
                "attempts": submission["attempt_number"] if submission else 0,
                # New fields for leaderboard and due dates
                "show_leaderboard": assessment.get("show_leaderboard", False),
                "due_date": due_date,
                "is_overdue": is_overdue,
                "max_attempts": assessment.get("max_attempts", 1),
            }
            quizzes.append(quiz_info)
            
            # Group by course
            course_id = lecture.get("course_id")
            if course_id:
                if course_id not in by_course:
                    by_course[course_id] = {
                        "course_name": course.get("name"),
                        "course_code": course.get("code"),
                        "quizzes": [],
                    }
                by_course[course_id]["quizzes"].append(quiz_info)
        
        # Sort quizzes by created_at descending
        quizzes.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
        return {
            "student_id": str(student.id),
            "total_quizzes": len(quizzes),
            "completed_quizzes": completed_count,
            "pending_quizzes": len(quizzes) - completed_count,
            "completion_rate": round((completed_count / len(quizzes)) * 100, 1) if quizzes else 0,
            "quizzes": quizzes,
            "by_course": by_course,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching all assessments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching assessments",
        )


# Include router in main application
from routes_config import student_router as main_student_router

main_student_router.include_router(router)

