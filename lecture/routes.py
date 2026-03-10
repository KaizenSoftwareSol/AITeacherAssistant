# lecture/routes.py

import json
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import File, UploadFile, Form

from dependencies import get_current_user, require_teacher
from logger import logger
from models.lecture import (
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    LectureDownloadResponse,
    LectureGenerationRequest,
    LectureGenerationResponse,
    LectureModifyRequest,
    LectureModifyResponse,
    LecturePlanGenerationResponse,
)
from models.user import User, UserRole
from services.embedding_service import EmbeddingService
from services.flashcard_service import FlashcardService
from services.lecture_service import LectureService
from services.notification_service import NotificationService
from services.quiz_service import QuizService
from services.summary_service import SummaryService
from supabase_config import supabase
from utils.db import get_db
from utils.id_converter import IDConverter

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

        # Normalize document IDs: support both single document_id (backward compat) and document_ids list
        document_ids = request.document_ids
        if not document_ids and request.document_id:
            document_ids = [request.document_id]
        
        if not document_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either document_id or document_ids must be provided",
            )

        logger.info(
            f"Generating lecture from {len(document_ids)} document(s) "
            f"for teacher {teacher.id}"
        )

        # Generate and save lecture
        result = await LectureService.generate_and_save_lecture(
            db=db,
            document_ids=document_ids,
            teacher_id=teacher.id,
            course_id=request.course_id,
            semester_id=request.semester_id,
            lecture_title=request.title,
            lecture_description=request.description,
            learning_outcomes=request.learning_outcomes,
            selected_chapters=request.selected_chapters,
            topic=request.topic,
            extra_document_ids=request.extra_document_ids or None,
            extra_texts=request.extra_texts or None,
            extra_file_urls=request.extra_file_urls or None,
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
    "/generate-with-files",
    response_model=LectureGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_lecture_with_files(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str = Form(None),  # Single document (backward compatibility)
    document_ids: str = Form(None),  # JSON array of document IDs (new way)
    course_id: str = Form(...),
    semester_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    learning_outcomes: str = Form(None),
    selected_chapters: str = Form(None),  # JSON array or comma-separated
    topic: str = Form(None),
    extra_files: list[UploadFile] = File(None),
    db=Depends(get_db),
):
    """
    Generate a lecture from one or more ingested documents using AI with additional uploaded files.

    Notes:
    - Supports multiple documents via document_ids (JSON array) or single document via document_id (backward compat)
    - extra_files are parsed transiently (txt/pdf/docx) and truncated for LLM context,
      nothing is persisted from these uploads.
    - selected_chapters can be a JSON array of strings or a comma-separated string.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        # Parse document_ids: support both JSON array string and single document_id
        parsed_document_ids = None
        if document_ids:
            try:
                parsed = json.loads(document_ids)
                if isinstance(parsed, list):
                    parsed_document_ids = parsed
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="document_ids must be a JSON array of document IDs",
                    )
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="document_ids must be a valid JSON array",
                )
        elif document_id:
            parsed_document_ids = [document_id]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either document_id or document_ids must be provided",
            )

        # Parse selected_chapters
        parsed_selected = None
        if selected_chapters:
            try:
                parsed = json.loads(selected_chapters)
                if isinstance(parsed, list):
                    parsed_selected = parsed
            except Exception:
                # Fallback: comma-separated
                parsed_selected = [s.strip() for s in selected_chapters.split(",") if s.strip()]

        # Prepare uploaded files
        uploads = []
        if extra_files:
            for f in extra_files:
                try:
                    content = await f.read()
                    uploads.append(
                        {
                            "filename": f.filename,
                            "content_type": f.content_type or "",
                            "bytes": content or b"",
                        }
                    )
                except Exception as read_err:
                    logger.warning(f"Failed to read uploaded file {getattr(f, 'filename', '')}: {read_err}")

        # Generate and save lecture
        result = await LectureService.generate_and_save_lecture(
            db=db,
            document_ids=parsed_document_ids,
            teacher_id=teacher.id,
            course_id=course_id,
            semester_id=semester_id,
            lecture_title=title,
            lecture_description=description,
            learning_outcomes=learning_outcomes,
            selected_chapters=parsed_selected,
            topic=topic,
            extra_uploads=uploads or None,
        )

        return LectureGenerationResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate-with-files endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during lecture generation with files",
        )

@router.get(
    "/by-topic",
    response_model=list,
)
async def get_lectures_by_topic(
    current_user: Annotated[User, Depends(require_teacher)],
    topic: str,
    course_id: str = None,
    semester_id: str = None,
    status: str = None,
    db=Depends(get_db),
):
    """
    Get all lectures for the current teacher within a specific topic.

    Validations and behavior:
    - Requires an authenticated teacher profile
    - Only returns lectures created by the current teacher
    - Required filter: topic
    - Optional filters: course_id, semester_id, status
    - Sorted by lecture_number (asc) then created_at (asc)
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        if not topic or not str(topic).strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'topic' is required",
            )

        logger.info(f"Fetching lectures for teacher {teacher.id} by topic '{topic}'")

        # Build filters
        filters = {"teacher_id": teacher.id, "topic": topic}
        if course_id:
            filters["course_id"] = course_id
        if semester_id:
            filters["semester_id"] = semester_id
        if status:
            filters["status"] = status

        # Get lectures
        lectures = db.get_records("lecture", filters=filters, skip=0, limit=1000)

        # Enrich with course names (batch fetch to avoid N+1 queries)
        try:
            course_ids = list(
                {lec.get("course_id") for lec in lectures if lec.get("course_id")}
            )

            course_name_by_id = {}
            if course_ids:
                response = (
                    db.admin_client.table("course")
                    .select("id,name")
                    .in_("id", course_ids)
                    .execute()
                )
                course_name_by_id = {row["id"]: row.get("name") for row in response.data}

            for lec in lectures:
                cid = lec.get("course_id")
                lec["course_name"] = course_name_by_id.get(cid)
        except Exception as enrich_error:
            logger.warning(f"Failed to enrich lectures with course names: {enrich_error}")

        # Sort by lecture_number (None -> 0) then created_at
        try:
            lectures.sort(
                key=lambda x: (
                    (x.get("lecture_number") or 0),
                    x.get("created_at") or "",
                )
            )
        except Exception as sort_error:
            logger.warning(f"Failed to sort lectures by topic order: {sort_error}")

        logger.info(
            f"Found {len(lectures)} lectures for teacher {teacher.id} in topic '{topic}'"
        )
        return lectures

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lectures by topic: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching lectures by topic",
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

    This endpoint checks for duplicate lectures using two strategies:
    1. Title-based: Same title for the same course (prevents storage path conflicts)
    2. Document-based: Same source document + course + semester combination
    
    Checks based on:
    - Title (required)
    - Course ID (required)
    - Semester ID (required)
    - Document ID (optional - for document-based duplicate detection)
    - Learning outcomes (optional)
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

        # Normalize document ID: use first document from document_ids if provided, otherwise use document_id
        document_id_for_check = request.document_id
        if not document_id_for_check and request.document_ids:
            document_id_for_check = request.document_ids[0] if request.document_ids else None

        # Convert IDs to integer IDs for database queries (handle both UUID strings and integers)
        course_int_id = request.course_id
        semester_int_id = request.semester_id
        document_int_id = document_id_for_check
        
        # Handle course_id (can be UUID string or integer)
        if isinstance(request.course_id, str):
            if IDConverter.is_uuid(request.course_id):
                course_int_id = await IDConverter.uuid_to_int(db, "course", request.course_id)
                if not course_int_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Course not found",
                    )
            else:
                # String that's not a UUID, try to convert to int
                try:
                    course_int_id = int(request.course_id)
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid course_id format",
                    )
        # If it's already an integer, use it directly
        
        # Handle semester_id (can be UUID string or integer)
        if isinstance(request.semester_id, str):
            if IDConverter.is_uuid(request.semester_id):
                semester_int_id = await IDConverter.uuid_to_int(db, "semester", request.semester_id)
                if not semester_int_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Semester not found",
                    )
            else:
                # String that's not a UUID, try to convert to int
                try:
                    semester_int_id = int(request.semester_id)
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid semester_id format",
                    )
        # If it's already an integer, use it directly
        
        # Handle document_id (can be UUID string or integer)
        if document_id_for_check:
            if isinstance(document_id_for_check, str):
                if IDConverter.is_uuid(document_id_for_check):
                    document_int_id = await IDConverter.uuid_to_int(db, "documents", document_id_for_check)
                else:
                    # String that's not a UUID, try to convert to int
                    try:
                        document_int_id = int(document_id_for_check)
                    except ValueError:
                        document_int_id = None  # Invalid format, ignore
            # If it's already an integer, use it directly

        # Check for duplicates
        result = await LectureService.check_for_duplicate_lecture(
            db=db,
            teacher_id=str(teacher.id),  # Convert to string for consistency
            course_id=course_int_id,
            semester_id=semester_int_id,
            title=request.title,
            document_id=document_int_id,
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


@router.patch(
    "/{lecture_id}",
    response_model=LectureModifyResponse,
    status_code=status.HTTP_200_OK,
)
async def modify_lecture(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    request: LectureModifyRequest,
    db=Depends(get_db),
):
    """
    Modify an existing generated lecture.

    This endpoint allows teachers to update:
    - title: New title for the lecture
    - description: New description/overview
    - learning_outcomes: Updated learning outcomes
    - content: Modified lecture content (will trigger PDF regeneration)
    - topic: Topic for grouping lectures
    - lecture_number: Sequential number within the topic
    - regenerate_pdf: Force PDF regeneration even if content unchanged

    When content or title is changed, or regenerate_pdf is True, a new PDF
    will be generated and the old one will be replaced.

    The lecture version will be incremented on each modification.

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

        logger.info(f"Modifying lecture {lecture_id} for teacher {teacher.id}")

        # Modify the lecture
        result = await LectureService.modify_lecture(
            db=db,
            lecture_id=lecture_id,
            teacher_id=teacher.id,
            title=request.title,
            description=request.description,
            learning_outcomes=request.learning_outcomes,
            content=request.content,
            topic=request.topic,
            lecture_number=request.lecture_number,
            regenerate_pdf=request.regenerate_pdf,
        )

        logger.info(f"Lecture {lecture_id} modified successfully")
        return LectureModifyResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error modifying lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while modifying lecture",
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

        # Convert UUID to integer ID if needed
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )

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
        assessments = db.get_records("assessment", {"lecture_id": lecture_int_id})
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
        engagements = db.get_records("student_engagement", {"lecture_id": lecture_int_id})
        for engagement in engagements:
            db.delete_record("student_engagement", engagement["id"])
        logger.info(f"Deleted {len(engagements)} student engagement records")

        # Delete assessments
        for assessment_id in assessment_ids:
            db.delete_record("assessment", assessment_id)
        logger.info(f"Deleted {len(assessment_ids)} assessments")

        # Delete AI conversations
        conversations = db.get_records("ai_conversation", {"lecture_id": lecture_int_id})
        for conversation in conversations:
            db.delete_record("ai_conversation", conversation["id"])
        logger.info(f"Deleted {len(conversations)} AI conversations")

        # Delete lecture analytics
        analytics = db.get_records("lecture_analytics", {"lecture_id": lecture_int_id})
        for analytic in analytics:
            db.delete_record("lecture_analytics", analytic["id"])
        logger.info(f"Deleted {len(analytics)} analytics records")

        # Delete lecture chunks
        chunks = db.get_records("lecture_chunk", {"lecture_id": lecture_int_id})
        for chunk in chunks:
            db.delete_record("lecture_chunk", chunk["id"])
        logger.info(f"Deleted {len(chunks)} lecture chunks")

        # Delete lecture embeddings
        embeddings = db.get_records("lecture_embedding", {"lecture_id": lecture_int_id})
        for embedding in embeddings:
            db.delete_record("lecture_embedding", embedding["id"])
        logger.info(f"Deleted {len(embeddings)} lecture embeddings")

        # Delete lecture content and associated files
        lecture_contents = db.get_records("lecture_content", {"lecture_id": lecture_int_id})
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
    current_user: Annotated[User, Depends(get_current_user)],
    lecture_id: str,  # UUID of the lecture
    db=Depends(get_db),
):
    """
    Get download link for a generated lecture PDF.

    This endpoint returns a public download URL and the lecture content.
    Accessible to the teacher who created it (or admins) and to students
    who are actively enrolled in the lecture's course.
    """
    try:
        logger.info(f"Fetching download link for lecture {lecture_id}")

        # Get lecture details
        lecture_data = db.get_record_by_id("lecture", lecture_id)
        if not lecture_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )

        user_role = current_user.role
        teacher = current_user.teacher_profile
        requester_teacher_id = None

        if user_role in [UserRole.TEACHER, UserRole.ADMIN]:
            if user_role == UserRole.TEACHER:
                if not teacher:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Teacher profile not found",
                    )
                if lecture_data.get("teacher_id") != teacher.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied to this lecture",
                    )
                requester_teacher_id = teacher.id
            else:
                # Admins bypass teacher ownership check
                requester_teacher_id = None
        elif user_role == UserRole.STUDENT:
            # Verify student enrollment in the lecture's course
            student_result = (
                db.admin_client.table("student")
                .select("id")
                .eq("user_id", str(current_user.id))
                .limit(1)
                .execute()
            )
            if not student_result.data:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Student profile not found",
                )
            student_id = student_result.data[0]["id"]

            enrollment_result = (
                db.admin_client.table("enrollment")
                .select("id")
                .eq("student_id", student_id)
                .eq("course_id", lecture_data.get("course_id"))
                .eq("is_active", True)
                .execute()
            )
            if not enrollment_result.data:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not enrolled in this course",
                )
            requester_teacher_id = None
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this lecture",
            )

        # Get download URL
        download_url = await LectureService.get_lecture_download_url(
            db=db, lecture_id=lecture_id, teacher_id=requester_teacher_id
        )

        # Convert UUID to integer ID if needed for filter
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                lecture_int_id = lecture_id  # Fallback to original if conversion fails

        # Get lecture content for file info
        lecture_contents = db.get_records("lecture_content", {"lecture_id": lecture_int_id})
        pdf_content = lecture_contents[0] if lecture_contents else None

        response = LectureDownloadResponse(
            lecture_id=lecture_id,
            title=lecture_data["title"],
            download_url=download_url,
            file_name=pdf_content["file_name"] if pdf_content else "lecture.pdf",
            file_size=pdf_content["file_size"] if pdf_content else 0,
            created_at=lecture_data["created_at"],
            lecture_content=lecture_data.get("content"),
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


@router.post(
    "/{lecture_id}/generate-plan",
    response_model=LecturePlanGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_lecture_plan(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Generate a comprehensive teaching plan for an existing lecture.

    This endpoint generates a detailed plan including:
    - Activities and exercises
    - Quiz questions with answers
    - Discussion questions
    - Time allocations per section
    - Differentiation strategies for diverse learners
    - Teaching notes and tips
    - Homework suggestions
    - Formative assessments

    **IMPORTANT:** This endpoint should be called AFTER generating a lecture.
    The lecture must have content before a plan can be generated.

    If a plan already exists, it will be replaced with a newly generated one.

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

        logger.info(f"Generating lecture plan for lecture {lecture_id}")

        # Generate the lecture plan
        result = await LectureService.generate_lecture_plan(
            db=db,
            lecture_id=lecture_id,
            teacher_id=teacher.id,
        )

        logger.info(f"Lecture plan generated successfully for lecture {lecture_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating lecture plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating lecture plan",
        )


@router.get(
    "/{lecture_id}/plan",
    status_code=status.HTTP_200_OK,
)
async def get_lecture_plan(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Get the lecture teaching plan for a generated lecture.

    This endpoint returns the comprehensive teaching plan including:
    - Activities and exercises
    - Quiz questions
    - Discussion questions
    - Time allocations
    - Differentiation strategies
    - Teaching notes and tips

    **NOTE:** The plan must be generated first using POST /{lecture_id}/generate-plan

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

        logger.info(f"Fetching lecture plan for lecture {lecture_id}")

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

        # Get lecture plan
        lecture_plan_json = lecture_data.get("lecture_plan")

        if not lecture_plan_json:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture plan not found. It may not have been generated yet.",
            )

        # Parse JSON
        import json

        try:
            lecture_plan = json.loads(lecture_plan_json)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse lecture plan JSON for lecture {lecture_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to parse lecture plan",
            )

        logger.info(f"Successfully retrieved lecture plan for lecture {lecture_id}")

        return {
            "lecture_id": lecture_id,
            "lecture_title": lecture_data["title"],
            "plan": lecture_plan,
            "created_at": lecture_data["created_at"],
            "updated_at": lecture_data["updated_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lecture plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching lecture plan",
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

        # Enrich with course names (batch fetch to avoid N+1 queries)
        try:
            course_ids = list(
                {lec.get("course_id") for lec in lectures if lec.get("course_id")}
            )

            course_name_by_id = {}
            if course_ids:
                # Use admin_client to fetch course names in a single query
                response = (
                    db.admin_client.table("course")
                    .select("id,name")
                    .in_("id", course_ids)
                    .execute()
                )
                course_name_by_id = {row["id"]: row.get("name") for row in response.data}

            # Attach course_name to each lecture
            for lec in lectures:
                cid = lec.get("course_id")
                lec["course_name"] = course_name_by_id.get(cid)
        except Exception as enrich_error:
            # If enrichment fails, continue returning base lectures
            logger.warning(f"Failed to enrich lectures with course names: {enrich_error}")

        # Return flat list to match response_model=list
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


@router.post(
    "/{lecture_id}/generate-summary",
    status_code=status.HTTP_200_OK,
)
async def generate_lecture_summary(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Generate a summary for a lecture.
    
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

        logger.info(f"Generating summary for lecture {lecture_id}")

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

        # Generate summary
        summary_service = SummaryService()
        summary = await summary_service.generate_lecture_summary(
            lecture_data.get("content", "")
        )
        
        # Convert lecture_id to integer for update if needed
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )
        
        db.update_record("lecture", lecture_int_id, {"summary": summary})
        
        logger.info(f"Summary generated for lecture {lecture_id}")

        return {
            "message": "Summary generated successfully",
            "lecture_id": lecture_id,
            "summary": summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating summary for lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating summary",
        )


@router.post(
    "/{lecture_id}/generate-quiz",
    status_code=status.HTTP_200_OK,
)
async def generate_lecture_quiz(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Generate a default quiz for a lecture.
    
    Creates a 10-question multiple choice quiz. If a default quiz already exists,
    it will be replaced.
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

        logger.info(f"Generating quiz for lecture {lecture_id}")

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

        # Convert UUID to integer ID if needed for filter
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                lecture_int_id = lecture_id  # Fallback to original if conversion fails

        # Check if default quiz already exists and delete it
        existing_quiz = db.get_records(
            "assessment", {"lecture_id": lecture_int_id, "is_default": True}
        )
        
        if existing_quiz:
            # Delete existing questions first
            for quiz in existing_quiz:
                questions = db.get_records("question", {"assessment_id": quiz["id"]})
                for question in questions:
                    db.delete_record("question", question["id"])
                # Delete the assessment
                db.delete_record("assessment", quiz["id"])
                logger.info(f"Deleted existing default quiz {quiz['id']}")

        # Generate quiz
        quiz_service = QuizService(db)
        quiz_data = await quiz_service.generate_quiz_from_lecture(
            lecture_id=lecture_id,
            lecture_content=lecture_data.get("content", ""),
            num_questions=10,
            question_types=["MULTIPLE_CHOICE"],
            difficulty="MEDIUM",
            focus_areas=None,
        )

        # Get integer IDs for assessment creation
        course_int_id = lecture_data.get("course_id")
        if isinstance(course_int_id, str):
            if IDConverter.is_uuid(course_int_id):
                course_int_id = await IDConverter.uuid_to_int(db, "course", course_int_id)
            else:
                try:
                    course_int_id = int(course_int_id)
                except ValueError:
                    course_int_id = lecture_data.get("course_id")  # Fallback
        
        teacher_int_id = teacher.id if isinstance(teacher.id, int) else teacher.id
        
        # Create default assessment with integer IDs
        assessment_uuid = str(uuid4())
        assessment_data = {
            "uuid": assessment_uuid,  # Store UUID for external use
            "title": f"Quiz: {lecture_data.get('title')}",
            "description": f"Default quiz for {lecture_data.get('title')}",
            "assessment_type": "QUIZ",
            "course_id": course_int_id,  # Integer FK
            "lecture_id": lecture_int_id,  # Integer FK
            "teacher_id": teacher_int_id,  # Integer FK
            "time_limit": 30,
            "max_attempts": 3,
            "passing_score": 60.0,
            "is_published": True,
            "is_default": True,  # Mark as default quiz
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        assessment_result = db.admin_client.table("assessment").insert(assessment_data).execute()
        assessment_record = assessment_result.data[0]
        assessment_int_id = assessment_record["id"]  # Integer ID from database
        assessment_uuid = assessment_record.get("uuid") or assessment_uuid

        # Create question records with integer assessment_id
        questions_data = []
        for idx, question in enumerate(quiz_data["questions"]):
            question_uuid = str(uuid4())
            question_data = {
                "uuid": question_uuid,  # Store UUID for external use
                "assessment_id": assessment_int_id,  # Integer FK
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
            f"Default quiz {assessment_uuid} created with {len(questions_data)} questions"
        )

        return {
            "message": "Quiz generated successfully",
            "lecture_id": lecture_id,  # UUID for API
            "assessment_id": assessment_uuid,  # UUID for API
            "num_questions": len(questions_data),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating quiz for lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating quiz",
        )


@router.post(
    "/{lecture_id}/generate-flashcards",
    status_code=status.HTTP_200_OK,
)
async def generate_lecture_flashcards(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Generate flashcards for a lecture.
    
    Creates 15 flashcards with mixed difficulty. If flashcards already exist,
    they will be replaced.
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

        logger.info(f"Generating flashcards for lecture {lecture_id}")

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

        # Convert UUID to integer ID if needed for filter
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                lecture_int_id = lecture_id  # Fallback to original if conversion fails

        # Check if flashcards already exist and delete them
        existing_flashcards = db.get_records("flashcard", {"lecture_id": lecture_int_id})
        if existing_flashcards:
            for flashcard in existing_flashcards:
                db.delete_record("flashcard", flashcard["id"])
            logger.info(f"Deleted {len(existing_flashcards)} existing flashcards")

        # Generate flashcards
        flashcard_service = FlashcardService(db)
        flashcards = await flashcard_service.generate_flashcards_from_lecture(
            lecture_content=lecture_data.get("content", ""),
            num_cards=15,
            difficulty_mix=True
        )
        
        # Save flashcards to database with integer lecture_id
        flashcards_data = []
        for idx, card in enumerate(flashcards):
            flashcard_uuid = str(uuid4())
            flashcard_record = {
                "uuid": flashcard_uuid,  # Store UUID for external use
                "lecture_id": lecture_int_id,  # Integer FK
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

        return {
            "message": "Flashcards generated successfully",
            "lecture_id": lecture_id,
            "num_flashcards": len(flashcards_data),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating flashcards for lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating flashcards",
        )


@router.post(
    "/{lecture_id}/generate-embeddings",
    status_code=status.HTTP_200_OK,
)
async def generate_lecture_embeddings(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Generate embeddings for a lecture to enable RAG-based chatbot.
    
    Creates chunks and embeddings from the lecture content. If embeddings already exist,
    they will be replaced.
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

        logger.info(f"Generating embeddings for lecture {lecture_id}")

        # Convert UUID to integer ID if needed
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )
        elif isinstance(lecture_id, str):
            try:
                lecture_int_id = int(lecture_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid lecture_id format",
                )

        # Get lecture details using integer ID
        lecture_data = db.get_record_by_id("lecture", lecture_int_id)
        if not lecture_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )

        # Verify access - compare integer IDs
        teacher_int_id = teacher.id if isinstance(teacher.id, int) else teacher.id
        if lecture_data.get("teacher_id") != teacher_int_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this lecture",
            )

        # Check if embeddings already exist and delete them
        if lecture_data.get("has_embeddings"):
            embedding_service = EmbeddingService(db)
            await embedding_service.delete_lecture_embeddings(lecture_id)  # Pass UUID for service
            logger.info(f"Deleted existing embeddings for lecture {lecture_id}")

        # Generate embeddings - pass UUID to service (it will convert internally)
        embedding_service = EmbeddingService(db)
        result = await embedding_service.generate_embeddings_for_lecture(
            lecture_id=lecture_id,  # Pass UUID to service
            lecture_content=lecture_data.get("content", "")
        )

        logger.info(
            f"Generated {result['chunks_created']} chunks and "
            f"{result['embeddings_created']} embeddings for lecture {lecture_id}"
        )

        return {
            "message": "Embeddings generated successfully",
            "lecture_id": lecture_id,
            "chunks_created": result["chunks_created"],
            "embeddings_created": result["embeddings_created"],
            "has_embeddings": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating embeddings for lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating embeddings",
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
    
    Note: This endpoint only changes the status. To generate content, use the separate endpoints:
    - POST /{lecture_id}/generate-summary
    - POST /{lecture_id}/generate-quiz
    - POST /{lecture_id}/generate-flashcards
    - POST /{lecture_id}/generate-embeddings (for RAG chatbot)
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

        # Notify all enrolled students
        try:
            course_id = lecture_data.get("course_id")
            lecture_title = lecture_data.get("title", "Lecture")
            
            # course_id from database should be integer already, but verify
            course_int_id = course_id if isinstance(course_id, int) else course_id
            
            # Get course name
            course_result = (
                db.admin_client.table("course")
                .select("name")
                .eq("id", course_int_id)
                .execute()
            )
            course_name = course_result.data[0]["name"] if course_result.data else "Course"
            
            # Get all enrolled students' user_ids
            enrollments_result = (
                db.admin_client.table("enrollment")
                .select("student_id")
                .eq("course_id", course_int_id)
                .eq("is_active", True)
                .execute()
            )
            
            if enrollments_result.data:
                student_ids = [e["student_id"] for e in enrollments_result.data]
                
                # Get user_ids for these students
                students_result = (
                    db.admin_client.table("student")
                    .select("user_id")
                    .in_("id", student_ids)
                    .execute()
                )
                
                if students_result.data:
                    student_user_ids = [s["user_id"] for s in students_result.data]
                    
                    # Get teacher name for email
                    teacher_name = None
                    teacher_result = (
                        db.admin_client.table("teacher")
                        .select("user_id, users!inner(*)")
                        .eq("user_id", current_user.id)
                        .limit(1)
                        .execute()
                    )
                    if teacher_result.data:
                        teacher_user_data = teacher_result.data[0].get("users", {})
                        teacher_name = f"{teacher_user_data.get('first_name', '')} {teacher_user_data.get('last_name', '')}".strip()
                    
                    # Send notifications
                    notification_service = NotificationService(db)
                    await notification_service.notify_lecture_published(
                        student_user_ids=student_user_ids,
                        lecture_title=lecture_title,
                        course_name=course_name,
                        lecture_id=lecture_id,
                        teacher_name=teacher_name,
                    )
                    logger.info(f"Sent lecture published notifications to {len(student_user_ids)} students")
        except Exception as notify_error:
            # Don't fail the publish if notification fails
            logger.warning(f"Failed to send lecture published notifications: {notify_error}")

        return {
            "message": "Lecture published successfully",
            "lecture_id": lecture_id,
            "status": "PUBLISHED",
            "title": lecture_data.get("title"),
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


@router.post(
    "/{lecture_id}/generate-audio",
    status_code=status.HTTP_200_OK,
)
async def generate_lecture_audio(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    voice: str | None = "george",
    model: str | None = "eleven_turbo_v2_5",
    db=Depends(get_db),
):
    """
    Generate audio narration for a lecture using ElevenLabs TTS.
    
    This endpoint generates an MP3 audio file from the lecture content.
    The audio is stored in Supabase storage and can be played by students.
    
    Query Parameters:
    - voice: Voice key (e.g., 'george', 'rachel', 'brian') or voice_id. Default: george
    - model: Model ID. Options:
        - eleven_multilingual_v2 (default): Best quality, stable for long-form
        - eleven_flash_v2_5: Fastest, lowest latency
        - eleven_turbo_v2_5: Balanced quality and speed
    
    If audio already exists for this lecture, it will be replaced.
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

        logger.info(f"Generating audio for lecture {lecture_id}")

        # Convert lecture_id to integer for database queries
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )
        elif isinstance(lecture_id, str):
            try:
                lecture_int_id = int(lecture_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid lecture_id format",
                )

        # Get lecture details using integer ID
        lecture_data = db.get_record_by_id("lecture", lecture_int_id)
        if not lecture_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )

        # Verify access
        teacher_int_id = teacher.id if isinstance(teacher.id, int) else teacher.id
        if lecture_data.get("teacher_id") != teacher_int_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this lecture",
            )

        # Check if lecture has content
        content = lecture_data.get("content", "")
        if not content or len(content.strip()) < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lecture content is too short to generate audio. "
                       "Minimum 100 characters required.",
            )

        # Check if audio already exists and delete it using integer ID
        existing_audio = db.get_records(
            "lecture_content",
            {"lecture_id": lecture_int_id, "file_type": "mp3"}
        )
        
        if existing_audio:
            for audio_record in existing_audio:
                # Delete from storage
                try:
                    storage_path = audio_record.get("storage_path")
                    bucket_name = audio_record.get("storage_bucket")
                    if storage_path and bucket_name:
                        supabase.delete_file(bucket_name, storage_path)
                except Exception as e:
                    logger.warning(f"Could not delete existing audio file: {e}")
                # Delete the record
                db.delete_record("lecture_content", audio_record["id"])
            logger.info(f"Deleted existing audio for lecture {lecture_id}")

        # Generate audio
        from services.audio_service import AudioService
        audio_service = AudioService(db)
        result = await audio_service.generate_audio_for_lecture(
            lecture_id=lecture_id,
            lecture_content=content,
            lecture_title=lecture_data.get("title", "Lecture"),
            voice=voice,
            model=model,
        )

        # Create lecture content record for the audio with integer lecture_id
        audio_content_uuid = str(uuid4())
        audio_content_data = {
            "uuid": audio_content_uuid,  # Store UUID for external use
            "lecture_id": lecture_int_id,  # Integer FK
            "file_name": result["audio_filename"],
            "file_type": "mp3",
            "file_size": result["file_size"],
            "storage_path": result["storage_path"],
            "storage_bucket": result["storage_bucket"],
            "mime_type": result["mime_type"],
            "created_at": datetime.utcnow().isoformat(),
        }
        audio_result = db.admin_client.table("lecture_content").insert(audio_content_data).execute()
        audio_content_record = audio_result.data[0] if audio_result.data else None
        audio_content_uuid = audio_content_record.get("uuid") or audio_content_uuid if audio_content_record else audio_content_uuid

        logger.info(f"Audio generated successfully for lecture {lecture_id}")

        return {
            "message": "Audio generated successfully",
            "lecture_id": lecture_id,  # UUID for API
            "audio_content_id": audio_content_uuid,  # UUID for API
            "audio_filename": result["audio_filename"],
            "download_url": result["download_url"],
            "file_size": result["file_size"],
            "estimated_duration_seconds": result["estimated_duration_seconds"],
            "voice": result["voice"],
            "model": result["model"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating audio for lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating audio",
        )


@router.get(
    "/{lecture_id}/audio",
    status_code=status.HTTP_200_OK,
)
async def get_lecture_audio(
    current_user: Annotated[User, Depends(get_current_user)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Get audio information for a lecture.
    
    Returns the audio file details and download URL if audio exists.
    Accessible to both teachers (who own the lecture) and students (enrolled in the course).
    """
    try:
        logger.info(f"Fetching audio for lecture {lecture_id}")

        # Convert lecture_id to integer for database queries
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )
        elif isinstance(lecture_id, str):
            try:
                lecture_int_id = int(lecture_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid lecture_id format",
                )

        # Get lecture details using integer ID
        lecture_data = db.get_record_by_id("lecture", lecture_int_id)
        if not lecture_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )

        # Check access - teachers can access their own, students can access published
        if current_user.role == UserRole.TEACHER:
            teacher = current_user.teacher_profile
            teacher_int_id = teacher.id if isinstance(teacher.id, int) else teacher.id
            if not teacher or lecture_data.get("teacher_id") != teacher_int_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this lecture",
                )
        elif current_user.role == UserRole.STUDENT:
            # Check if lecture is published
            if lecture_data.get("status") not in ["PUBLISHED", "DELIVERED"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Lecture is not published",
                )
            # Check if student is enrolled in the course
            student = current_user.student_profile
            if student:
                # Convert student_id and course_id to integers
                student_int_id = student.id if isinstance(student.id, int) else await IDConverter.uuid_to_int(db, "student", str(student.id))
                course_id = lecture_data.get("course_id")
                course_int_id = course_id if isinstance(course_id, int) else course_id
                
                if student_int_id:
                    enrollment = db.get_records(
                        "enrollment",
                        {"student_id": student_int_id, "course_id": course_int_id, "is_active": True}
                    )
                    if not enrollment:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="You are not enrolled in this course",
                        )

        # Get audio content record using integer ID
        audio_records = db.get_records(
            "lecture_content",
            {"lecture_id": lecture_int_id, "file_type": "mp3"}
        )
        
        if not audio_records:
            return {
                "lecture_id": lecture_id,
                "has_audio": False,
                "message": "No audio available for this lecture",
            }

        audio_record = audio_records[0]
        
        # Get download URL
        download_url = None
        try:
            bucket_name = audio_record.get("storage_bucket")
            storage_path = audio_record.get("storage_path")
            if bucket_name and storage_path:
                bucket = supabase.get_storage_bucket(bucket_name)
                download_url = bucket.get_public_url(storage_path)
        except Exception as e:
            logger.warning(f"Could not get audio download URL: {e}")

        return {
            "lecture_id": lecture_id,
            "has_audio": True,
            "audio_content_id": audio_record["id"],
            "audio_filename": audio_record.get("file_name"),
            "file_size": audio_record.get("file_size"),
            "download_url": download_url,
            "created_at": audio_record.get("created_at"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching audio for lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching audio",
        )


@router.delete(
    "/{lecture_id}/audio",
    status_code=status.HTTP_200_OK,
)
async def delete_lecture_audio(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Delete audio for a lecture.
    
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

        logger.info(f"Deleting audio for lecture {lecture_id}")

        # Convert lecture_id to integer for database queries
        lecture_int_id = lecture_id
        if IDConverter.is_uuid(lecture_id):
            lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
            if not lecture_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )
        elif isinstance(lecture_id, str):
            try:
                lecture_int_id = int(lecture_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid lecture_id format",
                )

        # Get lecture details using integer ID
        lecture_data = db.get_record_by_id("lecture", lecture_int_id)
        if not lecture_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )

        # Verify access
        teacher_int_id = teacher.id if isinstance(teacher.id, int) else teacher.id
        if lecture_data.get("teacher_id") != teacher_int_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this lecture",
            )

        # Get audio content records using integer ID
        audio_records = db.get_records(
            "lecture_content",
            {"lecture_id": lecture_int_id, "file_type": "mp3"}
        )
        
        if not audio_records:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No audio found for this lecture",
            )

        deleted_count = 0
        for audio_record in audio_records:
            # Delete from storage
            try:
                storage_path = audio_record.get("storage_path")
                bucket_name = audio_record.get("storage_bucket")
                if storage_path and bucket_name:
                    supabase.delete_file(bucket_name, storage_path)
            except Exception as e:
                logger.warning(f"Could not delete audio file from storage: {e}")
            
            # Delete the record
            db.delete_record("lecture_content", audio_record["id"])
            deleted_count += 1

        logger.info(f"Deleted {deleted_count} audio file(s) for lecture {lecture_id}")

        return {
            "message": "Audio deleted successfully",
            "lecture_id": lecture_id,
            "deleted_count": deleted_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting audio for lecture: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting audio",
        )


@router.get("/audio/voices")
async def get_available_voices():
    """
    Get list of available TTS voices and models.
    
    Returns ElevenLabs voice and model options for the audio generation feature.
    
    Voices include popular pre-made voices like George (British narrator),
    Rachel (professional female), Brian (deep narrator), and many more.
    
    Models:
    - eleven_multilingual_v2: Best quality, 29 languages, stable for long-form
    - eleven_flash_v2_5: Fastest, 32 languages, lowest cost
    - eleven_turbo_v2_5: Balanced quality and speed
    """
    from services.audio_service import AudioService
    return {
        "voices": AudioService.get_available_voices(),
        "default_voice": AudioService.DEFAULT_VOICE,
        "models": AudioService.get_available_models(),
        "default_model": AudioService.DEFAULT_MODEL,
        "provider": "elevenlabs",
    }


# Import and include the router in the lecture_router from routes_config
from routes_config import lecture_router as main_lecture_router

main_lecture_router.include_router(router)
