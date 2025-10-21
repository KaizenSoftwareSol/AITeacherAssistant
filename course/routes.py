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


# Import and include the router in the course_router from routes_config
from routes_config import course_router as main_course_router

main_course_router.include_router(router)
