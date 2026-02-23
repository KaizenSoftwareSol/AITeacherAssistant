# tests/test_llm_parser.py
"""
LLM-based PDF Parser - v4 with Prompt Library

Features:
- Detects book type using fingerprinting
- Uses specialized prompts for known book formats
- Falls back to generalized prompt for unknown formats
- Handles ANY book structure

Supported book types (via prompt_library.py):
- Medical Physiology (Section > Chapter X-Y format)
- Machine Learning/Technical (Parts > Chapters)
- Law/Simple books (Chapters only)
- Ganong's Medical Review
- Gray's Anatomy
- Generalized fallback for all others
"""

import asyncio
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import PyPDF2
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))  # Add tests dir for prompt_library
from dotenv import load_dotenv
from prompt_library import get_prompt_for_book, list_available_patterns

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class GeneralizedLLMParser:
    """
    Fully generalized PDF parser that handles ANY book structure.

    The LLM determines:
    1. What hierarchy the book uses (Parts/Sections/Chapters/Units)
    2. The complete structure with page numbers
    3. Page offset between book pages and PDF pages

    Uses multi-pass approach for large books:
    - Pass 1: Get structure overview and top-level items
    - Pass 2: Expand children for each top-level item (if needed)
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.pages_data: List[Dict] = []
        self.page_offset: int = 0
        self.toc_text: str = ""  # Cache TOC text for multi-pass
        self.detected_pattern: str = ""  # Track which pattern matched

    async def parse_pdf(self, file_path: str) -> Dict[str, Any]:
        """Main entry point for parsing any PDF."""
        filename = os.path.basename(file_path)
        print(f"\n{'='*60}")
        print(f"Parsing: {filename}")
        print(f"{'='*60}")

        # STEP 1: Extract raw text
        print("\n[STEP 1] Extracting raw text with PyPDF2...")
        with open(file_path, "rb") as f:
            file_content = f.read()

        self.pages_data, metadata = self._extract_all_pages(file_content, filename)
        print(f"   Extracted {len(self.pages_data)} PDF pages")

        # STEP 2: Let LLM analyze TOC and extract structure
        print("\n[STEP 2] Analyzing book structure with LLM...")
        structure_data = await self._analyze_book_structure()

        if structure_data.get("structure"):
            print(f"   Structure type: {structure_data.get('structure_type', 'unknown')}")
            print(f"   Page offset: {structure_data.get('page_offset', 0)}")
            print(f"   Top-level items: {len(structure_data.get('structure', []))}")
        else:
            print("   Failed to detect structure, using fallback...")
            structure_data = self._fallback_structure()

        self.page_offset = structure_data.get("page_offset", 0)

        # STEP 3: Assemble content using extracted structure
        print("\n[STEP 3] Assembling content...")
        content = self._assemble_content(structure_data)
        print(f"   Organized into {len(content)} top-level sections")

        # Build final result
        total_words = sum(p.get("word_count", 0) for p in self.pages_data)

        result = {
            "type": "pdf",
            "metadata": metadata,
            "content": content,
            "summary": {
                "total_pages": len(self.pages_data),
                "pages_with_content": len([p for p in self.pages_data if p.get("lines")]),
                "structure_type": structure_data.get("structure_type", "unknown"),
                "top_level_count": len(content),
            },
            "total_word_count": total_words,
            "parser_info": {
                "method": "llm_v4_with_prompt_library",
                "model": self.model,
                "page_offset": self.page_offset,
                "detected_structure": structure_data.get("structure_type"),
                "detected_pattern": self.detected_pattern,
            },
        }

        print(f"\nParsing complete!")
        return result

    def _extract_all_pages(
        self, file_content: bytes, filename: str
    ) -> Tuple[List[Dict], Dict]:
        """Extract text from all pages using PyPDF2."""
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        metadata = {
            "filename": filename,
            "file_type": "PDF",
            "parsed_at": datetime.utcnow().isoformat(),
            "total_pages": len(pdf_reader.pages),
        }

        # Try to get PDF metadata
        if pdf_reader.metadata:
            metadata["title"] = str(pdf_reader.metadata.get("/Title", "")) or ""
            metadata["author"] = str(pdf_reader.metadata.get("/Author", "")) or ""

        pages_data = []
        for page_num, page in enumerate(pdf_reader.pages, 1):
            try:
                text = page.extract_text() or ""
                text = text.encode("utf-8", errors="ignore").decode("utf-8")
                lines = [line.strip() for line in text.split("\n") if line.strip()]

                pages_data.append({
                    "pdf_page": page_num,
                    "text": text,
                    "lines": lines,
                    "word_count": len(text.split()) if text else 0,
                })
            except Exception as e:
                pages_data.append({
                    "pdf_page": page_num,
                    "text": "",
                    "lines": [],
                    "word_count": 0,
                    "error": str(e),
                })

        return pages_data, metadata

    async def _analyze_book_structure(self) -> Dict:
        """
        Let LLM analyze the TOC and extract the COMPLETE structure.
        Uses prompt library to get specialized prompts for known book types.
        Falls back to generalized prompt for unknown formats.
        """
        # Get first 35 pages (should contain TOC - some books have long TOCs)
        toc_text = ""
        for p in self.pages_data[:35]:
            if p.get("text"):
                toc_text += f"\n\n=== PDF PAGE {p['pdf_page']} ===\n"
                toc_text += p["text"][:4000]

        # Store TOC text for potential multi-pass extraction
        self.toc_text = toc_text

        # Get book metadata for fingerprinting
        metadata = {
            "total_pages": len(self.pages_data),
            "filename": self.pages_data[0].get("filename", "") if self.pages_data else "",
        }

        # Detect book type and get appropriate prompt
        print("\n   Detecting book type...")
        prompt_template, pattern_name = get_prompt_for_book(toc_text, metadata)
        self.detected_pattern = pattern_name

        # Build full prompt
        prompt = prompt_template + toc_text

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You analyze book structures. Extract the hierarchy from the TOC. Return only valid JSON. Keep titles short (max 50 chars). For large books, focus on main structure, not deep details.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=12000,  # Increased for complete extraction
            )

            result_text = response.choices[0].message.content.strip()

            # Clean markdown formatting
            if "```" in result_text:
                result_text = re.sub(r"```json\s*", "", result_text)
                result_text = re.sub(r"```\s*", "", result_text)
            result_text = result_text.strip()

            # Try to fix truncated JSON
            result_text = self._fix_truncated_json(result_text)

            result = json.loads(result_text)

            # Check if extraction seems incomplete (very few items for a large book)
            total_items = self._count_items(result.get("structure", []))
            if total_items < 10 and len(self.pages_data) > 200:
                print(f"   Warning: Only {total_items} items found for {len(self.pages_data)} page book")
                print(f"   Attempting more detailed extraction...")
                detailed_result = await self._detailed_extraction(toc_text)
                if detailed_result and self._count_items(detailed_result.get("structure", [])) > total_items:
                    result = detailed_result

            # Verify and fix page offset if needed
            if result.get("structure"):
                verified_offset = await self._verify_page_offset(result)
                result["page_offset"] = verified_offset

            return result

        except json.JSONDecodeError as e:
            print(f"   JSON parsing error: {e}")
            print(f"   Attempting fallback extraction...")
            return await self._fallback_llm_extraction(toc_text)

        except Exception as e:
            print(f"   Error analyzing structure: {e}")
            import traceback
            traceback.print_exc()
            return {"structure": [], "page_offset": 0, "structure_type": "unknown"}

    def _count_items(self, structure: List[Dict]) -> int:
        """Count total items in structure including children."""
        count = 0
        for item in structure:
            count += 1
            if item.get("children"):
                count += self._count_items(item["children"])
        return count

    async def _detailed_extraction(self, toc_text: str) -> Dict:
        """Second pass: Extract ALL chapters when first pass seems incomplete."""
        prompt = """Extract EVERY SINGLE CHAPTER from this Table of Contents.

This is important: The previous extraction missed chapters.
Please extract ALL chapters, one by one, with their page numbers.

Return ONLY a JSON object:
{
  "structure_type": "Parts > Chapters" or "Chapters only" etc,
  "page_offset": 15,
  "structure": [
    {"type": "part", "number": "I", "title": "Part Title", "book_page": 1, "children": [
      {"type": "chapter", "number": "1", "title": "Chapter Title", "book_page": 5, "children": []},
      {"type": "chapter", "number": "2", "title": "Chapter Title", "book_page": 35, "children": []}
    ]},
    {"type": "part", "number": "II", "title": "Part Title", "book_page": 200, "children": [
      {"type": "chapter", "number": "10", "title": "Chapter Title", "book_page": 205, "children": []}
    ]}
  ]
}

EXTRACT EVERY CHAPTER - Do not skip any! Look for patterns like:
- "Chapter 1", "Chapter 2", etc.
- "1. Title", "2. Title", etc.
- Roman numerals, letters, or any numbering system

TEXT FROM PDF:
""" + toc_text[:80000]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Extract EVERY chapter from the TOC. Do not skip any. Return valid JSON."},
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
            print(f"   Detailed extraction failed: {e}")
            return None

    def _fix_truncated_json(self, json_text: str) -> str:
        """Attempt to fix truncated JSON by closing open brackets."""
        # Count brackets
        open_braces = json_text.count('{')
        close_braces = json_text.count('}')
        open_brackets = json_text.count('[')
        close_brackets = json_text.count(']')

        # If truncated, try to close it
        if open_braces > close_braces or open_brackets > close_brackets:
            # Remove any trailing incomplete entry
            # Find last complete item
            last_complete = max(
                json_text.rfind('}],'),
                json_text.rfind('"children": []},'),
                json_text.rfind('"children": []}')
            )

            if last_complete > 0:
                # Cut at last complete item and close structure
                json_text = json_text[:last_complete + 1]

                # Close remaining brackets
                open_braces = json_text.count('{') - json_text.count('}')
                open_brackets = json_text.count('[') - json_text.count(']')

                json_text += ']' * open_brackets + '}' * open_braces

        return json_text

    async def _fallback_llm_extraction(self, toc_text: str) -> Dict:
        """Fallback: Extract just top-level structure when full extraction fails."""
        prompt = """Extract ONLY the TOP-LEVEL sections/parts from this Table of Contents.
Do NOT extract individual chapters - just the main divisions.

Return ONLY a JSON object:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 15,
  "structure": [
    {"type": "section", "number": "1", "title": "SECTION NAME", "book_page": 1, "children": []},
    {"type": "section", "number": "2", "title": "SECTION NAME", "book_page": 100, "children": []}
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
            print(f"   Fallback also failed: {e}")
            return {"structure": [], "page_offset": 0, "structure_type": "unknown"}

    async def _verify_page_offset(self, structure_data: Dict) -> int:
        """
        Verify page offset by finding where first content actually starts in PDF.
        """
        structure = structure_data.get("structure", [])
        if not structure:
            return structure_data.get("page_offset", 0)

        # Find first item with a book page
        def get_first_item(items):
            for item in items:
                if item.get("book_page"):
                    return item
                if item.get("children"):
                    result = get_first_item(item["children"])
                    if result:
                        return result
            return None

        first_item = get_first_item(structure)
        if not first_item:
            return structure_data.get("page_offset", 0)

        first_title = first_item.get("title", "")
        first_book_page = first_item.get("book_page", 1)

        # Search for this title in PDF pages
        search_text = first_title[:30].lower()

        for page_data in self.pages_data[5:50]:  # Skip first 5 pages (cover, etc.)
            page_text = page_data.get("text", "").lower()

            # Check if this page contains the title prominently
            if search_text in page_text[:500]:  # Title should be near top
                # Verify it's not just a TOC mention
                lines = page_data.get("lines", [])
                for line in lines[:5]:
                    if search_text in line.lower():
                        # Found it - calculate offset
                        pdf_page = page_data["pdf_page"]
                        offset = pdf_page - first_book_page
                        if offset >= 0:
                            return offset
                        break

        # Return LLM's calculation if verification fails
        return structure_data.get("page_offset", 0)

    def _fallback_structure(self) -> Dict:
        """Fallback when LLM fails to detect structure."""
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

    def _book_page_to_pdf_page(self, book_page: int) -> int:
        """Convert book page to PDF page."""
        if book_page is None or book_page == 0:
            return 1
        return book_page + self.page_offset

    def _assemble_content(self, structure_data: Dict) -> Dict[str, Any]:
        """
        Assemble content using the extracted structure.
        Recursively processes the hierarchy.
        """
        from collections import OrderedDict

        structure = structure_data.get("structure", [])
        if not structure:
            # No structure - return all content
            all_text = " ".join(
                " ".join(p.get("lines", [])) for p in self.pages_data
            )
            return {"Document Content": {"content": all_text[:100000]}}

        content = OrderedDict()

        # Flatten structure to get page ranges
        flat_items = self._flatten_structure(structure)

        # Calculate page ranges for each item
        for i, item in enumerate(flat_items):
            start_book_page = item.get("book_page", 0)
            if not start_book_page:
                continue

            start_pdf_page = self._book_page_to_pdf_page(start_book_page)

            # End page is start of next item
            if i + 1 < len(flat_items):
                next_book_page = flat_items[i + 1].get("book_page", 0)
                if next_book_page:
                    end_pdf_page = self._book_page_to_pdf_page(next_book_page) - 1
                else:
                    end_pdf_page = start_pdf_page + 20  # Default
            else:
                end_pdf_page = len(self.pages_data)

            # Ensure valid range
            if end_pdf_page < start_pdf_page:
                end_pdf_page = start_pdf_page + 20

            # Build key from item info
            item_type = item.get("type", "item")
            item_num = item.get("number", "")
            item_title = item.get("title", "Untitled")

            if item_num:
                key = f"{item_type.title()} {item_num}: {item_title}"
            else:
                key = f"{item_type.title()}: {item_title}"

            # Collect content
            lines = []
            for page_data in self.pages_data:
                pdf_page = page_data["pdf_page"]
                if start_pdf_page <= pdf_page <= end_pdf_page:
                    for line in page_data.get("lines", []):
                        if len(line) >= 10 and not line.isdigit():
                            lines.append(line)

            if lines:
                content[key] = {"content": " ".join(lines)}
                print(f"   {key[:50]}... (pages {start_pdf_page}-{end_pdf_page})")

        return dict(content)

    def _flatten_structure(self, items: List[Dict], depth: int = 0) -> List[Dict]:
        """Flatten nested structure into a list, preserving order."""
        result = []
        for item in items:
            # Add depth info for context
            item_copy = {**item, "depth": depth}
            result.append(item_copy)

            # Recursively add children
            if item.get("children"):
                result.extend(self._flatten_structure(item["children"], depth + 1))

        return result


async def test_single_pdf(pdf_path: Path, output_name: str = None):
    """Test the parser on a single PDF."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found")
        return None

    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        return None

    parser = GeneralizedLLMParser(api_key=api_key, model="gpt-4o-mini")

    try:
        result = await parser.parse_pdf(str(pdf_path))

        # Save result
        if output_name:
            output_path = Path(__file__).parent.parent / "test_pdfs" / f"{output_name}.json"
        else:
            output_path = Path(__file__).parent.parent / "test_pdfs" / "llm_parsed_output.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\nOutput saved to: {output_path}")

        # Print summary
        print(f"\n{'='*60}")
        print("PARSING SUMMARY")
        print(f"{'='*60}")
        print(f"Total pages: {result['summary']['total_pages']}")
        print(f"Detected pattern: {result['parser_info'].get('detected_pattern', 'N/A')}")
        print(f"Structure type: {result['summary']['structure_type']}")
        print(f"Top-level items: {result['summary']['top_level_count']}")
        print(f"Page offset: {result['parser_info']['page_offset']}")
        print(f"Total words: {result['total_word_count']}")

        print(f"\nContent structure (first 15 items):")
        for key in list(result["content"].keys())[:15]:
            content_data = result["content"][key]
            if isinstance(content_data, dict) and "content" in content_data:
                preview = content_data["content"][:60].replace("\n", " ")
                print(f"   - {key[:50]}...")
                print(f"     Preview: {preview}...")

        return result

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Test the generalized parser on multiple books."""
    test_pdfs_dir = Path(__file__).parent.parent / "test_pdfs"

    # List all available PDFs
    print("Available PDFs:")
    for pdf in test_pdfs_dir.glob("*.pdf"):
        print(f"   - {pdf.name}")
    med_dir = test_pdfs_dir / "med_pdfs"
    if med_dir.exists():
        for pdf in med_dir.glob("*.pdf"):
            print(f"   - med_pdfs/{pdf.name}")

    # Show available patterns
    print("\nAvailable book patterns:")
    for p in list_available_patterns():
        print(f"   - {p['name']}: {p['description']}")

    # Test books with different structures
    test_books = [
        # Medical book: Sections > Chapters (1-1, 1-2 numbering)
        (test_pdfs_dir / "med_pdfs" / "A textbook of practical physiology.pdf", "parsed_med_physiology"),

        # Machine Learning: Parts > Chapters
        (test_pdfs_dir / "Hands-On_Machine_Learning_with_Scikit-Learn-Keras-and-TensorFlow-2nd-Edition-Aurelien-Geron.pdf", "parsed_ml_book"),

        # Law book: Simple Chapters
        (test_pdfs_dir / "Law - A very Short Introduction - Wacks.pdf", "parsed_law_book"),
    ]

    print("\n" + "="*70)
    print("GENERALIZED LLM PARSER - MULTI-BOOK TEST")
    print("="*70)

    results = {}
    for pdf_path, output_name in test_books:
        if pdf_path.exists():
            print(f"\n\n{'#'*70}")
            print(f"# Testing: {pdf_path.name}")
            print(f"{'#'*70}")
            result = await test_single_pdf(pdf_path, output_name)
            if result:
                results[pdf_path.name] = {
                    "detected_pattern": result['parser_info'].get('detected_pattern', 'N/A'),
                    "structure_type": result['summary']['structure_type'],
                    "total_pages": result['summary']['total_pages'],
                    "items_found": result['summary']['top_level_count'],
                    "page_offset": result['parser_info']['page_offset'],
                }
        else:
            print(f"\n[SKIP] Not found: {pdf_path.name}")

    # Final summary
    print(f"\n\n{'='*70}")
    print("FINAL SUMMARY - ALL BOOKS")
    print(f"{'='*70}")
    for book_name, stats in results.items():
        print(f"\n{book_name}:")
        print(f"   Pattern matched: {stats['detected_pattern']}")
        print(f"   Structure: {stats['structure_type']}")
        print(f"   Pages: {stats['total_pages']}, Items: {stats['items_found']}, Offset: {stats['page_offset']}")


if __name__ == "__main__":
    # To test a single book, use:
    # asyncio.run(test_single_pdf(Path("path/to/book.pdf")))

    # To test all books:
    asyncio.run(main())
