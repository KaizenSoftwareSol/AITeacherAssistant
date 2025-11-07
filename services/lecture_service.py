# services/lecture_service.py

import json
import re
from datetime import datetime
from io import BytesIO

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
    def sanitize_filename(filename: str, max_length: int = 100) -> str:
        """
        Sanitize a string to be used as a filename.

        Args:
            filename: The string to sanitize
            max_length: Maximum length for the filename (default 100)

        Returns:
            Sanitized filename safe for filesystem use
        """
        # Remove or replace invalid characters
        # Keep alphanumeric, spaces, hyphens, underscores
        sanitized = re.sub(r"[^\w\s-]", "", filename)
        # Replace spaces with underscores
        sanitized = re.sub(r"\s+", "_", sanitized)
        # Remove multiple consecutive underscores
        sanitized = re.sub(r"_+", "_", sanitized)
        # Trim to max length
        sanitized = sanitized[:max_length]
        # Remove leading/trailing underscores or hyphens
        sanitized = sanitized.strip("_-")
        # If empty after sanitization, use a default name
        if not sanitized:
            sanitized = "lecture"
        return sanitized

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
    def extract_chapters_content(
        document_content: dict, selected_chapters: list = None
    ) -> dict:
        """
        Extract content from specific chapters or all chapters.

        Args:
            document_content: Full document content
            selected_chapters: List of chapter names to include (None = all chapters)

        Returns:
            Filtered document content with only selected chapters
        """
        try:
            # If no chapters specified, return all content
            if not selected_chapters:
                logger.info("No chapters selected, using all content")
                return document_content

            # If content is not structured by chapters, return as is
            if "content" not in document_content or not isinstance(
                document_content["content"], dict
            ):
                logger.warning(
                    "Document content is not structured by chapters, returning all content"
                )
                return document_content

            # Filter content by selected chapters
            filtered_content = {}
            all_chapters = document_content["content"]

            for chapter_name in selected_chapters:
                if chapter_name in all_chapters:
                    filtered_content[chapter_name] = all_chapters[chapter_name]
                    logger.info(f"Included chapter: {chapter_name}")
                else:
                    logger.warning(f"Chapter not found: {chapter_name}")

            if not filtered_content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="None of the selected chapters were found in the document",
                )

            # Create filtered document structure
            filtered_document = {
                **document_content,
                "content": filtered_content,
            }

            logger.info(
                f"Filtered document to {len(filtered_content)} out of {len(all_chapters)} chapters"
            )
            return filtered_document

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error extracting chapters content: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to extract chapters: {str(e)}",
            )

    @staticmethod
    async def generate_lecture_content(
        document_content: dict,
        description: str,
        title: str,
        learning_outcomes: str = None,
    ) -> str:
        """
        Generate lecture content using OpenAI GPT-4o.

        Args:
            document_content: Parsed document content
            description: Teacher's description and overview for the lecture
            title: Title for the lecture
            learning_outcomes: Learning outcomes for students (optional)

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

            # Build learning outcomes section if provided
            learning_outcomes_section = ""
            if learning_outcomes:
                learning_outcomes_section = f"""

LEARNING OUTCOMES FOR STUDENTS:
========================================
{learning_outcomes}

"""

            # Create prompt for lecture generation
            prompt = f"""You are an expert educational content creator and lecturer. Generate a **comprehensive, engaging, and descriptive lecture script** based on the provided source material and teacher's overview.

The lecture should be written **as if the teacher is speaking to the class**, guiding students through concepts, examples, and explanations in a natural, instructive tone.

---

**Title:** {title}

**Teacher's Description / Overview:**
{description}
{learning_outcomes_section}
**Source Material:**
{source_text}

---

### Instructions for the Lecture Script:

1. **Write in a teacher’s spoken voice** — the tone should be clear, conversational, and engaging, as though the teacher is explaining concepts live in class.  
2. **Be descriptive and vivid** — elaborate on key points, provide context, and help students visualize or deeply understand the topic.  
3. **Structure clearly**:
   - Introduction (set learning objectives, connect with prior knowledge)
   - Main Sections (each with explanations, transitions, and subtopics)
   - Examples and Illustrations (real-world or conceptual where appropriate)
   - Summary / Conclusion (recap key ideas, ask reflective or guiding questions)
4. **Align fully** with the teacher’s overview — reflect the intended focus, tone, and depth.
5. **Integrate the source material naturally** — explain and expand on its content instead of simply restating it.  
6. **Use educational techniques**:
   - Analogies and storytelling to make abstract ideas concrete  
   - Questions to prompt student thinking  
   - Emphasis and pauses (use phrases like “Let’s think about this for a moment…” or “Now, this part is really important…”)
7. Maintain **academic accuracy** and logical flow, but keep it accessible for students.
8. The final output should be a **ready-to-deliver lecture script**, not just notes or bullet points.

---

Now, generate a **complete, engaging, teacher-style lecture script** that fulfills these requirements.
CREATE COMPREHENSIVE AND ENGAGING LECTURE SCRIPT
"""

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
        If file already exists, it will be overwritten.

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

            # Try to delete existing file first (if it exists)
            try:
                supabase.delete_file(BUCKETS["GENERATED_CONTENT"], storage_path)
                logger.info(f"Deleted existing PDF at: {storage_path}")
            except Exception as delete_error:
                # File might not exist, which is fine
                logger.debug(
                    f"No existing file to delete (or delete failed): {delete_error}"
                )

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
        learning_outcomes: str = None,
        selected_chapters: list = None,
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
            learning_outcomes: Learning outcomes for students (optional)
            selected_chapters: List of chapter names to include (None = all chapters)

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

            # 3. Filter content by selected chapters (if specified)
            if selected_chapters:
                logger.info(f"Filtering content to {len(selected_chapters)} chapters")
                document_content = LectureService.extract_chapters_content(
                    document_content, selected_chapters
                )

            # 4. Generate lecture content using AI
            generated_content = await LectureService.generate_lecture_content(
                document_content, lecture_description, lecture_title, learning_outcomes
            )

            # 4. Create PDF from generated content
            pdf_bytes = LectureService.create_pdf(lecture_title, generated_content)

            # 5. Save PDF to Supabase storage
            # Use sanitized lecture title as filename
            sanitized_title = LectureService.sanitize_filename(lecture_title)
            pdf_filename = f"{sanitized_title}.pdf"
            storage_path = await LectureService.save_lecture_pdf(
                pdf_bytes,
                document_data["university_id"],
                teacher_id,
                course_id,
                pdf_filename,
            )

            # 6. Generate lecture plan for teacher (activities, quizzes, etc.)
            lecture_plan = None
            try:
                from services.lecture_planning_service import (
                    LecturePlanningService,
                )

                logger.info("Generating lecture plan for teacher...")
                plan_data = await LecturePlanningService.generate_lecture_plan(
                    lecture_content=generated_content,
                    lecture_title=lecture_title,
                    lecture_description=lecture_description,
                    learning_outcomes=learning_outcomes,
                )
                lecture_plan = json.dumps(plan_data)
                logger.info("Lecture plan generated successfully")
            except Exception as plan_error:
                logger.warning(
                    f"Failed to generate lecture plan: {str(plan_error)}"
                )
                # Don't fail the entire generation if planning fails
                lecture_plan = None

            # 7. Create lecture record in database
            lecture_data = {
                "title": lecture_title,
                "description": lecture_description,
                "learning_outcomes": learning_outcomes,
                "content": generated_content,
                "lecture_type": "AI_GENERATED",
                "status": "GENERATED",
                "course_id": course_id,
                "semester_id": semester_id,
                "teacher_id": teacher_id,
                "document_id": document_id,  # Store source document for duplicate detection
                "lecture_plan": lecture_plan,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            lecture_record = db.create_record("lecture", lecture_data)
            logger.info(f"Lecture record created: {lecture_record['id']}")

            # 8. Create lecture content record (PDF metadata)
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

            # 9. Return lecture information
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
    def check_for_duplicate_lecture(
        db,
        teacher_id: str,
        course_id: str,
        semester_id: str,
        title: str,
        document_id: str = None,
        learning_outcomes: str = None,
        selected_chapters: list = None,
    ) -> dict:
        """
        Check if a lecture with the same details already exists.
        
        This method checks for duplicates using two strategies:
        1. Title-based: Checks if a lecture with the same title exists for the same course (via storage path)
        2. Document-based: Checks if the same document has been used for the same course and semester
        
        Storage path format: university_{univ_id}/teacher_{teacher_id}/course_{course_id}/generated_lectures/{sanitized_title}.pdf

        Args:
            db: Database instance
            teacher_id: Teacher ID
            course_id: Course ID
            semester_id: Semester ID
            title: Lecture title
            document_id: Source document ID (optional)
            learning_outcomes: Learning outcomes (optional)
            selected_chapters: List of chapter names (optional)

        Returns:
            Dictionary with duplicate status and information
        """
        try:
            logger.info(f"Checking for duplicate lecture - Title: {title}, Document ID: {document_id}")

            # Get teacher's university_id
            teacher_data = db.get_record_by_id("teacher", teacher_id)
            if not teacher_data:
                logger.warning(f"Teacher not found: {teacher_id}")
                return {
                    "has_duplicate": False,
                    "duplicate_lecture": None,
                    "message": "No duplicate found",
                }

            university_id = teacher_data.get("university_id")
            if not university_id:
                logger.warning(f"Teacher has no university_id: {teacher_id}")
                return {
                    "has_duplicate": False,
                    "duplicate_lecture": None,
                    "message": "No duplicate found",
                }

            # ========== Strategy 1: Check for title-based duplicates (storage path) ==========
            sanitized_title = LectureService.sanitize_filename(title)
            pdf_filename = f"{sanitized_title}.pdf"
            expected_storage_path = f"university_{university_id}/teacher_{teacher_id}/course_{course_id}/generated_lectures/{pdf_filename}"

            logger.info(f"Checking title-based duplicate - Expected storage path: {expected_storage_path}")

            # Check if a lecture_content record exists with this storage path
            lecture_contents = db.get_records(
                "lecture_content", {"storage_path": expected_storage_path}
            )

            duplicate_lecture = None
            duplicate_reason = None

            if lecture_contents:
                pdf_content = lecture_contents[0]
                lecture_id = pdf_content["lecture_id"]
                
                logger.info(f"Found title-based duplicate. Lecture ID: {lecture_id}")
                
                # Get the full lecture record
                lecture = db.get_record_by_id("lecture", lecture_id)
                
                if lecture:
                    duplicate_lecture = lecture
                    duplicate_reason = "A lecture with the same title already exists for this course"
            
            # ========== Strategy 2: Check for document-based duplicates ==========
            if not duplicate_lecture and document_id:
                logger.info(f"Checking document-based duplicate - Document ID: {document_id}, Course ID: {course_id}, Semester ID: {semester_id}")
                
                # Check if a lecture already exists with this document_id + course_id + semester_id combination
                # Using admin_client to query with multiple filters
                try:
                    response = db.admin_client.table("lecture").select("*").eq(
                        "document_id", document_id
                    ).eq(
                        "course_id", course_id
                    ).eq(
                        "semester_id", semester_id
                    ).execute()
                    
                    if response.data and len(response.data) > 0:
                        duplicate_lecture = response.data[0]
                        duplicate_reason = "A lecture has already been generated from this document for this course and semester"
                        logger.info(f"Found document-based duplicate. Lecture ID: {duplicate_lecture['id']}")
                except Exception as query_error:
                    logger.warning(f"Error querying for document-based duplicate: {query_error}")

            # ========== If no duplicate found, return success ==========
            if not duplicate_lecture:
                logger.info("No duplicate found - lecture can be created")
                return {
                    "has_duplicate": False,
                    "duplicate_lecture": None,
                    "message": "No duplicate found",
                }

            # ========== Duplicate found! Build response with lecture details ==========
            lecture_id = duplicate_lecture["id"]
            
            # Get lecture content for download URL
            lecture_contents = db.get_records("lecture_content", {"lecture_id": lecture_id})
            
            download_url = None
            file_name = "lecture.pdf"
            file_size = 0
            
            if lecture_contents:
                pdf_content = lecture_contents[0]
                storage_bucket = pdf_content["storage_bucket"]
                storage_path = pdf_content["storage_path"]
                file_name = pdf_content["file_name"]
                file_size = pdf_content["file_size"]
                
                try:
                    bucket = supabase.get_storage_bucket(storage_bucket)
                    download_url = bucket.get_public_url(storage_path)
                except Exception as e:
                    logger.warning(f"Could not get download URL: {e}")

            duplicate_info = {
                "lecture_id": duplicate_lecture["id"],
                "title": duplicate_lecture["title"],
                "description": duplicate_lecture.get("description"),
                "learning_outcomes": duplicate_lecture.get("learning_outcomes"),
                "status": duplicate_lecture["status"],
                "created_at": duplicate_lecture["created_at"],
                "download_url": download_url,
                "file_name": file_name,
                "file_size": file_size,
            }

            logger.info(
                f"Duplicate found: Lecture '{duplicate_lecture['title']}' - Reason: {duplicate_reason}"
            )

            return {
                "has_duplicate": True,
                "duplicate_lecture": duplicate_info,
                "message": duplicate_reason,
            }

        except Exception as e:
            logger.error(f"Error checking for duplicate lecture: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to check for duplicates: {str(e)}",
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
