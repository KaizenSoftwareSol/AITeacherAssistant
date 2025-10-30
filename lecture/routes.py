# lecture/routes.py

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import require_teacher
from logger import logger
from models.lecture import (
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    LectureDownloadResponse,
    LectureGenerationRequest,
    LectureGenerationResponse,
)
from models.user import User
from services.lecture_service import LectureService
from supabase_config import supabase
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
            learning_outcomes=request.learning_outcomes,
            selected_chapters=request.selected_chapters,
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


@router.post(
    "/check-duplicate",
    response_model=DuplicateCheckResponse,
)
async def check_duplicate_lecture(
    current_user: Annotated[User, Depends(require_teacher)],
    request: DuplicateCheckRequest,
    db=Depends(get_db),
):
    """
    Check if a lecture with the same details already exists.

    This endpoint checks for duplicate lectures based on:
    - Title
    - Course ID
    - Semester ID
    - Learning outcomes
    - Selected chapters (optional)

    Returns duplicate lecture information if found, including download link.
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

        logger.info(f"Checking for duplicate lecture: {request.title}")

        # Check for duplicates
        result = LectureService.check_for_duplicate_lecture(
            db=db,
            teacher_id=teacher.id,
            course_id=request.course_id,
            semester_id=request.semester_id,
            title=request.title,
            learning_outcomes=request.learning_outcomes,
            selected_chapters=request.selected_chapters,
        )

        logger.info(f"Duplicate check result: {result['has_duplicate']}")
        return DuplicateCheckResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in check duplicate endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during duplicate check",
        )


@router.delete(
    "/{lecture_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_lecture(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Delete a lecture and all its associated data.

    This endpoint deletes:
    - All child records (student engagement, assessments, questions, submissions, etc.)
    - Associated lecture content records
    - The PDF file from Supabase storage
    - AI conversations and analytics
    - Lecture embeddings and chunks
    - The lecture record from the database

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

        logger.info(f"Deleting lecture {lecture_id} and all associated data")

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

        # Step 1: Get assessments for this lecture (needed for cascading deletes)
        assessments = db.get_records("assessment", {"lecture_id": lecture_id})
        assessment_ids = [a["id"] for a in assessments]

        # Step 2: Delete deepest children first (assessment-related)
        if assessment_ids:
            # Delete questions for each assessment
            for assessment_id in assessment_ids:
                questions = db.get_records("question", {"assessment_id": assessment_id})
                for question in questions:
                    db.delete_record("question", question["id"])

                # Delete assessment submissions
                submissions = db.get_records(
                    "assessment_submission", {"assessment_id": assessment_id}
                )
                for submission in submissions:
                    db.delete_record("assessment_submission", submission["id"])

            logger.info(
                f"Deleted questions and submissions for {len(assessment_ids)} assessments"
            )

        # Step 3: Delete all direct children of lecture
        # Delete student engagement
        engagements = db.get_records("student_engagement", {"lecture_id": lecture_id})
        for engagement in engagements:
            db.delete_record("student_engagement", engagement["id"])
        logger.info(f"Deleted {len(engagements)} student engagement records")

        # Delete assessments
        for assessment_id in assessment_ids:
            db.delete_record("assessment", assessment_id)
        logger.info(f"Deleted {len(assessment_ids)} assessments")

        # Delete AI conversations
        conversations = db.get_records("ai_conversation", {"lecture_id": lecture_id})
        for conversation in conversations:
            db.delete_record("ai_conversation", conversation["id"])
        logger.info(f"Deleted {len(conversations)} AI conversations")

        # Delete lecture analytics
        analytics = db.get_records("lecture_analytics", {"lecture_id": lecture_id})
        for analytic in analytics:
            db.delete_record("lecture_analytics", analytic["id"])
        logger.info(f"Deleted {len(analytics)} analytics records")

        # Delete lecture chunks
        chunks = db.get_records("lecture_chunk", {"lecture_id": lecture_id})
        for chunk in chunks:
            db.delete_record("lecture_chunk", chunk["id"])
        logger.info(f"Deleted {len(chunks)} lecture chunks")

        # Delete lecture embeddings
        embeddings = db.get_records("lecture_embedding", {"lecture_id": lecture_id})
        for embedding in embeddings:
            db.delete_record("lecture_embedding", embedding["id"])
        logger.info(f"Deleted {len(embeddings)} lecture embeddings")

        # Delete lecture content and associated files
        lecture_contents = db.get_records("lecture_content", {"lecture_id": lecture_id})
        for content in lecture_contents:
            try:
                storage_bucket = content["storage_bucket"]
                storage_path = content["storage_path"]
                supabase.delete_file(storage_bucket, storage_path)
                logger.info(f"Deleted file: {storage_path}")
            except Exception as e:
                logger.warning(f"Failed to delete file {storage_path}: {str(e)}")

            db.delete_record("lecture_content", content["id"])
        logger.info(f"Deleted {len(lecture_contents)} lecture content records")

        # Step 4: Finally, delete the lecture record itself
        db.delete_record("lecture", lecture_id)

        logger.info(
            f"Successfully deleted lecture {lecture_id} and all associated data"
        )
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete lecture endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during lecture deletion",
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


@router.get("/", response_model=list)
async def get_teacher_lectures(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str = None,
    semester_id: str = None,
    status: str = None,
    db=Depends(get_db),
):
    """
    Get all lectures created by the teacher.

    Optional filters:
    - course_id: Filter by course
    - semester_id: Filter by semester
    - status: Filter by lecture status (GENERATED, PUBLISHED, etc.)

    Only accessible to the teacher who created the lectures.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching lectures for teacher {teacher.id}")

        # Build filters
        filters = {"teacher_id": teacher.id}
        if course_id:
            filters["course_id"] = course_id
        if semester_id:
            filters["semester_id"] = semester_id
        if status:
            filters["status"] = status

        # Get lectures
        lectures = db.get_records("lecture", filters=filters, skip=0, limit=1000)

        logger.info(f"Found {len(lectures)} lectures for teacher {teacher.id}")
        return lectures

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lectures: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching lectures",
        )


@router.patch(
    "/{lecture_id}/publish",
    status_code=status.HTTP_200_OK,
)
async def publish_lecture(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Publish a lecture (change status from GENERATED to PUBLISHED).

    Published lectures become visible to students enrolled in the course.
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

        logger.info(f"Publishing lecture {lecture_id}")

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

        # Update status to PUBLISHED
        db.update_record("lecture", lecture_id, {"status": "PUBLISHED"})

        logger.info(f"Successfully published lecture {lecture_id}")

        # Auto-generate summary and basic quiz in background
        try:
            import json
            from uuid import uuid4

            from services.quiz_service import QuizService
            from services.summary_service import SummaryService

            # Generate summary if not exists
            if not lecture_data.get("summary"):
                logger.info(f"Auto-generating summary for lecture {lecture_id}")
                summary_service = SummaryService()
                summary = await summary_service.generate_lecture_summary(
                    lecture_data.get("content", "")
                )
                db.update_record("lecture", lecture_id, {"summary": summary})
                logger.info(f"Summary generated for lecture {lecture_id}")

            # Check if default quiz already exists
            existing_quiz = db.get_records(
                "assessment", {"lecture_id": lecture_id, "is_default": True}
            )

            if not existing_quiz:
                logger.info(f"Auto-generating default quiz for lecture {lecture_id}")
                quiz_service = QuizService(db)
                quiz_data = await quiz_service.generate_quiz_from_lecture(
                    lecture_id=lecture_id,
                    lecture_content=lecture_data.get("content", ""),
                    num_questions=10,
                    question_types=["MULTIPLE_CHOICE"],
                    difficulty="MEDIUM",
                    focus_areas=None,
                )

                # Create default assessment
                assessment_id = str(uuid4())
                assessment_data = {
                    "id": assessment_id,
                    "title": f"Quiz: {lecture_data.get('title')}",
                    "description": f"Default quiz for {lecture_data.get('title')}",
                    "assessment_type": "QUIZ",
                    "course_id": lecture_data.get("course_id"),
                    "lecture_id": lecture_id,
                    "teacher_id": teacher.id,
                    "time_limit": 30,
                    "max_attempts": 3,
                    "passing_score": 60.0,
                    "is_published": True,
                    "is_default": True,  # Mark as default quiz
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
                db.admin_client.table("assessment").insert(assessment_data).execute()

                # Create question records
                questions_data = []
                for idx, question in enumerate(quiz_data["questions"]):
                    question_id = str(uuid4())
                    question_data = {
                        "id": question_id,
                        "assessment_id": assessment_id,
                        "question_text": question["question_text"],
                        "question_type": question["question_type"],
                        "points": question.get("points", 1.0),
                        "order_index": idx,
                        "options": json.dumps(question.get("options", [])),
                        "correct_answer": question["correct_answer"],
                        "explanation": question.get("explanation"),
                        "created_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                    questions_data.append(question_data)

                db.admin_client.table("question").insert(questions_data).execute()
                logger.info(
                    f"Default quiz {assessment_id} created with {len(questions_data)} questions"
                )
            
            # Generate flashcards
            logger.info(f"Auto-generating flashcards for lecture {lecture_id}")
            from services.flashcard_service import FlashcardService
            
            flashcard_service = FlashcardService(db)
            flashcards = await flashcard_service.generate_flashcards_from_lecture(
                lecture_content=lecture_data.get("content", ""),
                num_cards=15,
                difficulty_mix=True
            )
            
            # Save flashcards to database
            flashcards_data = []
            for idx, card in enumerate(flashcards):
                flashcard_record = {
                    "id": str(uuid4()),
                    "lecture_id": lecture_id,
                    "question": card["question"],
                    "answer": card["answer"],
                    "order_index": idx,
                    "difficulty": card.get("difficulty", "MEDIUM"),
                    "topic": card.get("topic", "General"),
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
                flashcards_data.append(flashcard_record)
            
            if flashcards_data:
                db.admin_client.table("flashcard").insert(flashcards_data).execute()
                logger.info(f"Created {len(flashcards_data)} flashcards for lecture {lecture_id}")

        except Exception as e:
            logger.warning(
                f"Failed to auto-generate summary/quiz/flashcards for lecture {lecture_id}: {str(e)}"
            )
            # Don't fail the publish operation if generation fails

        return {
            "message": "Lecture published successfully",
            "lecture_id": lecture_id,
            "status": "PUBLISHED",
            "title": lecture_data.get("title"),
            "auto_generated": "Summary and quiz generation started",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while publishing lecture",
        )


@router.patch(
    "/{lecture_id}/unpublish",
    status_code=status.HTTP_200_OK,
)
async def unpublish_lecture(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Unpublish a lecture (change status from PUBLISHED to GENERATED).

    Unpublished lectures become hidden from students.
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

        logger.info(f"Unpublishing lecture {lecture_id}")

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

        # Update status to GENERATED
        db.update_record("lecture", lecture_id, {"status": "GENERATED"})

        logger.info(f"Successfully unpublished lecture {lecture_id}")

        return {
            "message": "Lecture unpublished successfully",
            "lecture_id": lecture_id,
            "status": "GENERATED",
            "title": lecture_data.get("title"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unpublishing lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while unpublishing lecture",
        )


# Import and include the router in the lecture_router from routes_config
from routes_config import lecture_router as main_lecture_router

main_lecture_router.include_router(router)
