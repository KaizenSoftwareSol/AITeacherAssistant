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
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from pydantic import BaseModel

from dependencies import require_teacher
from logger import logger
from models.user import User
from services.notification_service import NotificationService
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

        # Get courses for this teacher from multiple sources (same logic as courses endpoint):
        # 1. Courses created by this teacher (created_by_teacher_id)
        # 2. Courses assigned to this teacher (via course_teacher table)
        # 3. Courses where this teacher has created at least one lecture
        
        course_ids_set = set()
        courses_dict = {}
        
        # 1. Get courses created by this teacher
        created_courses_result = (
            db.admin_client.table("course")
            .select("*")
            .eq("university_id", teacher.university_id)
            .eq("created_by_teacher_id", teacher.id)
            .execute()
        )
        
        for course in created_courses_result.data or []:
            course_id = course.get("id")
            if course_id:
                course_ids_set.add(course_id)
                courses_dict[course_id] = course
        
        # 2. Get courses assigned to this teacher
        assigned_courses_result = (
            db.admin_client.table("course_teacher")
            .select("course_id, course!inner(*)")
            .eq("teacher_id", teacher.id)
            .eq("is_active", True)
            .execute()
        )
        
        for assignment in assigned_courses_result.data or []:
            course_id = assignment.get("course_id")
            if course_id:
                course_ids_set.add(course_id)
                course_data = assignment.get("course", {})
                if course_data and course_id not in courses_dict:
                    courses_dict[course_id] = course_data
        
        # 3. Get courses where this teacher has created at least one lecture
        lectures_result = (
            db.admin_client.table("lecture")
            .select("course_id, course!inner(*)")
            .eq("teacher_id", teacher.id)
            .execute()
        )
        
        for lecture in lectures_result.data or []:
            course_id = lecture.get("course_id")
            if course_id:
                course_ids_set.add(course_id)
                course_data = lecture.get("course", {})
                if course_data and course_id not in courses_dict:
                    courses_dict[course_id] = course_data
        
        # Convert to list and enrich with stats
        courses = []
        total_students = 0
        course_ids = list(course_ids_set)
        
        # Batch fetch enrollment counts
        if course_ids:
            enrollments_result = (
                db.admin_client.table("enrollment")
                .select("course_id")
                .in_("course_id", course_ids)
                .eq("is_active", True)
                .execute()
            )
            enrollment_counts = {}
            for e in (enrollments_result.data or []):
                cid = e.get("course_id")
                enrollment_counts[cid] = enrollment_counts.get(cid, 0) + 1
        
        # Batch fetch lecture counts for this teacher
        if course_ids:
            teacher_lectures_result = (
                db.admin_client.table("lecture")
                .select("course_id, status")
                .in_("course_id", course_ids)
                .eq("teacher_id", teacher.id)
                .execute()
            )
            lecture_counts = {}
            published_counts = {}
            for lec in (teacher_lectures_result.data or []):
                cid = lec.get("course_id")
                lecture_counts[cid] = lecture_counts.get(cid, 0) + 1
                if lec.get("status") in ["PUBLISHED", "DELIVERED"]:
                    published_counts[cid] = published_counts.get(cid, 0) + 1
        
        for course in courses_dict.values():
            course_id = course.get("id")
            enrollment_count = enrollment_counts.get(course_id, 0) if course_ids else 0
            total_students += enrollment_count
            
            courses.append({
                "id": course_id,
                "name": course.get("name"),
                "code": course.get("code"),
                "description": course.get("description"),
                "created_at": course.get("created_at"),
                "enrollment_count": enrollment_count,
                "lecture_count": lecture_counts.get(course_id, 0) if course_ids else 0,
                "published_lectures": published_counts.get(course_id, 0) if course_ids else 0,
            })
        
        # Sort by created_at desc
        courses.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
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
                .select("id, student_id, user_id")
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
                        "student_id_number": student.get("student_id"),
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


# ==================== TEST QUIZ MANAGEMENT ENDPOINTS ====================


class TestQuizCreateRequest(BaseModel):
    """Request model for creating a test quiz."""
    title: str
    description: str | None = None
    lecture_id: str
    difficulty: str = "MEDIUM"
    time_limit: int | None = None
    max_attempts: int = 1
    passing_score: float = 60.0
    due_date: str  # ISO format datetime string
    show_leaderboard: bool = True


class TestQuizAIGenerateRequest(BaseModel):
    """Request model for AI-generating questions."""
    num_questions: int = 10
    question_types: list[str] | None = None
    focus_areas: list[str] | None = None


@router.post("/lectures/{lecture_id}/test-quiz")
async def create_test_quiz(
    current_user: Annotated[User, Depends(require_teacher)],
    lecture_id: str,
    request: TestQuizCreateRequest,
    db=Depends(get_db),
):
    """
    Create a new TEST quiz for a lecture.
    
    Teachers can create graded quizzes with deadlines. Questions can be added
    manually or generated by AI afterwards.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Creating test quiz for lecture {lecture_id}, teacher {teacher.id}")

        # Verify lecture ownership
        lecture_result = (
            db.admin_client.table("lecture")
            .select("id, title, course_id, content")
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

        # Validate difficulty
        if request.difficulty not in ["EASY", "MEDIUM", "HARD"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Difficulty must be EASY, MEDIUM, or HARD",
            )

        # Parse due_date
        try:
            due_date = datetime.fromisoformat(request.due_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid due_date format. Use ISO format (e.g., 2024-12-31T23:59:59Z)",
            )

        # Create assessment
        assessment_id = str(uuid4())
        assessment_data = {
            "id": assessment_id,
            "title": request.title,
            "description": request.description,
            "assessment_type": "QUIZ",
            "course_id": lecture["course_id"],
            "lecture_id": lecture_id,
            "teacher_id": str(teacher.id),
            "time_limit": request.time_limit,
            "max_attempts": request.max_attempts,
            "passing_score": request.passing_score,
            "is_published": False,  # Not published until teacher is ready
            "quiz_mode": "TEST",
            "difficulty": request.difficulty,
            "is_default": False,
            "show_leaderboard": request.show_leaderboard,
            "due_date": due_date.isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        db.admin_client.table("assessment").insert(assessment_data).execute()

        logger.info(f"Created test quiz {assessment_id} for lecture {lecture_id}")

        return {
            "message": "Test quiz created successfully",
            "assessment_id": assessment_id,
            "title": request.title,
            "lecture_id": lecture_id,
            "lecture_title": lecture["title"],
            "difficulty": request.difficulty,
            "due_date": due_date.isoformat(),
            "is_published": False,
            "questions_count": 0,
            "next_step": "Add questions manually or use AI generation",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating test quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating test quiz",
        )


# ==================== CONSOLIDATED ASSESSMENT ENDPOINTS ====================
# NOTE: These static routes MUST be defined BEFORE the parameterized routes
# to avoid FastAPI matching "/assessments/all" as "/assessments/{assessment_id}"


@router.get("/assessments/all")
async def get_all_teacher_assessments(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Get ALL quizzes across ALL courses the teacher has created.
    
    Returns quizzes from all lectures created by this teacher, grouped by course.
    Includes submission statistics for each quiz.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching all assessments for teacher {teacher.id}")

        # Get all lectures by this teacher
        lectures_result = (
            db.admin_client.table("lecture")
            .select("id, title, course_id, status, topic, lecture_number, created_at")
            .eq("teacher_id", teacher.id)
            .order("created_at", desc=True)
            .execute()
        )
        
        if not lectures_result.data:
            return {
                "teacher_id": str(teacher.id),
                "total_quizzes": 0,
                "published_quizzes": 0,
                "quizzes": [],
                "by_course": {},
            }
        
        lecture_ids = [lec["id"] for lec in lectures_result.data]
        lecture_map = {lec["id"]: lec for lec in lectures_result.data}
        
        # Get course IDs and fetch course info
        course_ids = list(set(lec["course_id"] for lec in lectures_result.data if lec.get("course_id")))
        course_map = {}
        if course_ids:
            courses_result = (
                db.admin_client.table("course")
                .select("id, name, code")
                .in_("id", course_ids)
                .execute()
            )
            course_map = {c["id"]: c for c in (courses_result.data or [])}
        
        # Get all GRADED TEST assessments (is_default=False means graded test, not practice quiz)
        assessments_result = (
            db.admin_client.table("assessment")
            .select("id, lecture_id, title, description, time_limit, passing_score, max_attempts, created_at")
            .in_("lecture_id", lecture_ids)
            .eq("is_default", False)
            .execute()
        )
        
        if not assessments_result.data:
            return {
                "teacher_id": str(teacher.id),
                "total_quizzes": 0,
                "published_quizzes": 0,
                "quizzes": [],
                "by_course": {},
            }
        
        assessment_ids = [a["id"] for a in assessments_result.data]
        
        # Get question counts
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
        
        # Get submission statistics for each assessment
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("assessment_id, score, max_score, student_id")
            .in_("assessment_id", assessment_ids)
            .execute()
        )
        
        # Calculate stats per assessment
        submission_stats = {}
        for sub in (submissions_result.data or []):
            aid = sub["assessment_id"]
            if aid not in submission_stats:
                submission_stats[aid] = {
                    "total_submissions": 0,
                    "unique_students": set(),
                    "scores": [],
                    "passed": 0,
                }
            submission_stats[aid]["total_submissions"] += 1
            submission_stats[aid]["unique_students"].add(sub["student_id"])
            if sub["max_score"] and sub["max_score"] > 0:
                percentage = (sub["score"] / sub["max_score"]) * 100
                submission_stats[aid]["scores"].append(percentage)
        
        # Build quizzes list
        quizzes = []
        by_course = {}
        published_count = 0
        
        for assessment in assessments_result.data:
            lecture = lecture_map.get(assessment["lecture_id"], {})
            course = course_map.get(lecture.get("course_id"), {})
            stats = submission_stats.get(assessment["id"], {})
            
            is_published = lecture.get("status") in ["PUBLISHED", "DELIVERED"]
            if is_published:
                published_count += 1
            
            scores = stats.get("scores", [])
            avg_score = round(sum(scores) / len(scores), 1) if scores else None
            
            quiz_info = {
                "assessment_id": assessment["id"],
                "title": assessment["title"],
                "description": assessment.get("description"),
                "lecture_id": assessment["lecture_id"],
                "lecture_title": lecture.get("title"),
                "lecture_status": lecture.get("status"),
                "lecture_topic": lecture.get("topic"),
                "lecture_number": lecture.get("lecture_number"),
                "course_id": lecture.get("course_id"),
                "course_name": course.get("name"),
                "course_code": course.get("code"),
                "questions_count": question_counts.get(assessment["id"], 0),
                "time_limit": assessment.get("time_limit", 30),
                "passing_score": assessment.get("passing_score", 60.0),
                "max_attempts": assessment.get("max_attempts", 3),
                "created_at": assessment.get("created_at"),
                "is_published": is_published,
                # Submission stats
                "total_submissions": stats.get("total_submissions", 0),
                "unique_students": len(stats.get("unique_students", set())),
                "average_score": avg_score,
                "highest_score": round(max(scores), 1) if scores else None,
                "lowest_score": round(min(scores), 1) if scores else None,
            }
            quizzes.append(quiz_info)
            
            # Group by course
            cid = lecture.get("course_id")
            if cid:
                if cid not in by_course:
                    by_course[cid] = {
                        "course_name": course.get("name"),
                        "course_code": course.get("code"),
                        "quizzes": [],
                    }
                by_course[cid]["quizzes"].append(quiz_info)
        
        return {
            "teacher_id": str(teacher.id),
            "total_quizzes": len(quizzes),
            "published_quizzes": published_count,
            "draft_quizzes": len(quizzes) - published_count,
            "quizzes": quizzes,
            "by_course": by_course,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching all teacher assessments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching assessments",
        )


@router.get("/assessments/analytics")
async def get_assessment_analytics(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Get comprehensive assessment analytics for teacher dashboard.
    
    Returns:
    - Total quizzes created
    - Total submissions
    - Average scores
    - Completion rates
    - Recent quiz activity
    - Performance by course
    - Top performing quizzes
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching assessment analytics for teacher {teacher.id}")

        # Get all lectures by this teacher
        lectures_result = (
            db.admin_client.table("lecture")
            .select("id, title, course_id, status")
            .eq("teacher_id", teacher.id)
            .execute()
        )
        
        if not lectures_result.data:
            return {
                "teacher_id": str(teacher.id),
                "summary": {
                    "total_quizzes": 0,
                    "published_quizzes": 0,
                    "total_submissions": 0,
                    "unique_students": 0,
                    "average_score": None,
                    "pass_rate": None,
                },
                "by_course": [],
                "recent_activity": [],
                "top_quizzes": [],
                "score_distribution": {},
            }
        
        lecture_ids = [lec["id"] for lec in lectures_result.data]
        lecture_map = {lec["id"]: lec for lec in lectures_result.data}
        
        # Get course info
        course_ids = list(set(lec["course_id"] for lec in lectures_result.data if lec.get("course_id")))
        course_map = {}
        if course_ids:
            courses_result = (
                db.admin_client.table("course")
                .select("id, name, code")
                .in_("id", course_ids)
                .execute()
            )
            course_map = {c["id"]: c for c in (courses_result.data or [])}
        
        # Get all GRADED TEST assessments (is_default=False means graded test, not practice quiz)
        assessments_result = (
            db.admin_client.table("assessment")
            .select("id, lecture_id, title, passing_score, created_at")
            .in_("lecture_id", lecture_ids)
            .eq("is_default", False)
            .execute()
        )
        
        total_quizzes = len(assessments_result.data) if assessments_result.data else 0
        
        if not assessments_result.data:
            return {
                "teacher_id": str(teacher.id),
                "summary": {
                    "total_quizzes": 0,
                    "published_quizzes": 0,
                    "total_submissions": 0,
                    "unique_students": 0,
                    "average_score": None,
                    "pass_rate": None,
                },
                "by_course": [],
                "recent_activity": [],
                "top_quizzes": [],
                "score_distribution": {},
            }
        
        assessment_ids = [a["id"] for a in assessments_result.data]
        assessment_map = {a["id"]: a for a in assessments_result.data}
        
        # Count published quizzes
        published_quizzes = sum(
            1 for a in assessments_result.data 
            if lecture_map.get(a["lecture_id"], {}).get("status") in ["PUBLISHED", "DELIVERED"]
        )
        
        # Get all submissions
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("id, assessment_id, student_id, score, max_score, submitted_at")
            .in_("assessment_id", assessment_ids)
            .order("submitted_at", desc=True)
            .execute()
        )
        
        submissions = submissions_result.data or []
        total_submissions = len(submissions)
        unique_students = len(set(s["student_id"] for s in submissions))
        
        # Calculate overall statistics
        all_scores = []
        passed_count = 0
        score_distribution = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
        
        for sub in submissions:
            if sub["max_score"] and sub["max_score"] > 0:
                percentage = (sub["score"] / sub["max_score"]) * 100
                all_scores.append(percentage)
                
                # Score distribution
                if percentage <= 20:
                    score_distribution["0-20"] += 1
                elif percentage <= 40:
                    score_distribution["21-40"] += 1
                elif percentage <= 60:
                    score_distribution["41-60"] += 1
                elif percentage <= 80:
                    score_distribution["61-80"] += 1
                else:
                    score_distribution["81-100"] += 1
                
                # Check if passed
                assessment = assessment_map.get(sub["assessment_id"], {})
                passing_score = assessment.get("passing_score", 60.0)
                if percentage >= passing_score:
                    passed_count += 1
        
        average_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else None
        pass_rate = round((passed_count / len(all_scores)) * 100, 1) if all_scores else None
        
        # Performance by course
        course_stats = {}
        for sub in submissions:
            assessment = assessment_map.get(sub["assessment_id"], {})
            lecture = lecture_map.get(assessment.get("lecture_id"), {})
            cid = lecture.get("course_id")
            
            if cid:
                if cid not in course_stats:
                    course_stats[cid] = {
                        "submissions": 0,
                        "students": set(),
                        "scores": [],
                    }
                course_stats[cid]["submissions"] += 1
                course_stats[cid]["students"].add(sub["student_id"])
                if sub["max_score"] and sub["max_score"] > 0:
                    course_stats[cid]["scores"].append((sub["score"] / sub["max_score"]) * 100)
        
        by_course = []
        for cid, stats in course_stats.items():
            course = course_map.get(cid, {})
            scores = stats["scores"]
            by_course.append({
                "course_id": cid,
                "course_name": course.get("name"),
                "course_code": course.get("code"),
                "total_submissions": stats["submissions"],
                "unique_students": len(stats["students"]),
                "average_score": round(sum(scores) / len(scores), 1) if scores else None,
            })
        
        # Sort by submissions descending
        by_course.sort(key=lambda x: x["total_submissions"], reverse=True)
        
        # Recent activity (last 10 submissions)
        recent_activity = []
        for sub in submissions[:10]:
            assessment = assessment_map.get(sub["assessment_id"], {})
            lecture = lecture_map.get(assessment.get("lecture_id"), {})
            course = course_map.get(lecture.get("course_id"), {})
            
            percentage = round((sub["score"] / sub["max_score"]) * 100, 1) if sub["max_score"] else 0
            
            recent_activity.append({
                "submission_id": sub["id"],
                "assessment_title": assessment.get("title"),
                "lecture_title": lecture.get("title"),
                "course_name": course.get("name"),
                "score": sub["score"],
                "max_score": sub["max_score"],
                "percentage": percentage,
                "submitted_at": sub["submitted_at"],
            })
        
        # Top performing quizzes (by average score)
        quiz_performance = {}
        for sub in submissions:
            aid = sub["assessment_id"]
            if aid not in quiz_performance:
                quiz_performance[aid] = {"scores": [], "submissions": 0}
            quiz_performance[aid]["submissions"] += 1
            if sub["max_score"] and sub["max_score"] > 0:
                quiz_performance[aid]["scores"].append((sub["score"] / sub["max_score"]) * 100)
        
        top_quizzes = []
        for aid, perf in quiz_performance.items():
            if perf["scores"]:
                assessment = assessment_map.get(aid, {})
                lecture = lecture_map.get(assessment.get("lecture_id"), {})
                course = course_map.get(lecture.get("course_id"), {})
                
                top_quizzes.append({
                    "assessment_id": aid,
                    "title": assessment.get("title"),
                    "lecture_title": lecture.get("title"),
                    "course_name": course.get("name"),
                    "total_submissions": perf["submissions"],
                    "average_score": round(sum(perf["scores"]) / len(perf["scores"]), 1),
                })
        
        # Sort by average score descending
        top_quizzes.sort(key=lambda x: x["average_score"], reverse=True)
        
        return {
            "teacher_id": str(teacher.id),
            "summary": {
                "total_quizzes": total_quizzes,
                "published_quizzes": published_quizzes,
                "total_submissions": total_submissions,
                "unique_students": unique_students,
                "average_score": average_score,
                "pass_rate": pass_rate,
            },
            "by_course": by_course,
            "recent_activity": recent_activity,
            "top_quizzes": top_quizzes[:5],  # Top 5
            "score_distribution": score_distribution,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching assessment analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching analytics",
        )


# ==================== PARAMETERIZED ASSESSMENT ENDPOINTS ====================


@router.post("/assessments/{assessment_id}/generate-questions")
async def generate_quiz_questions(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    request: TestQuizAIGenerateRequest,
    db=Depends(get_db),
):
    """
    Generate questions for a test quiz using AI.
    
    Uses the lecture content to generate questions at the specified difficulty level.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Generating questions for assessment {assessment_id}, teacher {teacher.id}")

        # Get assessment and verify ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(id, title, content)")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        assessment = assessment_result.data[0]
        lecture = assessment["lecture"]

        if not lecture.get("content"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lecture has no content to generate questions from",
            )

        # Generate questions using AI
        from services.quiz_service import QuizService
        
        quiz_service = QuizService(db)
        quiz_data = await quiz_service.generate_quiz_from_lecture(
            lecture_id=lecture["id"],
            lecture_content=lecture["content"],
            num_questions=request.num_questions,
            question_types=request.question_types,
            difficulty=assessment.get("difficulty", "MEDIUM"),
            focus_areas=request.focus_areas,
        )

        # Get current max order_index
        existing_questions = (
            db.admin_client.table("question")
            .select("order_index")
            .eq("assessment_id", assessment_id)
            .order("order_index", desc=True)
            .limit(1)
            .execute()
        )
        
        start_order = 0
        if existing_questions.data:
            start_order = (existing_questions.data[0].get("order_index", 0) or 0) + 1

        # Insert generated questions
        questions_to_insert = []
        for i, q in enumerate(quiz_data.get("questions", [])):
            question_data = {
                "id": str(uuid4()),
                "assessment_id": assessment_id,
                "question_text": q["question_text"],
                "question_type": q.get("question_type", "MULTIPLE_CHOICE"),
                "points": q.get("points", 1.0),
                "order_index": start_order + i,
                "options": json.dumps(q.get("options", [])),
                "correct_answer": q["correct_answer"],
                "explanation": q.get("explanation"),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            questions_to_insert.append(question_data)

        if questions_to_insert:
            db.admin_client.table("question").insert(questions_to_insert).execute()

        logger.info(f"Generated {len(questions_to_insert)} questions for assessment {assessment_id}")

        return {
            "message": f"Generated {len(questions_to_insert)} questions successfully",
            "assessment_id": assessment_id,
            "questions_generated": len(questions_to_insert),
            "difficulty": assessment.get("difficulty", "MEDIUM"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating questions: {str(e)}",
        )


@router.put("/assessments/{assessment_id}/publish")
async def publish_test_quiz(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    db=Depends(get_db),
):
    """
    Publish a test quiz, making it available to students.
    
    Once published, students can see and attempt the quiz until the deadline.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        # Verify ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title, quiz_mode")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        # Check if quiz has questions
        questions_result = (
            db.admin_client.table("question")
            .select("id")
            .eq("assessment_id", assessment_id)
            .execute()
        )

        if not questions_result.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot publish quiz without questions",
            )

        # Update is_published
        db.admin_client.table("assessment").update({
            "is_published": True,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", assessment_id).execute()

        quiz_title = assessment_result.data[0]["title"]
        
        # Notify enrolled students about the quiz
        try:
            # Get quiz details including course
            quiz_full = (
                db.admin_client.table("assessment")
                .select("course_id, due_date")
                .eq("id", assessment_id)
                .execute()
            )
            
            if quiz_full.data:
                course_id = quiz_full.data[0].get("course_id")
                due_date = quiz_full.data[0].get("due_date")
                
                # Get all enrolled students' user_ids
                enrollments_result = (
                    db.admin_client.table("enrollment")
                    .select("student_id")
                    .eq("course_id", course_id)
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
                        
                        notification_service = NotificationService(db)
                        await notification_service.notify_quiz_published(
                            student_user_ids=student_user_ids,
                            quiz_title=quiz_title,
                            due_date=due_date,
                            assessment_id=assessment_id,
                        )
                        logger.info(f"Sent quiz published notifications to {len(student_user_ids)} students")
        except Exception as notify_error:
            logger.warning(f"Failed to send quiz published notifications: {notify_error}")

        return {
            "message": "Quiz published successfully",
            "assessment_id": assessment_id,
            "title": quiz_title,
            "is_published": True,
            "questions_count": len(questions_result.data),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error publishing quiz",
        )


@router.get("/assessments/{assessment_id}")
async def get_assessment_details(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    db=Depends(get_db),
):
    """
    Get full details of an assessment/quiz.
    
    Returns all assessment information including questions.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching assessment {assessment_id}, teacher {teacher.id}")

        # Get assessment with lecture info
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(id, title, course_id)")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        assessment = assessment_result.data[0]
        lecture = assessment.get("lecture", {})

        # Get questions
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_id)
            .order("order_index")
            .execute()
        )

        questions = []
        total_points = 0
        for q in (questions_result.data or []):
            points = q.get("points", 1.0)
            total_points += points
            questions.append({
                "question_id": q["id"],
                "question_text": q["question_text"],
                "question_type": q.get("question_type", "MULTIPLE_CHOICE"),
                "points": points,
                "order_index": q.get("order_index", 0),
                "options": json.loads(q.get("options", "[]")),
                "correct_answer": q["correct_answer"],
                "explanation": q.get("explanation"),
            })

        # Get submission count
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("id")
            .eq("assessment_id", assessment_id)
            .eq("is_submitted", True)
            .execute()
        )

        # Check if overdue
        due_date = assessment.get("due_date")
        is_overdue = False
        if due_date:
            try:
                due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                is_overdue = datetime.utcnow() > due_dt.replace(tzinfo=None)
            except Exception:
                pass

        return {
            "assessment_id": assessment_id,
            "title": assessment["title"],
            "description": assessment.get("description"),
            "assessment_type": assessment.get("assessment_type", "QUIZ"),
            "quiz_mode": assessment.get("quiz_mode", "PRACTICE"),
            "difficulty": assessment.get("difficulty", "MEDIUM"),
            "lecture_id": lecture.get("id"),
            "lecture_title": lecture.get("title"),
            "course_id": lecture.get("course_id"),
            "time_limit": assessment.get("time_limit"),
            "max_attempts": assessment.get("max_attempts", 1),
            "passing_score": assessment.get("passing_score", 60.0),
            "is_published": assessment.get("is_published", False),
            "show_leaderboard": assessment.get("show_leaderboard", True),
            "due_date": due_date,
            "is_overdue": is_overdue,
            "created_at": assessment.get("created_at"),
            "updated_at": assessment.get("updated_at"),
            "questions_count": len(questions),
            "total_points": total_points,
            "submissions_count": len(submissions_result.data) if submissions_result.data else 0,
            "questions": questions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching assessment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching assessment",
        )


@router.get("/assessments/{assessment_id}/submissions")
async def get_quiz_submissions(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    db=Depends(get_db),
):
    """
    Get all student submissions for a test quiz.
    
    Shows a summary of each student's submission with score, rank, and submission time.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching submissions for assessment {assessment_id}, teacher {teacher.id}")

        # Verify ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title, course_id, due_date")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        assessment = assessment_result.data[0]

        # Get all enrolled students
        enrollments = (
            db.admin_client.table("enrollment")
            .select("student_id")
            .eq("course_id", assessment["course_id"])
            .eq("is_active", True)
            .execute()
        )

        student_ids = [e["student_id"] for e in (enrollments.data or [])]

        if not student_ids:
            return {
                "assessment_id": assessment_id,
                "assessment_title": assessment["title"],
                "total_enrolled": 0,
                "total_submitted": 0,
                "submissions": [],
            }

        # Get student details
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
            .select("id, first_name, last_name, email")
            .in_("id", user_ids)
            .execute()
        )
        user_map = {u["id"]: u for u in (users_result.data or [])}

        # Get submissions
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("*")
            .eq("assessment_id", assessment_id)
            .eq("is_submitted", True)
            .order("score", desc=True)
            .execute()
        )

        # Build submission map (best score per student)
        best_submissions = {}
        for sub in (submissions_result.data or []):
            sid = sub["student_id"]
            if sid not in best_submissions or (sub.get("score") or 0) > (best_submissions[sid].get("score") or 0):
                best_submissions[sid] = sub

        # Build response with rankings
        submissions = []
        sorted_subs = sorted(
            best_submissions.values(),
            key=lambda x: (x.get("score") or 0),
            reverse=True
        )

        for rank, sub in enumerate(sorted_subs, 1):
            student_id = sub["student_id"]
            user_id = student_user_map.get(student_id)
            user = user_map.get(user_id, {})
            
            submissions.append({
                "rank": rank,
                "student_id": student_id,
                "student_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Unknown",
                "student_email": user.get("email"),
                "submission_id": sub["id"],
                "score": sub.get("score"),
                "max_score": sub.get("max_score"),
                "percentage": (sub.get("score", 0) / sub.get("max_score", 1) * 100) if sub.get("max_score") else 0,
                "attempt_number": sub.get("attempt_number", 1),
                "submitted_at": sub.get("submitted_at"),
                "time_taken": sub.get("time_taken"),
                "is_submitted": True,
                "is_graded": sub.get("is_graded", False),
            })

        # Add students who haven't submitted
        submitted_student_ids = set(best_submissions.keys())
        for student_id in student_ids:
            if student_id not in submitted_student_ids:
                user_id = student_user_map.get(student_id)
                user = user_map.get(user_id, {})
                submissions.append({
                    "rank": None,
                    "student_id": student_id,
                    "student_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Unknown",
                    "student_email": user.get("email"),
                    "submission_id": None,
                    "score": None,
                    "max_score": None,
                    "percentage": None,
                    "attempt_number": 0,
                    "submitted_at": None,
                    "time_taken": None,
                    "is_submitted": False,
                    "is_graded": False,
                })

        # Calculate stats
        scores = [s["score"] for s in submissions if s["score"] is not None]
        
        return {
            "assessment_id": assessment_id,
            "assessment_title": assessment["title"],
            "due_date": assessment.get("due_date"),
            "total_enrolled": len(student_ids),
            "total_submitted": len(best_submissions),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "highest_score": max(scores) if scores else 0,
            "lowest_score": min(scores) if scores else 0,
            "submissions": submissions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching submissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching submissions",
        )


@router.get("/assessments/{assessment_id}/submissions/{student_id}")
async def get_detailed_submission(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    student_id: str,
    db=Depends(get_db),
):
    """
    Get detailed submission for a specific student.
    
    Shows what questions the student answered correctly and incorrectly,
    along with their answers and the correct answers.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching detailed submission for student {student_id}, assessment {assessment_id}")

        # Verify ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        assessment = assessment_result.data[0]

        # Get student info
        student_result = (
            db.admin_client.table("student")
            .select("id, user_id")
            .eq("id", student_id)
            .execute()
        )

        if not student_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found",
            )

        student = student_result.data[0]
        
        user_result = (
            db.admin_client.table("users")
            .select("first_name, last_name, email")
            .eq("id", student["user_id"])
            .execute()
        )
        user = user_result.data[0] if user_result.data else {}

        # Get best submission
        submission_result = (
            db.admin_client.table("assessment_submission")
            .select("*")
            .eq("assessment_id", assessment_id)
            .eq("student_id", student_id)
            .eq("is_submitted", True)
            .order("score", desc=True)
            .limit(1)
            .execute()
        )

        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No submission found for this student",
            )

        submission = submission_result.data[0]
        student_answers = json.loads(submission.get("answers", "{}"))

        # Get questions
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_id)
            .order("order_index")
            .execute()
        )

        # Build question results
        question_results = []
        correct_count = 0
        
        for q in (questions_result.data or []):
            student_answer = student_answers.get(q["id"], "")
            correct_answer = q["correct_answer"]
            
            # Check if correct (case-insensitive)
            is_correct = str(student_answer).strip().lower() == str(correct_answer).strip().lower()
            if is_correct:
                correct_count += 1
            
            question_results.append({
                "question_id": q["id"],
                "question_text": q["question_text"],
                "question_type": q.get("question_type", "MULTIPLE_CHOICE"),
                "points_possible": q.get("points", 1.0),
                "points_earned": q.get("points", 1.0) if is_correct else 0,
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
                "explanation": q.get("explanation"),
                "options": json.loads(q.get("options", "[]")),
            })

        return {
            "submission_id": submission["id"],
            "assessment_id": assessment_id,
            "assessment_title": assessment["title"],
            "student_id": student_id,
            "student_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "student_email": user.get("email"),
            "score": submission.get("score", 0),
            "max_score": submission.get("max_score", 0),
            "percentage": (submission.get("score", 0) / submission.get("max_score", 1) * 100) if submission.get("max_score") else 0,
            "correct_count": correct_count,
            "total_questions": len(question_results),
            "attempt_number": submission.get("attempt_number", 1),
            "time_taken": submission.get("time_taken"),
            "started_at": submission.get("started_at"),
            "submitted_at": submission.get("submitted_at"),
            "question_results": question_results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching detailed submission: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching detailed submission",
        )


@router.get("/assessments/{assessment_id}/leaderboard")
async def get_quiz_leaderboard_teacher(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    db=Depends(get_db),
):
    """
    Get the leaderboard for a test quiz (teacher view).
    
    Shows student names, ranks, and scores. Teachers see full information.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        # Verify ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title, show_leaderboard")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        assessment = assessment_result.data[0]

        # Get submissions ordered by score
        submissions_result = (
            db.admin_client.table("assessment_submission")
            .select("student_id, score, max_score, submitted_at")
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
                "total_participants": 0,
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

        # Build leaderboard
        sorted_entries = sorted(
            best_by_student.items(),
            key=lambda x: (x[1].get("score") or 0),
            reverse=True
        )

        leaderboard = []
        scores = []
        for rank, (student_id, sub) in enumerate(sorted_entries, 1):
            user_id = student_user_map.get(student_id)
            user = user_map.get(user_id, {})
            score = sub.get("score", 0)
            max_score = sub.get("max_score", 1)
            scores.append(score)
            
            leaderboard.append({
                "rank": rank,
                "student_id": student_id,
                "student_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Unknown",
                "score": score,
                "max_score": max_score,
                "percentage": (score / max_score * 100) if max_score else 0,
                "submitted_at": sub.get("submitted_at"),
            })

        return {
            "assessment_id": assessment_id,
            "assessment_title": assessment["title"],
            "total_participants": len(leaderboard),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "highest_score": max(scores) if scores else 0,
            "lowest_score": min(scores) if scores else 0,
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


@router.get("/courses/{course_id}/test-quizzes")
async def get_course_test_quizzes(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    db=Depends(get_db),
):
    """
    Get all test quizzes for a course.
    
    Returns list of test quizzes with submission stats.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching test quizzes for course {course_id}, teacher {teacher.id}")

        # Get test quizzes
        assessments_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(id, title)")
            .eq("course_id", course_id)
            .eq("teacher_id", str(teacher.id))
            .eq("quiz_mode", "TEST")
            .order("created_at", desc=True)
            .execute()
        )

        quizzes = []
        for a in (assessments_result.data or []):
            # Get submission count
            submissions_result = (
                db.admin_client.table("assessment_submission")
                .select("id")
                .eq("assessment_id", a["id"])
                .eq("is_submitted", True)
                .execute()
            )
            
            # Get question count
            questions_result = (
                db.admin_client.table("question")
                .select("id")
                .eq("assessment_id", a["id"])
                .execute()
            )

            due_date = a.get("due_date")
            is_overdue = False
            if due_date:
                try:
                    due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    is_overdue = datetime.utcnow() > due_dt.replace(tzinfo=None)
                except:
                    pass

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
                "is_published": a.get("is_published", False),
                "show_leaderboard": a.get("show_leaderboard", True),
                "questions_count": len(questions_result.data) if questions_result.data else 0,
                "submissions_count": len(submissions_result.data) if submissions_result.data else 0,
                "created_at": a.get("created_at"),
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


# ==================== MANUAL QUESTION MANAGEMENT FOR TEST QUIZZES ====================


class TestQuizQuestionCreateRequest(BaseModel):
    """Request model for adding a question to a test quiz."""
    question_text: str
    question_type: str = "MULTIPLE_CHOICE"  # MULTIPLE_CHOICE, TRUE_FALSE, SHORT_ANSWER
    points: float = 1.0
    options: list[str]  # For MULTIPLE_CHOICE: ["A", "B", "C", "D"], for TRUE_FALSE: ["True", "False"]
    correct_answer: str
    explanation: str | None = None


class TestQuizQuestionUpdateRequest(BaseModel):
    """Request model for updating a question."""
    question_text: str | None = None
    question_type: str | None = None
    points: float | None = None
    options: list[str] | None = None
    correct_answer: str | None = None
    explanation: str | None = None


@router.get("/assessments/{assessment_id}/questions")
async def get_test_quiz_questions(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    db=Depends(get_db),
):
    """
    Get all questions for a test quiz.
    
    Returns all questions with correct answers for teacher review.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        # Verify ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title, quiz_mode, difficulty")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        assessment = assessment_result.data[0]

        # Get questions
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_id)
            .order("order_index")
            .execute()
        )

        questions = []
        total_points = 0
        for q in (questions_result.data or []):
            points = q.get("points", 1.0)
            total_points += points
            questions.append({
                "question_id": q["id"],
                "question_text": q["question_text"],
                "question_type": q.get("question_type", "MULTIPLE_CHOICE"),
                "points": points,
                "order_index": q.get("order_index", 0),
                "options": json.loads(q.get("options", "[]")),
                "correct_answer": q["correct_answer"],
                "explanation": q.get("explanation"),
                "created_at": q.get("created_at"),
            })

        return {
            "assessment_id": assessment_id,
            "assessment_title": assessment["title"],
            "quiz_mode": assessment.get("quiz_mode", "TEST"),
            "difficulty": assessment.get("difficulty", "MEDIUM"),
            "questions_count": len(questions),
            "total_points": total_points,
            "questions": questions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching questions",
        )


@router.post("/assessments/{assessment_id}/questions")
async def add_test_quiz_question(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    request: TestQuizQuestionCreateRequest,
    db=Depends(get_db),
):
    """
    Add a question to a test quiz manually.
    
    Teachers can add their own custom questions to the quiz.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Adding question to assessment {assessment_id}, teacher {teacher.id}")

        # Verify ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title, is_published")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        # Validate question type
        valid_types = ["MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER", "FILL_IN_BLANK"]
        if request.question_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid question type. Must be one of: {', '.join(valid_types)}",
            )

        # Validate correct answer is in options
        if request.question_type in ["MULTIPLE_CHOICE", "TRUE_FALSE"]:
            if request.correct_answer not in request.options:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Correct answer must be one of the options",
                )

        # Get current max order_index
        existing_questions = (
            db.admin_client.table("question")
            .select("order_index")
            .eq("assessment_id", assessment_id)
            .order("order_index", desc=True)
            .limit(1)
            .execute()
        )

        next_order = 0
        if existing_questions.data:
            next_order = (existing_questions.data[0].get("order_index", 0) or 0) + 1

        # Create question
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

        logger.info(f"Added question {question_id} to assessment {assessment_id}")

        return {
            "message": "Question added successfully",
            "question_id": question_id,
            "assessment_id": assessment_id,
            "order_index": next_order,
            "question_type": request.question_type,
            "points": request.points,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error adding question",
        )


@router.put("/assessments/{assessment_id}/questions/{question_id}")
async def update_test_quiz_question(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    question_id: str,
    request: TestQuizQuestionUpdateRequest,
    db=Depends(get_db),
):
    """
    Update a question in a test quiz.
    
    Teachers can modify any field of an existing question.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Updating question {question_id} in assessment {assessment_id}")

        # Verify assessment ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        # Verify question exists and belongs to this assessment
        question_result = (
            db.admin_client.table("question")
            .select("id")
            .eq("id", question_id)
            .eq("assessment_id", assessment_id)
            .execute()
        )

        if not question_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found in this assessment",
            )

        # Build update data
        update_data = {"updated_at": datetime.utcnow().isoformat()}

        if request.question_text is not None:
            update_data["question_text"] = request.question_text
        if request.question_type is not None:
            valid_types = ["MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER", "FILL_IN_BLANK"]
            if request.question_type not in valid_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid question type. Must be one of: {', '.join(valid_types)}",
                )
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
            "assessment_id": assessment_id,
            "updated_fields": [k for k in update_data.keys() if k != "updated_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating question",
        )


@router.delete("/assessments/{assessment_id}/questions/{question_id}")
async def delete_test_quiz_question(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    question_id: str,
    db=Depends(get_db),
):
    """
    Delete a question from a test quiz.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Deleting question {question_id} from assessment {assessment_id}")

        # Verify assessment ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        # Verify question exists and belongs to this assessment
        question_result = (
            db.admin_client.table("question")
            .select("id")
            .eq("id", question_id)
            .eq("assessment_id", assessment_id)
            .execute()
        )

        if not question_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found in this assessment",
            )

        # Delete the question
        db.admin_client.table("question").delete().eq("id", question_id).execute()

        logger.info(f"Deleted question {question_id}")

        return {
            "message": "Question deleted successfully",
            "question_id": question_id,
            "assessment_id": assessment_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting question",
        )


@router.put("/assessments/{assessment_id}/questions/reorder")
async def reorder_test_quiz_questions(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    question_order: list[str],  # List of question IDs in new order
    db=Depends(get_db),
):
    """
    Reorder questions in a test quiz.
    
    Pass a list of question IDs in the desired order.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Reordering questions in assessment {assessment_id}")

        # Verify assessment ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        # Update order for each question
        for index, q_id in enumerate(question_order):
            db.admin_client.table("question").update({
                "order_index": index,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", q_id).eq("assessment_id", assessment_id).execute()

        logger.info(f"Reordered {len(question_order)} questions")

        return {
            "message": "Questions reordered successfully",
            "assessment_id": assessment_id,
            "new_order": question_order,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reordering questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error reordering questions",
        )


@router.post("/assessments/{assessment_id}/questions/bulk")
async def add_bulk_questions(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    questions: list[TestQuizQuestionCreateRequest],
    db=Depends(get_db),
):
    """
    Add multiple questions to a test quiz at once.
    
    Useful for quickly populating a quiz with multiple questions.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Adding {len(questions)} questions to assessment {assessment_id}")

        # Verify assessment ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        # Get current max order_index
        existing_questions = (
            db.admin_client.table("question")
            .select("order_index")
            .eq("assessment_id", assessment_id)
            .order("order_index", desc=True)
            .limit(1)
            .execute()
        )

        start_order = 0
        if existing_questions.data:
            start_order = (existing_questions.data[0].get("order_index", 0) or 0) + 1

        # Prepare questions for insertion
        questions_to_insert = []
        for i, q in enumerate(questions):
            # Validate correct answer is in options
            if q.question_type in ["MULTIPLE_CHOICE", "TRUE_FALSE"]:
                if q.correct_answer not in q.options:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Question {i+1}: Correct answer must be one of the options",
                    )

            question_data = {
                "id": str(uuid4()),
                "assessment_id": assessment_id,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "points": q.points,
                "order_index": start_order + i,
                "options": json.dumps(q.options),
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            questions_to_insert.append(question_data)

        # Insert all questions
        if questions_to_insert:
            db.admin_client.table("question").insert(questions_to_insert).execute()

        logger.info(f"Added {len(questions_to_insert)} questions to assessment {assessment_id}")

        return {
            "message": f"Added {len(questions_to_insert)} questions successfully",
            "assessment_id": assessment_id,
            "questions_added": len(questions_to_insert),
            "total_questions": start_order + len(questions_to_insert),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding bulk questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error adding questions",
        )


# ==================== CSV Export/Import for Quiz Questions ====================


@router.get("/assessments/{assessment_id}/questions/export-csv")
async def export_questions_to_csv(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    db=Depends(get_db),
):
    """
    Export quiz questions to a CSV file for download.
    
    CSV Structure:
    Question | Option 1 | Option 2 | Option 3 | Option 4 | Correct Answer | Points
    
    For True/False questions, Option 3 and Option 4 will be empty.
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse
    
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        # Verify assessment exists and belongs to teacher's lecture
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(teacher_id, title)")
            .eq("id", assessment_id)
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found",
            )

        assessment = assessment_result.data[0]
        if assessment["lecture"]["teacher_id"] != str(teacher.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this assessment",
            )

        # Get all questions
        questions_result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_id)
            .order("order_index")
            .execute()
        )

        questions = questions_result.data or []

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Question",
            "Option 1",
            "Option 2", 
            "Option 3",
            "Option 4",
            "Correct Answer",
            "Points",
            "Explanation"
        ])
        
        # Write questions
        for q in questions:
            options = q.get("options", [])
            # Pad options to always have 4 columns
            while len(options) < 4:
                options.append("")
            
            writer.writerow([
                q.get("question_text", ""),
                options[0] if len(options) > 0 else "",
                options[1] if len(options) > 1 else "",
                options[2] if len(options) > 2 else "",
                options[3] if len(options) > 3 else "",
                q.get("correct_answer", ""),
                q.get("points", 1.0),
                q.get("explanation", "") or ""
            ])

        # Prepare response
        output.seek(0)
        
        # Create filename
        lecture_title = assessment["lecture"]["title"].replace(" ", "_")[:30]
        assessment_title = assessment.get("title", "quiz").replace(" ", "_")[:30]
        filename = f"quiz_questions_{lecture_title}_{assessment_title}.csv"

        logger.info(f"Exported {len(questions)} questions for assessment {assessment_id}")

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error exporting questions",
        )


@router.get("/assessments/{assessment_id}/questions/template-csv")
async def get_csv_template(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    db=Depends(get_db),
):
    """
    Get an empty CSV template for adding questions.
    
    CSV Structure:
    Question | Option 1 | Option 2 | Option 3 | Option 4 | Correct Answer | Points
    
    Instructions:
    - For Multiple Choice: Fill all 4 options, set Correct Answer to one of the options
    - For True/False: Set Option 1 = "True", Option 2 = "False", leave Option 3 & 4 empty
    - Points default to 1.0 if not specified
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse
    
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        # Verify assessment exists and belongs to teacher's lecture
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(teacher_id)")
            .eq("id", assessment_id)
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found",
            )

        assessment = assessment_result.data[0]
        if assessment["lecture"]["teacher_id"] != str(teacher.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this assessment",
            )

        # Create CSV template in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Question",
            "Option 1",
            "Option 2", 
            "Option 3",
            "Option 4",
            "Correct Answer",
            "Points",
            "Explanation"
        ])
        
        # Write example rows
        writer.writerow([
            "What is the capital of France?",
            "London",
            "Paris",
            "Berlin",
            "Madrid",
            "Paris",
            "1",
            "Paris is the capital and largest city of France."
        ])
        writer.writerow([
            "The Earth is flat.",
            "True",
            "False",
            "",
            "",
            "False",
            "1",
            "The Earth is approximately spherical."
        ])

        # Prepare response
        output.seek(0)
        filename = "quiz_questions_template.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating template: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating template",
        )


@router.post("/assessments/{assessment_id}/questions/import-csv")
async def import_questions_from_csv(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    file: UploadFile,
    replace_existing: bool = False,
    db=Depends(get_db),
):
    """
    Import quiz questions from a CSV file.
    
    CSV Structure (header row required):
    Question | Option 1 | Option 2 | Option 3 | Option 4 | Correct Answer | Points | Explanation
    
    Parameters:
    - file: The CSV file to upload
    - replace_existing: If True, deletes all existing questions before import. 
                        If False, appends to existing questions.
    
    Notes:
    - For True/False questions, leave Option 3 and Option 4 empty
    - Points defaults to 1.0 if not specified
    - Explanation is optional
    """
    import csv
    import io
    
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        # Verify assessment exists and belongs to teacher's lecture
        assessment_result = (
            db.admin_client.table("assessment")
            .select("*, lecture!inner(teacher_id)")
            .eq("id", assessment_id)
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found",
            )

        assessment = assessment_result.data[0]
        if assessment["lecture"]["teacher_id"] != str(teacher.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this assessment",
            )

        # Read and parse CSV file
        contents = await file.read()
        try:
            # Try UTF-8 first, then fall back to latin-1
            try:
                decoded = contents.decode("utf-8")
            except UnicodeDecodeError:
                decoded = contents.decode("latin-1")
            
            csv_file = io.StringIO(decoded)
            reader = csv.DictReader(csv_file)
            
            # Validate headers
            required_headers = ["Question", "Option 1", "Option 2", "Correct Answer"]
            if not reader.fieldnames:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="CSV file is empty or has no headers",
                )
            
            missing_headers = [h for h in required_headers if h not in reader.fieldnames]
            if missing_headers:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required headers: {', '.join(missing_headers)}",
                )
            
            # Parse questions
            questions_to_add = []
            errors = []
            row_num = 1
            
            for row in reader:
                row_num += 1
                question_text = row.get("Question", "").strip()
                
                if not question_text:
                    errors.append(f"Row {row_num}: Empty question text")
                    continue
                
                # Get options (filter out empty ones)
                options = []
                for i in range(1, 5):
                    opt = row.get(f"Option {i}", "").strip()
                    if opt:
                        options.append(opt)
                
                if len(options) < 2:
                    errors.append(f"Row {row_num}: At least 2 options required")
                    continue
                
                correct_answer = row.get("Correct Answer", "").strip()
                if not correct_answer:
                    errors.append(f"Row {row_num}: Missing correct answer")
                    continue
                
                if correct_answer not in options:
                    errors.append(f"Row {row_num}: Correct answer must match one of the options")
                    continue
                
                # Determine question type
                if len(options) == 2 and set(opt.lower() for opt in options) == {"true", "false"}:
                    question_type = "TRUE_FALSE"
                else:
                    question_type = "MULTIPLE_CHOICE"
                
                # Get points (default to 1.0)
                try:
                    points = float(row.get("Points", "1").strip() or "1")
                except ValueError:
                    points = 1.0
                
                explanation = row.get("Explanation", "").strip() or None
                
                questions_to_add.append({
                    "question_text": question_text,
                    "question_type": question_type,
                    "options": options,
                    "correct_answer": correct_answer,
                    "points": points,
                    "explanation": explanation,
                })
            
            if not questions_to_add:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No valid questions found. Errors: {'; '.join(errors)}",
                )
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error parsing CSV: {str(e)}",
            )

        # If replace_existing, delete all current questions
        if replace_existing:
            db.admin_client.table("question").delete().eq(
                "assessment_id", assessment_id
            ).execute()
            start_order = 0
        else:
            # Get current max order_index
            existing_result = (
                db.admin_client.table("question")
                .select("order_index")
                .eq("assessment_id", assessment_id)
                .order("order_index", desc=True)
                .limit(1)
                .execute()
            )
            start_order = (existing_result.data[0]["order_index"] + 1) if existing_result.data else 0

        # Insert questions
        questions_to_insert = []
        for i, q in enumerate(questions_to_add):
            question_id = str(uuid4())
            questions_to_insert.append({
                "id": question_id,
                "assessment_id": assessment_id,
                "question_text": q["question_text"],
                "question_type": q["question_type"],
                "options": q["options"],
                "correct_answer": q["correct_answer"],
                "points": q["points"],
                "explanation": q["explanation"],
                "order_index": start_order + i,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            })

        if questions_to_insert:
            db.admin_client.table("question").insert(questions_to_insert).execute()

        logger.info(f"Imported {len(questions_to_insert)} questions for assessment {assessment_id}")

        response = {
            "message": f"Successfully imported {len(questions_to_insert)} questions",
            "assessment_id": assessment_id,
            "questions_imported": len(questions_to_insert),
            "replace_existing": replace_existing,
        }
        
        if errors:
            response["warnings"] = errors
            response["rows_skipped"] = len(errors)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error importing questions",
        )


# ==================== Result View Request Routes ====================


class ResultRequestResponse(BaseModel):
    """Request body for approving/rejecting a result view request."""
    message: Optional[str] = None  # Optional message to student


@router.get("/result-requests")
async def get_result_view_requests(
    current_user: Annotated[User, Depends(require_teacher)],
    status_filter: Optional[str] = None,
    assessment_id: Optional[str] = None,
    db=Depends(get_db),
):
    """
    Get all result view requests for assessments owned by this teacher.
    
    Optionally filter by:
    - status: PENDING, APPROVED, REJECTED
    - assessment_id: Filter by specific assessment
    
    Returns list of requests with student and assessment details.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching result view requests for teacher {teacher.id}")

        # Build query
        query = (
            db.admin_client.table("result_view_request")
            .select("*, assessment!inner(id, title, quiz_mode, lecture!inner(id, title, course_id)), student!inner(id, user_id)")
            .eq("teacher_id", str(teacher.id))
            .order("requested_at", desc=True)
        )

        if status_filter and status_filter.upper() in ["PENDING", "APPROVED", "REJECTED"]:
            query = query.eq("status", status_filter.upper())

        if assessment_id:
            query = query.eq("assessment_id", assessment_id)

        result = query.execute()

        # Get student user details
        student_user_ids = list(set(
            req["student"]["user_id"] 
            for req in (result.data or []) 
            if req.get("student", {}).get("user_id")
        ))

        user_map = {}
        if student_user_ids:
            users_result = (
                db.admin_client.table("users")
                .select("id, first_name, last_name, email")
                .in_("id", student_user_ids)
                .execute()
            )
            user_map = {u["id"]: u for u in (users_result.data or [])}

        # Build response
        requests = []
        pending_count = 0
        approved_count = 0
        rejected_count = 0

        for req in (result.data or []):
            student = req.get("student", {})
            user_id = student.get("user_id")
            user = user_map.get(user_id, {})

            status_val = req["status"]
            if status_val == "PENDING":
                pending_count += 1
            elif status_val == "APPROVED":
                approved_count += 1
            elif status_val == "REJECTED":
                rejected_count += 1

            requests.append({
                "request_id": req["id"],
                "assessment_id": req["assessment_id"],
                "assessment_title": req["assessment"]["title"],
                "lecture_title": req["assessment"]["lecture"]["title"],
                "student_id": student.get("id"),
                "student_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Unknown",
                "student_email": user.get("email"),
                "status": status_val,
                "request_message": req.get("request_message"),
                "response_message": req.get("response_message"),
                "requested_at": req["requested_at"],
                "responded_at": req.get("responded_at"),
            })

        return {
            "total_count": len(requests),
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "requests": requests,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching result view requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching result view requests",
        )


@router.get("/result-requests/pending")
async def get_pending_result_requests(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Get only pending result view requests (shortcut for common use case).
    
    Returns pending requests grouped by assessment for easy review.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching pending result view requests for teacher {teacher.id}")

        # Get pending requests
        result = (
            db.admin_client.table("result_view_request")
            .select("*, assessment!inner(id, title, lecture!inner(id, title)), student!inner(id, user_id)")
            .eq("teacher_id", str(teacher.id))
            .eq("status", "PENDING")
            .order("requested_at", desc=False)  # Oldest first
            .execute()
        )

        if not result.data:
            return {
                "total_pending": 0,
                "assessments": [],
            }

        # Get student user details
        student_user_ids = list(set(
            req["student"]["user_id"] 
            for req in result.data 
            if req.get("student", {}).get("user_id")
        ))

        user_map = {}
        if student_user_ids:
            users_result = (
                db.admin_client.table("users")
                .select("id, first_name, last_name, email")
                .in_("id", student_user_ids)
                .execute()
            )
            user_map = {u["id"]: u for u in (users_result.data or [])}

        # Group by assessment
        by_assessment = {}
        for req in result.data:
            aid = req["assessment_id"]
            if aid not in by_assessment:
                by_assessment[aid] = {
                    "assessment_id": aid,
                    "assessment_title": req["assessment"]["title"],
                    "lecture_title": req["assessment"]["lecture"]["title"],
                    "requests": [],
                }

            student = req.get("student", {})
            user_id = student.get("user_id")
            user = user_map.get(user_id, {})

            by_assessment[aid]["requests"].append({
                "request_id": req["id"],
                "student_id": student.get("id"),
                "student_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Unknown",
                "student_email": user.get("email"),
                "request_message": req.get("request_message"),
                "requested_at": req["requested_at"],
            })

        assessments = list(by_assessment.values())

        return {
            "total_pending": len(result.data),
            "assessments": assessments,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching pending requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching pending requests",
        )


@router.post("/result-requests/{request_id}/approve")
async def approve_result_request(
    current_user: Annotated[User, Depends(require_teacher)],
    request_id: str,
    response: Optional[ResultRequestResponse] = None,
    db=Depends(get_db),
):
    """
    Approve a student's request to view quiz results.
    
    Once approved, the student will be able to see their detailed results
    including correct answers and explanations.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Teacher {teacher.id} approving request {request_id}")

        # Get the request and verify ownership
        request_result = (
            db.admin_client.table("result_view_request")
            .select("*, student!inner(user_id)")
            .eq("id", request_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not request_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Request not found or access denied",
            )

        req = request_result.data[0]

        if req["status"] != "PENDING":
            return {
                "message": f"Request has already been {req['status'].lower()}",
                "request_id": request_id,
                "status": req["status"],
            }

        # Update the request
        update_data = {
            "status": "APPROVED",
            "response_message": response.message if response else None,
            "responded_at": datetime.utcnow().isoformat(),
        }

        db.admin_client.table("result_view_request").update(update_data).eq("id", request_id).execute()

        # Get student name for response
        student_user_id = req["student"]["user_id"]
        user_result = (
            db.admin_client.table("users")
            .select("first_name, last_name")
            .eq("id", student_user_id)
            .execute()
        )
        user = user_result.data[0] if user_result.data else {}
        student_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Unknown"

        logger.info(f"Approved result view request {request_id}")

        # Notify student about the approval
        try:
            notification_service = NotificationService(db)
            
            # Get quiz title from assessment
            assessment_result = (
                db.admin_client.table("assessment")
                .select("title")
                .eq("id", req.get("assessment_id"))
                .execute()
            )
            quiz_title = assessment_result.data[0]["title"] if assessment_result.data else "Quiz"
            
            await notification_service.notify_result_approved(
                student_user_id=student_user_id,
                quiz_title=quiz_title,
                assessment_id=req.get("assessment_id"),
            )
        except Exception as notify_error:
            logger.warning(f"Failed to send result approval notification: {notify_error}")

        return {
            "message": f"Request approved. {student_name} can now view their quiz results.",
            "request_id": request_id,
            "status": "APPROVED",
            "student_name": student_name,
            "responded_at": update_data["responded_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error approving request",
        )


@router.post("/result-requests/{request_id}/reject")
async def reject_result_request(
    current_user: Annotated[User, Depends(require_teacher)],
    request_id: str,
    response: Optional[ResultRequestResponse] = None,
    db=Depends(get_db),
):
    """
    Reject a student's request to view quiz results.
    
    Optionally include a message explaining the rejection reason.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Teacher {teacher.id} rejecting request {request_id}")

        # Get the request and verify ownership
        request_result = (
            db.admin_client.table("result_view_request")
            .select("*, student!inner(user_id)")
            .eq("id", request_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not request_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Request not found or access denied",
            )

        req = request_result.data[0]

        if req["status"] != "PENDING":
            return {
                "message": f"Request has already been {req['status'].lower()}",
                "request_id": request_id,
                "status": req["status"],
            }

        # Update the request
        update_data = {
            "status": "REJECTED",
            "response_message": response.message if response else None,
            "responded_at": datetime.utcnow().isoformat(),
        }

        db.admin_client.table("result_view_request").update(update_data).eq("id", request_id).execute()

        # Get student name for response
        student_user_id = req["student"]["user_id"]
        user_result = (
            db.admin_client.table("users")
            .select("first_name, last_name")
            .eq("id", student_user_id)
            .execute()
        )
        user = user_result.data[0] if user_result.data else {}
        student_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Unknown"

        logger.info(f"Rejected result view request {request_id}")

        # Notify student about the rejection
        try:
            notification_service = NotificationService(db)
            
            # Get quiz title from assessment
            assessment_result = (
                db.admin_client.table("assessment")
                .select("title")
                .eq("id", req.get("assessment_id"))
                .execute()
            )
            quiz_title = assessment_result.data[0]["title"] if assessment_result.data else "Quiz"
            
            await notification_service.notify_result_rejected(
                student_user_id=student_user_id,
                quiz_title=quiz_title,
                reason=response.message if response else None,
                assessment_id=req.get("assessment_id"),
            )
        except Exception as notify_error:
            logger.warning(f"Failed to send result rejection notification: {notify_error}")

        return {
            "message": f"Request rejected. {student_name} will not be able to view their results.",
            "request_id": request_id,
            "status": "REJECTED",
            "student_name": student_name,
            "responded_at": update_data["responded_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error rejecting request",
        )


@router.post("/result-requests/bulk-approve")
async def bulk_approve_requests(
    current_user: Annotated[User, Depends(require_teacher)],
    request_ids: list[str],
    response: Optional[ResultRequestResponse] = None,
    db=Depends(get_db),
):
    """
    Approve multiple result view requests at once.
    
    Useful for approving all pending requests for an assessment.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Teacher {teacher.id} bulk approving {len(request_ids)} requests")

        # Verify all requests belong to this teacher and are pending
        requests_result = (
            db.admin_client.table("result_view_request")
            .select("id, status")
            .eq("teacher_id", str(teacher.id))
            .in_("id", request_ids)
            .execute()
        )

        valid_ids = [r["id"] for r in (requests_result.data or []) if r["status"] == "PENDING"]

        if not valid_ids:
            return {
                "message": "No valid pending requests found",
                "approved_count": 0,
                "skipped_count": len(request_ids),
            }

        # Update all valid requests
        update_data = {
            "status": "APPROVED",
            "response_message": response.message if response else None,
            "responded_at": datetime.utcnow().isoformat(),
        }

        for req_id in valid_ids:
            db.admin_client.table("result_view_request").update(update_data).eq("id", req_id).execute()

        logger.info(f"Bulk approved {len(valid_ids)} requests")

        return {
            "message": f"Successfully approved {len(valid_ids)} requests",
            "approved_count": len(valid_ids),
            "skipped_count": len(request_ids) - len(valid_ids),
            "approved_ids": valid_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bulk approving requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error approving requests",
        )


@router.post("/assessments/{assessment_id}/approve-all-requests")
async def approve_all_assessment_requests(
    current_user: Annotated[User, Depends(require_teacher)],
    assessment_id: str,
    response: Optional[ResultRequestResponse] = None,
    db=Depends(get_db),
):
    """
    Approve all pending result view requests for a specific assessment.
    
    Quick way to allow all students who requested to see their results.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Teacher {teacher.id} approving all requests for assessment {assessment_id}")

        # Verify assessment ownership
        assessment_result = (
            db.admin_client.table("assessment")
            .select("id, title")
            .eq("id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .execute()
        )

        if not assessment_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assessment not found or access denied",
            )

        assessment = assessment_result.data[0]

        # Get all pending requests for this assessment
        pending_result = (
            db.admin_client.table("result_view_request")
            .select("id")
            .eq("assessment_id", assessment_id)
            .eq("teacher_id", str(teacher.id))
            .eq("status", "PENDING")
            .execute()
        )

        if not pending_result.data:
            return {
                "message": "No pending requests for this assessment",
                "assessment_id": assessment_id,
                "assessment_title": assessment["title"],
                "approved_count": 0,
            }

        # Update all pending requests
        update_data = {
            "status": "APPROVED",
            "response_message": response.message if response else None,
            "responded_at": datetime.utcnow().isoformat(),
        }

        for req in pending_result.data:
            db.admin_client.table("result_view_request").update(update_data).eq("id", req["id"]).execute()

        count = len(pending_result.data)
        logger.info(f"Approved all {count} requests for assessment {assessment_id}")

        return {
            "message": f"Successfully approved all {count} pending requests",
            "assessment_id": assessment_id,
            "assessment_title": assessment["title"],
            "approved_count": count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving all requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error approving requests",
        )




# Import and include the router in routes_config
# This import is at the end to avoid circular imports
from routes_config import teacher_router as main_teacher_router

main_teacher_router.include_router(router)

