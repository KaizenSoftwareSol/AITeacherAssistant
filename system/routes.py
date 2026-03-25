# system/routes.py

import secrets
import string
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth.models import UserCreate
from auth.service import AuthService
from dependencies import SystemUser
from models.user import UserRole
from system.models import (
    AdminCreateRequest,
    AdminCreateResponse,
    AdminSummary,
    UniversityCreateRequest,
    UniversityDetail,
    UniversityResponse,
)
from utils.db import get_db
from utils.id_converter import IDConverter
from logger import logger

router = APIRouter()


def _generate_password(length: int = 12) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    return password


def _sanitize_for_username(name: str) -> str:
    """Convert university name to a valid username format."""
    # Remove special characters, keep alphanumeric and underscores
    sanitized = "".join(c if c.isalnum() or c in (" ", "_") else "" for c in name)
    # Replace spaces with underscores and convert to lowercase
    sanitized = sanitized.replace(" ", "_").lower()
    # Remove consecutive underscores
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")
    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")
    return sanitized


@router.post("/universities", status_code=status.HTTP_201_CREATED, response_model=UniversityResponse)
async def create_university(
    university_data: UniversityCreateRequest,
    current_user: SystemUser,
    db=Depends(get_db),
):
    """
    Create/onboard a new university.

    System users can onboard universities that can then have admins assigned.
    """
    try:
        # Check if university with this name already exists
        existing_universities = db.get_records(
            "university", {"name": university_data.name}, use_cache=False
        )
        if existing_universities:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"University with name '{university_data.name}' already exists",
            )

        # Create university
        uni_type = (university_data.type or "GENERAL").upper()
        valid_types = {"MEDICAL", "ENGINEERING", "LAW", "BUSINESS", "ARTS", "GENERAL"}
        if uni_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid university type '{uni_type}'. Must be one of: {', '.join(sorted(valid_types))}",
            )

        university_payload = {
            "id": str(uuid4()),
            "name": university_data.name.strip(),
            "type": uni_type,
        }
        if university_data.location:
            university_payload["location"] = university_data.location.strip()

        new_university = db.create_record("university", university_payload)

        logger.info(
            f"System user {current_user.id} created university {new_university['id']} "
            f"({university_data.name})"
        )

        return UniversityResponse(
            id=new_university["id"],
            name=new_university["name"],
            location=new_university.get("location"),
            type=new_university.get("type", "GENERAL"),
            created_at=str(new_university.get("created_at", "")),
            updated_at=str(new_university.get("updated_at", "")),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating university: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating university",
        ) from e


@router.get("/universities")
async def list_universities(
    current_user: SystemUser,
    db=Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: str = Query(None, description="Search by university name or location"),
    sort_by: str = Query("name", description="Sort by: name, location, created_at, admin_count"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
):
    """
    List all universities with admin counts and pagination.

    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - search: Search by university name or location
    - sort_by: Sort field (default: name)
    - sort_order: asc or desc (default: asc)
    """
    try:
        # Get all universities
        universities = db.get_records(
            "university", {}, skip=0, limit=1000, use_cache=False
        )

        if not universities:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 1,
                "has_next": False,
                "has_previous": False,
            }
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            universities = [
                u for u in universities
                if search_lower in (u.get("name") or "").lower()
                or search_lower in (u.get("location") or "").lower()
            ]

        university_ids = [u["id"] for u in universities]

        # Convert university UUIDs to integer IDs for database query
        university_int_ids = []
        uuid_to_int_map = {}
        for univ_uuid in university_ids:
            if IDConverter.is_uuid(univ_uuid):
                univ_int_id = await IDConverter.uuid_to_int(db, "university", univ_uuid)
                if univ_int_id:
                    university_int_ids.append(univ_int_id)
                    uuid_to_int_map[univ_uuid] = univ_int_id
            else:
                # Already an integer
                university_int_ids.append(univ_uuid)
                uuid_to_int_map[univ_uuid] = univ_uuid

        # Get admin counts for each university
        admin_counts = {}
        admin_users_map = {}

        if university_int_ids:
            admins_result = (
                db.admin_client.table("users")
                .select("id, email, username, first_name, last_name, university_id, is_active, created_at")
                .in_("university_id", university_int_ids)
                .eq("role", UserRole.ADMIN.value)
                .execute()
            )

            # Map integer university_id back to UUID for response
            int_to_uuid_map = {v: k for k, v in uuid_to_int_map.items()}

            for admin in admins_result.data or []:
                univ_int_id = admin.get("university_id")
                if univ_int_id:
                    # Convert integer ID back to UUID for response
                    univ_uuid = int_to_uuid_map.get(univ_int_id)
                    if univ_uuid:
                        if univ_uuid not in admin_counts:
                            admin_counts[univ_uuid] = 0
                            admin_users_map[univ_uuid] = []
                        admin_counts[univ_uuid] += 1
                        admin_users_map[univ_uuid].append(
                            AdminSummary(
                                user_id=admin["id"],
                                email=admin["email"],
                                username=admin["username"],
                                first_name=admin.get("first_name", ""),
                                last_name=admin.get("last_name", ""),
                                university_id=univ_uuid,
                                university_name="",  # Will be populated below
                                is_active=admin.get("is_active", True),
                                created_at=str(admin.get("created_at", "")),
                            )
                        )

        # Sort
        sort_desc = sort_order.lower() == "desc"
        if sort_by == "admin_count":
            universities.sort(key=lambda u: admin_counts.get(u["id"], 0), reverse=sort_desc)
        else:
            sort_key_map = {
                "name": lambda u: (u.get("name") or "").lower(),
                "location": lambda u: (u.get("location") or "").lower(),
                "created_at": lambda u: u.get("created_at") or "",
            }
            sort_fn = sort_key_map.get(sort_by, sort_key_map["name"])
            universities.sort(key=sort_fn, reverse=sort_desc)
        
        # Calculate pagination
        total = len(universities)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = universities[start:end]

        # Build response
        universities_detail = []
        for university in page_data:
            univ_id = university["id"]
            admin_list = admin_users_map.get(univ_id, [])
            # Populate university_name in admin summaries
            for admin in admin_list:
                admin.university_name = university["name"]

            universities_detail.append(
                UniversityDetail(
                    id=univ_id,
                    name=university["name"],
                    location=university.get("location"),
                    type=university.get("type", "GENERAL"),
                    created_at=str(university.get("created_at", "")),
                    updated_at=str(university.get("updated_at", "")),
                    admin_count=admin_counts.get(univ_id, 0),
                    admin_users=admin_list,
                )
            )

        return {
            "items": universities_detail,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    except Exception as e:
        logger.error(f"Error listing universities: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching universities",
        ) from e


@router.get("/universities/{university_id}", response_model=UniversityDetail)
async def get_university(
    university_id: str,
    current_user: SystemUser,
    db=Depends(get_db),
):
    """
    Get detailed information about a specific university.

    Includes all admin users for that university.
    """
    try:
        university = db.get_record_by_id("university", university_id, use_cache=False)
        if not university:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="University not found",
            )

        # Convert UUID to integer ID if needed
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="University not found",
                )

        # Get all admins for this university
        admins_result = (
            db.admin_client.table("users")
            .select("id, email, username, first_name, last_name, university_id, is_active, created_at")
            .eq("university_id", university_int_id)
            .eq("role", UserRole.ADMIN.value)
            .execute()
        )

        admin_users = []
        for admin in admins_result.data or []:
            admin_users.append(
                AdminSummary(
                    user_id=admin["id"],
                    email=admin["email"],
                    username=admin["username"],
                    first_name=admin.get("first_name", ""),
                    last_name=admin.get("last_name", ""),
                    university_id=university_id,
                    university_name=university["name"],
                    is_active=admin.get("is_active", True),
                    created_at=str(admin.get("created_at", "")),
                )
            )

        return UniversityDetail(
            id=university["id"],
            name=university["name"],
            location=university.get("location"),
            type=university.get("type", "GENERAL"),
            created_at=str(university.get("created_at", "")),
            updated_at=str(university.get("updated_at", "")),
            admin_count=len(admin_users),
            admin_users=admin_users,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching university: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching university",
        ) from e


@router.delete("/universities/{university_id}", status_code=status.HTTP_200_OK)
async def delete_university(
    university_id: str,
    current_user: SystemUser,
    db=Depends(get_db),
):
    """
    Delete a university and ALL associated data.

    This will cascade delete:
    - All courses and their related data (lectures, assessments, quizzes, enrollments)
    - All users (admins, teachers, students) and their profiles
    - All documents uploaded by teachers
    - All enrollments
    - All semesters
    - The university itself

    WARNING: This is a destructive operation. Use with caution.
    """
    try:
        university = db.get_record_by_id("university", university_id, use_cache=False)
        if not university:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="University not found",
            )

        university_name = university.get("name", university_id)

        # Convert UUID to integer ID if needed
        university_int_id = university_id
        if IDConverter.is_uuid(university_id):
            university_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if not university_int_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="University not found",
                )

        logger.info(
            f"System user {current_user.id} initiating cascade delete for university "
            f"{university_id} ({university_name})"
        )

        # Delete modules and module_course entries for this university
        modules = db.get_records("module", {"university_id": university_int_id}, use_cache=False)
        for module in modules:
            # module_course entries cascade-delete via FK
            db.delete_record("module", module["id"])
        if modules:
            logger.info(f"Deleted {len(modules)} modules")

        # Get all courses for this university
        courses = db.get_records(
            "course", {"university_id": university_int_id}, use_cache=False
        )
        course_ids = [c["id"] for c in courses]
        deleted_courses = 0

        # Delete all courses and their related data (similar to course deletion logic)
        for course in courses:
            course_id = course["id"]
            # course_id from database is already an integer
            try:
                # Get all lectures for this course
                lectures = db.get_records("lecture", {"course_id": course_id}, use_cache=False)
                lecture_ids = [lec["id"] for lec in lectures]

                # Delete lecture-related data
                for lecture_id in lecture_ids:
                    # lecture_id from database is already an integer
                    # Delete assessments and their children
                    assessments = db.get_records("assessment", {"lecture_id": lecture_id})
                    for assessment in assessments:
                        assessment_id = assessment["id"]
                        # assessment_id from database is already an integer
                        # Delete questions
                        questions = db.get_records("question", {"assessment_id": assessment_id})
                        for question in questions:
                            db.delete_record("question", question["id"])
                        # Delete submissions
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
                        db.delete_record("assessment", assessment_id)

                    # Delete lecture children
                    for table_name in [
                        "student_engagement",
                        "ai_conversation",
                        "lecture_analytics",
                        "flashcard",
                    ]:
                        records = db.get_records(table_name, {"lecture_id": lecture_id})
                        for record in records:
                            db.delete_record(table_name, record["id"])

                    # Delete lecture chunks and embeddings
                    chunks = db.get_records("lecture_chunk", {"lecture_id": lecture_id})
                    chunk_ids = [chunk["id"] for chunk in chunks]
                    if chunk_ids:
                        embeddings = db.get_records(
                            "lecture_embedding", {"chunk_id": chunk_ids}
                        )
                        for embedding in embeddings:
                            db.delete_record("lecture_embedding", embedding["id"])
                        for chunk in chunks:
                            db.delete_record("lecture_chunk", chunk["id"])

                    # Delete lecture content and files
                    contents = db.get_records("lecture_content", {"lecture_id": lecture_id})
                    for content in contents:
                        try:
                            from services.supabase_storage import supabase
                            storage_bucket = content.get("storage_bucket")
                            storage_path = content.get("storage_path")
                            if storage_bucket and storage_path:
                                supabase.delete_file(storage_bucket, storage_path)
                        except Exception as e:
                            logger.warning(f"Failed to delete file {storage_path}: {str(e)}")
                        db.delete_record("lecture_content", content["id"])

                    # Delete lecture
                    db.delete_record("lecture", lecture_id)

                # Delete course-level assessments (not linked to lectures)
                course_assessments = db.get_records("assessment", {"course_id": course_id})
                for assessment in course_assessments:
                    assessment_id = assessment["id"]
                    questions = db.get_records("question", {"assessment_id": assessment_id})
                    for question in questions:
                        db.delete_record("question", question["id"])
                    submissions = db.get_records(
                        "assessment_submission", {"assessment_id": assessment_id}
                    )
                    for submission in submissions:
                        db.delete_record("assessment_submission", submission["id"])
                    result_requests = db.get_records(
                        "result_view_request", {"assessment_id": assessment_id}
                    )
                    for request in result_requests:
                        db.delete_record("result_view_request", request["id"])
                    db.delete_record("assessment", assessment_id)

                # Delete enrollments
                enrollments = db.get_records("enrollment", {"course_id": course_id})
                for enrollment in enrollments:
                    db.delete_record("enrollment", enrollment["id"])

                # Delete document assignments
                doc_assignments = db.get_records(
                    "document_assignment", {"course_id": course_id}
                )
                for assignment in doc_assignments:
                    db.delete_record("document_assignment", assignment["id"])

                # Delete course-teacher assignments
                course_teachers = db.get_records(
                    "course_teacher", {"course_id": course_id}
                )
                for assignment in course_teachers:
                    db.delete_record("course_teacher", assignment["id"])

                # Delete semesters
                semesters = db.get_records("semester", {"course_id": course_id})
                for semester in semesters:
                    db.delete_record("semester", semester["id"])

                # Delete course
                db.delete_record("course", course_id)
                deleted_courses += 1

            except Exception as e:
                logger.error(f"Error deleting course {course_id}: {e!s}")
                # Continue with other courses

        logger.info(f"Deleted {deleted_courses} courses and all related data")

        # Delete generated lecture PDFs from GENERATED_CONTENT bucket
        # These are stored with path pattern: university_{id}/teacher_{id}/course_{id}/generated_lectures/*
        deleted_generated_files = 0
        try:
            from supabase_config import supabase, BUCKETS
            
            # Delete files based on university path pattern
            # Generated PDFs and audio files are stored under: university_{id}/...
            university_prefix = f"university_{university_id}/"
            bucket_name = BUCKETS["GENERATED_CONTENT"]
            
            try:
                # List all files in the university folder in GENERATED_CONTENT bucket
                files_list = supabase.list_files(bucket_name, university_prefix)
                
                # Delete all files that match the university path
                if files_list:
                    for file_info in files_list:
                        file_path = file_info.get("name") if isinstance(file_info, dict) else str(file_info)
                        if file_path and file_path.startswith(university_prefix):
                            try:
                                supabase.delete_file(bucket_name, file_path)
                                deleted_generated_files += 1
                            except Exception as e:
                                logger.warning(f"Failed to delete generated file {file_path}: {str(e)}")
                
                if deleted_generated_files > 0:
                    logger.info(f"Deleted {deleted_generated_files} generated lecture files from storage")
            except Exception as e:
                logger.warning(f"Failed to list/delete generated lecture files: {str(e)}")
        except Exception as e:
            logger.warning(f"Failed to delete generated lecture files: {str(e)}")

        # Get all teachers for this university to delete their documents
        teachers = db.get_records("teacher", {"university_id": university_int_id}, use_cache=False)
        teacher_ids = [t["id"] for t in teachers]
        deleted_documents = 0

        # Delete documents uploaded by teachers
        for teacher_id in teacher_ids:
            # teacher_id from database is already an integer
            documents = db.get_records("documents", {"teacher_id": teacher_id}, use_cache=False)
            for doc in documents:
                try:
                    from services.supabase_storage import supabase
                    # Delete the main file
                    file_path = doc.get("file_path")
                    if file_path:
                        try:
                            supabase.delete_file("documents", file_path)
                        except Exception as e:
                            logger.warning(f"Failed to delete document file {file_path}: {str(e)}")
                    
                    # Delete the content JSON file if it exists and is different
                    content_json_path = doc.get("content_json_path")
                    if content_json_path and content_json_path != file_path:
                        try:
                            supabase.delete_file("documents", content_json_path)
                        except Exception as e:
                            logger.warning(f"Failed to delete content JSON file {content_json_path}: {str(e)}")
                except Exception as e:
                    logger.warning(f"Failed to delete document files for doc {doc.get('id')}: {str(e)}")
                db.delete_record("documents", doc["id"])
                deleted_documents += 1

        logger.info(f"Deleted {deleted_documents} documents")

        # Get all users associated with this university
        users_result = (
            db.admin_client.table("users")
            .select("id, role")
            .eq("university_id", university_int_id)
            .execute()
        )

        # Get all students for this university FIRST
        students = db.get_records("student", {"university_id": university_int_id}, use_cache=False)
        student_ids = [s["id"] for s in students]

        # Delete ALL enrollments for ALL students in this university
        # (Even if the courses were already deleted, ensure no orphaned enrollments remain)
        deleted_enrollments = 0
        if student_ids:
            all_enrollments = (
                db.admin_client.table("enrollment")
                .select("id")
                .in_("student_id", student_ids)
                .execute()
            )
            for enrollment in all_enrollments.data or []:
                try:
                    db.delete_record("enrollment", enrollment["id"])
                    deleted_enrollments += 1
                except Exception as e:
                    logger.warning(f"Error deleting enrollment {enrollment['id']}: {str(e)}")

        logger.info(f"Deleted {deleted_enrollments} enrollments for students")

        # Now delete all users and their profiles
        deleted_users = 0
        deleted_admins = 0
        deleted_teachers = 0
        deleted_students = 0

        for user in users_result.data or []:
            user_id = user["id"]
            user_role = user.get("role")

            try:
                # Manually delete related profiles BEFORE deleting the user
                if user_role == UserRole.TEACHER.value:
                    teacher_profiles = db.get_records("teacher", {"user_id": user_id})
                    for profile in teacher_profiles:
                        db.delete_record("teacher", profile["id"])
                    deleted_teachers += 1
                elif user_role == UserRole.STUDENT.value:
                    # Student profiles should now be safe to delete (enrollments already deleted)
                    student_profiles = db.get_records("student", {"user_id": user_id})
                    for profile in student_profiles:
                        db.delete_record("student", profile["id"])
                    deleted_students += 1
                elif user_role == UserRole.ADMIN.value:
                    deleted_admins += 1

                # Delete the user
                success = db.delete_user(user_id)
                if success:
                    deleted_users += 1
            except Exception as e:
                logger.error(f"Error deleting user {user_id}: {str(e)}")
                # Continue with other users

        logger.info(
            f"Deleted {deleted_users} users ({deleted_admins} admins, "
            f"{deleted_teachers} teachers, {deleted_students} students)"
        )

        # Verify all users are deleted before deleting the university
        remaining_users = (
            db.admin_client.table("users")
            .select("id")
            .eq("university_id", university_int_id)
            .execute()
        )

        if remaining_users.data:
            remaining_count = len(remaining_users.data)
            logger.warning(
                f"Warning: {remaining_count} users still reference this university. "
                f"Attempting to delete them..."
            )
            # Try to delete remaining users
            for user in remaining_users.data:
                try:
                    db.delete_user(user["id"])
                    deleted_users += 1
                except Exception as e:
                    logger.error(f"Failed to delete remaining user {user['id']}: {str(e)}")

        # Double-check before deleting university
        final_check = (
            db.admin_client.table("users")
            .select("id")
            .eq("university_id", university_int_id)
            .execute()
        )

        if final_check.data:
            remaining_ids = [u["id"] for u in final_check.data]
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cannot delete university: {len(final_check.data)} users still reference it. User IDs: {remaining_ids}",
            )

        # Delete the university itself (now safe)
        success = db.delete_record("university", university_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete university",
            )

        logger.info(
            f"System user {current_user.id} successfully deleted university {university_id} "
            f"({university_name})"
        )

        return {
            "message": "University deleted successfully",
            "university_name": university_name,
            "deleted_courses": deleted_courses,
            "deleted_users": deleted_users,
            "deleted_admins": deleted_admins,
            "deleted_teachers": deleted_teachers,
            "deleted_students": deleted_students,
            "deleted_documents": deleted_documents,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting university: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting university",
        ) from e


@router.post(
    "/universities/{university_id}/admins",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminCreateResponse,
)
async def create_admin_user(
    university_id: str,
    admin_data: AdminCreateRequest,
    current_user: SystemUser,
    db=Depends(get_db),
):
    """
    Create a default admin user for a university.

    System users can create admin users by providing only an email.
    Username and password are auto-generated.
    Username format: {university_name}_admin
    """
    try:
        # Verify university exists
        university = db.get_record_by_id("university", university_id, use_cache=False)
        if not university:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="University not found",
            )

        university_name = university.get("name", "")

        # Check if user with this email already exists
        existing_user = db.get_user_by_email(admin_data.email, use_cache=False)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email '{admin_data.email}' already exists",
            )

        # Generate username from university name
        username_base = _sanitize_for_username(university_name)
        username = f"{username_base}_admin"

        # Check if username exists, if so, append number
        existing_username_check = db.get_records("users", {"username": username})
        if existing_username_check:
            counter = 1
            while True:
                new_username = f"{username_base}_admin_{counter}"
                check = db.get_records("users", {"username": new_username})
                if not check:
                    username = new_username
                    break
                counter += 1

        # Generate secure random password
        generated_password = _generate_password(12)

        # Create user using AuthService
        user_create = UserCreate(
            email=admin_data.email,
            username=username,
            password=generated_password,
            first_name=university_name or "Admin",  # Default to university name
            last_name="Admin",
            role=UserRole.ADMIN,
            university_id=university_id,
        )

        new_user = await AuthService.create_user(db, user_create)

        logger.info(
            f"System user {current_user.id} created admin account "
            f"{new_user.id} for university {university_id} ({university_name})"
        )

        return AdminCreateResponse(
            user_id=new_user.id,
            email=admin_data.email,
            username=username,
            password=generated_password,  # Return plain password for sharing
            university_id=university_id,
            university_name=university_name,
            message=f"Admin user created successfully for {university_name}",
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Error creating admin user: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating admin user",
        ) from e


@router.get("/admins")
async def list_all_admins(
    current_user: SystemUser,
    db=Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: str = Query(None, description="Search by name, email, or university"),
    university_id: str = Query(None, description="Filter by university ID"),
    sort_by: str = Query("created_at", description="Sort by: first_name, last_name, email, created_at"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
):
    """
    List all admin users across all universities with pagination.

    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - search: Search by name, email, or university name
    - university_id: Filter by university ID
    - sort_by: Sort field (default: created_at)
    - sort_order: asc or desc (default: desc)
    """
    try:
        # Get all admin users
        admins_query = (
            db.admin_client.table("users")
            .select("id, email, username, first_name, last_name, university_id, is_active, created_at")
            .eq("role", UserRole.ADMIN.value)
        )
        
        # Filter by university if specified
        if university_id:
            univ_int_id = university_id
            if IDConverter.is_uuid(university_id):
                univ_int_id = await IDConverter.uuid_to_int(db, "university", university_id)
            if univ_int_id:
                admins_query = admins_query.eq("university_id", univ_int_id)
        
        admins_result = admins_query.execute()

        if not admins_result.data:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 1,
                "has_next": False,
                "has_previous": False,
            }

        university_int_ids = list(set(a.get("university_id") for a in admins_result.data if a.get("university_id")))

        # Convert integer IDs to UUIDs for get_records_batch
        university_uuids = []
        int_to_uuid_map = {}
        for univ_int_id in university_int_ids:
            if univ_int_id:
                univ_uuid = await IDConverter.int_to_uuid(db, "university", univ_int_id)
                if univ_uuid:
                    university_uuids.append(univ_uuid)
                    int_to_uuid_map[univ_int_id] = univ_uuid

        # Get university names
        university_names = {}
        if university_uuids:
            universities = db.get_records_batch("university", university_uuids)
            for univ in universities.values():
                university_names[univ["id"]] = univ.get("name", "")
        
        all_admins_data = admins_result.data
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            filtered = []
            for admin in all_admins_data:
                univ_int_id = admin.get("university_id")
                univ_uuid = int_to_uuid_map.get(univ_int_id, "")
                univ_name = university_names.get(univ_uuid, "")
                if (
                    search_lower in (admin.get("first_name") or "").lower()
                    or search_lower in (admin.get("last_name") or "").lower()
                    or search_lower in (admin.get("email") or "").lower()
                    or search_lower in univ_name.lower()
                    or search_lower in f"{admin.get('first_name', '')} {admin.get('last_name', '')}".lower()
                ):
                    filtered.append(admin)
            all_admins_data = filtered
        
        # Sort
        sort_desc = sort_order.lower() == "desc"
        sort_key_map = {
            "first_name": lambda a: (a.get("first_name") or "").lower(),
            "last_name": lambda a: (a.get("last_name") or "").lower(),
            "email": lambda a: (a.get("email") or "").lower(),
            "created_at": lambda a: a.get("created_at") or "",
        }
        sort_fn = sort_key_map.get(sort_by, sort_key_map["created_at"])
        all_admins_data.sort(key=sort_fn, reverse=sort_desc)
        
        # Calculate pagination
        total = len(all_admins_data)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = all_admins_data[start:end]

        admin_summaries = []
        for admin in page_data:
            univ_int_id = admin.get("university_id")
            # Convert integer ID to UUID for response
            univ_uuid = int_to_uuid_map.get(univ_int_id, "") if univ_int_id else ""
            admin_summaries.append(
                AdminSummary(
                    user_id=admin["id"],
                    email=admin["email"],
                    username=admin["username"],
                    first_name=admin.get("first_name", ""),
                    last_name=admin.get("last_name", ""),
                    university_id=univ_uuid,
                    university_name=university_names.get(univ_uuid, ""),
                    is_active=admin.get("is_active", True),
                    created_at=str(admin.get("created_at", "")),
                )
            )

        return {
            "items": admin_summaries,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    except Exception as e:
        logger.error(f"Error listing admins: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching admin users",
        ) from e


@router.delete("/admins/{user_id}", status_code=status.HTTP_200_OK)
async def delete_admin_user(
    user_id: str,
    current_user: SystemUser,
    db=Depends(get_db),
):
    """
    Delete an admin user.

    System users can delete any admin user in the system.
    """
    try:
        # Get user to verify they exist and are an admin
        user_data = db.get_user_by_id(user_id, use_cache=False)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if user_data.get("role") != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not an admin",
            )

        # Delete the user (this will cascade delete the admin profile)
        success = db.delete_user(user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete admin user",
            )

        logger.info(
            f"System user {current_user.id} deleted admin user {user_id} "
            f"({user_data.get('email')})"
        )

        return {
            "message": "Admin user deleted successfully",
            "email": user_data.get("email"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting admin user: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting admin user",
        ) from e


# Import and include the router in the system_router from routes_config
# This import is at the end to avoid circular imports
from routes_config import system_router as main_system_router

main_system_router.include_router(router)
