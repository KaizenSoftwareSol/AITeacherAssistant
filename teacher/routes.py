# teacher/routes.py
"""
Teacher-specific endpoints for accessing lecture resources.
These mirror student endpoints but are accessible to teachers with full access.
Teachers can view summary, flashcards, quiz (with correct answers), and all lecture resources.

CONSOLIDATED ENDPOINTS (reduce API calls):
- GET /dashboard - All data for teacher dashboard in ONE call
- GET /courses/{course_id}/full - Complete course details with lectures, enrollments, outline
- GET /lectures/{lecture_id}/full - Complete lecture with summary, quiz, flashcards, PDF
"""

import json
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dependencies import require_teacher
from logger import logger
from models.user import User
from utils.db import get_db

router = APIRouter()


# ==================== CONSOLIDATED ENDPOINTS ====================


@router.get("/dashboard")
async def get_teacher_dashboard(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Get ALL data needed for teacher dashboard in ONE API call.
    
    Returns:
    - courses: List of courses with enrollment counts
    - documents: List of documents with stats
    - lectures: List of lectures grouped by course
    - stats: Overall statistics
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching dashboard data for teacher {teacher.id}")

        # Get all courses for the university
        courses_result = (
            db.admin_client.table("course")
            .select("id, name, code, description, created_at")
            .eq("university_id", str(teacher.university_id))
            .order("created_at", desc=True)
            .execute()
        )
        
        courses = []
        total_students = 0
        
        for course in (courses_result.data or []):
            # Get enrollment count for this course
            enrollment_result = (
                db.admin_client.table("enrollment")
                .select("id, student_id")
                .eq("course_id", course["id"])
                .eq("is_active", True)
                .execute()
            )
            enrollment_count = len(enrollment_result.data) if enrollment_result.data else 0
            total_students += enrollment_count
            
            # Get lecture count for this course (by this teacher)
            lectures_result = (
                db.admin_client.table("lecture")
                .select("id, status")
                .eq("course_id", course["id"])
                .eq("teacher_id", teacher.id)
                .execute()
            )
            lecture_count = len(lectures_result.data) if lectures_result.data else 0
            published_count = sum(1 for l in (lectures_result.data or []) if l.get("status") in ["PUBLISHED", "DELIVERED"])
            
            courses.append({
                "id": course["id"],
                "name": course["name"],
                "code": course["code"],
                "description": course.get("description"),
                "created_at": course["created_at"],
                "enrollment_count": enrollment_count,
                "lecture_count": lecture_count,
                "published_lectures": published_count,
            })
        
        # Get all documents
        documents_result = (
            db.admin_client.table("documents")
            .select("id, title, document_type, status, file_size, created_at")
            .eq("teacher_id", teacher.id)
            .order("created_at", desc=True)
            .execute()
        )
        
        documents = []
        for doc in (documents_result.data or []):
            documents.append({
                "id": doc["id"],
                "title": doc["title"],
                "document_type": doc["document_type"],
                "status": doc["status"],
                "file_size": doc.get("file_size"),
                "created_at": doc["created_at"],
            })
        
        # Get all lectures by this teacher
        lectures_result = (
            db.admin_client.table("lecture")
            .select("id, title, status, course_id, topic, lecture_number, created_at")
            .eq("teacher_id", teacher.id)
            .order("created_at", desc=True)
            .execute()
        )
        
        lectures = []
        lectures_by_course = {}
        
        for lec in (lectures_result.data or []):
            lecture_info = {
                "id": lec["id"],
                "title": lec["title"],
                "status": lec["status"],
                "course_id": lec["course_id"],
                "topic": lec.get("topic"),
                "lecture_number": lec.get("lecture_number"),
                "created_at": lec["created_at"],
            }
            lectures.append(lecture_info)
            
            # Group by course
            course_id = lec["course_id"]
            if course_id not in lectures_by_course:
                lectures_by_course[course_id] = []
            lectures_by_course[course_id].append(lecture_info)
        
        # Calculate stats
        stats = {
            "total_courses": len(courses),
            "total_documents": len(documents),
            "total_lectures": len(lectures),
            "published_lectures": sum(1 for l in lectures if l["status"] in ["PUBLISHED", "DELIVERED"]),
            "draft_lectures": sum(1 for l in lectures if l["status"] == "DRAFT"),
            "total_students": total_students,
            "completed_documents": sum(1 for d in documents if d["status"] == "COMPLETED"),
            "pending_documents": sum(1 for d in documents if d["status"] in ["PENDING", "PROCESSING"]),
        }

        return {
            "teacher_id": str(teacher.id),
            "teacher_name": f"{current_user.first_name} {current_user.last_name}",
            "courses": courses,
            "documents": documents,
            "lectures": lectures,
            "lectures_by_course": lectures_by_course,
            "stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching teacher dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching dashboard data",
        )


@router.get("/documents/full")
async def get_all_documents_with_assignments(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Get ALL documents with their assignments in ONE API call.
    
    Returns:
    - documents: List of documents with their course assignments
    - stats: Document statistics
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching all documents with assignments for teacher {teacher.id}")

        # Get all documents
        documents_result = (
            db.admin_client.table("documents")
            .select("id, title, document_type, status, file_size, description, created_at, updated_at")
            .eq("teacher_id", teacher.id)
            .order("created_at", desc=True)
            .execute()
        )
        
        doc_ids = [doc["id"] for doc in (documents_result.data or [])]
        
        # Batch get all assignments for all documents
        assignments_by_doc = {}
        if doc_ids:
            assignments_result = (
                db.admin_client.table("document_assignment")
                .select("id, document_id, course_id, topic, created_at")
                .in_("document_id", doc_ids)
                .execute()
            )
            
            # Group assignments by document_id
            for a in (assignments_result.data or []):
                doc_id = a["document_id"]
                if doc_id not in assignments_by_doc:
                    assignments_by_doc[doc_id] = []
                assignments_by_doc[doc_id].append(a)
        
        # Get all courses for assignment details (batch query)
        course_ids = set()
        for assignments in assignments_by_doc.values():
            for a in assignments:
                course_ids.add(a["course_id"])
        
        course_map = {}
        if course_ids:
            courses_result = (
                db.admin_client.table("course")
                .select("id, name, code")
                .in_("id", list(course_ids))
                .execute()
            )
            course_map = {c["id"]: c for c in (courses_result.data or [])}
        
        # Build documents array with assignments
        documents = []
        for doc in (documents_result.data or []):
            doc_id = doc["id"]
            doc_assignments = assignments_by_doc.get(doc_id, [])
            
            # Enrich assignments with course info
            enriched_assignments = []
            for a in doc_assignments:
                course = course_map.get(a["course_id"], {})
                enriched_assignments.append({
                    "assignment_id": a["id"],
                    "course_id": a["course_id"],
                    "course_name": course.get("name", "Unknown"),
                    "course_code": course.get("code", "N/A"),
                    "topic": a.get("topic"),
                    "assigned_at": a["created_at"],
                })
            
            documents.append({
                "id": doc_id,
                "title": doc["title"],
                "document_type": doc["document_type"],
                "status": doc["status"],
                "file_size": doc.get("file_size"),
                "description": doc.get("description"),
                "created_at": doc["created_at"],
                "updated_at": doc.get("updated_at"),
                "assignment_count": len(enriched_assignments),
                "is_assigned": len(enriched_assignments) > 0,
                "assignments": enriched_assignments,
            })
        
        # Calculate stats
        stats = {
            "total_documents": len(documents),
            "completed": sum(1 for d in documents if d["status"] == "COMPLETED"),
            "processing": sum(1 for d in documents if d["status"] in ["PENDING", "PROCESSING"]),
            "failed": sum(1 for d in documents if d["status"] == "FAILED"),
            "assigned": sum(1 for d in documents if d["is_assigned"]),
            "unassigned": sum(1 for d in documents if not d["is_assigned"]),
            "total_assignments": sum(d["assignment_count"] for d in documents),
            "by_type": {},
        }
        
        # Count by document type
        for doc in documents:
            doc_type = doc["document_type"]
            stats["by_type"][doc_type] = stats["by_type"].get(doc_type, 0) + 1

        return {
            "teacher_id": str(teacher.id),
            "documents": documents,
            "stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching documents with assignments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching documents",
        )


@router.get("/courses/{course_id}/full")
async def get_course_full_details(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    db=Depends(get_db),
):
    """
    Get COMPLETE course details in ONE API call.
    
    Returns:
    - course: Course info with description
    - lectures: All lectures with quiz/flashcard status
    - enrollments: All enrolled students
    - outline: Course outline/curriculum
    - documents: Attached documents
    - stats: Course statistics
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching full course details for course {course_id}, teacher {teacher.id}")

        # Get course info
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code, description, curriculum_content, created_at, updated_at")
            .eq("id", course_id)
            .eq("university_id", str(teacher.university_id))
            .execute()
        )
        
        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        
        course = course_result.data[0]
        
        # Get all lectures for this course by this teacher
        lectures_result = (
            db.admin_client.table("lecture")
            .select("id, title, description, status, topic, lecture_number, summary, created_at, updated_at")
            .eq("course_id", course_id)
            .eq("teacher_id", teacher.id)
            .order("lecture_number", desc=False)
            .execute()
        )
        
        # Get lecture IDs for batch queries
        lecture_ids = [lec["id"] for lec in (lectures_result.data or [])]
        
        # Batch get assessments (quizzes) for all lectures
        quiz_by_lecture = {}
        if lecture_ids:
            assessments_result = (
                db.admin_client.table("assessment")
                .select("id, lecture_id, title")
                .in_("lecture_id", lecture_ids)
                .eq("is_default", True)
                .execute()
            )
            for a in (assessments_result.data or []):
                quiz_by_lecture[a["lecture_id"]] = a
        
        # Batch get flashcard counts
        flashcard_counts = {}
        if lecture_ids:
            flashcards_result = (
                db.admin_client.table("flashcard")
                .select("id, lecture_id")
                .in_("lecture_id", lecture_ids)
                .execute()
            )
            for f in (flashcards_result.data or []):
                lid = f["lecture_id"]
                flashcard_counts[lid] = flashcard_counts.get(lid, 0) + 1
        
        # Batch get lecture content (PDFs)
        pdf_by_lecture = {}
        if lecture_ids:
            content_result = (
                db.admin_client.table("lecture_content")
                .select("lecture_id, file_name, file_size, storage_bucket, storage_path")
                .in_("lecture_id", lecture_ids)
                .execute()
            )
            for c in (content_result.data or []):
                pdf_by_lecture[c["lecture_id"]] = c
        
        # Build lectures array with all info
        lectures = []
        for lec in (lectures_result.data or []):
            lid = lec["id"]
            quiz_info = quiz_by_lecture.get(lid)
            pdf_info = pdf_by_lecture.get(lid)
            
            # Generate PDF download URL if available
            pdf_download_url = None
            if pdf_info:
                try:
                    from supabase_config import supabase
                    if pdf_info.get("storage_bucket") and pdf_info.get("storage_path"):
                        bucket = supabase.get_storage_bucket(pdf_info["storage_bucket"])
                        pdf_download_url = bucket.get_public_url(pdf_info["storage_path"])
                except Exception:
                    pass
            
            lectures.append({
                "id": lid,
                "title": lec["title"],
                "description": lec.get("description"),
                "status": lec["status"],
                "topic": lec.get("topic"),
                "lecture_number": lec.get("lecture_number"),
                "has_summary": bool(lec.get("summary")),
                "summary_preview": (lec.get("summary", "")[:150] + "...") if lec.get("summary") and len(lec.get("summary", "")) > 150 else lec.get("summary"),
                "has_quiz": quiz_info is not None,
                "quiz_title": quiz_info["title"] if quiz_info else None,
                "flashcard_count": flashcard_counts.get(lid, 0),
                "has_flashcards": flashcard_counts.get(lid, 0) > 0,
                "has_pdf": pdf_info is not None,
                "pdf_file_name": pdf_info["file_name"] if pdf_info else None,
                "pdf_file_size": pdf_info["file_size"] if pdf_info else None,
                "pdf_download_url": pdf_download_url,
                "created_at": lec["created_at"],
                "updated_at": lec.get("updated_at"),
            })
        
        # Get enrollments
        enrollments_result = (
            db.admin_client.table("enrollment")
            .select("id, student_id, enrolled_at, is_active")
            .eq("course_id", course_id)
            .eq("is_active", True)
            .order("enrolled_at", desc=True)
            .execute()
        )
        
        # Get student details for enrollments
        students = []
        student_ids = [e["student_id"] for e in (enrollments_result.data or [])]
        if student_ids:
            students_result = (
                db.admin_client.table("student")
                .select("id, student_id_number, user_id")
                .in_("id", student_ids)
                .execute()
            )
            
            student_map = {s["id"]: s for s in (students_result.data or [])}
            
            # Get user details
            user_ids = [s["user_id"] for s in (students_result.data or [])]
            if user_ids:
                users_result = (
                    db.admin_client.table("users")
                    .select("id, first_name, last_name, email")
                    .in_("id", user_ids)
                    .execute()
                )
                user_map = {u["id"]: u for u in (users_result.data or [])}
                
                for enrollment in (enrollments_result.data or []):
                    student = student_map.get(enrollment["student_id"], {})
                    user = user_map.get(student.get("user_id"), {})
                    students.append({
                        "enrollment_id": enrollment["id"],
                        "student_id": enrollment["student_id"],
                        "student_id_number": student.get("student_id_number"),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                        "email": user.get("email"),
                        "enrolled_at": enrollment["enrolled_at"],
                    })
        
        # Get attached documents (if any document assignment exists)
        documents = []
        try:
            doc_assignment_result = (
                db.admin_client.table("document_assignment")
                .select("document_id")
                .eq("course_id", course_id)
                .execute()
            )
            doc_ids = [d["document_id"] for d in (doc_assignment_result.data or [])]
            if doc_ids:
                docs_result = (
                    db.admin_client.table("documents")
                    .select("id, title, document_type, status")
                    .in_("id", doc_ids)
                    .execute()
                )
                documents = docs_result.data or []
        except Exception:
            # Table might not exist yet
            pass
        
        # Calculate stats
        stats = {
            "total_lectures": len(lectures),
            "published_lectures": sum(1 for l in lectures if l["status"] in ["PUBLISHED", "DELIVERED"]),
            "draft_lectures": sum(1 for l in lectures if l["status"] == "DRAFT"),
            "generated_lectures": sum(1 for l in lectures if l["status"] == "GENERATED"),
            "total_students": len(students),
            "lectures_with_quiz": sum(1 for l in lectures if l["has_quiz"]),
            "lectures_with_flashcards": sum(1 for l in lectures if l["has_flashcards"]),
            "attached_documents": len(documents),
        }
        
        return {
            "course": {
                "id": course["id"],
                "name": course["name"],
                "code": course["code"],
                "description": course.get("description"),
                "curriculum_content": course.get("curriculum_content"),
                "created_at": course["created_at"],
                "updated_at": course.get("updated_at"),
            },
            "lectures": lectures,
            "students": students,
            "documents": documents,
            "stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching full course details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching course details",
        )


@router.get("/lectures/{lecture_id}/full")
async def get_lecture_full_details(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Get COMPLETE lecture details in ONE API call.
    
    Returns:
    - lecture: Full lecture info with content
    - summary: Full summary (if available)
    - pdf: PDF info with download URL
    - quiz: Full quiz with questions and answers
    - flashcards: All flashcards
    - plan: Lecture plan (if available)
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching full lecture details for lecture {lecture_id}, teacher {teacher.id}")

        # Get lecture with all fields
        lecture_result = (
            db.admin_client.table("lecture")
            .select("*")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )
        
        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )
        
        lecture = lecture_result.data[0]
        
        # Get course info
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .eq("id", lecture["course_id"])
            .execute()
        )
        course_info = course_result.data[0] if course_result.data else None
        
        # Get PDF info
        pdf_info = None
        content_result = (
            db.admin_client.table("lecture_content")
            .select("*")
            .eq("lecture_id", lecture_id)
            .execute()
        )
        if content_result.data:
            lc = content_result.data[0]
            pdf_info = {
                "file_name": lc.get("file_name"),
                "file_size": lc.get("file_size"),
                "content_type": lc.get("content_type"),
                "storage_bucket": lc.get("storage_bucket"),
                "storage_path": lc.get("storage_path"),
            }
            try:
                from supabase_config import supabase
                if lc.get("storage_bucket") and lc.get("storage_path"):
                    bucket = supabase.get_storage_bucket(lc["storage_bucket"])
                    pdf_info["download_url"] = bucket.get_public_url(lc["storage_path"])
            except Exception as e:
                logger.warning(f"Could not get PDF download URL: {e}")
        
        # Get quiz with questions
        quiz = None
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*")
            .eq("lecture_id", lecture_id)
            .eq("is_default", True)
            .execute()
        )
        if assessment_result.data:
            assessment = assessment_result.data[0]
            questions_result = (
                db.admin_client.table("question")
                .select("*")
                .eq("assessment_id", assessment["id"])
                .order("order_index")
                .execute()
            )
            
            questions = []
            for q in (questions_result.data or []):
                questions.append({
                    "id": q["id"],
                    "question_text": q["question_text"],
                    "question_type": q.get("question_type", "MULTIPLE_CHOICE"),
                    "points": q.get("points", 1.0),
                    "options": json.loads(q.get("options", "[]")),
                    "correct_answer": q["correct_answer"],
                    "explanation": q.get("explanation"),
                })
            
            quiz = {
                "id": assessment["id"],
                "title": assessment["title"],
                "description": assessment.get("description"),
                "time_limit": assessment.get("time_limit", 30),
                "max_attempts": assessment.get("max_attempts", 3),
                "passing_score": assessment.get("passing_score", 60.0),
                "questions_count": len(questions),
                "questions": questions,
                "created_at": assessment.get("created_at"),
            }
        
        # Get flashcards
        flashcards_result = (
            db.admin_client.table("flashcard")
            .select("*")
            .eq("lecture_id", lecture_id)
            .order("order_index")
            .execute()
        )
        
        flashcards = []
        flashcard_stats = {"EASY": 0, "MEDIUM": 0, "HARD": 0}
        for card in (flashcards_result.data or []):
            diff = card.get("difficulty", "MEDIUM")
            flashcards.append({
                "id": card["id"],
                "question": card["question"],
                "answer": card["answer"],
                "difficulty": diff,
                "topic": card.get("topic", "General"),
            })
            flashcard_stats[diff] = flashcard_stats.get(diff, 0) + 1
        
        # Get lecture plan (if exists)
        plan = None
        try:
            plan_result = (
                db.admin_client.table("lecture_plan")
                .select("*")
                .eq("lecture_id", lecture_id)
                .execute()
            )
            if plan_result.data:
                plan = plan_result.data[0]
        except Exception:
            pass
        
        return {
            "lecture": {
                "id": lecture["id"],
                "title": lecture["title"],
                "description": lecture.get("description"),
                "status": lecture["status"],
                "topic": lecture.get("topic"),
                "lecture_number": lecture.get("lecture_number"),
                "chapter": lecture.get("chapter"),
                "learning_outcomes": lecture.get("learning_outcomes"),
                "content": lecture.get("content"),
                "created_at": lecture["created_at"],
                "updated_at": lecture.get("updated_at"),
            },
            "course": course_info,
            "summary": {
                "has_summary": bool(lecture.get("summary")),
                "content": lecture.get("summary"),
            },
            "pdf": pdf_info,
            "quiz": quiz,
            "flashcards": {
                "count": len(flashcards),
                "by_difficulty": flashcard_stats,
                "items": flashcards,
            },
            "plan": plan,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching full lecture details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching lecture details",
        )


@router.get("/lectures/{lecture_id}/documents")
async def get_lecture_documents(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Get all documents associated with a lecture.
    
    Returns:
    - source_document: The document used to generate this lecture
    - course_documents: Documents assigned to the course this lecture belongs to
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching documents for lecture {lecture_id}, teacher {teacher.id}")

        # Get lecture with document_id and course_id
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, title, document_id, course_id, topic")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )
        
        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )
        
        lecture = lecture_result.data[0]
        
        # Get source document (the document used to generate this lecture)
        source_document = None
        if lecture.get("document_id"):
            doc_result = (
                db.admin_client.table("documents")
                .select("id, title, document_type, status, file_size, created_at")
                .eq("id", lecture["document_id"])
                .execute()
            )
            if doc_result.data:
                source_document = doc_result.data[0]
        
        # Get all documents assigned to the course
        course_documents = []
        if lecture.get("course_id"):
            # Get document assignments for this course
            assignments_result = (
                db.admin_client.table("document_assignment")
                .select("document_id, topic, created_at")
                .eq("course_id", lecture["course_id"])
                .execute()
            )
            
            if assignments_result.data:
                doc_ids = [a["document_id"] for a in assignments_result.data]
                assignment_map = {
                    a["document_id"]: a for a in assignments_result.data
                }
                
                # Get document details
                docs_result = (
                    db.admin_client.table("documents")
                    .select("id, title, document_type, status, file_size, created_at")
                    .in_("id", doc_ids)
                    .execute()
                )
                
                for doc in (docs_result.data or []):
                    assignment = assignment_map.get(doc["id"], {})
                    course_documents.append({
                        "id": doc["id"],
                        "title": doc["title"],
                        "document_type": doc["document_type"],
                        "status": doc["status"],
                        "file_size": doc.get("file_size"),
                        "created_at": doc["created_at"],
                        "assigned_topic": assignment.get("topic"),
                        "assigned_at": assignment.get("created_at"),
                    })
        
        # Filter course documents by lecture topic if available
        topic_documents = []
        other_documents = []
        lecture_topic = lecture.get("topic")
        
        for doc in course_documents:
            if lecture_topic and doc.get("assigned_topic") == lecture_topic:
                topic_documents.append(doc)
            else:
                other_documents.append(doc)
        
        return {
            "lecture_id": lecture_id,
            "lecture_title": lecture.get("title"),
            "lecture_topic": lecture_topic,
            "source_document": source_document,
            "course_documents": {
                "total": len(course_documents),
                "matching_topic": topic_documents,
                "other": other_documents,
                "all": course_documents,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lecture documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching lecture documents",
        )


# ==================== INDIVIDUAL RESOURCE ENDPOINTS ====================


@router.get("/lectures/{lecture_id}/summary")
async def get_lecture_summary(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Get summary for a lecture (teacher access).
    
    Returns: {
        lecture_id, lecture_title, summary (markdown), 
        generated_at, status, has_summary
    }
    
    Teachers can access summaries for their own lectures.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching summary for lecture {lecture_id}, teacher {teacher.id}")

        # Get lecture and verify ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, title, summary, status, created_at, updated_at")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        lecture = lecture_result.data[0]
        summary = lecture.get("summary")
        has_summary = summary is not None and len(summary) > 0

        return {
            "lecture_id": lecture_id,
            "lecture_title": lecture.get("title"),
            "summary": summary,
            "has_summary": has_summary,
            "status": lecture.get("status"),
            "generated_at": lecture.get("updated_at", lecture["created_at"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lecture summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching lecture summary",
        )


@router.get("/lectures/{lecture_id}/flashcards")
async def get_lecture_flashcards(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Get flashcards for a lecture (teacher access).
    
    Returns: {
        lecture_id, lecture_title, total_flashcards,
        by_difficulty, by_topic, flashcards[{id, question, answer, difficulty, topic, order_index}]
    }
    
    Teachers can access flashcards for their own lectures.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching flashcards for lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, title, status")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        lecture = lecture_result.data[0]

        # Get flashcards for this lecture
        flashcards_result = (
            db.admin_client.table("flashcard")
            .select("*")
            .eq("lecture_id", lecture_id)
            .order("order_index")
            .execute()
        )

        flashcards = []
        difficulties = {}
        topics = {}
        
        for card in (flashcards_result.data or []):
            diff = card.get("difficulty", "MEDIUM")
            topic = card.get("topic", "General")
            
            flashcards.append({
                "id": card["id"],
                "question": card["question"],
                "answer": card["answer"],
                "difficulty": diff,
                "topic": topic,
                "order_index": card.get("order_index", 0),
            })
            
            # Count by difficulty and topic
            difficulties[diff] = difficulties.get(diff, 0) + 1
            topics[topic] = topics.get(topic, 0) + 1

        return {
            "lecture_id": lecture_id,
            "lecture_title": lecture.get("title"),
            "lecture_status": lecture.get("status"),
            "total_flashcards": len(flashcards),
            "has_flashcards": len(flashcards) > 0,
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
            detail="Error fetching flashcards",
        )


@router.get("/lectures/{lecture_id}/quiz")
async def get_lecture_quiz(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Get quiz for a lecture (teacher access).
    
    Returns: {
        assessment_id, title, description, num_questions, 
        time_limit, max_attempts, passing_score, is_default,
        questions[{ question_id, question_text, question_type, points, options[], correct_answer, explanation }]
    }
    
    Teachers get full quiz with correct answers and explanations.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching quiz for lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, title, status")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        lecture = lecture_result.data[0]

        # Get default quiz for this lecture
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*")
            .eq("lecture_id", lecture_id)
            .eq("is_default", True)
            .execute()
        )

        if not assessment_result.data:
            return {
                "lecture_id": lecture_id,
                "lecture_title": lecture.get("title"),
                "lecture_status": lecture.get("status"),
                "has_quiz": False,
                "message": "No quiz available for this lecture yet. Quiz is generated when the lecture is published.",
            }

        assessment = assessment_result.data[0]

        # Get questions with all details (including correct answers for teachers)
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment["id"])
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
                "correct_answer": q["correct_answer"],
                "explanation": q.get("explanation"),
                "order_index": q.get("order_index", 0),
            })

        return {
            "lecture_id": lecture_id,
            "lecture_title": lecture.get("title"),
            "lecture_status": lecture.get("status"),
            "has_quiz": True,
            "assessment_id": assessment["id"],
            "title": assessment["title"],
            "description": assessment.get("description"),
            "num_questions": len(questions),
            "time_limit": assessment.get("time_limit", 30),
            "max_attempts": assessment.get("max_attempts", 3),
            "passing_score": assessment.get("passing_score", 60.0),
            "is_default": assessment.get("is_default", True),
            "created_at": assessment.get("created_at"),
            "questions": questions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching quiz",
        )


@router.get("/lectures/{lecture_id}/resources")
async def get_lecture_resources(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    db=Depends(get_db),
):
    """
    Get all resources for a lecture (summary, flashcards, quiz) in one call.
    
    Useful for the teacher dashboard to show lecture details at a glance.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching all resources for lecture {lecture_id}, teacher {teacher.id}")

        # Get lecture details
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, title, summary, status, content, description, learning_outcomes, created_at, updated_at")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        lecture = lecture_result.data[0]

        # Get lecture content (PDF info)
        lecture_content_result = (
            db.admin_client.table("lecture_content")
            .select("file_name, file_size, storage_bucket, storage_path")
            .eq("lecture_id", lecture_id)
            .execute()
        )
        
        pdf_info = None
        if lecture_content_result.data:
            lc = lecture_content_result.data[0]
            pdf_info = {
                "file_name": lc.get("file_name"),
                "file_size": lc.get("file_size"),
                "storage_bucket": lc.get("storage_bucket"),
                "storage_path": lc.get("storage_path"),
            }
            # Generate download URL
            try:
                from supabase_config import supabase
                if lc.get("storage_bucket") and lc.get("storage_path"):
                    bucket = supabase.get_storage_bucket(lc["storage_bucket"])
                    pdf_info["download_url"] = bucket.get_public_url(lc["storage_path"])
            except Exception as e:
                logger.warning(f"Could not get PDF download URL: {e}")

        # Get flashcards count
        flashcards_result = (
            db.admin_client.table("flashcard")
            .select("id")
            .eq("lecture_id", lecture_id)
            .execute()
        )
        flashcards_count = len(flashcards_result.data) if flashcards_result.data else 0

        # Get quiz info
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title")
            .eq("lecture_id", lecture_id)
            .eq("is_default", True)
            .execute()
        )
        has_quiz = len(assessment_result.data) > 0 if assessment_result.data else False
        quiz_title = assessment_result.data[0]["title"] if has_quiz else None

        # Check if quiz has questions
        quiz_questions_count = 0
        if has_quiz:
            questions_result = (
                db.admin_client.table("question")
                .select("id")
                .eq("assessment_id", assessment_result.data[0]["id"])
                .execute()
            )
            quiz_questions_count = len(questions_result.data) if questions_result.data else 0

        return {
            "lecture_id": lecture_id,
            "lecture_title": lecture.get("title"),
            "lecture_status": lecture.get("status"),
            "description": lecture.get("description"),
            "learning_outcomes": lecture.get("learning_outcomes"),
            "created_at": lecture.get("created_at"),
            "updated_at": lecture.get("updated_at"),
            # Summary info
            "has_summary": bool(lecture.get("summary")),
            "summary_preview": lecture.get("summary", "")[:200] + "..." if lecture.get("summary") and len(lecture.get("summary", "")) > 200 else lecture.get("summary"),
            # PDF info
            "pdf_info": pdf_info,
            # Flashcards info
            "has_flashcards": flashcards_count > 0,
            "flashcards_count": flashcards_count,
            # Quiz info
            "has_quiz": has_quiz,
            "quiz_title": quiz_title,
            "quiz_questions_count": quiz_questions_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lecture resources: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching lecture resources",
        )


@router.get("/courses/{course_id}/lectures")
async def get_course_lectures_for_teacher(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    status_filter: str | None = None,
    db=Depends(get_db),
):
    """
    Get all lectures for a specific course (teacher access).
    
    Teachers can see all lectures for their courses including draft and generated ones.
    Optional status_filter: DRAFT, GENERATED, PUBLISHED, DELIVERED
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching lectures for course {course_id}, teacher {teacher.id}")

        # Build query
        query = (
            db.admin_client.table("lecture")
            .select("id, title, description, status, topic, lecture_number, created_at, updated_at")
            .eq("course_id", course_id)
            .eq("teacher_id", teacher.id)
        )

        if status_filter:
            query = query.eq("status", status_filter.upper())

        lectures_result = query.order("created_at", desc=False).execute()

        if not lectures_result.data:
            return {
                "course_id": course_id,
                "lectures": [],
                "total_count": 0,
            }

        # Get additional info for each lecture
        lectures = []
        for lec in lectures_result.data:
            # Check for quiz and flashcards
            assessment_result = (
                db.admin_client.table("assessment")
                .select("id")
                .eq("lecture_id", lec["id"])
                .eq("is_default", True)
                .execute()
            )
            
            flashcards_result = (
                db.admin_client.table("flashcard")
                .select("id")
                .eq("lecture_id", lec["id"])
                .execute()
            )

            lectures.append({
                "lecture_id": lec["id"],
                "title": lec["title"],
                "description": lec.get("description"),
                "status": lec["status"],
                "topic": lec.get("topic"),
                "lecture_number": lec.get("lecture_number"),
                "created_at": lec["created_at"],
                "updated_at": lec.get("updated_at"),
                "has_quiz": len(assessment_result.data) > 0 if assessment_result.data else False,
                "has_flashcards": len(flashcards_result.data) > 0 if flashcards_result.data else False,
            })

        # Group by status
        by_status = {}
        for lec in lectures:
            s = lec["status"]
            if s not in by_status:
                by_status[s] = []
            by_status[s].append(lec)

        return {
            "course_id": course_id,
            "lectures": lectures,
            "total_count": len(lectures),
            "by_status": by_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching course lectures: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching course lectures",
        )


@router.get("/courses/{course_id}/quizzes")
async def get_course_quizzes(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    db=Depends(get_db),
):
    """
    Get all quizzes for published lectures in a course.
    
    Allows teachers to view quizzes by selecting a published lecture.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching quizzes for course {course_id}, teacher {teacher.id}")

        # Get published lectures with quizzes
        lectures_result = (
            db.admin_client.table("lecture")
            .select("id, title, status, topic, lecture_number")
            .eq("course_id", course_id)
            .eq("teacher_id", teacher.id)
            .in_("status", ["PUBLISHED", "DELIVERED"])
            .order("created_at", desc=False)
            .execute()
        )

        if not lectures_result.data:
            return {
                "course_id": course_id,
                "lectures_with_quizzes": [],
                "total_count": 0,
            }

        lectures_with_quizzes = []
        for lec in lectures_result.data:
            # Get quiz for this lecture
            assessment_result = (
                db.admin_client.table("assessment")
                .select("id, title, created_at")
                .eq("lecture_id", lec["id"])
                .eq("is_default", True)
                .execute()
            )

            if assessment_result.data:
                assessment = assessment_result.data[0]
                
                # Get question count
                questions_result = (
                    db.admin_client.table("question")
                    .select("id")
                    .eq("assessment_id", assessment["id"])
                    .execute()
                )

                lectures_with_quizzes.append({
                    "lecture_id": lec["id"],
                    "lecture_title": lec["title"],
                    "lecture_status": lec["status"],
                    "topic": lec.get("topic"),
                    "lecture_number": lec.get("lecture_number"),
                    "quiz_id": assessment["id"],
                    "quiz_title": assessment["title"],
                    "quiz_created_at": assessment["created_at"],
                    "questions_count": len(questions_result.data) if questions_result.data else 0,
                })

        return {
            "course_id": course_id,
            "lectures_with_quizzes": lectures_with_quizzes,
            "total_count": len(lectures_with_quizzes),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching course quizzes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching course quizzes",
        )


# ==================== QUIZ MODIFICATION ENDPOINTS ====================


class QuestionUpdateRequest(BaseModel):
    """Request model for updating a quiz question."""
    question_text: str | None = None
    question_type: str | None = None
    points: float | None = None
    options: list[str] | None = None
    correct_answer: str | None = None
    explanation: str | None = None


class QuestionCreateRequest(BaseModel):
    """Request model for creating a new quiz question."""
    question_text: str
    question_type: str = "MULTIPLE_CHOICE"
    points: float = 1.0
    options: list[str]
    correct_answer: str
    explanation: str | None = None


@router.put("/lectures/{lecture_id}/quiz/questions/{question_id}")
async def update_quiz_question(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    question_id: str,
    request: QuestionUpdateRequest,
    db=Depends(get_db),
):
    """
    Update a quiz question for a lecture.
    
    Teachers can modify question text, options, correct answer, explanation, and points.
    Only accessible to the teacher who created the lecture.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Updating question {question_id} for lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, teacher_id")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        # Get the question and verify it belongs to an assessment for this lecture
        question_result = (
            db.admin_client.table("question")
            .select("*, assessment!inner(lecture_id)")
            .eq("id", question_id)
            .execute()
        )

        if not question_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            )

        question = question_result.data[0]
        if question.get("assessment", {}).get("lecture_id") != lecture_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Question does not belong to this lecture",
            )

        # Build update data
        update_data = {"updated_at": datetime.utcnow().isoformat()}
        
        if request.question_text is not None:
            update_data["question_text"] = request.question_text
        if request.question_type is not None:
            update_data["question_type"] = request.question_type
        if request.points is not None:
            update_data["points"] = request.points
        if request.options is not None:
            update_data["options"] = json.dumps(request.options)
        if request.correct_answer is not None:
            update_data["correct_answer"] = request.correct_answer
        if request.explanation is not None:
            update_data["explanation"] = request.explanation

        # Update the question
        db.admin_client.table("question").update(update_data).eq("id", question_id).execute()

        logger.info(f"Updated question {question_id}")

        return {
            "message": "Question updated successfully",
            "question_id": question_id,
            "updated_fields": list(update_data.keys()),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating question",
        )


@router.post("/lectures/{lecture_id}/quiz/questions")
async def add_quiz_question(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    request: QuestionCreateRequest,
    db=Depends(get_db),
):
    """
    Add a new question to a lecture's quiz.
    
    Creates a new question and appends it to the default quiz for this lecture.
    Only accessible to the teacher who created the lecture.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Adding question to quiz for lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, teacher_id, title")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        # Get the default assessment for this lecture
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id")
            .eq("lecture_id", lecture_id)
            .eq("is_default", True)
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No quiz found for this lecture. Generate a quiz first.",
            )

        assessment_id = assessment_result.data[0]["id"]

        # Get current max order_index
        questions_result = (
            db.admin_client.table("question")
            .select("order_index")
            .eq("assessment_id", assessment_id)
            .order("order_index", desc=True)
            .limit(1)
            .execute()
        )

        next_order = 0
        if questions_result.data:
            next_order = (questions_result.data[0].get("order_index", 0) or 0) + 1

        # Create new question
        question_id = str(uuid4())
        question_data = {
            "id": question_id,
            "assessment_id": assessment_id,
            "question_text": request.question_text,
            "question_type": request.question_type,
            "points": request.points,
            "order_index": next_order,
            "options": json.dumps(request.options),
            "correct_answer": request.correct_answer,
            "explanation": request.explanation,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        db.admin_client.table("question").insert(question_data).execute()

        logger.info(f"Created question {question_id} for assessment {assessment_id}")

        return {
            "message": "Question added successfully",
            "question_id": question_id,
            "assessment_id": assessment_id,
            "order_index": next_order,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error adding question",
        )


@router.delete("/lectures/{lecture_id}/quiz/questions/{question_id}")
async def delete_quiz_question(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    question_id: str,
    db=Depends(get_db),
):
    """
    Delete a question from a lecture's quiz.
    
    Only accessible to the teacher who created the lecture.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Deleting question {question_id} from lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, teacher_id")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        # Get the question and verify it belongs to an assessment for this lecture
        question_result = (
            db.admin_client.table("question")
            .select("*, assessment!inner(lecture_id)")
            .eq("id", question_id)
            .execute()
        )

        if not question_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            )

        question = question_result.data[0]
        if question.get("assessment", {}).get("lecture_id") != lecture_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Question does not belong to this lecture",
            )

        # Delete the question
        db.admin_client.table("question").delete().eq("id", question_id).execute()

        logger.info(f"Deleted question {question_id}")

        return {
            "message": "Question deleted successfully",
            "question_id": question_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting question",
        )


# ==================== FLASHCARD MODIFICATION ENDPOINTS ====================


class FlashcardUpdateRequest(BaseModel):
    """Request model for updating a flashcard."""
    question: str | None = None
    answer: str | None = None
    difficulty: str | None = None
    topic: str | None = None


class FlashcardCreateRequest(BaseModel):
    """Request model for creating a new flashcard."""
    question: str
    answer: str
    difficulty: str = "MEDIUM"
    topic: str | None = "General"


@router.put("/lectures/{lecture_id}/flashcards/{flashcard_id}")
async def update_flashcard(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    flashcard_id: str,
    request: FlashcardUpdateRequest,
    db=Depends(get_db),
):
    """
    Update a flashcard for a lecture.
    
    Teachers can modify the question, answer, difficulty, and topic.
    Only accessible to the teacher who created the lecture.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Updating flashcard {flashcard_id} for lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, teacher_id")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        # Get the flashcard and verify it belongs to this lecture
        flashcard_result = (
            db.admin_client.table("flashcard")
            .select("*")
            .eq("id", flashcard_id)
            .eq("lecture_id", lecture_id)
            .execute()
        )

        if not flashcard_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flashcard not found or does not belong to this lecture",
            )

        # Build update data
        update_data = {"updated_at": datetime.utcnow().isoformat()}
        
        if request.question is not None:
            update_data["question"] = request.question
        if request.answer is not None:
            update_data["answer"] = request.answer
        if request.difficulty is not None:
            # Validate difficulty
            if request.difficulty not in ["EASY", "MEDIUM", "HARD"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Difficulty must be EASY, MEDIUM, or HARD",
                )
            update_data["difficulty"] = request.difficulty
        if request.topic is not None:
            update_data["topic"] = request.topic

        # Update the flashcard
        db.admin_client.table("flashcard").update(update_data).eq("id", flashcard_id).execute()

        logger.info(f"Updated flashcard {flashcard_id}")

        return {
            "message": "Flashcard updated successfully",
            "flashcard_id": flashcard_id,
            "updated_fields": list(update_data.keys()),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating flashcard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating flashcard",
        )


@router.post("/lectures/{lecture_id}/flashcards")
async def add_flashcard(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    request: FlashcardCreateRequest,
    db=Depends(get_db),
):
    """
    Add a new flashcard to a lecture.
    
    Creates a new flashcard and appends it to the lecture's flashcard set.
    Only accessible to the teacher who created the lecture.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Adding flashcard to lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, teacher_id")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        # Validate difficulty
        if request.difficulty not in ["EASY", "MEDIUM", "HARD"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Difficulty must be EASY, MEDIUM, or HARD",
            )

        # Get current max order_index
        flashcards_result = (
            db.admin_client.table("flashcard")
            .select("order_index")
            .eq("lecture_id", lecture_id)
            .order("order_index", desc=True)
            .limit(1)
            .execute()
        )

        next_order = 0
        if flashcards_result.data:
            next_order = (flashcards_result.data[0].get("order_index", 0) or 0) + 1

        # Create new flashcard
        flashcard_id = str(uuid4())
        flashcard_data = {
            "id": flashcard_id,
            "lecture_id": lecture_id,
            "question": request.question,
            "answer": request.answer,
            "difficulty": request.difficulty,
            "topic": request.topic or "General",
            "order_index": next_order,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        db.admin_client.table("flashcard").insert(flashcard_data).execute()

        logger.info(f"Created flashcard {flashcard_id} for lecture {lecture_id}")

        return {
            "message": "Flashcard added successfully",
            "flashcard_id": flashcard_id,
            "order_index": next_order,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding flashcard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error adding flashcard",
        )


@router.delete("/lectures/{lecture_id}/flashcards/{flashcard_id}")
async def delete_flashcard(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    flashcard_id: str,
    db=Depends(get_db),
):
    """
    Delete a flashcard from a lecture.
    
    Only accessible to the teacher who created the lecture.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Deleting flashcard {flashcard_id} from lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, teacher_id")
            .eq("id", lecture_id)
            .eq("teacher_id", teacher.id)
            .execute()
        )

        if not lecture_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found or access denied",
            )

        # Get the flashcard and verify it belongs to this lecture
        flashcard_result = (
            db.admin_client.table("flashcard")
            .select("id")
            .eq("id", flashcard_id)
            .eq("lecture_id", lecture_id)
            .execute()
        )

        if not flashcard_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flashcard not found or does not belong to this lecture",
            )

        # Delete the flashcard
        db.admin_client.table("flashcard").delete().eq("id", flashcard_id).execute()

        logger.info(f"Deleted flashcard {flashcard_id}")

        return {
            "message": "Flashcard deleted successfully",
            "flashcard_id": flashcard_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting flashcard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting flashcard",
        )


# Import and include the router in routes_config
# This import is at the end to avoid circular imports
from routes_config import teacher_router as main_teacher_router

main_teacher_router.include_router(router)

