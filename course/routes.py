# course/routes.py

from datetime import date, datetime
import random
import string
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from dependencies import require_teacher
from logger import logger
from models.user import User
from utils.db import get_db

router = APIRouter()


class CourseCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    code: str | None = Field(default=None, min_length=4, max_length=10)
    description: str | None = None
    curriculum_content: str | None = None
    semester_name: str | None = Field(
        default=None,
        description="Name of the initial semester (optional)",
        max_length=80,
    )
    semester_start_date: date | None = Field(
        default=None, description="Start date of the initial semester"
    )
    semester_end_date: date | None = Field(
        default=None, description="End date of the initial semester"
    )

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None):
        if value:
            value = value.strip().upper()
        return value or None

    @field_validator("semester_end_date")
    @classmethod
    def validate_semester_dates(cls, end_date: date | None, values):
        start_date = values.get("semester_start_date")
        if end_date and start_date and end_date < start_date:
            raise ValueError("Semester end date must be after the start date")
        return end_date


def _generate_course_code(db, length: int = 6) -> str:
    """Generate a unique alphanumeric course code."""
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):
        candidate = "".join(random.choices(alphabet, k=length))
        existing = db.get_records("course", {"code": candidate})
        if not existing:
            return candidate
    raise ValueError("Unable to generate unique course code. Please try again with a custom code.")


@router.get("/", response_model=list[dict])
async def get_teacher_courses(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Get all courses for the current teacher's university.

    This endpoint is only accessible to teachers and admins.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(
            f"Fetching courses for teacher {teacher.id}, university {teacher.university_id}"
        )

        # Get courses for this teacher's university
        courses = db.get_records(
            "course",
            filters={"university_id": teacher.university_id},
            skip=0,
            limit=1000,
        )

        logger.info(
            f"Found {len(courses)} courses for university {teacher.university_id}"
        )
        return courses

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching courses: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching courses",
        )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_course(
    request: CourseCreateRequest,
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """Create a new course for the teacher's university."""

    teacher = current_user.teacher_profile
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Teacher profile not found. Please complete your teacher profile before creating courses.",
        )

    try:
        code = request.code
        if code:
            if not code.isalnum():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Course code must contain only letters and numbers.",
                )

            if not (4 <= len(code) <= 10):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Course code must be between 4 and 10 characters.",
                )

            existing = db.get_records("course", {"code": code})
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Course code already exists. Please choose a different code.",
                )
        else:
            code = _generate_course_code(db)

        course_payload = {
            "name": request.name.strip(),
            "code": code,
            "description": request.description.strip() if request.description else None,
            "curriculum_content": request.curriculum_content,
            "university_id": teacher.university_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        course_result = (
            db.admin_client.table("course").insert(course_payload).execute()
        )

        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create course",
            )

        course_data = course_result.data[0]
        semester_data = None

        if request.semester_name:
            semester_payload = {
                "name": request.semester_name.strip(),
                "course_id": course_data["id"],
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            if request.semester_start_date:
                semester_payload["start_date"] = request.semester_start_date.isoformat()
            if request.semester_end_date:
                semester_payload["end_date"] = request.semester_end_date.isoformat()

            semester_result = (
                db.admin_client.table("semester").insert(semester_payload).execute()
            )

            if semester_result.data:
                semester_data = semester_result.data[0]

        logger.info(
            "Course created",
            extra={
                "course_id": course_data.get("id"),
                "teacher_id": teacher.id,
                "university_id": teacher.university_id,
            },
        )

        response = {
            "message": "Course created successfully",
            "course": course_data,
        }
        if semester_data:
            response["semester"] = semester_data

        return response

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        ) from ve
    except Exception as e:
        logger.error("Error creating course", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating course",
        ) from e


@router.get("/{course_id}/semesters", response_model=list[dict])
async def get_course_semesters(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    db=Depends(get_db),
):
    """
    Get all semesters for a specific course.

    This endpoint is only accessible to teachers and admins.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching semesters for course {course_id}")

        # Get semesters for this course
        semesters = db.get_records(
            "semester", filters={"course_id": course_id}, skip=0, limit=1000
        )

        logger.info(f"Found {len(semesters)} semesters for course {course_id}")
        return semesters

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching semesters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching semesters",
        )


@router.get("/{course_id}/code", response_model=dict)
async def get_course_code(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    db=Depends(get_db),
):
    """
    Get the enrollment code for a course.
    
    Teachers can share this code with students for enrollment.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )
        
        # Get course
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code, university_id")
            .eq("id", course_id)
            .eq("university_id", teacher.university_id)
            .execute()
        )
        
        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        
        course = course_result.data[0]
        
        # Get enrollment count
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("id", count="exact")
            .eq("course_id", course_id)
            .eq("is_active", True)
            .execute()
        )
        
        enrolled_count = enrollment_result.count or 0
        
        return {
            "course_id": course["id"],
            "course_name": course["name"],
            "course_code": course["code"],
            "enrolled_students": enrolled_count,
            "message": f"Share this code with students: {course['code']}",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting course code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching course code",
        )


@router.put("/{course_id}/code", response_model=dict)
async def update_course_code(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    request: dict,
    db=Depends(get_db),
):
    """
    Update the enrollment code for a course.
    
    Request body:
    {
        "new_code": "CS101"
    }
    
    Note: Changing the code will not affect already enrolled students.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )
        
        new_code = request.get("new_code", "").strip().upper()
        
        if not new_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New code is required",
            )
        
        # Validate code format (letters and numbers only, 4-10 chars)
        import re
        if not re.match(r'^[A-Z0-9]{4,10}$', new_code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Course code must be 4-10 characters, letters and numbers only",
            )
        
        # Get course
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .eq("id", course_id)
            .eq("university_id", teacher.university_id)
            .execute()
        )
        
        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        
        old_code = course_result.data[0]["code"]
        
        # Check if new code already exists
        existing = (
            db.admin_client.table("course")
            .select("id, name")
            .eq("code", new_code)
            .eq("university_id", teacher.university_id)
            .execute()
        )
        
        if existing.data and existing.data[0]["id"] != course_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Course code '{new_code}' is already used by another course: {existing.data[0]['name']}",
            )
        
        # Update the code
        db.admin_client.table("course").update({
            "code": new_code,
        }).eq("id", course_id).execute()
        
        logger.info(f"Updated course code: {old_code} -> {new_code}")
        
        return {
            "success": True,
            "old_code": old_code,
            "new_code": new_code,
            "message": f"Course code updated to: {new_code}",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating course code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating course code",
        )


@router.get("/{course_id}/enrollments", response_model=dict)
async def get_course_enrollments(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    db=Depends(get_db),
):
    """
    Get list of students enrolled in a course.
    
    Shows students who enrolled using the course code.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )
        
        # Verify course belongs to teacher's university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .eq("id", course_id)
            .eq("university_id", teacher.university_id)
            .execute()
        )
        
        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        
        course = course_result.data[0]
        
        # Get enrollments with student info
        enrollments_result = (
            db.admin_client.table("enrollment")
            .select("*, student!inner(*, users!inner(first_name, last_name, email))")
            .eq("course_id", course_id)
            .eq("is_active", True)
            .order("enrolled_at", desc=True)
            .execute()
        )
        
        students = []
        for enrollment in enrollments_result.data or []:
            student_data = enrollment.get("student", {})
            user_data = student_data.get("users", {})
            
            students.append({
                "enrollment_id": enrollment["id"],
                "student_id": student_data.get("id"),
                "name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                "email": user_data.get("email"),
                "enrolled_at": enrollment["enrolled_at"],
            })
        
        return {
            "course_name": course["name"],
            "course_code": course["code"],
            "total_students": len(students),
            "students": students,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting course enrollments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching enrollments",
        )


# Import and include the router in the course_router from routes_config
from routes_config import course_router as main_course_router

main_course_router.include_router(router)
