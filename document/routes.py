# document/routes.py

from datetime import datetime
from typing import Annotated, List, Optional
from pydantic import BaseModel

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile,
                     status)

from dependencies import get_current_user, require_teacher
from logger import logger
from models.document import DocumentRead, DocumentType, DocumentUpdate
from models.user import Teacher, User
from services.document_service import DocumentService
from utils.db import get_db


class DocumentAssignment(BaseModel):
    """Model for document assignment information."""
    course_id: str
    course_name: str
    topic: Optional[str] = None


class DocumentWithAssignments(BaseModel):
    """Document model extended with assignments."""
    id: str
    title: str
    description: Optional[str] = None
    document_type: str
    file_size: Optional[int] = None
    file_path: str
    content_json_path: str
    status: str
    document_metadata: Optional[str] = None
    teacher_id: str
    university_id: str
    created_at: str  # ISO format datetime string
    updated_at: str  # ISO format datetime string
    assignments: List[DocumentAssignment] = []
    
    class Config:
        from_attributes = True

router = APIRouter()


@router.post(
    "/upload/file", response_model=DocumentRead, status_code=status.HTTP_201_CREATED
)
async def upload_document_file(
    current_user: Annotated[User, Depends(require_teacher)],
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    db=Depends(get_db),
):
    """
    Upload a document file (PDF, PPTX, DOCX) for parsing and storage.

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

        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided"
            )

        # Read file content (no size limit)
        file_content = await file.read()

        # Reset file pointer
        await file.seek(0)

        # Process document upload
        document = await DocumentService.process_document_upload(
            db=db, teacher=teacher, file=file, title=title, description=description
        )

        logger.info(
            f"Document uploaded successfully by teacher {teacher.id}: {document.id}"
        )
        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in document upload endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during document upload",
        )


@router.get("/", response_model=List[DocumentWithAssignments])
async def get_teacher_documents(
    current_user: Annotated[User, Depends(require_teacher)],
    skip: int = 0,
    limit: int = 100,
    course_id: str = None,
    db=Depends(get_db),
):
    """
    Get all documents uploaded by the current teacher.

    Each document includes assignments[{ course_id, course_name, topic }] 
    so the review tab can display existing links.

    Optional filter: ?course_id= to narrow the list per course.

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

        logger.info(f"Fetching documents for teacher_id: {teacher.id}")

        # Validate pagination parameters
        if skip < 0:
            skip = 0
        if limit <= 0 or limit > 1000:
            limit = 100

        documents = DocumentService.get_teacher_documents(
            db=db, teacher_id=teacher.id, skip=skip, limit=limit
        )

        # Get all document IDs
        document_ids = [doc.id for doc in documents]
        
        # Fetch assignments for these documents
        assignments_by_doc = {}
        if document_ids:
            try:
                # Query document_assignment table
                assignments_result = (
                    db.admin_client.table("document_assignment")
                    .select("*, course!inner(id, name)")
                    .in_("document_id", document_ids)
                    .execute()
                )
                
                for assignment in (assignments_result.data or []):
                    doc_id = assignment.get("document_id")
                    if doc_id not in assignments_by_doc:
                        assignments_by_doc[doc_id] = []
                    
                    course_data = assignment.get("course", {})
                    assignments_by_doc[doc_id].append(
                        DocumentAssignment(
                            course_id=assignment.get("course_id"),
                            course_name=course_data.get("name", "Unknown Course"),
                            topic=assignment.get("topic"),
                        )
                    )
            except Exception as assign_err:
                # Table might not exist yet - log but don't fail
                logger.warning(f"Could not fetch document assignments: {assign_err}")

        # Enrich documents with assignments
        enriched_documents = []
        for doc in documents:
            doc_dict = doc.model_dump() if hasattr(doc, 'model_dump') else dict(doc)
            assignments = assignments_by_doc.get(doc.id, [])
            
            # Convert datetime objects to ISO strings if needed
            if isinstance(doc_dict.get("created_at"), datetime):
                doc_dict["created_at"] = doc_dict["created_at"].isoformat()
            if isinstance(doc_dict.get("updated_at"), datetime):
                doc_dict["updated_at"] = doc_dict["updated_at"].isoformat()
            
            # Convert enum values to strings
            if hasattr(doc_dict.get("document_type"), "value"):
                doc_dict["document_type"] = doc_dict["document_type"].value
            if hasattr(doc_dict.get("status"), "value"):
                doc_dict["status"] = doc_dict["status"].value
            
            # Apply course_id filter if provided
            if course_id:
                if any(assign.course_id == course_id for assign in assignments):
                    enriched_doc = DocumentWithAssignments(
                        **doc_dict,
                        assignments=assignments
                    )
                    enriched_documents.append(enriched_doc)
            else:
                enriched_doc = DocumentWithAssignments(
                    **doc_dict,
                    assignments=assignments
                )
                enriched_documents.append(enriched_doc)

        logger.info(f"Found {len(enriched_documents)} documents for teacher {teacher.id}")
        return enriched_documents

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching teacher documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching documents",
        )


@router.get("/{document_id}/chapters")
async def get_document_chapters(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,
    db=Depends(get_db),
):
    """
    Get list of chapters from a parsed document.

    This endpoint returns the chapter structure from a PDF document.
    Only accessible to the teacher who owns the document.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching chapters for document {document_id}")

        # Get document
        document = DocumentService.get_document_by_id(
            db=db, document_id=document_id, teacher_id=teacher.id
        )

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Get chapters using DocumentService
        chapters = await DocumentService.get_document_chapters(
            document_json_path=document.content_json_path
        )

        logger.info(f"Found {len(chapters)} chapters in document {document_id}")
        return {"chapters": chapters}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching chapters for document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching chapters",
        )


@router.get("/{document_id}/assignments", response_model=List[DocumentAssignment])
async def get_document_assignments(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,
    db=Depends(get_db),
):
    """
    Get all assignments for a specific document.
    
    Returns: [{ course_id, course_name, topic }]
    
    This endpoint is only accessible to teachers and admins.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching assignments for document {document_id}")

        # Verify document ownership
        document = db.get_record_by_id("documents", document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        if document.get("teacher_id") != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this document",
            )

        # Get assignments
        try:
            assignments_result = (
                db.admin_client.table("document_assignment")
                .select("*, course!inner(id, name)")
                .eq("document_id", document_id)
                .execute()
            )

            assignments = []
            for assignment in (assignments_result.data or []):
                course_data = assignment.get("course", {})
                assignments.append(
                    DocumentAssignment(
                        course_id=assignment.get("course_id"),
                        course_name=course_data.get("name", "Unknown Course"),
                        topic=assignment.get("topic"),
                    )
                )

            return assignments
        except Exception as assign_err:
            # Table might not exist - return empty list
            logger.warning(f"Could not fetch document assignments: {assign_err}")
            return []

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching document assignments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching assignments",
        )


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,  # UUID string
    db=Depends(get_db),
):
    """
    Get a specific document by ID.

    This endpoint is only accessible to teachers and admins.
    Teachers can only access their own documents.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"Fetching document {document_id} for teacher_id: {teacher.id}")

        document = DocumentService.get_document_by_id(
            db=db, document_id=document_id, teacher_id=teacher.id
        )

        if not document:
            logger.warning(
                f"Document {document_id} not found or access denied for teacher {teacher.id}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching document",
        )


@router.put("/{document_id}", response_model=DocumentRead)
async def update_document(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,  # UUID string
    document_update: DocumentUpdate,
    db=Depends(get_db),
):
    """
    Update document information.

    This endpoint is only accessible to teachers and admins.
    Teachers can only update their own documents.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        document = DocumentService.update_document(
            db=db,
            document_id=document_id,
            teacher_id=teacher.id,
            document_update=document_update,
        )

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        logger.info(f"Document {document_id} updated by teacher {teacher.id}")
        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating document",
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,  # UUID string
    db=Depends(get_db),
):
    """
    Delete a document and its associated files.

    This endpoint is only accessible to teachers and admins.
    Teachers can only delete their own documents.
    """
    try:
        # Get teacher profile
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        success = DocumentService.delete_document(
            db=db, document_id=document_id, teacher_id=teacher.id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        logger.info(f"Document {document_id} deleted by teacher {teacher.id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting document",
        )


@router.post("/{document_id}/assignments", status_code=status.HTTP_201_CREATED)
async def create_document_assignment(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,
    assignment_data: dict,
    db=Depends(get_db),
):
    """
    Assign a document to a course.
    
    Body: { course_id, topic? }
    
    Rejects with 409 if the document isn't fully processed yet (status != COMPLETED).
    
    This endpoint is only accessible to teachers and admins.
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        course_id = assignment_data.get("course_id")
        topic = assignment_data.get("topic")

        if not course_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="course_id is required",
            )

        logger.info(f"Creating assignment for document {document_id} to course {course_id}")

        # Get document and verify ownership
        document = db.get_record_by_id("documents", document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        if document.get("teacher_id") != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this document",
            )

        # Check if document is fully processed
        if document.get("status") != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document is not fully processed yet. Please wait for processing to complete.",
            )

        # Verify course belongs to teacher's university
        course = db.get_record_by_id("course", course_id)
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        if course.get("university_id") != teacher.university_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this course",
            )

        # Check if assignment already exists
        try:
            existing_result = (
                db.admin_client.table("document_assignment")
                .select("*")
                .eq("document_id", document_id)
                .eq("course_id", course_id)
                .execute()
            )

            if existing_result.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Document is already assigned to this course",
                )
        except Exception as check_err:
            # Table might not exist - we'll create it
            logger.info("document_assignment table might not exist, will create assignment")

        # Create assignment
        from uuid import uuid4
        from datetime import datetime

        assignment_record = {
            "id": str(uuid4()),
            "document_id": document_id,
            "course_id": course_id,
            "topic": topic,
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            result = (
                db.admin_client.table("document_assignment")
                .insert(assignment_record)
                .execute()
            )
        except Exception as insert_err:
            error_msg = str(insert_err)
            # Check if it's a table not found error
            if "PGRST205" in error_msg or "table" in error_msg.lower() and "not found" in error_msg.lower():
                logger.error(f"document_assignment table does not exist: {insert_err}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="The document_assignment table does not exist. Please run migration 007_add_document_assignment.sql to create it.",
                )
            # Re-raise other errors
            logger.error(f"Failed to create document assignment: {insert_err}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create assignment: {error_msg}",
            )

        logger.info(f"Created assignment: document {document_id} -> course {course_id}")

        return {
            "id": assignment_record["id"],
            "document_id": document_id,
            "course_id": course_id,
            "course_name": course.get("name"),
            "topic": topic,
            "message": "Document assigned to course successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating document assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating assignment",
        )


@router.get("/types/supported", response_model=List[str])
async def get_supported_document_types():
    """
    Get list of supported document types.

    This endpoint is accessible to all authenticated users.
    """
    return [doc_type.value for doc_type in DocumentType]


@router.get("/debug/all")
async def debug_get_all_documents(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    """
    Debug endpoint to get ALL documents in the database (no filtering).

    **WARNING: This should only be used for debugging and removed in production!**
    """
    try:
        teacher = current_user.teacher_profile
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher profile not found",
            )

        logger.info(f"DEBUG: Current teacher_id: {teacher.id}")
        logger.info(f"DEBUG: Current user_id: {current_user.id}")

        # Try both possible table names
        all_documents_plural = []
        all_documents_singular = []
        error_plural = None
        error_singular = None

        try:
            all_documents_plural = db.get_records("documents", {}, skip=0, limit=1000)
            logger.info(
                f"DEBUG: Table 'documents' returned {len(all_documents_plural)} records"
            )
        except Exception as e:
            error_plural = str(e)
            logger.warning(f"DEBUG: Error querying 'documents': {e}")

        try:
            all_documents_singular = db.get_records("document", {}, skip=0, limit=1000)
            logger.info(
                f"DEBUG: Table 'document' returned {len(all_documents_singular)} records"
            )
        except Exception as e:
            error_singular = str(e)
            logger.warning(f"DEBUG: Error querying 'document': {e}")

        # Use whichever worked
        all_documents = (
            all_documents_plural if all_documents_plural else all_documents_singular
        )

        # Return summary info
        result = {
            "current_teacher_id": teacher.id,
            "current_user_id": current_user.id,
            "table_name_plural": "documents",
            "table_name_singular": "document",
            "plural_count": len(all_documents_plural),
            "singular_count": len(all_documents_singular),
            "plural_error": error_plural,
            "singular_error": error_singular,
            "documents": [
                {
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "teacher_id": doc.get("teacher_id"),
                    "university_id": doc.get("university_id"),
                    "status": doc.get("status"),
                    "created_at": doc.get("created_at"),
                }
                for doc in all_documents
            ],
        }

        return result

    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Debug error: {str(e)}",
        )


# Import and include the router in the document_router from routes_config
from routes_config import document_router as main_document_router

main_document_router.include_router(router)
