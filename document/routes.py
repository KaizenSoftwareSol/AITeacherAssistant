# document/routes.py

from typing import Annotated, List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile,
                     status)

from dependencies import get_current_user, require_teacher
from logger import logger
from models.document import DocumentRead, DocumentType, DocumentUpdate
from models.user import Teacher, User
from services.document_service import DocumentService
from utils.db import get_db

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


@router.post(
    "/upload/website", response_model=DocumentRead, status_code=status.HTTP_201_CREATED
)
async def upload_website_url(
    current_user: Annotated[User, Depends(require_teacher)],
    url: str = Form(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    db=Depends(get_db),
):
    """
    Upload a website URL for content extraction and storage.

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

        # Validate URL
        if not url or not url.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="URL is required"
            )

        # Process website upload
        document = await DocumentService.process_website_upload(
            db=db,
            teacher=teacher,
            url=url.strip(),
            title=title,
            description=description,
        )

        logger.info(
            f"Website uploaded successfully by teacher {teacher.id}: {document.id}"
        )
        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in website upload endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during website upload",
        )


@router.get("/", response_model=List[DocumentRead])
async def get_teacher_documents(
    current_user: Annotated[User, Depends(require_teacher)],
    skip: int = 0,
    limit: int = 100,
    db=Depends(get_db),
):
    """
    Get all documents uploaded by the current teacher.

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

        logger.info(f"Found {len(documents)} documents for teacher {teacher.id}")
        return documents

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching teacher documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching documents",
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

        logger.info(
            f"Fetching document {document_id} for teacher_id: {teacher.id}"
        )
        
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
            logger.info(f"DEBUG: Table 'documents' returned {len(all_documents_plural)} records")
        except Exception as e:
            error_plural = str(e)
            logger.warning(f"DEBUG: Error querying 'documents': {e}")
        
        try:
            all_documents_singular = db.get_records("document", {}, skip=0, limit=1000)
            logger.info(f"DEBUG: Table 'document' returned {len(all_documents_singular)} records")
        except Exception as e:
            error_singular = str(e)
            logger.warning(f"DEBUG: Error querying 'document': {e}")
        
        # Use whichever worked
        all_documents = all_documents_plural if all_documents_plural else all_documents_singular
        
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
