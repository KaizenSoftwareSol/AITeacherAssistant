# services/document_service.py

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile, status

from logger import logger
from models.document import (Document, DocumentCreate, DocumentRead,
                             DocumentStatus, DocumentType, DocumentUpdate)
from models.user import Teacher
from services.document_parser import DocumentParser
from supabase_config import BUCKETS, supabase
from utils.id_converter import IDConverter


class DocumentService:
    """Service for managing document uploads, parsing, and storage."""

    @staticmethod
    def create_directory_structure(
        teacher_id: str, university_id: str, document_type: DocumentType
    ) -> str:
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
        content_type: str = "application/octet-stream",
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
                file_path, file_content, file_options={"content-type": content_type}
            )

            # Get public URL
            public_url = bucket.get_public_url(file_path)
            return public_url

        except Exception as e:
            logger.error(f"Error uploading file to Supabase: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file: {str(e)}",
            )

    @staticmethod
    async def process_document_upload(
        db,
        teacher: Teacher,
        file: UploadFile,
        title: str,
        description: Optional[str] = None,
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
            logger.info(
                f"Starting document upload for teacher {teacher.id}: {file.filename}"
            )

            # Validate file type
            document_type = DocumentService._get_document_type(file.filename)
            if not document_type:
                logger.warning(f"Unsupported file type: {file.filename}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unsupported file type. Only PDF, PPTX, and DOCX files are allowed.",
                )

            logger.info(f"File type validated: {document_type.value}")

            # Read file content
            file_content = await file.read()
            file_size = len(file_content)
            logger.info(f"File read successfully: {file_size} bytes")

            # Parse document content FIRST
            logger.info(f"Starting document parsing: {file.filename}")
            parsed_content = await DocumentParser.parse_document(
                file_content, document_type, file.filename
            )
            logger.info(
                f"Document parsed successfully. Word count: {parsed_content.get('total_word_count', 0)}"
            )

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
            json_size = len(json_content.encode("utf-8"))
            logger.info(f"JSON content created: {json_size} bytes")

            # Upload ONLY the parsed JSON to Supabase (not the original file)
            logger.info(f"Uploading parsed JSON to Supabase: {json_path}")
            await DocumentService.upload_file_to_supabase(
                json_content.encode("utf-8"), json_path, "application/json"
            )
            logger.info(f"JSON uploaded successfully to Supabase")

            # Use LLM-extracted book title if available (instead of filename-based title)
            book_title = parsed_content.get("metadata", {}).get("title", "")
            if book_title and len(book_title) > 3:
                title = book_title
                logger.info(f"Using LLM-extracted book title: {title}")

            # Create document record in database
            document_create = DocumentCreate(
                title=title,
                description=description,
                document_type=document_type,
                file_size=len(
                    json_content.encode("utf-8")
                ),  # Size of JSON, not original file
                file_path=json_path,  # Store JSON path as main file path
                content_json_path=json_path,
                document_metadata=json.dumps(
                    {
                        "original_filename": file.filename,
                        "original_file_size": file_size,
                        "parsed_at": datetime.utcnow().isoformat(),
                        "total_word_count": parsed_content.get("total_word_count", 0),
                        "parser_version": "3.0",
                        "parser_method": parsed_content.get("parser_info", {}).get("method", "rule_based"),
                        "detected_pattern": parsed_content.get("parser_info", {}).get("detected_pattern", ""),
                        "parser_model": parsed_content.get("parser_info", {}).get("model", ""),
                        "book_title": book_title,
                    }
                ),
            )

            # Create document dict for database
            logger.info("Creating document record in database")
            document_dict = {
                **document_create.dict(),
                "teacher_id": teacher.id,  # Integer ID for database
                "university_id": teacher.university_id,  # Integer ID for database
                "status": DocumentStatus.COMPLETED.value,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            logger.info(
                f"Document dict: {json.dumps({k: str(v)[:50] for k, v in document_dict.items()}, indent=2)}"
            )
            document_data = db.create_record("documents", document_dict)
            logger.info(
                f"✅ Document uploaded successfully! ID: {document_data['id']}, Title: {title}"
            )
            
            # Convert integer IDs to UUIDs for response
            # Document ID should already be converted by db.create_record, but ensure it's a UUID string
            if isinstance(document_data.get("id"), int):
                doc_uuid = await IDConverter.int_to_uuid(db, "documents", document_data["id"])
                if doc_uuid:
                    document_data["id"] = doc_uuid
            
            # Convert teacher_id and university_id from integers to UUIDs
            if isinstance(document_data.get("teacher_id"), int):
                teacher_uuid = await IDConverter.int_to_uuid(db, "teacher", document_data["teacher_id"])
                if teacher_uuid:
                    document_data["teacher_id"] = teacher_uuid
            if isinstance(document_data.get("university_id"), int):
                university_uuid = await IDConverter.int_to_uuid(db, "university", document_data["university_id"])
                if university_uuid:
                    document_data["university_id"] = university_uuid
            
            return DocumentRead.model_validate(document_data)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing document upload: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process document: {str(e)}",
            )

    @staticmethod
    async def get_document_chapters(document_json_path: str) -> List[Dict[str, Any]]:
        """
        Get chapters from a parsed document.

        Args:
            document_json_path: Path to the document JSON in Supabase storage

        Returns:
            List of chapter information dictionaries
        """
        try:
            logger.info(f"Fetching document chapters from: {document_json_path}")

            # Download JSON from Supabase
            json_bytes = supabase.download_file(
                BUCKETS["USER_UPLOADS"], document_json_path
            )

            # Parse JSON
            document_data = json.loads(json_bytes.decode("utf-8"))

            # Extract chapters from content
            chapters = []
            if "content" in document_data and isinstance(
                document_data["content"], dict
            ):
                for chapter_name in document_data["content"].keys():
                    # Get chapter metadata
                    chapter_data = document_data["content"][chapter_name]

                    # Calculate word count for this chapter
                    word_count = 0
                    if isinstance(chapter_data, dict):
                        for section_content in chapter_data.values():
                            if isinstance(section_content, str):
                                word_count += len(section_content.split())
                    elif isinstance(chapter_data, str):
                        word_count = len(chapter_data.split())

                    chapters.append(
                        {
                            "chapter_name": chapter_name,
                            "word_count": word_count,
                        }
                    )

            logger.info(f"Found {len(chapters)} chapters")
            return chapters

        except Exception as e:
            logger.error(f"Error fetching document chapters: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch document chapters: {str(e)}",
            )

    @staticmethod
    def _get_document_type(filename: str) -> Optional[DocumentType]:
        """Determine document type from filename."""
        if not filename:
            return None

        extension = filename.lower().split(".")[-1]

        if extension == "pdf":
            return DocumentType.PDF
        elif extension == "pptx":
            return DocumentType.PPTX
        elif extension == "docx":
            return DocumentType.DOCX
        else:
            return None

    @staticmethod
    def get_teacher_documents(
        db, teacher_id: str, skip: int = 0, limit: int = 100
    ) -> List[DocumentRead]:
        """Get all documents uploaded by a teacher."""
        try:
            logger.info(f"Querying documents for teacher_id: {teacher_id}")
            documents_data = db.get_records(
                "documents", {"teacher_id": teacher_id}, skip=skip, limit=limit
            )
            logger.info(f"Query returned {len(documents_data)} documents")

            if documents_data:
                logger.debug(
                    f"Sample document teacher_id: {documents_data[0].get('teacher_id')}"
                )

            return [
                DocumentRead.model_validate(Document(**doc_data))
                for doc_data in documents_data
            ]
        except Exception as e:
            logger.error(f"Error fetching teacher documents: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch documents",
            )

    @staticmethod
    async def get_document_by_id(
        db, document_id: str, teacher_id: str
    ) -> Optional[DocumentRead]:
        """Get a specific document by ID (only if owned by teacher)."""
        try:
            document_data = db.get_record_by_id("documents", document_id)
            if not document_data:
                logger.warning(f"Document {document_id} not found in database")
                return None

            doc_teacher_id = document_data.get("teacher_id")
            logger.info(
                f"Document {document_id}: stored teacher_id={doc_teacher_id}, "
                f"requested teacher_id={teacher_id}"
            )

            # Compare teacher IDs - handle both integer and UUID
            # First, try direct integer comparison if both are integers
            if isinstance(doc_teacher_id, int) and isinstance(teacher_id, int):
                if doc_teacher_id != teacher_id:
                    logger.warning(
                        f"Teacher ID mismatch for document {document_id}: "
                        f"stored={doc_teacher_id}, requested={teacher_id}"
                    )
                    return None
            else:
                # Convert both to UUIDs for comparison
                doc_teacher_uuid = None
                requested_teacher_uuid = None
                
                if isinstance(doc_teacher_id, int):
                    # Convert stored integer ID to UUID
                    doc_teacher_uuid = await IDConverter.int_to_uuid(db, "teacher", doc_teacher_id)
                else:
                    doc_teacher_uuid = doc_teacher_id
                
                if isinstance(teacher_id, int):
                    # Convert requested integer ID to UUID
                    requested_teacher_uuid = await IDConverter.int_to_uuid(db, "teacher", teacher_id)
                elif IDConverter.is_uuid(teacher_id):
                    requested_teacher_uuid = teacher_id
                else:
                    # Try to convert string to int and then to UUID
                    try:
                        teacher_int = int(teacher_id)
                        requested_teacher_uuid = await IDConverter.int_to_uuid(db, "teacher", teacher_int)
                    except (ValueError, TypeError):
                        requested_teacher_uuid = teacher_id
                
                if doc_teacher_uuid != requested_teacher_uuid:
                    logger.warning(
                        f"Teacher ID mismatch for document {document_id}: "
                        f"stored={doc_teacher_id} (uuid={doc_teacher_uuid}), requested={teacher_id} (uuid={requested_teacher_uuid})"
                    )
                    return None

            # Convert integer IDs to UUIDs for response
            if isinstance(document_data.get("id"), int):
                doc_uuid = await IDConverter.int_to_uuid(db, "documents", document_data["id"])
                if doc_uuid:
                    document_data["id"] = doc_uuid
            
            if isinstance(document_data.get("teacher_id"), int):
                teacher_uuid = await IDConverter.int_to_uuid(db, "teacher", document_data["teacher_id"])
                if teacher_uuid:
                    document_data["teacher_id"] = teacher_uuid
            
            if isinstance(document_data.get("university_id"), int):
                university_uuid = await IDConverter.int_to_uuid(db, "university", document_data["university_id"])
                if university_uuid:
                    document_data["university_id"] = university_uuid

            return DocumentRead.model_validate(Document(**document_data))
        except Exception as e:
            logger.error(f"Error fetching document {document_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch document",
            )

    @staticmethod
    async def update_document(
        db, document_id: str, teacher_id: str, document_update: DocumentUpdate
    ) -> Optional[DocumentRead]:
        """Update document information."""
        try:
            # Check if document exists and belongs to teacher
            document_data = db.get_record_by_id("documents", document_id)
            if not document_data:
                return None
            
            # Compare teacher IDs - handle both integer and UUID
            doc_teacher_id = document_data.get("teacher_id")
            if isinstance(doc_teacher_id, int):
                doc_teacher_uuid = await IDConverter.int_to_uuid(db, "teacher", doc_teacher_id)
                if doc_teacher_uuid != teacher_id:
                    return None
            elif doc_teacher_id != teacher_id:
                return None

            # Update fields
            update_data = document_update.dict(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow().isoformat()

            # Update document in Supabase
            updated_document = db.update_record("documents", document_id, update_data)
            if not updated_document:
                return None

            # Convert integer IDs to UUIDs for response
            if isinstance(updated_document.get("id"), int):
                doc_uuid = await IDConverter.int_to_uuid(db, "documents", updated_document["id"])
                if doc_uuid:
                    updated_document["id"] = doc_uuid
            
            if isinstance(updated_document.get("teacher_id"), int):
                teacher_uuid = await IDConverter.int_to_uuid(db, "teacher", updated_document["teacher_id"])
                if teacher_uuid:
                    updated_document["teacher_id"] = teacher_uuid
            
            if isinstance(updated_document.get("university_id"), int):
                university_uuid = await IDConverter.int_to_uuid(db, "university", updated_document["university_id"])
                if university_uuid:
                    updated_document["university_id"] = university_uuid

            return DocumentRead.model_validate(Document(**updated_document))

        except Exception as e:
            logger.error(f"Error updating document {document_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update document",
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
                supabase.delete_file(
                    BUCKETS["USER_UPLOADS"], document_data["file_path"]
                )
                if (
                    document_data.get("content_json_path")
                    and document_data["content_json_path"] != document_data["file_path"]
                ):
                    supabase.delete_file(
                        BUCKETS["USER_UPLOADS"], document_data["content_json_path"]
                    )
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
                detail="Failed to delete document",
            )
