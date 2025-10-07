# lecture/routes.py

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import require_teacher
from logger import logger
from models.lecture import (LectureDownloadResponse, LectureGenerationRequest,
                            LectureGenerationResponse)
from models.user import User
from services.lecture_service import LectureService
from utils.db import get_db

router = APIRouter()


# ==================== Endpoints ====================


@router.post(
    "/generate",
    response_model=LectureGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_lecture(
    current_user: Annotated[User, Depends(require_teacher)],
    request: LectureGenerationRequest,
    db=Depends(get_db),
):
    """
    Generate a lecture from an ingested document using AI.

    This endpoint:
    1. Fetches the selected document's JSON content from storage
    2. Uses the teacher's description to generate lecture content with OpenAI GPT-4o
    3. Creates a PDF of the generated lecture
    4. Saves the PDF to Supabase storage in GENERATED_CONTENT bucket
    5. Creates lecture and lecture content records in the database

    Only accessible to teachers.
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
            f"Generating lecture from document {request.document_id} "
            f"for teacher {teacher.id}"
        )

        # Generate and save lecture
        result = await LectureService.generate_and_save_lecture(
            db=db,
            document_id=request.document_id,
            teacher_id=teacher.id,
            course_id=request.course_id,
            semester_id=request.semester_id,
            lecture_title=request.title,
            lecture_description=request.description,
        )

        logger.info(
            f"Lecture generated successfully: {result['lecture_id']} "
            f"for teacher {teacher.id}"
        )

        return LectureGenerationResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate lecture endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during lecture generation",
        )


@router.get(
    "/{lecture_id}/download",
    response_model=LectureDownloadResponse,
)
async def get_lecture_download_link(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,  # UUID of the lecture
    db=Depends(get_db),
):
    """
    Get download link for a generated lecture PDF.

    This endpoint returns a public download URL for the lecture PDF file.
    Only accessible to the teacher who created the lecture.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching download link for lecture {lecture_id}")

        # Get lecture details
        lecture_data = db.get_record_by_id("lecture", lecture_id)
        if not lecture_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )

        # Verify access
        if lecture_data.get("teacher_id") != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this lecture",
            )

        # Get download URL
        download_url = LectureService.get_lecture_download_url(
            db=db, lecture_id=lecture_id, teacher_id=teacher.id
        )

        # Get lecture content for file info
        lecture_contents = db.get_records("lecture_content", {"lecture_id": lecture_id})
        pdf_content = lecture_contents[0] if lecture_contents else None

        response = LectureDownloadResponse(
            lecture_id=lecture_id,
            title=lecture_data["title"],
            download_url=download_url,
            file_name=pdf_content["file_name"] if pdf_content else "lecture.pdf",
            file_size=pdf_content["file_size"] if pdf_content else 0,
            created_at=lecture_data["created_at"],
        )

        logger.info(f"Download link generated for lecture {lecture_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get download link endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching download link",
        )


# Import and include the router in the lecture_router from routes_config
from routes_config import lecture_router as main_lecture_router

main_lecture_router.include_router(router)
