# services/document_parser.py

import json
import io
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime
import PyPDF2
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from docx import Document as DocxDocument
from bs4 import BeautifulSoup
from logger import logger

from models.document import DocumentType, WebsiteContent


class DocumentParser:
    """Service for parsing various document types and extracting content."""
    
    @staticmethod
    async def parse_document(file_content: bytes, document_type: DocumentType, filename: str) -> Dict[str, Any]:
        """
        Parse document content based on type and return structured data.
        
        Args:
            file_content: Raw file content as bytes
            document_type: Type of document to parse
            filename: Original filename
            
        Returns:
            Dictionary containing parsed content and metadata
        """
        try:
            logger.info(f"📄 Parsing {document_type.value} document: {filename}")
            
            if document_type == DocumentType.PDF:
                result = await DocumentParser._parse_pdf(file_content, filename)
                logger.info(f"✅ PDF parsed: {result.get('summary', {}).get('total_pages', 0)} pages")
                return result
            elif document_type == DocumentType.PPTX:
                result = await DocumentParser._parse_pptx(file_content, filename)
                logger.info(f"✅ PPTX parsed: {result.get('summary', {}).get('total_pages', 0)} slides")
                return result
            elif document_type == DocumentType.DOCX:
                result = await DocumentParser._parse_docx(file_content, filename)
                logger.info(f"✅ DOCX parsed: {result.get('summary', {}).get('total_headings', 0)} headings")
                return result
            else:
                raise ValueError(f"Unsupported document type: {document_type}")
                
        except Exception as e:
            logger.error(f"❌ Error parsing document {filename}: {str(e)}")
            raise Exception(f"Failed to parse document: {str(e)}")
    
    @staticmethod
    async def _parse_pdf(file_content: bytes, filename: str) -> Dict[str, Any]:
        """Parse PDF content with comprehensive extraction and page-based organization."""
        try:
            pdf_file = io.BytesIO(file_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Extract PDF metadata
            pdf_metadata = pdf_reader.metadata if pdf_reader.metadata else {}
            metadata = {
                "filename": filename,
                "file_type": "PDF",
                "parsed_at": datetime.utcnow().isoformat(),
                "total_pages": len(pdf_reader.pages),
                "title": pdf_metadata.get("/Title", "") if pdf_metadata.get("/Title") else "",
                "author": pdf_metadata.get("/Author", "") if pdf_metadata.get("/Author") else "",
                "subject": pdf_metadata.get("/Subject", "") if pdf_metadata.get("/Subject") else "",
                "creator": pdf_metadata.get("/Creator", "") if pdf_metadata.get("/Creator") else "",
                "producer": pdf_metadata.get("/Producer", "") if pdf_metadata.get("/Producer") else "",
                "creation_date": str(pdf_metadata.get("/CreationDate", "")) if pdf_metadata.get("/CreationDate") else "",
                "modification_date": str(pdf_metadata.get("/ModDate", "")) if pdf_metadata.get("/ModDate") else "",
            }
            
            # Organize content by pages
            pages_content = {}
            total_words = 0
            pages_with_content = 0
            pages_with_errors = 0
            
            for page_num, page in enumerate(pdf_reader.pages, 1):
                page_key = f"Page {page_num}"
                page_content = {
                    "page_number": page_num,
                    "text": "",
                    "word_count": 0,
                    "char_count": 0,
                    "lines": [],
                    "has_content": False,
                    "error": None
                }
                
                try:
                    # Extract text from page
                    text = page.extract_text()
                    
                    if text and text.strip():
                        # Split text into lines and clean
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        
                        page_content["text"] = text.strip()
                        page_content["word_count"] = len(text.split())
                        page_content["char_count"] = len(text.strip())
                        page_content["lines"] = lines
                        page_content["line_count"] = len(lines)
                        page_content["has_content"] = True
                        
                        total_words += page_content["word_count"]
                        pages_with_content += 1
                    
                    # Try to extract page metadata
                    try:
                        if hasattr(page, 'mediabox'):
                            page_content["dimensions"] = {
                                "width": float(page.mediabox.width) if page.mediabox.width else 0,
                                "height": float(page.mediabox.height) if page.mediabox.height else 0
                            }
                        
                        if hasattr(page, 'rotate'):
                            page_content["rotation"] = page.get('/Rotate', 0)
                    except Exception as meta_error:
                        logger.debug(f"Could not extract page {page_num} metadata: {str(meta_error)}")
                    
                except Exception as e:
                    logger.warning(f"Error extracting text from page {page_num}: {str(e)}")
                    page_content["error"] = str(e)
                    page_content["has_content"] = False
                    pages_with_errors += 1
                
                # Add page to content
                pages_content[page_key] = page_content
            
            # Compile final result
            result = {
                "type": "pdf",
                "metadata": metadata,
                "content": pages_content,
                "summary": {
                    "total_pages": len(pdf_reader.pages),
                    "pages_with_content": pages_with_content,
                    "pages_with_errors": pages_with_errors,
                    "empty_pages": len(pdf_reader.pages) - pages_with_content - pages_with_errors,
                    "total_lines": sum(p.get("line_count", 0) for p in pages_content.values()),
                    "total_characters": sum(p["char_count"] for p in pages_content.values()),
                    "average_words_per_page": round(total_words / pages_with_content, 2) if pages_with_content > 0 else 0
                },
                "total_word_count": total_words
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing PDF {filename}: {str(e)}")
            raise Exception(f"Failed to parse PDF: {str(e)}")
    
    @staticmethod
    async def _parse_pptx(file_content: bytes, filename: str) -> Dict[str, Any]:
        """Parse PowerPoint presentation content with comprehensive extraction."""
        try:
            pptx_file = io.BytesIO(file_content)
            presentation = Presentation(pptx_file)
            
            # Extract presentation metadata
            metadata = {
                "filename": filename,
                "file_type": "PPTX",
                "parsed_at": datetime.utcnow().isoformat(),
                "total_slides": len(presentation.slides),
                "title": presentation.core_properties.title or "",
                "author": presentation.core_properties.author or "",
                "subject": presentation.core_properties.subject or "",
                "created": presentation.core_properties.created.isoformat() if presentation.core_properties.created else "",
                "modified": presentation.core_properties.modified.isoformat() if presentation.core_properties.modified else "",
            }
            
            # Organize content by pages
            pages_content = {}
            
            for slide_num, slide in enumerate(presentation.slides, 1):
                page_key = f"Page {slide_num}"
                page_content = {
                    "slide_number": slide_num,
                    "title": "",
                    "text_content": [],
                    "images": [],
                    "tables": [],
                    "notes": "",
                    "raw_content": []
                }
                
                # Extract slide title (usually from first text box)
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        if not page_content["title"]:
                            page_content["title"] = shape.text.strip()
                        break
                
                # Extract all content from shapes
                for shape in slide.shapes:
                    shape_data = DocumentParser._extract_shape_content(shape)
                    if shape_data:
                        page_content["raw_content"].append(shape_data)
                        
                        # Extract text content
                        if shape_data["type"] == "text" and shape_data["text"].strip():
                            page_content["text_content"].append(shape_data["text"].strip())
                        
                        # Categorize content
                        if shape_data["type"] == "image":
                            page_content["images"].append(shape_data)
                        elif shape_data["type"] == "table":
                            page_content["tables"].append(shape_data)
                
                # Extract slide notes
                if slide.has_notes_slide:
                    notes_slide = slide.notes_slide
                    if notes_slide.notes_text_frame:
                        page_content["notes"] = notes_slide.notes_text_frame.text
                
                # Only add page if it has content
                if page_content["title"] or page_content["text_content"] or page_content["images"] or page_content["tables"]:
                    pages_content[page_key] = page_content
            
            # Calculate total word count
            total_words = 0
            for page in pages_content.values():
                for text in page["text_content"]:
                    total_words += len(text.split())
                if page["notes"]:
                    total_words += len(page["notes"].split())
            
            # Compile final result
            result = {
                "type": "pptx",
                "metadata": metadata,
                "content": pages_content,
                "summary": {
                    "total_pages": len(pages_content),
                    "pages_with_images": len([p for p in pages_content.values() if p["images"]]),
                    "pages_with_tables": len([p for p in pages_content.values() if p["tables"]]),
                    "pages_with_notes": len([p for p in pages_content.values() if p["notes"]]),
                    "total_text_blocks": sum(len(p["text_content"]) for p in pages_content.values())
                },
                "total_word_count": total_words
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing PPTX {filename}: {str(e)}")
            raise Exception(f"Failed to parse PPTX: {str(e)}")
    
    @staticmethod
    async def _parse_docx(file_content: bytes, filename: str) -> Dict[str, Any]:
        """Parse Word document content with heading-based organization."""
        try:
            docx_file = io.BytesIO(file_content)
            document = DocxDocument(docx_file)
            
            # Extract document metadata
            metadata = {
                "filename": filename,
                "file_type": "DOCX",
                "parsed_at": datetime.utcnow().isoformat(),
                "total_paragraphs": len(document.paragraphs),
                "total_tables": len(document.tables),
                "total_images": len(document.inline_shapes),
                "title": document.core_properties.title or "",
                "author": document.core_properties.author or "",
                "subject": document.core_properties.subject or "",
                "created": document.core_properties.created.isoformat() if document.core_properties.created else "",
                "modified": document.core_properties.modified.isoformat() if document.core_properties.modified else "",
            }
            
            # Organize content by headings
            content_by_headings = {}
            current_heading = None
            current_subheading = None
            content_buffer = []
            
            for paragraph in document.paragraphs:
                if not paragraph.text.strip():
                    continue
                
                # Check if it's a heading
                style_name = paragraph.style.name if paragraph.style else "Normal"
                is_heading = style_name.startswith('Heading')
                
                if is_heading:
                    # Save previous content if exists
                    if current_heading and content_buffer:
                        if current_subheading:
                            if current_heading not in content_by_headings:
                                content_by_headings[current_heading] = {}
                            content_by_headings[current_heading][current_subheading] = content_buffer.copy()
                        else:
                            content_by_headings[current_heading] = content_buffer.copy()
                        content_buffer = []
                    
                    # Determine heading level
                    if style_name == 'Heading 1':
                        current_heading = paragraph.text.strip()
                        current_subheading = None
                    elif style_name == 'Heading 2':
                        current_subheading = paragraph.text.strip()
                    else:
                        # Handle other heading levels as subheadings
                        if current_subheading:
                            current_subheading = f"{current_subheading} - {paragraph.text.strip()}"
                        else:
                            current_subheading = paragraph.text.strip()
                else:
                    # Regular paragraph - add to content buffer
                    para_content = {
                        "text": paragraph.text.strip(),
                        "style": style_name,
                        "formatting": DocumentParser._extract_paragraph_formatting(paragraph)
                    }
                    content_buffer.append(para_content)
            
            # Save final content
            if current_heading and content_buffer:
                if current_subheading:
                    if current_heading not in content_by_headings:
                        content_by_headings[current_heading] = {}
                    content_by_headings[current_heading][current_subheading] = content_buffer.copy()
                else:
                    content_by_headings[current_heading] = content_buffer.copy()
            
            # Extract tables
            tables_data = []
            for table_num, table in enumerate(document.tables, 1):
                table_data = {
                    "type": "table",
                    "table_number": table_num,
                    "rows": len(table.rows),
                    "columns": len(table.columns) if table.rows else 0,
                    "data": []
                }
                
                for row in table.rows:
                    row_data = []
                    for cell in row.cells:
                        row_data.append(cell.text.strip())
                    table_data["data"].append(row_data)
                
                tables_data.append(table_data)
            
            # Extract images
            images_data = []
            for i, shape in enumerate(document.inline_shapes, 1):
                image_data = {
                    "type": "image",
                    "image_number": i,
                    "shape_type": str(shape.type),
                    "width": shape.width.inches if shape.width else None,
                    "height": shape.height.inches if shape.height else None
                }
                images_data.append(image_data)
            
            # Calculate total word count
            total_words = 0
            for heading, sections in content_by_headings.items():
                if isinstance(sections, dict):
                    for subheading, content in sections.items():
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                total_words += len(item["text"].split())
                elif isinstance(sections, list):
                    for item in sections:
                        if isinstance(item, dict) and "text" in item:
                            total_words += len(item["text"].split())
            
            for table in tables_data:
                for row in table["data"]:
                    for cell in row:
                        total_words += len(cell.split())
            
            # Compile final result
            result = {
                "type": "docx",
                "metadata": metadata,
                "content": content_by_headings,
                "tables": tables_data,
                "images": images_data,
                "summary": {
                    "total_headings": len(content_by_headings),
                    "total_sections": sum(len(v) if isinstance(v, dict) else 1 for v in content_by_headings.values()),
                    "total_paragraphs": sum(len(v) if isinstance(v, list) else sum(len(sub) if isinstance(sub, list) else 0 for sub in v.values()) for v in content_by_headings.values()),
                    "total_tables": len(tables_data),
                    "total_images": len(images_data)
                },
                "total_word_count": total_words
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing DOCX {filename}: {str(e)}")
            raise Exception(f"Failed to parse DOCX: {str(e)}")
    
    @staticmethod
    async def parse_website(url: str) -> WebsiteContent:
        """
        Parse website content and extract text.
        
        Args:
            url: Website URL to parse
            
        Returns:
            WebsiteContent object with extracted data
        """
        try:
            # Validate URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to fetch website: HTTP {response.status}")
                    
                    html_content = await response.text()
            
            # Parse HTML content
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Extract title
            title = soup.find('title')
            title_text = title.get_text().strip() if title else ""
            
            # Extract main content
            # Try to find main content areas
            main_content = ""
            
            # Look for common content containers
            content_selectors = [
                'main', 'article', '.content', '#content', 
                '.main-content', '#main-content', '.post-content',
                '.entry-content', '.article-content'
            ]
            
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    main_content = content_elem.get_text(separator=' ', strip=True)
                    break
            
            # If no main content found, get all text
            if not main_content:
                main_content = soup.get_text(separator=' ', strip=True)
            
            # Clean up text
            main_content = ' '.join(main_content.split())
            
            # Extract metadata
            metadata = {
                "url": url,
                "title": title_text,
                "description": "",
                "keywords": "",
                "author": "",
                "word_count": len(main_content.split()),
                "extracted_at": datetime.utcnow().isoformat()
            }
            
            # Try to extract meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                metadata["description"] = meta_desc.get('content', '')
            
            # Try to extract meta keywords
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords:
                metadata["keywords"] = meta_keywords.get('content', '')
            
            # Try to extract author
            meta_author = soup.find('meta', attrs={'name': 'author'})
            if meta_author:
                metadata["author"] = meta_author.get('content', '')
            
            return WebsiteContent(
                url=url,
                title=title_text,
                content=main_content,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Error parsing website {url}: {str(e)}")
            raise Exception(f"Failed to parse website: {str(e)}")
    
    @staticmethod
    def _extract_shape_content(shape) -> Optional[Dict[str, Any]]:
        """Extract content from a shape in PPTX"""
        try:
            shape_data = {
                "type": "unknown",
                "text": "",
                "position": {},
                "size": {}
            }
            
            # Get position and size
            if hasattr(shape, 'left') and hasattr(shape, 'top'):
                shape_data["position"] = {
                    "left": shape.left,
                    "top": shape.top
                }
            
            if hasattr(shape, 'width') and hasattr(shape, 'height'):
                shape_data["size"] = {
                    "width": shape.width,
                    "height": shape.height
                }
            
            # Handle different shape types
            if shape.has_text_frame:
                shape_data["type"] = "text"
                shape_data["text"] = shape.text
                
                # Extract text formatting
                if shape.text_frame:
                    shape_data["paragraphs"] = []
                    for paragraph in shape.text_frame.paragraphs:
                        para_text = paragraph.text.strip()
                        if para_text:
                            shape_data["paragraphs"].append({
                                "text": para_text,
                                "alignment": str(paragraph.alignment) if paragraph.alignment else None,
                                "level": paragraph.level
                            })
            
            elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                shape_data["type"] = "image"
                shape_data["text"] = f"[Image: {shape.name if hasattr(shape, 'name') else 'Unknown'}]"
            
            elif shape.has_table:
                shape_data["type"] = "table"
                table = shape.table
                shape_data["table_data"] = {
                    "rows": len(table.rows),
                    "columns": len(table.columns),
                    "data": []
                }
                
                for row in table.rows:
                    row_data = []
                    for cell in row.cells:
                        cell_text = cell.text.strip()
                        row_data.append(cell_text)
                    shape_data["table_data"]["data"].append(row_data)
            
            else:
                shape_data["type"] = "shape"
                shape_data["text"] = shape.name if hasattr(shape, 'name') else ""
            
            return shape_data if shape_data["text"] or shape_data["type"] in ["image", "table"] else None
            
        except Exception as e:
            logger.warning(f"Error extracting shape content: {str(e)}")
            return None
    
    @staticmethod
    def _extract_paragraph_formatting(paragraph) -> Dict[str, Any]:
        """Extract formatting information from a paragraph"""
        formatting = {
            "runs": []
        }
        
        for run in paragraph.runs:
            if run.text.strip():
                run_data = {
                    "text": run.text,
                    "bold": run.bold,
                    "italic": run.italic,
                    "underline": run.underline,
                    "font_size": str(run.font.size) if run.font.size else None,
                    "font_name": run.font.name if run.font.name else None
                }
                formatting["runs"].append(run_data)
        
        return formatting
    
    @staticmethod
    def save_content_to_json(content: Dict[str, Any], file_path: str) -> str:
        """
        Save parsed content to JSON file.
        
        Args:
            content: Parsed content dictionary
            file_path: Path where to save the JSON file
            
        Returns:
            Path to the saved JSON file
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2, ensure_ascii=False)
            return file_path
        except Exception as e:
            logger.error(f"Error saving content to JSON {file_path}: {str(e)}")
            raise Exception(f"Failed to save content to JSON: {str(e)}")
