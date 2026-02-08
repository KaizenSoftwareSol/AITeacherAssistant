# services/llm_pdf_parser.py
"""
LLM-based PDF Parser for production use.

Uses GPT-4o-mini to:
1. Detect book structure via fingerprinting + prompt library
2. Extract TOC structure with page offsets
3. Extract the real book title from the content
4. Assemble chapter content using detected page ranges

Output matches the format expected by:
- DocumentService.get_document_chapters()
- LectureService._flatten_parsed_content()
- LectureService.extract_chapters_content()
"""

import io
import json
import re
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Tuple

import PyPDF2
from openai import AsyncOpenAI

from logger import logger
from settings import settings
from services.prompt_library import get_prompt_for_book


class LLMPDFParser:
    """
    Production LLM-based PDF parser.

    Replaces rule-based parsing with intelligent TOC analysis.
    Falls back gracefully if LLM calls fail.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model
        self.pages_data: List[Dict] = []
        self.page_offset: int = 0
        self.detected_pattern: str = ""

    async def parse(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Main entry point. Parse a PDF and return structured content.

        Returns dict matching the schema expected by downstream consumers:
        {
            "type": "pdf",
            "metadata": {...},
            "content": {"Chapter N: Title": {"section_key": "text", ...}},
            "summary": {...},
            "total_word_count": int,
            "parser_info": {...}
        }
        """
        logger.info(f"LLM Parser: Starting parse of {filename}")

        # STEP 1: Extract raw text from all pages
        metadata = self._extract_all_pages(file_content, filename)
        logger.info(f"LLM Parser: Extracted {len(self.pages_data)} pages")

        # STEP 2: Extract real book title from content
        first_pages_text = ""
        for p in self.pages_data[:5]:
            if p.get("text"):
                first_pages_text += p["text"][:2000]

        title, author = await self._extract_book_title(first_pages_text)
        if title:
            metadata["title"] = title
            logger.info(f"LLM Parser: Extracted title: {title}")
        if author:
            metadata["author"] = author

        # STEP 3: Analyze book structure with LLM
        toc_text = ""
        for p in self.pages_data[:35]:
            if p.get("text"):
                toc_text += f"\n\n=== PDF PAGE {p['pdf_page']} ===\n"
                toc_text += p["text"][:4000]

        book_metadata = {"total_pages": len(self.pages_data), "filename": filename}
        structure_data = await self._analyze_book_structure(toc_text, book_metadata)

        if structure_data.get("structure"):
            logger.info(
                f"LLM Parser: Structure type: {structure_data.get('structure_type', 'unknown')}, "
                f"Offset: {structure_data.get('page_offset', 0)}, "
                f"Items: {self._count_items(structure_data.get('structure', []))}"
            )
        else:
            logger.warning("LLM Parser: No structure detected, using fallback")
            structure_data = self._fallback_structure()

        self.page_offset = structure_data.get("page_offset", 0)

        # STEP 4: Assemble content using detected structure
        content = self._assemble_content(structure_data)
        logger.info(f"LLM Parser: Assembled {len(content)} chapters")

        # Compute stats
        total_words = sum(p.get("word_count", 0) for p in self.pages_data)
        pages_with_content = len([p for p in self.pages_data if p.get("lines")])
        total_sections = sum(
            len(v) if isinstance(v, dict) else 0 for v in content.values()
        )

        result = {
            "type": "pdf",
            "metadata": metadata,
            "content": content,
            "summary": {
                "total_pages": len(self.pages_data),
                "pages_with_content": pages_with_content,
                "pages_with_errors": 0,
                "empty_pages": len(self.pages_data) - pages_with_content,
                "total_chapters": len(content),
                "total_sections": total_sections,
            },
            "total_word_count": total_words,
            "parser_info": {
                "method": "llm_with_prompt_library",
                "model": self.model,
                "page_offset": self.page_offset,
                "detected_structure": structure_data.get("structure_type", "unknown"),
                "detected_pattern": self.detected_pattern,
                "parser_version": "3.0",
            },
        }

        logger.info(
            f"LLM Parser: Complete - {len(content)} chapters, "
            f"{total_words} words, pattern={self.detected_pattern}"
        )
        return result

    # --------------------------------------------------------------------------
    # Text extraction
    # --------------------------------------------------------------------------

    def _extract_all_pages(self, file_content: bytes, filename: str) -> Dict:
        """Extract text from all pages. Returns metadata dict."""
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        pdf_metadata = pdf_reader.metadata if pdf_reader.metadata else {}
        metadata = {
            "filename": filename,
            "file_type": "PDF",
            "parsed_at": datetime.utcnow().isoformat(),
            "total_pages": len(pdf_reader.pages),
            "title": str(pdf_metadata.get("/Title", "") or ""),
            "author": str(pdf_metadata.get("/Author", "") or ""),
            "subject": str(pdf_metadata.get("/Subject", "") or ""),
            "creator": str(pdf_metadata.get("/Creator", "") or ""),
            "producer": str(pdf_metadata.get("/Producer", "") or ""),
            "creation_date": str(pdf_metadata.get("/CreationDate", "") or ""),
            "modification_date": str(pdf_metadata.get("/ModDate", "") or ""),
        }

        self.pages_data = []
        for page_num, page in enumerate(pdf_reader.pages, 1):
            try:
                text = page.extract_text() or ""
                text = text.encode("utf-8", errors="ignore").decode("utf-8")
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                self.pages_data.append({
                    "pdf_page": page_num,
                    "text": text,
                    "lines": lines,
                    "word_count": len(text.split()) if text else 0,
                })
            except Exception as e:
                self.pages_data.append({
                    "pdf_page": page_num,
                    "text": "",
                    "lines": [],
                    "word_count": 0,
                    "error": str(e),
                })

        return metadata

    # --------------------------------------------------------------------------
    # Book title extraction
    # --------------------------------------------------------------------------

    async def _extract_book_title(self, first_pages_text: str) -> Tuple[str, str]:
        """Use LLM to extract the real book title from first pages."""
        if not first_pages_text.strip():
            return "", ""

        prompt = f"""Extract the EXACT book title and author from these title pages of a book.

Look for:
- The main title (usually the largest text on the title page)
- The author name(s)
- Ignore publisher info, edition numbers, ISBNs

Return ONLY a JSON object (no markdown):
{{"title": "The Full Book Title", "author": "Author Name(s)"}}

TEXT FROM FIRST PAGES:
{first_pages_text[:3000]}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Extract book title and author. Return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=200,
            )

            result_text = response.choices[0].message.content.strip()
            if "```" in result_text:
                result_text = re.sub(r"```json\s*", "", result_text)
                result_text = re.sub(r"```\s*", "", result_text)

            data = json.loads(result_text.strip())
            return data.get("title", ""), data.get("author", "")

        except Exception as e:
            logger.warning(f"LLM Parser: Title extraction failed: {e}")
            return "", ""

    # --------------------------------------------------------------------------
    # Structure analysis
    # --------------------------------------------------------------------------

    async def _analyze_book_structure(self, toc_text: str, metadata: Dict) -> Dict:
        """Analyze TOC using prompt library for specialized detection."""
        # Get appropriate prompt via fingerprinting
        prompt_template, pattern_name = get_prompt_for_book(toc_text, metadata)
        self.detected_pattern = pattern_name
        logger.info(f"LLM Parser: Detected pattern: {pattern_name}")

        prompt = prompt_template + toc_text

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You analyze book structures. Extract the hierarchy from the TOC. "
                            "Return only valid JSON. Keep titles short (max 50 chars). "
                            "For large books, focus on main structure."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=12000,
            )

            result_text = response.choices[0].message.content.strip()

            # Clean markdown
            if "```" in result_text:
                result_text = re.sub(r"```json\s*", "", result_text)
                result_text = re.sub(r"```\s*", "", result_text)
            result_text = result_text.strip()

            # Fix truncated JSON
            result_text = self._fix_truncated_json(result_text)

            result = json.loads(result_text)

            # Check if extraction seems incomplete for large books
            total_items = self._count_items(result.get("structure", []))
            if total_items < 10 and len(self.pages_data) > 200:
                logger.warning(
                    f"LLM Parser: Only {total_items} items for {len(self.pages_data)} pages, retrying..."
                )
                detailed = await self._detailed_extraction(toc_text)
                if detailed and self._count_items(detailed.get("structure", [])) > total_items:
                    result = detailed

            # Verify page offset
            if result.get("structure"):
                verified_offset = self._verify_page_offset(result)
                result["page_offset"] = verified_offset

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"LLM Parser: JSON parse error: {e}")
            return await self._fallback_llm_extraction(toc_text)

        except Exception as e:
            logger.error(f"LLM Parser: Structure analysis error: {e}")
            return {"structure": [], "page_offset": 0, "structure_type": "unknown"}

    async def _detailed_extraction(self, toc_text: str) -> Dict:
        """Second pass: extract ALL chapters when first pass seems incomplete."""
        prompt = """Extract EVERY SINGLE CHAPTER from this Table of Contents.

The previous extraction missed chapters. Please extract ALL chapters with page numbers.

Return ONLY a JSON object:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 15,
  "structure": [
    {"type": "part", "number": "I", "title": "Part Title", "book_page": 1, "children": [
      {"type": "chapter", "number": "1", "title": "Chapter Title", "book_page": 5, "children": []}
    ]}
  ]
}

EXTRACT EVERY CHAPTER!

TEXT FROM PDF:
""" + toc_text[:80000]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Extract EVERY chapter from the TOC. Return valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=12000,
            )

            result_text = response.choices[0].message.content.strip()
            if "```" in result_text:
                result_text = re.sub(r"```json\s*", "", result_text)
                result_text = re.sub(r"```\s*", "", result_text)
            result_text = self._fix_truncated_json(result_text.strip())
            return json.loads(result_text)

        except Exception as e:
            logger.warning(f"LLM Parser: Detailed extraction failed: {e}")
            return None

    async def _fallback_llm_extraction(self, toc_text: str) -> Dict:
        """Fallback: extract just top-level structure."""
        prompt = """Extract ONLY the TOP-LEVEL sections/parts from this Table of Contents.
Do NOT extract individual chapters - just the main divisions.

Return ONLY a JSON object:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 15,
  "structure": [
    {"type": "section", "number": "1", "title": "SECTION NAME", "book_page": 1, "children": []}
  ]
}

If there are no top-level sections, extract the first 20 chapters only.

TEXT FROM PDF:
""" + toc_text[:15000]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Extract only top-level structure. Return valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=2000,
            )

            result_text = response.choices[0].message.content.strip()
            if "```" in result_text:
                result_text = re.sub(r"```json\s*", "", result_text)
                result_text = re.sub(r"```\s*", "", result_text)
            return json.loads(result_text.strip())

        except Exception as e:
            logger.warning(f"LLM Parser: Fallback extraction failed: {e}")
            return {"structure": [], "page_offset": 0, "structure_type": "unknown"}

    # --------------------------------------------------------------------------
    # Page offset verification
    # --------------------------------------------------------------------------

    def _verify_page_offset(self, structure_data: Dict) -> int:
        """Verify page offset by finding where first content actually starts."""
        structure = structure_data.get("structure", [])
        if not structure:
            return structure_data.get("page_offset", 0)

        # Find first leaf item with a book page
        first_item = self._get_first_leaf(structure)
        if not first_item:
            return structure_data.get("page_offset", 0)

        first_title = first_item.get("title", "")
        first_book_page = first_item.get("book_page", 1)

        # Search for this title in PDF pages
        search_text = first_title[:30].lower()
        if not search_text:
            return structure_data.get("page_offset", 0)

        for page_data in self.pages_data[5:50]:
            page_text = page_data.get("text", "").lower()

            if search_text in page_text[:500]:
                lines = page_data.get("lines", [])
                for line in lines[:5]:
                    if search_text in line.lower():
                        pdf_page = page_data["pdf_page"]
                        offset = pdf_page - first_book_page
                        if offset >= 0:
                            return offset
                        break

        return structure_data.get("page_offset", 0)

    def _get_first_leaf(self, items: List[Dict]):
        """Get first leaf node (chapter) from structure."""
        for item in items:
            if item.get("children"):
                result = self._get_first_leaf(item["children"])
                if result:
                    return result
            elif item.get("book_page"):
                return item
        # If no leaf found, return first item with book_page
        for item in items:
            if item.get("book_page"):
                return item
        return None

    # --------------------------------------------------------------------------
    # Content assembly
    # --------------------------------------------------------------------------

    def _assemble_content(self, structure_data: Dict) -> Dict[str, Any]:
        """
        Assemble content in the format expected by downstream consumers:
        {"Chapter N: Title": {"section_key": "text content", ...}}
        """
        structure = structure_data.get("structure", [])
        if not structure:
            all_text = " ".join(
                " ".join(p.get("lines", [])) for p in self.pages_data
            )
            return {"Document Content": {"content": all_text[:100000]}}

        content = OrderedDict()

        # Flatten to get leaf chapters with page ranges
        flat_items = self._flatten_structure(structure)

        # Only keep leaf-level items (actual chapters, not section headers)
        leaf_items = [item for item in flat_items if not item.get("has_children")]
        if not leaf_items:
            leaf_items = flat_items

        for i, item in enumerate(leaf_items):
            start_book_page = item.get("book_page", 0)
            if not start_book_page:
                continue

            start_pdf_page = self._book_page_to_pdf_page(start_book_page)

            # End page is start of next item
            if i + 1 < len(leaf_items):
                next_book_page = leaf_items[i + 1].get("book_page", 0)
                if next_book_page:
                    end_pdf_page = self._book_page_to_pdf_page(next_book_page) - 1
                else:
                    end_pdf_page = start_pdf_page + 20
            else:
                end_pdf_page = len(self.pages_data)

            if end_pdf_page < start_pdf_page:
                end_pdf_page = start_pdf_page + 20

            # Build chapter key
            item_num = item.get("number", "")
            item_title = item.get("title", "Untitled")

            if item_num:
                key = f"Chapter {item_num}: {item_title}"
            else:
                key = f"Chapter: {item_title}"

            # Collect text from page range
            lines = []
            for page_data in self.pages_data:
                pdf_page = page_data["pdf_page"]
                if start_pdf_page <= pdf_page <= end_pdf_page:
                    for line in page_data.get("lines", []):
                        if len(line) >= 10 and not line.isdigit():
                            lines.append(line)

            if lines:
                full_text = " ".join(lines)
                content[key] = {"content": full_text}

        return dict(content)

    def _flatten_structure(self, items: List[Dict], depth: int = 0) -> List[Dict]:
        """Flatten nested structure, marking items that have children."""
        result = []
        for item in items:
            item_copy = {**item, "depth": depth, "has_children": bool(item.get("children"))}
            result.append(item_copy)
            if item.get("children"):
                result.extend(self._flatten_structure(item["children"], depth + 1))
        return result

    # --------------------------------------------------------------------------
    # Utility methods
    # --------------------------------------------------------------------------

    def _book_page_to_pdf_page(self, book_page: int) -> int:
        if book_page is None or book_page == 0:
            return 1
        return book_page + self.page_offset

    def _count_items(self, structure: List[Dict]) -> int:
        count = 0
        for item in structure:
            count += 1
            if item.get("children"):
                count += self._count_items(item["children"])
        return count

    def _fallback_structure(self) -> Dict:
        return {
            "structure_type": "unknown",
            "page_offset": 0,
            "structure": [{
                "type": "document",
                "number": "",
                "title": "Full Document",
                "book_page": 1,
                "children": []
            }]
        }

    def _fix_truncated_json(self, json_text: str) -> str:
        """Fix truncated JSON by closing open brackets."""
        open_braces = json_text.count('{')
        close_braces = json_text.count('}')
        open_brackets = json_text.count('[')
        close_brackets = json_text.count(']')

        if open_braces > close_braces or open_brackets > close_brackets:
            last_complete = max(
                json_text.rfind('}],'),
                json_text.rfind('"children": []},'),
                json_text.rfind('"children": []}'),
            )

            if last_complete > 0:
                json_text = json_text[:last_complete + 1]
                open_braces = json_text.count('{') - json_text.count('}')
                open_brackets = json_text.count('[') - json_text.count(']')
                json_text += ']' * max(0, open_brackets) + '}' * max(0, open_braces)

        return json_text
