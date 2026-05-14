# course/routes.py
"""
Course management routes for teachers.
Optimized with caching for improved performance.
"""

from datetime import date, datetime, timedelta
import random
import string
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, ValidationInfo

from dependencies import require_teacher
from logger import logger
from models.user import User, UserRole
from services.cache_service import cache
from utils.db import get_db
from utils.id_converter import IDConverter

router = APIRouter()


class CourseCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    code: str | None = Field(default=None, min_length=4, max_length=10)
    description: str | None = None
    curriculum_content: str | None = None
    semester_name: str | None = None
    semester_start_date: str | None = None
    semester_end_date: str | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None):
        if value:
            value = value.strip().upper()
        return value or None


def _generate_course_code(db, length: int = 6) -> str:
    """Generate a unique alphanumeric course code."""
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):
        candidate = "".join(random.choices(alphabet, k=length))
        existing = db.get_records("course", {"code": candidate})
        if not existing:
            return candidate
    raise ValueError("Unable to generate unique course code. Please try again with a custom code.")


@router.get("/", response_model=dict)
async def get_teacher_courses(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Get all courses associated with the current teacher.

    Returns courses where:
    1. Teacher created the course (created_by_teacher_id)
    2. Course was assigned to teacher by admin (via course_teacher table)
    3. Teacher has created at least one lecture for the course

    Returns courses with extended stats: description, curriculum_content, 
    total_students, published_lectures (by this teacher), total_documents, 
    created_at, updated_at.

    This endpoint is only accessible to teachers.
    Optimized with caching and batch queries.
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
        
        # Check cache first
        cache_key = f"teacher_courses:{teacher.id}"
        cached_courses = cache.get("courses", cache_key)
        if cached_courses is not None:
            return cached_courses

        # Get courses for this teacher from multiple sources:
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
        
        # Convert to list
        courses = list(courses_dict.values())
        
        if not courses:
            # Still need university_type for the wrapper
            uni = db.get_record_by_id("university", teacher.university_id)
            uni_type = uni.get("type", "GENERAL") if uni else "GENERAL"
            return {"university_type": uni_type, "courses": []}
        
        course_ids = list(course_ids_set)
        
        # Batch fetch all enrollment counts at once
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
        
        # Batch fetch all lectures for this teacher with status at once
        # Only count this teacher's lectures for stats
        teacher_lectures_result = (
            db.admin_client.table("lecture")
            .select("course_id, status, document_id")
            .in_("course_id", course_ids)
            .eq("teacher_id", teacher.id)
            .execute()
        )
        
        # Process lecture data (only this teacher's lectures)
        published_counts = {}
        for lec in (teacher_lectures_result.data or []):
            cid = lec.get("course_id")
            if lec.get("status") in ["PUBLISHED", "DELIVERED"]:
                published_counts[cid] = published_counts.get(cid, 0) + 1

        # Count documents from document_assignment table (not from lectures)
        # This matches what the frontend expects when querying /courses/{id}/documents
        doc_assignment_counts = {}
        if course_ids:
            try:
                doc_assignments_result = (
                    db.admin_client.table("document_assignment")
                    .select("course_id, document_id")
                    .in_("course_id", course_ids)
                    .execute()
                )
                # Count unique documents per course
                for assignment in (doc_assignments_result.data or []):
                    cid = assignment.get("course_id")
                    if cid not in doc_assignment_counts:
                        doc_assignment_counts[cid] = set()
                    doc_assignment_counts[cid].add(assignment.get("document_id"))
            except Exception as e:
                logger.warning(f"Could not fetch document assignments for course stats: {e}")

        # Enrich each course with aggregate stats (keep integer IDs for now)
        enriched_courses = []
        for course in courses:
            course_id = course.get("id")  # Integer ID

            enriched_course = {
                **course,
                "total_students": enrollment_counts.get(course_id, 0),
                "published_lectures": published_counts.get(course_id, 0),
                "total_documents": len(doc_assignment_counts.get(course_id, set())),
            }
            enriched_courses.append(enriched_course)

        # Get university type
        university = db.get_record_by_id("university", teacher.university_id)
        university_type = university.get("type", "GENERAL") if university else "GENERAL"

        # Enrich courses with module info (using integer IDs)
        if course_ids:
            # Batch fetch module_course mappings for all courses
            mc_result = (
                db.admin_client.table("module_course")
                .select("course_id, module_id")
                .in_("course_id", course_ids)
                .execute()
            )
            course_module_map = {}
            all_module_ids = set()
            for mc in (mc_result.data or []):
                cid = mc["course_id"]
                mid = mc["module_id"]
                course_module_map.setdefault(cid, []).append(mid)
                all_module_ids.add(mid)

            # Batch fetch all modules
            modules_map = {}
            if all_module_ids:
                modules_result = (
                    db.admin_client.table("module")
                    .select("id, name, semester_id, display_order")
                    .in_("id", list(all_module_ids))
                    .execute()
                )
                for mod in (modules_result.data or []):
                    modules_map[mod["id"]] = mod

            # Batch fetch all semesters referenced by modules
            all_semester_ids = set(m["semester_id"] for m in modules_map.values() if m.get("semester_id"))
            semesters_map = {}
            if all_semester_ids:
                semesters_result = (
                    db.admin_client.table("semester")
                    .select("id, name")
                    .in_("id", list(all_semester_ids))
                    .execute()
                )
                for sem in (semesters_result.data or []):
                    semesters_map[sem["id"]] = sem

            # Attach modules array to each course (still using integer IDs)
            for ec in enriched_courses:
                course_id = ec.get("id")  # Still integer at this point
                module_ids = course_module_map.get(course_id, [])
                if module_ids:
                    ec["modules"] = []
                    for mid in module_ids:
                        mod = modules_map.get(mid, {})
                        sem = semesters_map.get(mod.get("semester_id", ""), {})
                        ec["modules"].append({
                            "module_id": mid,  # Will convert to UUID later
                            "module_name": mod.get("name"),
                            "module_display_order": mod.get("display_order", 0),
                            "semester_id": sem.get("id") if sem.get("id") else None,  # Will convert to UUID later
                            "semester_name": sem.get("name"),
                        })
        
        # Now convert all IDs to UUIDs for response
        for ec in enriched_courses:
            course_id = ec.get("id")
            if isinstance(course_id, int):
                # Convert course integer ID to UUID
                course_uuid = await IDConverter.int_to_uuid(db, "course", course_id)
                if course_uuid:
                    ec["id"] = course_uuid
                    ec["uuid"] = course_uuid
            
            # Convert module and semester IDs in modules array
            if "modules" in ec:
                for module in ec["modules"]:
                    if "module_id" in module and isinstance(module["module_id"], int):
                        module_uuid = await IDConverter.int_to_uuid(db, "module", module["module_id"])
                        if module_uuid:
                            module["module_id"] = module_uuid
                    if "semester_id" in module and isinstance(module["semester_id"], int):
                        semester_uuid = await IDConverter.int_to_uuid(db, "semester", module["semester_id"])
                        if semester_uuid:
                            module["semester_id"] = semester_uuid

        # Wrap response with university_type
        result = {"university_type": university_type, "courses": enriched_courses}

        # Cache the result for 2 minutes
        cache.set("courses", result, cache_key, ttl=120)

        logger.info(
            f"Found {len(enriched_courses)} courses for teacher {teacher.id}"
        )
        return result

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
    """
    Create a new course for the user's university.
    Available to both teachers and admins.
    """

    # Get university_id - from teacher profile or admin's university_id
    university_id = None
    created_by_teacher_id = None

    if current_user.role == UserRole.ADMIN:
        # Admin creating course
        if not current_user.university_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin must be associated with a university to create courses.",
            )
        university_id = current_user.university_id
        # Admins don't have teacher profiles, so created_by_teacher_id will be NULL
        created_by_teacher_id = None
    else:
        # Teacher creating course
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found. Please complete your teacher profile before creating courses.",
            )
        university_id = teacher.university_id
        created_by_teacher_id = teacher.id

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
            "university_id": university_id,
            "created_by_teacher_id": created_by_teacher_id,  # NULL for admin-created courses
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

        # Create or reuse a university-level semester if the teacher provided one
        if request.semester_name:
            try:
                sem_name = request.semester_name.strip()
                existing_sem = (
                    db.admin_client.table("semester")
                    .select("*")
                    .eq("university_id", university_id)
                    .eq("name", sem_name)
                    .is_("course_id", "null")
                    .limit(1)
                    .execute()
                )
                if existing_sem.data:
                    semester_data = existing_sem.data[0]
                else:
                    start = request.semester_start_date or datetime.utcnow().date().isoformat()
                    end = request.semester_end_date or (
                        (datetime.utcnow() + timedelta(days=120)).date().isoformat()
                    )
                    new_sem = (
                        db.admin_client.table("semester")
                        .insert({
                            "name": sem_name,
                            "university_id": university_id,
                            "start_date": start,
                            "end_date": end,
                            "created_at": datetime.utcnow().isoformat(),
                            "updated_at": datetime.utcnow().isoformat(),
                        })
                        .execute()
                    )
                    if new_sem.data:
                        semester_data = new_sem.data[0]
            except Exception as sem_err:
                logger.warning(f"Failed to create semester during course creation: {sem_err}")

        # Invalidate courses cache
        if created_by_teacher_id:
            # Invalidate cache for the teacher who created it
            cache.caches["courses"].delete_pattern(
                f"courses:teacher_courses:{created_by_teacher_id}"
            )
        # Invalidate all course caches for this university
        cache.caches["courses"].delete_pattern(f"courses:teacher_courses:*")
        # Invalidate admin courses cache
        cache.caches["courses"].delete_pattern(f"courses:admin_courses:{university_id}")

        # Auto-assign course to all Default Modules for this university
        try:
            default_modules = (
                db.admin_client.table("module")
                .select("id, semester_id")
                .eq("university_id", university_id)
                .eq("name", "Default Module")
                .execute()
            )
            if default_modules.data:
                mc_rows = [
                    {
                        "module_id": dm["id"],
                        "course_id": course_data["id"],
                    }
                    for dm in default_modules.data
                ]
                db.admin_client.table("module_course").insert(mc_rows).execute()
        except Exception as mc_err:
            logger.warning(f"Failed to auto-assign course to default modules: {mc_err}")

        logger.info(
            "Course created",
            extra={
                "course_id": course_data.get("id"),
                "created_by": current_user.id,
                "role": current_user.role.value,
                "university_id": university_id,
                "created_by_teacher_id": created_by_teacher_id,
            },
        )

        response = {
            "message": "Course created successfully",
            "course": course_data,
        }

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


@router.get("/{course_id}", response_model=dict)
async def get_course(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    db=Depends(get_db),
):
    """
    Get a specific course by ID with full details including semesters and aggregate stats.

    Returns: curriculum_content (markdown), semesters[{id,name,start_date,end_date}], 
    and aggregate stats (total_students, published_lectures, total_documents).

    This endpoint is only accessible to teachers and admins.
    Optimized with caching.
    """
    try:
        # Get university_id - from teacher profile or admin's university_id
        university_id = None
        
        if current_user.role == UserRole.ADMIN:
            if not current_user.university_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Admin must be associated with a university.",
                )
            university_id = current_user.university_id
        else:
            teacher = current_user.teacher_profile
            if not teacher:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Teacher profile not found",
                )
            university_id = teacher.university_id

        logger.info(f"Fetching course {course_id}")
        
        # Check cache first
        cache_key = f"course_detail:{course_id}"
        cached_course = cache.get("courses", cache_key)
        if cached_course is not None:
            # Still verify access
            if cached_course.get("university_id") == university_id:
                return cached_course

        # Get course (cached)
        course = db.get_record_by_id("course", course_id)
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        # Verify course belongs to user's university
        if course.get("university_id") != university_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this course",
            )

        # Get university-level semesters for this course's university
        # Semesters are now managed at university level, not course level
        semesters_result = (
            db.admin_client.table("semester")
            .select("id, name, start_date, end_date, created_at, updated_at")
            .eq("university_id", university_id)
            .is_("course_id", "null")  # Only university-level semesters
            .order("start_date", desc=True)
            .execute()
        )
        
        semesters = []
        for sem in (semesters_result.data or []):
            if sem.get("course_id") is not None:
                continue  # Skip course-level semesters (legacy)
            semesters.append({
                "id": sem["id"],
                "name": sem["name"],
                "start_date": sem.get("start_date"),
                "end_date": sem.get("end_date"),
            })

        # Batch fetch all stats in parallel
        # Get enrollment count, lecture data
        enrollments_result = (
            db.admin_client.table("enrollment")
            .select("id", count="exact")
            .eq("course_id", course_id)
            .eq("is_active", True)
            .execute()
        )
        total_students = enrollments_result.count or 0

        # Get all lectures with status and document_id in one query
        lectures_result = (
            db.admin_client.table("lecture")
            .select("status, document_id")
            .eq("course_id", course_id)
            .execute()
        )
        
        published_lectures = 0
        unique_doc_ids = set()
        for lec in (lectures_result.data or []):
            if lec.get("status") in ["PUBLISHED", "DELIVERED"]:
                published_lectures += 1
            if lec.get("document_id"):
                unique_doc_ids.add(lec["document_id"])
        total_documents = len(unique_doc_ids)

        # Include module info for this course
        modules_info = []
        module_courses_result = (
            db.admin_client.table("module_course")
            .select("module_id")
            .eq("course_id", course_id)
            .execute()
        )
        module_ids = [mc["module_id"] for mc in (module_courses_result.data or [])]
        if module_ids:
            for mid in module_ids:
                mod = db.get_record_by_id("module", mid)
                if mod:
                    modules_info.append({
                        "id": mod["id"],
                        "name": mod["name"],
                        "semester_id": mod["semester_id"],
                    })

        # Build response
        response = {
            **course,
            "semesters": semesters,
            "total_students": total_students,
            "published_lectures": published_lectures,
            "total_documents": total_documents,
        }
        if modules_info:
            response["modules"] = modules_info

        # Cache the result for 3 minutes
        cache.set("courses", response, cache_key, ttl=180)

        logger.info(f"Found course {course_id} with {len(semesters)} semesters")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching course: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching course",
        )


@router.get("/{course_id}/semesters", response_model=list[dict])
async def get_course_semesters(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    db=Depends(get_db),
):
    """
    Get all semesters for a specific course.

    This endpoint is accessible to teachers and admins.
    """
    try:
        # Get university_id - from teacher profile or admin's university_id
        university_id = None
        
        if current_user.role == UserRole.ADMIN:
            if not current_user.university_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Admin must be associated with a university.",
                )
            university_id = current_user.university_id
        else:
            teacher = current_user.teacher_profile
            if not teacher:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Teacher profile not found",
                )
            university_id = teacher.university_id

        # Verify course belongs to user's university
        course = db.get_record_by_id("course", course_id, use_cache=False)
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        if course.get("university_id") != university_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this course",
            )

        # Get university-level semesters for this course's university
        # Semesters are now managed at university level, not course level
        # Use direct query with .is_() for NULL check instead of get_records
        try:
            semesters_result = (
                db.get_admin_client()
                .table("semester")
                .select("*")
                .eq("university_id", university_id)
                .is_("course_id", "null")  # Use .is_() for NULL check
                .order("start_date", desc=True)
                .execute()
            )

            semesters = semesters_result.data or []

            # Fallback: filter in Python if .is_() doesn't work properly
            semesters = [s for s in semesters if s.get("course_id") is None]

        except Exception as e:
            logger.error(f"Error fetching semesters with direct query: {e}")
            # Fallback to get_records but filter None manually
            all_semesters = db.get_records(
                "semester",
                filters={"university_id": university_id},
                skip=0,
                limit=1000
            )
            semesters = [s for s in all_semesters if s.get("course_id") is None]

        # Fallback filter: ensure only university-level semesters (course_id is None)
        semesters = [s for s in semesters if s.get("course_id") is None]

        logger.info(f"Found {len(semesters)} university-level semesters for university {university_id}")
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
    
    Returns course_code and accurate total_students that matches students.length.
    Shows students who enrolled using the course code.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )
        
        # Convert UUID to integer ID if needed
        course_int_id = course_id
        if IDConverter.is_uuid(course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )
        
        # Verify course belongs to teacher's university
        course_result = (
            db.admin_client.table("course")
            .select("id, name, code")
            .eq("id", course_int_id)
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
            .eq("course_id", course_int_id)
            .eq("is_active", True)
            .order("enrolled_at", desc=True)
            .execute()
        )
        
        students = []
        for enrollment in enrollments_result.data or []:
            student_data = enrollment.get("student", {})
            user_data = student_data.get("users", {})
            
            # Convert integer IDs to UUIDs for response
            enrollment_id = enrollment["id"]
            if isinstance(enrollment_id, int):
                enrollment_uuid = await IDConverter.int_to_uuid(db, "enrollment", enrollment_id)
                if enrollment_uuid:
                    enrollment_id = enrollment_uuid
            
            student_id = student_data.get("id")
            if isinstance(student_id, int):
                student_uuid = await IDConverter.int_to_uuid(db, "student", student_id)
                if student_uuid:
                    student_id = student_uuid
            
            students.append({
                "enrollment_id": enrollment_id if isinstance(enrollment_id, str) else str(enrollment_id),
                "student_id": student_id if isinstance(student_id, str) else str(student_id),
                "name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                "email": user_data.get("email"),
                "enrolled_at": enrollment["enrolled_at"],
            })
        
        # Ensure total_students matches students.length
        total_students = len(students)
        
        return {
            "course_id": course_id,
            "course_name": course["name"],
            "course_code": course["code"],
            "total_students": total_students,
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


@router.get("/{course_id}/lectures", response_model=list[dict])
async def get_course_lectures(
    current_user: Annotated[User, Depends(require_teacher)],
    course_id: str,
    lecture_status: str = None,
    topic: str = None,
    db=Depends(get_db),
):
    """
    Get all lectures for a specific course.
    
    Returns: id, title, status, topic, lecture_number, created_at, 
    has_embeddings, pdf_filename, pdf_size.
    
    Optional filters: ?lecture_status=, ?topic=
    
    This endpoint is only accessible to teachers and admins.
    Optimized with caching.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching lectures for course {course_id}")
        
        # Check cache (include filters in cache key)
        cache_key = f"teacher_lectures:{course_id}:s:{lecture_status or 'all'}:t:{topic or 'all'}"
        cached_lectures = cache.get("lectures", cache_key)
        if cached_lectures is not None:
            return cached_lectures

        # Verify course belongs to teacher's university
        course_result = (
            db.admin_client.table("course")
            .select("id")
            .eq("id", course_id)
            .eq("university_id", teacher.university_id)
            .execute()
        )
        
        if not course_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        # Build query
        query = (
            db.admin_client.table("lecture")
            .select("id, title, status, topic, lecture_number, created_at, has_embeddings")
            .eq("course_id", course_id)
        )
        
        # Apply filters
        if lecture_status:
            query = query.eq("status", lecture_status)
        if topic:
            query = query.eq("topic", topic)
        
        lectures_result = query.order("created_at", desc=True).execute()
        
        lectures = []
        lecture_ids = [lec["id"] for lec in (lectures_result.data or [])]
        
        # Batch fetch PDF info from lecture_content
        pdf_info_by_lecture = {}
        if lecture_ids:
            content_result = (
                db.admin_client.table("lecture_content")
                .select("lecture_id, file_name, file_size")
                .in_("lecture_id", lecture_ids)
                .execute()
            )
            for content in (content_result.data or []):
                lid = content.get("lecture_id")
                if lid and lid not in pdf_info_by_lecture:
                    pdf_info_by_lecture[lid] = {
                        "pdf_filename": content.get("file_name"),
                        "pdf_size": content.get("file_size", 0),
                    }
        
        # Build response
        for lecture in (lectures_result.data or []):
            pdf_info = pdf_info_by_lecture.get(lecture["id"], {})
            lectures.append({
                "id": lecture["id"],
                "title": lecture["title"],
                "status": lecture["status"],
                "topic": lecture.get("topic"),
                "lecture_number": lecture.get("lecture_number"),
                "created_at": lecture["created_at"],
                "has_embeddings": lecture.get("has_embeddings", False),
                "pdf_filename": pdf_info.get("pdf_filename"),
                "pdf_size": pdf_info.get("pdf_size", 0),
            })

        # Cache the result for 2 minutes
        cache.set("lectures", lectures, cache_key, ttl=120)

        logger.info(f"Found {len(lectures)} lectures for course {course_id}")
        return lectures

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching course lectures: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching course lectures",
        )


@router.delete("/{course_id}", status_code=status.HTTP_200_OK)
async def delete_course(
    course_id: str,
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Delete a course and all associated data.
    Available to both teachers and admins.
    
    Teachers can only delete courses they created.
    Admins can delete any course in their university.
    
    This will cascade delete:
    - Enrollments
    - Semesters
    - Lectures (and all lecture-related data)
    - Course-teacher assignments
    """
    try:
        # Get course
        course = db.get_record_by_id("course", course_id, use_cache=False)
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        # Get university_id and verify access
        university_id = None
        can_delete = False

        if current_user.role == UserRole.ADMIN:
            # Admin can delete any course in their university
            if not current_user.university_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Admin must be associated with a university.",
                )
            university_id = current_user.university_id
            if course.get("university_id") != university_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only delete courses from your own university",
                )
            can_delete = True
        else:
            # Teacher can only delete courses they created
            teacher = current_user.teacher_profile
            if not teacher:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Teacher profile not found",
                )
            university_id = teacher.university_id
            
            if course.get("university_id") != university_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this course",
                )
            
            # Check if teacher created this course
            if course.get("created_by_teacher_id") == teacher.id:
                can_delete = True
            else:
                # Check if course is assigned to this teacher
                assignment_result = (
                    db.admin_client.table("course_teacher")
                    .select("id")
                    .eq("course_id", course_id)
                    .eq("teacher_id", teacher.id)
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )
                if assignment_result.data:
                    can_delete = True

            if not can_delete:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only delete courses you created",
                )

        # Delete all related data in proper order (cascade delete)
        logger.info(f"Starting cascade delete for course {course_id}")

        # Convert UUID to integer ID if needed
        course_int_id = course_id
        if IDConverter.is_uuid(course_id):
            course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
            if not course_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )

        # 1. Get all lectures for this course (need to delete them first)
        lectures = db.get_records("lecture", {"course_id": course_int_id}, use_cache=False)
        lecture_ids = [lec["id"] for lec in lectures]

        # 2. For each lecture, delete all related data (similar to delete_lecture endpoint)
        for lecture_id in lecture_ids:
            # lecture_id from database is already an integer
            # Get assessments for this lecture
            assessments = db.get_records("assessment", {"lecture_id": lecture_id})
            assessment_ids = [a["id"] for a in assessments]

            # Delete assessment-related data
            for assessment_id in assessment_ids:
                # assessment_id from database is already an integer
                # Delete questions
                questions = db.get_records("question", {"assessment_id": assessment_id})
                for question in questions:
                    db.delete_record("question", question["id"])

                # Delete assessment submissions
                submissions = db.get_records(
                    "assessment_submission", {"assessment_id": assessment_id}
                )
                for submission in submissions:
                    db.delete_record("assessment_submission", submission["id"])

                # Delete result view requests
                result_requests = db.get_records(
                    "result_view_request", {"assessment_id": assessment_id}
                )
                for request in result_requests:
                    db.delete_record("result_view_request", request["id"])

                # Delete assessment
                db.delete_record("assessment", assessment_id)

            # Delete lecture-related data
            engagements = db.get_records("student_engagement", {"lecture_id": lecture_id})
            for engagement in engagements:
                db.delete_record("student_engagement", engagement["id"])

            conversations = db.get_records("ai_conversation", {"lecture_id": lecture_id})
            for conversation in conversations:
                db.delete_record("ai_conversation", conversation["id"])

            analytics = db.get_records("lecture_analytics", {"lecture_id": lecture_id})
            for analytic in analytics:
                db.delete_record("lecture_analytics", analytic["id"])

            chunks = db.get_records("lecture_chunk", {"lecture_id": lecture_id})
            for chunk in chunks:
                db.delete_record("lecture_chunk", chunk["id"])

            embeddings = db.get_records("lecture_embedding", {"lecture_id": lecture_id})
            for embedding in embeddings:
                db.delete_record("lecture_embedding", embedding["id"])

            # Delete lecture content and files
            lecture_contents = db.get_records("lecture_content", {"lecture_id": lecture_id})
            for content in lecture_contents:
                try:
                    from supabase_config import supabase
                    storage_bucket = content.get("storage_bucket")
                    storage_path = content.get("storage_path")
                    if storage_bucket and storage_path:
                        supabase.delete_file(storage_bucket, storage_path)
                except Exception as e:
                    logger.warning(
                        f"Failed to delete file {content.get('storage_path', 'unknown')}: {str(e)}"
                    )
                db.delete_record("lecture_content", content["id"])

            # Delete flashcard
            flashcards = db.get_records("flashcard", {"lecture_id": lecture_id})
            for flashcard in flashcards:
                db.delete_record("flashcard", flashcard["id"])

            # Finally delete the lecture
            db.delete_record("lecture", lecture_id)

        logger.info(f"Deleted {len(lecture_ids)} lectures and related data")

        # 3. Delete enrollments (references course_id and semester_id)
        enrollments = db.get_records("enrollment", {"course_id": course_int_id}, use_cache=False)
        for enrollment in enrollments:
            db.delete_record("enrollment", enrollment["id"])
        logger.info(f"Deleted {len(enrollments)} enrollments")

        # 4. Delete assessments that reference course_id directly (not via lecture)
        course_assessments = db.get_records("assessment", {"course_id": course_int_id}, use_cache=False)
        for assessment in course_assessments:
            # Delete questions
            questions = db.get_records("question", {"assessment_id": assessment["id"]})
            for question in questions:
                db.delete_record("question", question["id"])

            # Delete submissions
            submissions = db.get_records(
                "assessment_submission", {"assessment_id": assessment["id"]}
            )
            for submission in submissions:
                db.delete_record("assessment_submission", submission["id"])

            # Delete result view requests
            result_requests = db.get_records(
                "result_view_request", {"assessment_id": assessment["id"]}
            )
            for request in result_requests:
                db.delete_record("result_view_request", request["id"])

            db.delete_record("assessment", assessment["id"])
        logger.info(f"Deleted {len(course_assessments)} course-level assessments")

        # 5. Delete document assignments
        doc_assignments = db.get_records(
            "document_assignment", {"course_id": course_id}, use_cache=False
        )
        for assignment in doc_assignments:
            db.delete_record("document_assignment", assignment["id"])
        logger.info(f"Deleted {len(doc_assignments)} document assignments")

        # 6. Delete course-teacher assignments
        course_teachers = db.get_records(
            "course_teacher", {"course_id": course_id}, use_cache=False
        )
        for assignment in course_teachers:
            db.delete_record("course_teacher", assignment["id"])
        logger.info(f"Deleted {len(course_teachers)} course-teacher assignments")

        # 7. Note: Semesters are now university-level and not tied to courses
        # They are managed separately by admins and should not be deleted when deleting a course
        # Legacy course-level semesters (if any) would be deleted here, but we now use university-level semesters

        # 8. Finally, delete the course itself
        success = db.delete_record("course", course_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete course",
            )

        # Invalidate caches
        cache.caches["courses"].delete_pattern(f"courses:teacher_courses:*")
        cache.caches["courses"].delete_pattern(f"courses:admin_courses:{university_id}")
        cache.caches["courses"].delete_pattern(f"courses:course_detail:{course_id}")

        logger.info(
            f"Course {course_id} deleted by {current_user.role.value} {current_user.id}"
        )

        return {"message": "Course deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting course: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting course",
        ) from e


# Import and include the router in the course_router from routes_config
from routes_config import course_router as main_course_router

main_course_router.include_router(router)
