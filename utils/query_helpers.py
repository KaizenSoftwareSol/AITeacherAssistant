# utils/query_helpers.py
"""
Optimized query helpers with caching for common database operations.
These helpers are designed to minimize database round-trips and leverage caching.
"""

from typing import Any, Dict, List, Optional, Tuple
from services.cache_service import cache


class CourseQueryHelper:
    """Optimized queries for course-related data."""
    
    @staticmethod
    def get_course_with_cache(db, course_id: str, ttl: int = 300) -> Optional[Dict[str, Any]]:
        """Get course by ID with caching."""
        cached = cache.get("courses", course_id)
        if cached is not None:
            return cached if cached != "__NONE__" else None
        
        result = (
            db.admin_client.table("course")
            .select("*")
            .eq("id", course_id)
            .execute()
        )
        course = result.data[0] if result.data else None
        cache.set("courses", course if course else "__NONE__", course_id, ttl=ttl)
        return course
    
    @staticmethod
    def get_course_by_code(db, code: str, university_id: str, ttl: int = 300) -> Optional[Dict[str, Any]]:
        """Get course by code and university with caching."""
        cache_key = f"code:{code}:uni:{university_id}"
        cached = cache.get("courses", cache_key)
        if cached is not None:
            return cached if cached != "__NONE__" else None
        
        result = (
            db.admin_client.table("course")
            .select("*")
            .eq("code", code.upper())
            .eq("university_id", str(university_id))
            .execute()
        )
        course = result.data[0] if result.data else None
        cache.set("courses", course if course else "__NONE__", cache_key, ttl=ttl)
        return course


class EnrollmentQueryHelper:
    """Optimized queries for enrollment-related data."""
    
    @staticmethod
    def check_enrollment(
        db, student_id: str, course_id: str, ttl: int = 120
    ) -> Optional[Dict[str, Any]]:
        """Check if a student is enrolled in a course with caching."""
        cache_key = f"student:{student_id}:course:{course_id}"
        cached = cache.get("enrollments", cache_key)
        if cached is not None:
            return cached if cached != "__NONE__" else None
        
        result = (
            db.admin_client.table("enrollment")
            .select("*")
            .eq("student_id", str(student_id))
            .eq("course_id", course_id)
            .eq("is_active", True)
            .execute()
        )
        enrollment = result.data[0] if result.data else None
        cache.set("enrollments", enrollment if enrollment else "__NONE__", cache_key, ttl=ttl)
        return enrollment
    
    @staticmethod
    def get_student_enrollments(db, student_id: str, ttl: int = 120) -> List[Dict[str, Any]]:
        """Get all active enrollments for a student with caching."""
        cache_key = f"student:{student_id}:active"
        cached = cache.get("enrollments", cache_key)
        if cached is not None:
            return cached
        
        result = (
            db.admin_client.table("enrollment")
            .select("*, course(*)")
            .eq("student_id", str(student_id))
            .eq("is_active", True)
            .order("enrolled_at", desc=True)
            .execute()
        )
        enrollments = result.data or []
        cache.set("enrollments", enrollments, cache_key, ttl=ttl)
        return enrollments
    
    @staticmethod
    def invalidate_student_enrollments(student_id: str) -> None:
        """Invalidate enrollment cache for a student."""
        cache.invalidate_student(str(student_id))


class LectureQueryHelper:
    """Optimized queries for lecture-related data."""
    
    @staticmethod
    def get_lecture_with_cache(db, lecture_id: str, ttl: int = 300) -> Optional[Dict[str, Any]]:
        """Get lecture by ID with caching."""
        cache_key = f"lecture:{lecture_id}"
        cached = cache.get("lectures", cache_key)
        if cached is not None:
            return cached if cached != "__NONE__" else None
        
        result = (
            db.admin_client.table("lecture")
            .select("*, course!inner(id)")
            .eq("id", lecture_id)
            .execute()
        )
        lecture = result.data[0] if result.data else None
        cache.set("lectures", lecture if lecture else "__NONE__", cache_key, ttl=ttl)
        return lecture
    
    @staticmethod
    def get_published_lecture(db, lecture_id: str, ttl: int = 300) -> Optional[Dict[str, Any]]:
        """Get a published/delivered lecture by ID with caching."""
        cache_key = f"lecture:published:{lecture_id}"
        cached = cache.get("lectures", cache_key)
        if cached is not None:
            return cached if cached != "__NONE__" else None
        
        result = (
            db.admin_client.table("lecture")
            .select("*, course!inner(id)")
            .eq("id", lecture_id)
            .in_("status", ["PUBLISHED", "DELIVERED"])
            .execute()
        )
        lecture = result.data[0] if result.data else None
        cache.set("lectures", lecture if lecture else "__NONE__", cache_key, ttl=ttl)
        return lecture
    
    @staticmethod
    def get_course_lectures(
        db, course_id: str, status_filter: List[str] = None, ttl: int = 180
    ) -> List[Dict[str, Any]]:
        """Get all lectures for a course with caching."""
        status_key = ",".join(sorted(status_filter)) if status_filter else "all"
        cache_key = f"course:{course_id}:status:{status_key}"
        cached = cache.get("lectures", cache_key)
        if cached is not None:
            return cached
        
        query = (
            db.admin_client.table("lecture")
            .select("id, title, description, summary, chapter, status, created_at, has_embeddings, topic, lecture_number, content")
            .eq("course_id", course_id)
        )
        
        if status_filter:
            query = query.in_("status", status_filter)
        
        result = query.order("created_at", desc=False).execute()
        lectures = result.data or []
        cache.set("lectures", lectures, cache_key, ttl=ttl)
        return lectures


class StudentQueryHelper:
    """Optimized queries for student-related data."""
    
    @staticmethod
    def get_student_profile(db, user_id: str, ttl: int = 300) -> Optional[Dict[str, Any]]:
        """Get student profile by user_id with caching."""
        cache_key = f"user:{user_id}"
        cached = cache.get("students", cache_key)
        if cached is not None:
            return cached if cached != "__NONE__" else None
        
        result = (
            db.admin_client.table("student")
            .select("*")
            .eq("user_id", str(user_id))
            .execute()
        )
        student = result.data[0] if result.data else None
        cache.set("students", student if student else "__NONE__", cache_key, ttl=ttl)
        return student


class AssessmentQueryHelper:
    """Optimized queries for assessment-related data."""
    
    @staticmethod
    def get_default_assessment(db, lecture_id: str, ttl: int = 300) -> Optional[Dict[str, Any]]:
        """Get default assessment for a lecture with caching."""
        cache_key = f"lecture:{lecture_id}:default"
        cached = cache.get("assessments", cache_key)
        if cached is not None:
            return cached if cached != "__NONE__" else None
        
        result = (
            db.admin_client.table("assessment")
            .select("*")
            .eq("lecture_id", lecture_id)
            .eq("is_default", True)
            .execute()
        )
        assessment = result.data[0] if result.data else None
        cache.set("assessments", assessment if assessment else "__NONE__", cache_key, ttl=ttl)
        return assessment
    
    @staticmethod
    def get_assessment_questions(db, assessment_id: str, ttl: int = 300) -> List[Dict[str, Any]]:
        """Get questions for an assessment with caching."""
        cache_key = f"assessment:{assessment_id}:questions"
        cached = cache.get("assessments", cache_key)
        if cached is not None:
            return cached
        
        result = (
            db.admin_client.table("question")
            .select("*")
            .eq("assessment_id", assessment_id)
            .order("order_index")
            .execute()
        )
        questions = result.data or []
        cache.set("assessments", questions, cache_key, ttl=ttl)
        return questions


class FlashcardQueryHelper:
    """Optimized queries for flashcard-related data."""
    
    @staticmethod
    def get_lecture_flashcards(db, lecture_id: str, ttl: int = 600) -> List[Dict[str, Any]]:
        """Get flashcards for a lecture with caching."""
        cache_key = f"lecture:{lecture_id}"
        cached = cache.get("flashcards", cache_key)
        if cached is not None:
            return cached
        
        result = (
            db.admin_client.table("flashcard")
            .select("*")
            .eq("lecture_id", lecture_id)
            .order("order_index")
            .execute()
        )
        flashcards = result.data or []
        cache.set("flashcards", flashcards, cache_key, ttl=ttl)
        return flashcards


class TeacherQueryHelper:
    """Optimized queries for teacher-related data."""
    
    @staticmethod
    def get_teacher_name(db, teacher_id: str, ttl: int = 600) -> str:
        """Get teacher name by ID with caching."""
        cache_key = f"name:{teacher_id}"
        cached = cache.get("teachers", cache_key)
        if cached is not None:
            return cached
        
        result = (
            db.admin_client.table("teacher")
            .select("*, users(*)")
            .eq("id", teacher_id)
            .limit(1)
            .execute()
        )
        
        name = "Unknown Teacher"
        if result.data:
            user_data = result.data[0].get("users", {})
            if user_data:
                first_name = user_data.get("first_name", "")
                last_name = user_data.get("last_name", "")
                name = f"{first_name} {last_name}".strip() or "Unknown Teacher"
        
        cache.set("teachers", name, cache_key, ttl=ttl)
        return name
    
    @staticmethod
    def get_teacher_by_lecture(db, lecture_id: str, ttl: int = 600) -> Optional[str]:
        """Get teacher ID from a lecture with caching."""
        cache_key = f"lecture:{lecture_id}:teacher"
        cached = cache.get("teachers", cache_key)
        if cached is not None:
            return cached if cached != "__NONE__" else None
        
        result = (
            db.admin_client.table("lecture")
            .select("teacher_id")
            .eq("id", lecture_id)
            .limit(1)
            .execute()
        )
        
        teacher_id = result.data[0].get("teacher_id") if result.data else None
        cache.set("teachers", teacher_id if teacher_id else "__NONE__", cache_key, ttl=ttl)
        return teacher_id


# Utility function to verify enrollment with caching
def verify_student_enrollment(db, student_id: str, course_id: str) -> bool:
    """Verify student is enrolled in course using cached lookup."""
    enrollment = EnrollmentQueryHelper.check_enrollment(db, student_id, course_id)
    return enrollment is not None


# Utility function to get lecture with enrollment verification
def get_lecture_if_enrolled(
    db, 
    lecture_id: str, 
    student_id: str, 
    published_only: bool = True
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Get lecture if student is enrolled in the course.
    Returns (lecture, error_message) tuple.
    """
    # Get lecture
    if published_only:
        lecture = LectureQueryHelper.get_published_lecture(db, lecture_id)
    else:
        lecture = LectureQueryHelper.get_lecture_with_cache(db, lecture_id)
    
    if not lecture:
        return None, "Lecture not found or not published"
    
    course_id = lecture.get("course", {}).get("id") or lecture.get("course_id")
    
    # Verify enrollment
    if not verify_student_enrollment(db, student_id, course_id):
        return None, "You are not enrolled in this course"
    
    return lecture, None

