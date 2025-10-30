# student/routes.py
"""
Student-facing API routes for course enrollment, lecture viewing, 
chatbot interaction, and quiz generation.
"""

import json
from datetime import datetime
from typing import Annotated, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

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
from services.embedding_service import EmbeddingService
from services.quiz_service import QuizService
from services.rag_service import RAGService
from utils.db import get_db

router = APIRouter()


# ==================== Dependencies ====================


async def require_student(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> tuple[User, Student]:
    """
    Dependency to ensure the user is a student and fetch their student profile.
    """
    if user.role not in [UserRole.STUDENT, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only accessible to students",
        )
    
    # Get student profile
    try:
        student_result = (
            db.admin_client.table("student")
            .select("*")
            .eq("user_id", str(user.id))
            .execute()
        )
        
        if not student_result.data or len(student_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student profile not found. Please contact administrator.",
            )
        
        student_data = student_result.data[0]
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
        
        # Find the course by code
        course_result = (
            db.admin_client.table("course")
            .select("*")
            .eq("code", request.course_code.upper())
            .eq("university_id", str(student.university_id))
            .execute()
        )
        
        if not course_result.data or len(course_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Course with code '{request.course_code}' not found at your university",
            )
        
        course = course_result.data[0]
        course_id = course["id"]
        
        # Check if already enrolled
        existing_enrollment = (
            db.admin_client.table("enrollment")
            .select("*")
            .eq("student_id", str(student.id))
            .eq("course_id", course_id)
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
        if not semester_id:
            # Get the most recent semester for this course
            semester_result = (
                db.admin_client.table("semester")
                .select("*")
                .eq("course_id", course_id)
                .order("start_date", desc=True)
                .limit(1)
                .execute()
            )
            
            if semester_result.data and len(semester_result.data) > 0:
                semester_id = semester_result.data[0]["id"]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No active semester found for this course. Please contact your instructor.",
                )
        
        # Create enrollment
        enrollment_data = {
            "id": str(uuid4()),
            "student_id": str(student.id),
            "course_id": course_id,
            "semester_id": semester_id,
            "enrolled_at": datetime.utcnow().isoformat(),
            "is_active": True,
        }
        
        result = db.admin_client.table("enrollment").insert(enrollment_data).execute()
        
        logger.info(f"Student {student.id} successfully enrolled in course {course_id}")
        
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


@router.get("/my-courses", response_model=List[StudentCourseInfo])
async def get_my_courses(
    user_student: Annotated[tuple[User, Student], Depends(require_student)],
    db=Depends(get_db),
):
    """
    Get all courses the student is enrolled in.
    
    Returns course information including teacher name and lecture counts.
    Format: "Course Name - Teacher Name"
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching courses for student {student.id}")
        
        # Get all active enrollments for this student
        enrollments_result = (
            db.admin_client.table("enrollment")
            .select("*, course(*)")
            .eq("student_id", str(student.id))
            .eq("is_active", True)
            .order("enrolled_at", desc=True)
            .execute()
        )
        
        if not enrollments_result.data:
            logger.info(f"No enrollments found for student {student.id}")
            return []
        
        courses = []
        for enrollment in enrollments_result.data:
            course = enrollment.get("course", {})
            course_id = course.get("id")
            
            if not course_id:
                continue
            
            # Get lectures for this course
            lectures_result = (
                db.admin_client.table("lecture")
                .select("id, status, teacher_id")
                .eq("course_id", course_id)
                .execute()
            )
            
            total_lectures = len(lectures_result.data) if lectures_result.data else 0
            published_lectures = sum(
                1 for l in (lectures_result.data or [])
                if l.get("status") in ["PUBLISHED", "DELIVERED"]
            )
            
            # Get teacher name from first lecture
            teacher_name = "Unknown Teacher"
            if lectures_result.data and len(lectures_result.data) > 0:
                teacher_id = lectures_result.data[0].get("teacher_id")
                if teacher_id:
                    teacher_result = (
                        db.admin_client.table("teacher")
                        .select("*, users(*)")
                        .eq("id", teacher_id)
                        .limit(1)
                        .execute()
                    )
                    
                    if teacher_result.data:
                        user_data = teacher_result.data[0].get("users", {})
                        if user_data:
                            first_name = user_data.get("first_name", "")
                            last_name = user_data.get("last_name", "")
                            teacher_name = f"{first_name} {last_name}".strip() or "Unknown Teacher"
            
            course_info = StudentCourseInfo(
                course_id=course_id,
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
        
        logger.info(f"Found {len(courses)} courses for student {student.id}")
        return courses
    
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
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching lectures for course {course_id}, student {student.id}")
        
        # Verify student is enrolled in this course
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("*")
            .eq("student_id", str(student.id))
            .eq("course_id", course_id)
            .eq("is_active", True)
            .execute()
        )
        
        if not enrollment_result.data or len(enrollment_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Get course information with teacher
        course_result = (
            db.admin_client.table("course")
            .select("*, lecture!inner(teacher_id, teacher!inner(user_id, users!inner(first_name, last_name)))")
            .eq("id", course_id)
            .limit(1)
            .execute()
        )
        
        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        
        course = course_result.data[0]
        
        # Get teacher name (from first lecture's teacher)
        teacher_name = "Unknown Teacher"
        if course.get("lecture") and len(course["lecture"]) > 0:
            teacher_data = course["lecture"][0].get("teacher", {})
            if teacher_data:
                user_data = teacher_data.get("users", {})
                teacher_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        
        # Get all published lectures for this course
        lectures_result = (
            db.admin_client.table("lecture")
            .select("id, title, description, summary, chapter, status, created_at, has_embeddings")
            .eq("course_id", course_id)
            .in_("status", ["PUBLISHED", "DELIVERED"])
            .order("created_at", desc=False)
            .execute()
        )
        
        lectures = []
        for lecture_data in lectures_result.data if lectures_result.data else []:
            lecture_info = StudentLectureInfo(
                lecture_id=lecture_data["id"],
                title=lecture_data["title"],
                description=lecture_data.get("description"),
                summary=lecture_data.get("summary"),
                chapter=lecture_data.get("chapter"),
                status=lecture_data["status"],
                created_at=lecture_data["created_at"],
                has_embeddings=lecture_data.get("has_embeddings", False),
            )
            lectures.append(lecture_info)
        
        # Build response
        course_info = StudentCourseInfo(
            course_id=course["id"],
            course_code=course["code"],
            course_name=course["name"],
            course_description=course.get("description"),
            teacher_name=teacher_name,
            display_name=f"{course['name']} - {teacher_name}",
            enrolled_at=enrollment_result.data[0]["enrolled_at"],
            total_lectures=len(lectures),
            published_lectures=len(lectures),
        )
        
        response = StudentCourseLecturesResponse(
            course_info=course_info,
            lectures=lectures,
            total_count=len(lectures),
        )
        
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
        lecture_result = (
            db.admin_client.table("lecture")
            .select("*, course!inner(id)")
            .eq("id", lecture_id)
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
        }).eq("id", lecture_id).execute()
        
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
        
        # Verify lecture access and enrollment
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, title, content, has_embeddings, course_id")
            .eq("id", lecture_id)
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
        
        # Verify student is enrolled in the course
        enrollment_result = (
            db.admin_client.table("enrollment")
            .select("*")
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
        
        logger.info(f"Chat request for lecture {lecture_id}, student {student.id}")
        
        # Verify lecture access (same as summary endpoint)
        lecture_result = (
            db.admin_client.table("lecture")
            .select("*, course!inner(id)")
            .eq("id", lecture_id)
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
        
        # Get or create conversation
        if not session_id:
            session_id = str(uuid4())
        
        conversation_result = (
            db.admin_client.table("ai_conversation")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", str(user.id))
            .eq("lecture_id", lecture_id)
            .execute()
        )
        
        if not conversation_result.data:
            # Create new conversation
            conversation_data = {
                "id": str(uuid4()),
                "user_id": str(user.id),
                "lecture_id": lecture_id,
                "conversation_type": "LECTURE_QA",
                "session_id": session_id,
                "title": f"Chat about {lecture['title'][:50]}",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            conversation_result = db.admin_client.table("ai_conversation").insert(conversation_data).execute()
            conversation_id = conversation_result.data[0]["id"]
        else:
            conversation_id = conversation_result.data[0]["id"]
        
        # Save user message
        user_msg_data = {
            "id": str(uuid4()),
            "conversation_id": conversation_id,
            "role": "USER",
            "content": user_message,
            "created_at": datetime.utcnow().isoformat(),
        }
        db.admin_client.table("chat_message").insert(user_msg_data).execute()
        
        # Use RAG service to get response
        rag_service = RAGService(db)
        response = await rag_service.generate_response(
            lecture_id=lecture_id,
            query=user_message,
            conversation_id=conversation_id,
        )
        
        # Save assistant message
        assistant_msg_data = {
            "id": str(uuid4()),
            "conversation_id": conversation_id,
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
        
        return {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "response": response["answer"],
            "sources": response.get("sources", []),
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
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching flashcards for lecture {lecture_id}, student {student.id}")
        
        # Verify lecture access
        lecture_result = (
            db.admin_client.table("lecture")
            .select("*, course!inner(id)")
            .eq("id", lecture_id)
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
        
        # Get flashcards for this lecture
        flashcards_result = (
            db.admin_client.table("flashcard")
            .select("*")
            .eq("lecture_id", lecture_id)
            .order("order_index")
            .execute()
        )
        
        if not flashcards_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No flashcards available for this lecture yet. They may still be generating.",
            )
        
        flashcards = []
        for card in flashcards_result.data:
            flashcards.append({
                "id": card["id"],
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
        
        return {
            "lecture_id": lecture_id,
            "lecture_title": lecture.get("title"),
            "total_flashcards": len(flashcards),
            "by_difficulty": difficulties,
            "by_topic": topics,
            "flashcards": flashcards,
        }
    
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
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching saved quiz for lecture {lecture_id}, student {student.id}")
        
        # Verify lecture access
        lecture_result = (
            db.admin_client.table("lecture")
            .select("*, course!inner(id, name), teacher!inner(id)")
            .eq("id", lecture_id)
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
        
        # Get default quiz for this lecture
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*")
            .eq("lecture_id", lecture_id)
            .eq("is_default", True)
            .execute()
        )
        
        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No quiz available for this lecture yet. It may still be generating.",
            )
        
        assessment = assessment_result.data[0]
        
        # Get questions
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment["id"])
            .order("order_index")
            .execute()
        )
        
        questions = []
        for q in questions_result.data:
            questions.append({
                "question_id": q["id"],
                "question_text": q["question_text"],
                "question_type": q["question_type"],
                "points": q.get("points", 1.0),
                "options": json.loads(q.get("options", "[]")),
                "explanation": q.get("explanation"),
            })
        
        return {
            "assessment_id": assessment["id"],
            "title": assessment["title"],
            "description": assessment.get("description"),
            "num_questions": len(questions),
            "time_limit": assessment.get("time_limit", 30),
            "max_attempts": assessment.get("max_attempts", 3),
            "passing_score": assessment.get("passing_score", 60.0),
            "is_default": True,
            "questions": questions,
        }
    
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
        lecture_result = (
            db.admin_client.table("lecture")
            .select("*, course!inner(id, name), teacher!inner(id)")
            .eq("id", lecture_id)
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
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(id, course_id)")
            .eq("id", assessment_id)
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
        
        # Get questions
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_id)
            .order("order_index")
            .execute()
        )
        
        questions = questions_result.data
        
        # Grade the submission
        quiz_service = QuizService(db)
        grading_result = quiz_service.grade_submission(
            questions=questions,
            student_answers=submission.get("answers", {}),
        )
        
        # Create submission record
        submission_id = str(uuid4())
        submission_data = {
            "id": submission_id,
            "assessment_id": assessment_id,
            "student_id": str(student.id),
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
        db.admin_client.table("assessment_submission").insert(submission_data).execute()
        
        # Calculate percentage and weak areas
        percentage = (grading_result["score"] / grading_result["max_score"]) * 100 if grading_result["max_score"] > 0 else 0
        weak_areas = [item["topic"] for item in grading_result.get("weak_areas", [])]
        
        # Add quiz results to chat history
        # Find or create conversation for this lecture
        conversation_result = (
            db.admin_client.table("ai_conversation")
            .select("*")
            .eq("user_id", str(user.id))
            .eq("lecture_id", lecture_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        
        if conversation_result.data:
            conversation_id = conversation_result.data[0]["id"]
            
            # Create system message with quiz results
            
            quiz_result_message = f"""
Quiz Results:
- Score: {grading_result['score']}/{grading_result['max_score']} ({percentage:.1f}%)
- Questions Correct: {grading_result['correct_count']}/{grading_result['total_questions']}
- Topics to Review: {', '.join(weak_areas) if weak_areas else 'None - Great job!'}

I'm here to help you understand any topics you found challenging. Feel free to ask questions about: {', '.join(weak_areas) if weak_areas else 'anything from the lecture'}.
            """.strip()
            
            quiz_metadata = {
                "assessment_id": assessment_id,
                "submission_id": submission_id,
                "score": grading_result["score"],
                "max_score": grading_result["max_score"],
                "percentage": percentage,
                "weak_areas": weak_areas,
                "question_results": grading_result.get("question_results", []),
            }
            
            system_msg_data = {
                "id": str(uuid4()),
                "conversation_id": conversation_id,
                "role": "SYSTEM",
                "content": quiz_result_message,
                "message_metadata": json.dumps(quiz_metadata),
                "created_at": datetime.utcnow().isoformat(),
            }
            db.admin_client.table("chat_message").insert(system_msg_data).execute()
        
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
    session_id: Optional[str] = None,
    db=Depends(get_db),
):
    """
    Get chat history for a lecture conversation.
    
    Includes quiz results that were added to the chat history.
    """
    user, student = user_student
    
    try:
        logger.info(f"Fetching chat history for lecture {lecture_id}, student {student.id}")
        
        # Build query
        query = (
            db.admin_client.table("ai_conversation")
            .select("*, chat_message(*)")
            .eq("user_id", str(user.id))
            .eq("lecture_id", lecture_id)
        )
        
        if session_id:
            query = query.eq("session_id", session_id)
        
        result = query.order("created_at", desc=True).limit(1).execute()
        
        if not result.data:
            return {
                "conversation_id": None,
                "messages": [],
            }
        
        conversation = result.data[0]
        messages = conversation.get("chat_message", [])
        
        # Sort messages by created_at
        messages.sort(key=lambda x: x["created_at"])
        
        return {
            "conversation_id": conversation["id"],
            "session_id": conversation["session_id"],
            "messages": messages,
        }
    
    except Exception as e:
        logger.error(f"Error fetching chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching chat history",
        )


# Include router in main application
from routes_config import student_router as main_student_router

main_student_router.include_router(router)

