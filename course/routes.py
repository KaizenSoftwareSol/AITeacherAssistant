# course/routes.py

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import require_teacher
from logger import logger
from models.course import Course, Semester
from models.user import User
from utils.db import get_db

router = APIRouter()


@router.get("/", response_model=List[dict])
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


@router.get("/{course_id}/semesters", response_model=List[dict])
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
