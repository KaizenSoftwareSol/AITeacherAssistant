# document/routes.py

from typing import List, Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form

from models.document import DocumentRead, DocumentUpdate, DocumentType
from models.user import Teacher, User
from services.document_service import DocumentService
from dependencies import get_current_user, require_teacher
from utils.db import get_db
from logger import logger

router = APIRouter()


@router.post("/upload/file", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document_file(
    current_user: Annotated[User, Depends(require_teacher)],
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    db = Depends(get_db)
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
                detail="Teacher profile not found"
            )
        
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )
        
        # Check file size (limit to 50MB)
        file_content = await file.read()
        if len(file_content) > 50 * 1024 * 1024:  # 50MB
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds 50MB limit"
            )
        
        # Reset file pointer
        await file.seek(0)
        
        # Process document upload
        document = await DocumentService.process_document_upload(
            db=db,
            teacher=teacher,
            file=file,
            title=title,
            description=description
        )
        
        logger.info(f"Document uploaded successfully by teacher {teacher.id}: {document.id}")
        return document
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in document upload endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during document upload"
        )


@router.post("/upload/website", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_website_url(
    current_user: Annotated[User, Depends(require_teacher)],
    url: str = Form(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    db = Depends(get_db)
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
                detail="Teacher profile not found"
            )
        
        # Validate URL
        if not url or not url.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL is required"
            )
        
        # Process website upload
        document = await DocumentService.process_website_upload(
            db=db,
            teacher=teacher,
            url=url.strip(),
            title=title,
            description=description
        )
        
        logger.info(f"Website uploaded successfully by teacher {teacher.id}: {document.id}")
        return document
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in website upload endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during website upload"
        )


@router.get("/", response_model=List[DocumentRead])
async def get_teacher_documents(
    current_user: Annotated[User, Depends(require_teacher)],
    skip: int = 0,
    limit: int = 100,
    db = Depends(get_db)
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
                detail="Teacher profile not found"
            )
        
        # Validate pagination parameters
        if skip < 0:
            skip = 0
        if limit <= 0 or limit > 1000:
            limit = 100
        
        documents = DocumentService.get_teacher_documents(
            db=db,
            teacher_id=teacher.id,
            skip=skip,
            limit=limit
        )
        
        return documents
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching teacher documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching documents"
        )


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,  # UUID string
    db = Depends(get_db)
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
                detail="Teacher profile not found"
            )
        
        document = DocumentService.get_document_by_id(
            db=db,
            document_id=document_id,
            teacher_id=teacher.id
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        return document
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching document"
        )


@router.put("/{document_id}", response_model=DocumentRead)
async def update_document(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,  # UUID string
    document_update: DocumentUpdate,
    db = Depends(get_db)
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
                detail="Teacher profile not found"
            )
        
        document = DocumentService.update_document(
            db=db,
            document_id=document_id,
            teacher_id=teacher.id,
            document_update=document_update
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        logger.info(f"Document {document_id} updated by teacher {teacher.id}")
        return document
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating document"
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    current_user: Annotated[User, Depends(require_teacher)],
    document_id: str,  # UUID string
    db = Depends(get_db)
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
                detail="Teacher profile not found"
            )
        
        success = DocumentService.delete_document(
            db=db,
            document_id=document_id,
            teacher_id=teacher.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        logger.info(f"Document {document_id} deleted by teacher {teacher.id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting document"
        )


@router.get("/types/supported", response_model=List[str])
async def get_supported_document_types():
    """
    Get list of supported document types.
    
    This endpoint is accessible to all authenticated users.
    """
    return [doc_type.value for doc_type in DocumentType]


# Import and include the router in the document_router from routes_config
from routes_config import document_router as main_document_router
main_document_router.include_router(router)