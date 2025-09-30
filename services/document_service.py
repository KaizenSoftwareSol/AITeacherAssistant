# services/document_service.py

import os
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import UploadFile, HTTPException, status

from models.document import Document, DocumentType, DocumentStatus, DocumentCreate, DocumentRead, DocumentUpdate
from models.user import Teacher
from supabase_config import supabase, BUCKETS
from services.document_parser import DocumentParser
from logger import logger


class DocumentService:
    """Service for managing document uploads, parsing, and storage."""
    
    @staticmethod
    def create_directory_structure(teacher_id: str, university_id: str, document_type: DocumentType) -> str:
        """
        Create a directory structure for storing documents.
        
        Args:
            teacher_id: ID of the teacher uploading the document
            university_id: ID of the university
            document_type: Type of document being uploaded
            
        Returns:
            Directory path for the document
        """
        # Create directory structure: university_id/teacher_id/document_type/year/month/
        now = datetime.utcnow()
        year = now.year
        month = now.month
        
        directory_path = f"university_{university_id}/teacher_{teacher_id}/{document_type.value}/{year}/{month:02d}"
        return directory_path
    
    @staticmethod
    async def upload_file_to_supabase(
        file_content: bytes, 
        file_path: str, 
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload file to Supabase storage.
        
        Args:
            file_content: File content as bytes
            file_path: Path where to store the file
            content_type: MIME type of the file
            
        Returns:
            Public URL of the uploaded file
        """
        try:
            bucket = supabase.get_storage_bucket(BUCKETS["USER_UPLOADS"])
            
            # Upload file
            bucket.upload(
                file_path, 
                file_content,
                file_options={"content-type": content_type}
            )
            
            # Get public URL
            public_url = bucket.get_public_url(file_path)
            return public_url
            
        except Exception as e:
            logger.error(f"Error uploading file to Supabase: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file: {str(e)}"
            )
    
    @staticmethod
    async def process_document_upload(
        db,
        teacher: Teacher,
        file: UploadFile,
        title: str,
        description: Optional[str] = None
    ) -> DocumentRead:
        """
        Process document upload including parsing and storage.
        
        Args:
            db: Database instance
            teacher: Teacher uploading the document
            file: Uploaded file
            title: Document title
            description: Document description
            
        Returns:
            DocumentRead object with document information
        """
        try:
            logger.info(f"Starting document upload for teacher {teacher.id}: {file.filename}")
            
            # Validate file type
            document_type = DocumentService._get_document_type(file.filename)
            if not document_type:
                logger.warning(f"Unsupported file type: {file.filename}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unsupported file type. Only PDF, PPTX, and DOCX files are allowed."
                )
            
            logger.info(f"File type validated: {document_type.value}")
            
            # Read file content
            file_content = await file.read()
            file_size = len(file_content)
            logger.info(f"File read successfully: {file_size} bytes")
            
            # Parse document content FIRST
            logger.info(f"Starting document parsing: {file.filename}")
            parsed_content = await DocumentParser.parse_document(file_content, document_type, file.filename)
            logger.info(f"Document parsed successfully. Word count: {parsed_content.get('total_word_count', 0)}")
            
            # Create directory structure
            directory_path = DocumentService.create_directory_structure(
                teacher.id, teacher.university_id, document_type
            )
            logger.info(f"Storage path: {directory_path}")
            
            # Generate unique filename for parsed JSON
            json_filename = f"{uuid.uuid4()}.json"
            json_path = f"{directory_path}/{json_filename}"
            logger.info(f"JSON path: {json_path}")
            
            # Convert parsed content to JSON string
            json_content = json.dumps(parsed_content, indent=2, ensure_ascii=False)
            json_size = len(json_content.encode('utf-8'))
            logger.info(f"JSON content created: {json_size} bytes")
            
            # Upload ONLY the parsed JSON to Supabase (not the original file)
            logger.info(f"Uploading parsed JSON to Supabase: {json_path}")
            await DocumentService.upload_file_to_supabase(
                json_content.encode('utf-8'), 
                json_path, 
                "application/json"
            )
            logger.info(f"JSON uploaded successfully to Supabase")
            
            # Create document record in database
            document_create = DocumentCreate(
                title=title,
                description=description,
                document_type=document_type,
                file_size=len(json_content.encode('utf-8')),  # Size of JSON, not original file
                file_path=json_path,  # Store JSON path as main file path
                content_json_path=json_path,
                document_metadata=json.dumps({
                    "original_filename": file.filename,
                    "original_file_size": file_size,
                    "parsed_at": datetime.utcnow().isoformat(),
                    "total_word_count": parsed_content.get("total_word_count", 0),
                    "parser_version": "2.0"
                })
            )
            
            # Create document dict for database
            logger.info("Creating document record in database")
            document_dict = {
                **document_create.dict(),
                "teacher_id": str(teacher.id),
                "university_id": str(teacher.university_id),
                "status": DocumentStatus.COMPLETED.value,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Document dict: {json.dumps({k: str(v)[:50] for k, v in document_dict.items()}, indent=2)}")
            document_data = db.create_record("documents", document_dict)
            logger.info(f"✅ Document uploaded successfully! ID: {document_data['id']}, Title: {title}")
            return DocumentRead.model_validate(document_data)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing document upload: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process document: {str(e)}"
            )
    
    @staticmethod
    async def process_website_upload(
        db,
        teacher: Teacher,
        url: str,
        title: str,
        description: Optional[str] = None
    ) -> DocumentRead:
        """
        Process website URL upload including content extraction and storage.
        
        Args:
            db: Database instance
            teacher: Teacher uploading the website
            url: Website URL
            title: Document title
            description: Document description
            
        Returns:
            DocumentRead object with document information
        """
        try:
            # Parse website content using regular web scraping (no AI needed)
            website_content = await DocumentParser.parse_website(url)
            
            # Create directory structure
            directory_path = DocumentService.create_directory_structure(
                teacher.id, teacher.university_id, DocumentType.WEBSITE
            )
            
            # Save website content as JSON
            json_filename = f"{uuid.uuid4()}.json"
            json_path = f"{directory_path}/{json_filename}"
            
            # Convert website content to JSON string
            json_content = json.dumps(website_content.dict(), indent=2, ensure_ascii=False)
            await DocumentService.upload_file_to_supabase(
                json_content.encode('utf-8'), 
                json_path, 
                "application/json"
            )
            
            # Create document record in database
            document_create = DocumentCreate(
                title=title,
                description=description,
                document_type=DocumentType.WEBSITE,
                file_size=len(json_content.encode('utf-8')),
                file_path=json_path,
                content_json_path=json_path,
                document_metadata=json.dumps({
                    "url": url,
                    "website_title": website_content.title,
                    "extracted_at": datetime.utcnow().isoformat(),
                    "word_count": website_content.metadata.get("word_count", 0) if website_content.metadata else 0
                })
            )
            
            # Create document dict for database
            document_dict = {
                **document_create.dict(),
                "teacher_id": str(teacher.id),
                "university_id": str(teacher.university_id),
                "status": DocumentStatus.COMPLETED.value,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            document_data = db.create_record("documents", document_dict)
            logger.info(f"Successfully processed website upload: {document_data['id']}")
            return DocumentRead.model_validate(document_data)
            
        except Exception as e:
            logger.error(f"Error processing website upload: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process website: {str(e)}"
            )
    
    @staticmethod
    def _get_document_type(filename: str) -> Optional[DocumentType]:
        """Determine document type from filename."""
        if not filename:
            return None
        
        extension = filename.lower().split('.')[-1]
        
        if extension == 'pdf':
            return DocumentType.PDF
        elif extension == 'pptx':
            return DocumentType.PPTX
        elif extension == 'docx':
            return DocumentType.DOCX
        else:
            return None
    
    @staticmethod
    def get_teacher_documents(db, teacher_id: str, skip: int = 0, limit: int = 100) -> List[DocumentRead]:
        """Get all documents uploaded by a teacher."""
        try:
            documents_data = db.get_records("documents", {"teacher_id": teacher_id}, skip=skip, limit=limit)
            return [DocumentRead.model_validate(Document(**doc_data)) for doc_data in documents_data]
        except Exception as e:
            logger.error(f"Error fetching teacher documents: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch documents"
            )
    
    @staticmethod
    def get_document_by_id(db, document_id: str, teacher_id: str) -> Optional[DocumentRead]:
        """Get a specific document by ID (only if owned by teacher)."""
        try:
            document_data = db.get_record_by_id("documents", document_id)
            if not document_data or document_data.get("teacher_id") != teacher_id:
                return None
            return DocumentRead.model_validate(Document(**document_data))
        except Exception as e:
            logger.error(f"Error fetching document {document_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch document"
            )
    
    @staticmethod
    def update_document(
        db, 
        document_id: str, 
        teacher_id: str, 
        document_update: DocumentUpdate
    ) -> Optional[DocumentRead]:
        """Update document information."""
        try:
            # Check if document exists and belongs to teacher
            document_data = db.get_record_by_id("documents", document_id)
            if not document_data or document_data.get("teacher_id") != teacher_id:
                return None
            
            # Update fields
            update_data = document_update.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
            # Update document in Supabase
            updated_document = db.update_record("documents", document_id, update_data)
            if not updated_document:
                return None
            
            return DocumentRead.model_validate(Document(**updated_document))
            
        except Exception as e:
            logger.error(f"Error updating document {document_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update document"
            )
    
    @staticmethod
    def delete_document(db, document_id: str, teacher_id: str) -> bool:
        """Delete a document and its associated files."""
        try:
            # Check if document exists and belongs to teacher
            document_data = db.get_record_by_id("documents", document_id)
            if not document_data or document_data.get("teacher_id") != teacher_id:
                return False
            
            # Delete files from Supabase storage
            try:
                supabase.delete_file(BUCKETS["USER_UPLOADS"], document_data["file_path"])
                if document_data.get("content_json_path") and document_data["content_json_path"] != document_data["file_path"]:
                    supabase.delete_file(BUCKETS["USER_UPLOADS"], document_data["content_json_path"])
            except Exception as e:
                logger.warning(f"Failed to delete files from storage: {str(e)}")
            
            # Delete from database
            success = db.delete_record("documents", document_id)
            
            if success:
                logger.info(f"Successfully deleted document: {document_id}")
                return True
            else:
                return False
            
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document"
            )
