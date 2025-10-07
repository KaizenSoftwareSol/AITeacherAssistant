# services/lecture_service.py

import json
import uuid
from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import HTTPException, status
from openai import OpenAI
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from logger import logger
from settings import settings
from supabase_config import BUCKETS, supabase


class LectureService:
    """Service for generating lectures from documents using AI."""

    @staticmethod
    def get_openai_client() -> OpenAI:
        """Get OpenAI client instance."""
        if not settings.OPENAI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API key not configured",
            )
        return OpenAI(api_key=settings.OPENAI_API_KEY)

    @staticmethod
    async def fetch_document_json(document_json_path: str) -> dict:
        """
        Fetch and parse document JSON from Supabase storage.

        Args:
            document_json_path: Path to the JSON file in Supabase storage

        Returns:
            Parsed JSON content as dictionary
        """
        try:
            logger.info(f"Fetching document JSON from: {document_json_path}")

            # Download file from Supabase
            json_bytes = supabase.download_file(
                BUCKETS["USER_UPLOADS"], document_json_path
            )

            # Parse JSON
            json_content = json.loads(json_bytes.decode("utf-8"))
            logger.info(f"Successfully fetched and parsed JSON content")

            return json_content

        except Exception as e:
            logger.error(f"Error fetching document JSON: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch document content: {str(e)}",
            )

    @staticmethod
    async def generate_lecture_content(
        document_content: dict, description: str, title: str
    ) -> str:
        """
        Generate lecture content using OpenAI GPT-4o.

        Args:
            document_content: Parsed document content
            description: Teacher's description and overview for the lecture
            title: Title for the lecture

        Returns:
            Generated lecture content as string
        """
        try:
            logger.info("Generating lecture content with OpenAI GPT-4o")

            # Extract text content from the document JSON
            # Handle different document structures
            if "content" in document_content:
                if isinstance(document_content["content"], str):
                    source_text = document_content["content"]
                elif isinstance(document_content["content"], list):
                    # Join list items if content is a list
                    source_text = "\n".join(
                        str(item) for item in document_content["content"]
                    )
                else:
                    source_text = str(document_content["content"])
            elif "text" in document_content:
                source_text = document_content["text"]
            else:
                # Fallback: convert entire JSON to string
                source_text = json.dumps(document_content, indent=2)

            logger.info(f"Source text length: {len(source_text)} characters")

            # Create prompt for lecture generation
            prompt = f"""You are an expert educational content creator. Generate a comprehensive, well-structured lecture based on the provided source material and teacher's description.

Title: {title}

Teacher's Description/Overview:
{description}

Source Material:
{source_text}

Instructions:
1. Create a detailed lecture that covers the key concepts from the source material
2. Align the lecture with the teacher's description and overview
3. Structure the lecture with clear sections and subsections
4. Include examples, explanations, and educational context where appropriate
5. Make the content engaging and suitable for students
6. Use proper academic language and formatting
7. Ensure the lecture is comprehensive but focused

Generate a complete lecture that is ready to be presented to students."""

            # Call OpenAI API
            client = LectureService.get_openai_client()
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational content creator specializing in generating high-quality academic lectures.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=4000,
            )

            generated_content = response.choices[0].message.content
            logger.info(
                f"Successfully generated lecture content: {len(generated_content)} characters"
            )

            return generated_content

        except Exception as e:
            logger.error(f"Error generating lecture content: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate lecture: {str(e)}",
            )

    @staticmethod
    def create_pdf(title: str, content: str) -> bytes:
        """
        Create a PDF from lecture content.

        Args:
            title: Lecture title
            content: Lecture content

        Returns:
            PDF file as bytes
        """
        try:
            logger.info("Creating PDF from lecture content")

            # Create a BytesIO buffer
            buffer = BytesIO()

            # Create the PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18,
            )

            # Container for the 'Flowable' objects
            elements = []

            # Define styles
            styles = getSampleStyleSheet()

            # Custom styles
            title_style = ParagraphStyle(
                "CustomTitle",
                parent=styles["Heading1"],
                fontSize=24,
                textColor="#1a1a1a",
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
            )

            heading_style = ParagraphStyle(
                "CustomHeading",
                parent=styles["Heading2"],
                fontSize=16,
                textColor="#2c3e50",
                spaceAfter=12,
                spaceBefore=12,
                fontName="Helvetica-Bold",
            )

            body_style = ParagraphStyle(
                "CustomBody",
                parent=styles["BodyText"],
                fontSize=11,
                textColor="#333333",
                alignment=TA_JUSTIFY,
                spaceAfter=12,
                leading=14,
            )

            # Add title
            elements.append(Paragraph(title, title_style))
            elements.append(Spacer(1, 0.2 * inch))

            # Add generation timestamp
            timestamp = datetime.utcnow().strftime("%B %d, %Y")
            timestamp_text = f"<i>Generated on {timestamp}</i>"
            elements.append(Paragraph(timestamp_text, styles["Italic"]))
            elements.append(Spacer(1, 0.3 * inch))

            # Process content - split by paragraphs and format
            paragraphs = content.split("\n\n")

            for para in paragraphs:
                if not para.strip():
                    continue

                # Check if it's a heading (simple heuristic: short lines or starts with #)
                if para.strip().startswith("#"):
                    # Remove markdown heading markers
                    heading_text = para.strip().lstrip("#").strip()
                    elements.append(Paragraph(heading_text, heading_style))
                elif len(para.strip()) < 100 and para.strip().endswith(":"):
                    # Likely a section heading
                    elements.append(Paragraph(para.strip(), heading_style))
                else:
                    # Regular paragraph
                    # Escape special XML characters and preserve formatting
                    safe_para = (
                        para.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                        .replace("\n", "<br/>")
                    )
                    elements.append(Paragraph(safe_para, body_style))

                elements.append(Spacer(1, 0.1 * inch))

            # Build PDF
            doc.build(elements)

            # Get PDF bytes
            pdf_bytes = buffer.getvalue()
            buffer.close()

            logger.info(f"Successfully created PDF: {len(pdf_bytes)} bytes")
            return pdf_bytes

        except Exception as e:
            logger.error(f"Error creating PDF: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create PDF: {str(e)}",
            )

    @staticmethod
    async def save_lecture_pdf(
        pdf_bytes: bytes,
        university_id: str,
        teacher_id: str,
        course_id: str,
        filename: str,
    ) -> str:
        """
        Save generated lecture PDF to Supabase storage.

        Args:
            pdf_bytes: PDF file as bytes
            university_id: University ID
            teacher_id: Teacher ID
            course_id: Course ID
            filename: Name for the PDF file

        Returns:
            Storage path of the saved PDF
        """
        try:
            logger.info("Saving lecture PDF to Supabase storage")

            # Create path: university/teacher/course/generated_lectures/filename.pdf
            storage_path = f"university_{university_id}/teacher_{teacher_id}/course_{course_id}/generated_lectures/{filename}"

            # Upload to GENERATED_CONTENT bucket
            supabase.upload_file(
                BUCKETS["GENERATED_CONTENT"],
                storage_path,
                pdf_bytes,
                {"content-type": "application/pdf"},
            )

            logger.info(f"Successfully saved PDF to: {storage_path}")
            return storage_path

        except Exception as e:
            logger.error(f"Error saving lecture PDF: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save lecture PDF: {str(e)}",
            )

    @staticmethod
    async def generate_and_save_lecture(
        db,
        document_id: str,
        teacher_id: str,
        course_id: str,
        semester_id: str,
        lecture_title: str,
        lecture_description: str,
    ) -> dict:
        """
        Complete workflow: generate lecture from document and save to storage.

        Args:
            db: Database instance
            document_id: ID of the source document
            teacher_id: Teacher ID
            course_id: Course ID
            semester_id: Semester ID
            lecture_title: Title for the lecture
            lecture_description: Description/overview from teacher

        Returns:
            Dictionary with lecture information and storage path
        """
        try:
            logger.info(f"Starting lecture generation for document: {document_id}")

            # 1. Fetch document from database
            document_data = db.get_record_by_id("documents", document_id)
            if not document_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found",
                )

            # Verify document belongs to teacher
            if document_data.get("teacher_id") != teacher_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this document",
                )

            logger.info(f"Document found: {document_data['title']}")

            # 2. Fetch document JSON content from Supabase
            document_content = await LectureService.fetch_document_json(
                document_data["content_json_path"]
            )

            # 3. Generate lecture content using AI
            generated_content = await LectureService.generate_lecture_content(
                document_content, lecture_description, lecture_title
            )

            # 4. Create PDF from generated content
            pdf_bytes = LectureService.create_pdf(lecture_title, generated_content)

            # 5. Save PDF to Supabase storage
            pdf_filename = f"{uuid.uuid4()}.pdf"
            storage_path = await LectureService.save_lecture_pdf(
                pdf_bytes,
                document_data["university_id"],
                teacher_id,
                course_id,
                pdf_filename,
            )

            # 6. Create lecture record in database
            lecture_data = {
                "title": lecture_title,
                "description": lecture_description,
                "content": generated_content,
                "lecture_type": "AI_GENERATED",
                "status": "GENERATED",
                "course_id": course_id,
                "semester_id": semester_id,
                "teacher_id": teacher_id,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            lecture_record = db.create_record("lecture", lecture_data)
            logger.info(f"Lecture record created: {lecture_record['id']}")

            # 7. Create lecture content record (PDF metadata)
            lecture_content_data = {
                "lecture_id": lecture_record["id"],
                "file_name": pdf_filename,
                "file_type": "pdf",
                "file_size": len(pdf_bytes),
                "storage_path": storage_path,
                "storage_bucket": BUCKETS["GENERATED_CONTENT"],
                "mime_type": "application/pdf",
                "created_at": datetime.utcnow().isoformat(),
            }

            content_record = db.create_record("lecture_content", lecture_content_data)
            logger.info(f"Lecture content record created: {content_record['id']}")

            # 8. Return lecture information
            result = {
                "lecture_id": lecture_record["id"],
                "title": lecture_title,
                "description": lecture_description,
                "status": "GENERATED",
                "pdf_storage_path": storage_path,
                "pdf_filename": pdf_filename,
                "content_length": len(generated_content),
                "pdf_size": len(pdf_bytes),
                "created_at": lecture_record["created_at"],
            }

            logger.info(
                f"✅ Lecture generation completed successfully: {result['lecture_id']}"
            )
            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in lecture generation workflow: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate lecture: {str(e)}",
            )

    @staticmethod
    def get_lecture_download_url(db, lecture_id: str, teacher_id: str) -> str:
        """
        Get download URL for a generated lecture PDF.

        Args:
            db: Database instance
            lecture_id: Lecture ID
            teacher_id: Teacher ID (for authorization)

        Returns:
            Public download URL for the PDF
        """
        try:
            logger.info(f"Fetching download URL for lecture: {lecture_id}")

            # 1. Fetch lecture record
            lecture_data = db.get_record_by_id("lecture", lecture_id)
            if not lecture_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )

            # Verify lecture belongs to teacher
            if lecture_data.get("teacher_id") != teacher_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this lecture",
                )

            # 2. Fetch lecture content records
            lecture_contents = db.get_records(
                "lecture_content", {"lecture_id": lecture_id}
            )

            if not lecture_contents:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture PDF not found",
                )

            # Get the PDF file (should be only one)
            pdf_content = lecture_contents[0]
            storage_path = pdf_content["storage_path"]
            storage_bucket = pdf_content["storage_bucket"]

            # 3. Get public URL from Supabase
            bucket = supabase.get_storage_bucket(storage_bucket)
            download_url = bucket.get_public_url(storage_path)

            logger.info(f"Generated download URL for lecture: {lecture_id}")
            return download_url

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching lecture download URL: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get download URL: {str(e)}",
            )
