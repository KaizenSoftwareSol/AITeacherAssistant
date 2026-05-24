# services/lecture_service.py

import base64
import json
import re
from datetime import datetime
from io import BytesIO

import httpx
from fastapi import HTTPException, status
from openai import OpenAI
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from logger import logger
from settings import settings
from supabase_config import BUCKETS, supabase
from models.document import DocumentType
from services.document_parser import DocumentParser
from utils.id_converter import IDConverter

# Register fonts: Tahoma for body text, Segoe UI Emoji for emoji glyphs
_FONTS_REGISTERED = False
_HAS_EMOJI_FONT = False
def _register_pdf_fonts():
    global _FONTS_REGISTERED, _HAS_EMOJI_FONT
    if _FONTS_REGISTERED:
        return
    try:
        # Tahoma — body text with broad Unicode coverage
        pdfmetrics.registerFont(TTFont("Tahoma", "C:/Windows/Fonts/tahoma.ttf"))
        pdfmetrics.registerFont(TTFont("TahomaBold", "C:/Windows/Fonts/tahomabd.ttf"))
        _FONTS_REGISTERED = True
    except Exception as e:
        logger.warning(f"Could not register Tahoma fonts: {e}")

    try:
        # Segoe UI Emoji — full coverage of modern emojis (monochrome in ReportLab)
        pdfmetrics.registerFont(TTFont("SegoeEmoji", "C:/Windows/Fonts/seguiemj.ttf"))
        _HAS_EMOJI_FONT = True
    except Exception as e:
        logger.warning(f"Could not register Segoe UI Emoji: {e}")


# Emoji Unicode ranges (commonly used in lectures)
_EMOJI_RANGES = [
    (0x2190, 0x21FF),    # Arrows
    (0x2300, 0x23FF),    # Misc Technical
    (0x2460, 0x24FF),    # Enclosed Alphanumerics
    (0x2500, 0x257F),    # Box Drawing
    (0x2580, 0x259F),    # Block Elements
    (0x25A0, 0x25FF),    # Geometric Shapes
    (0x2600, 0x26FF),    # Miscellaneous Symbols
    (0x2700, 0x27BF),    # Dingbats
    (0x2900, 0x297F),    # Supplemental Arrows-B
    (0x2B00, 0x2BFF),    # Misc Symbols and Arrows
    (0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs
    (0x1F600, 0x1F64F),  # Emoticons
    (0x1F680, 0x1F6FF),  # Transport and Map
    (0x1F700, 0x1F77F),  # Alchemical Symbols
    (0x1F900, 0x1F9FF),  # Supplemental Symbols and Pictographs
    (0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended-A
]


def _is_emoji_char(ch: str) -> bool:
    """Check if a character is in an emoji range."""
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _EMOJI_RANGES)


def _wrap_emojis_with_font(text: str) -> str:
    """
    Wrap emoji characters in <font name='SegoeEmoji'> tags so ReportLab renders them.
    Variation selectors (U+FE0F) are kept attached to the preceding emoji.
    """
    if not _HAS_EMOJI_FONT or not text:
        return text

    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if _is_emoji_char(ch):
            # Collect the emoji + any trailing variation selector
            emoji_seq = ch
            j = i + 1
            while j < len(text) and 0xFE00 <= ord(text[j]) <= 0xFE0F:
                emoji_seq += text[j]
                j += 1
            result.append(f'<font name="SegoeEmoji">{emoji_seq}</font>')
            i = j
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def _escape_xml(text: str) -> str:
    """Escape XML special chars for ReportLab Paragraph."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _markdown_inline_to_html(text: str) -> str:
    """
    Convert inline markdown (bold, italic, code) to ReportLab-compatible HTML,
    escape XML special chars, and wrap emoji glyphs in the emoji font.
    """
    if not text:
        return ""
    # Wrap emojis in font tags FIRST (before XML escape adds entities)
    text = _wrap_emojis_with_font(text)
    # Escape XML special chars (but preserve our font/b/i tags)
    # Strategy: split on our tags, escape only the text parts
    parts = re.split(r"(<font name=\"SegoeEmoji\">.*?</font>)", text)
    escaped_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # Inside font tag — keep as-is
            escaped_parts.append(part)
        else:
            escaped_parts.append(_escape_xml(part))
    text = "".join(escaped_parts)
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    # Italic: *text* or _text_ (must not match bold markers)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", text)
    # Inline code: `code`
    text = re.sub(r"`([^`]+)`", r'<font name="Courier" size="10">\1</font>', text)
    return text


class LectureService:
    """Service for generating lectures from documents using AI."""

    # ---------- Token-based context limits for GPT-4o (128k context window) ----------
    # Reserve tokens for: system message (~2k), prompt template (~3k), response (~10k)
    MAX_INPUT_TOKENS = 25_000  # Safe limit for input content (under 30k to avoid API errors)
    TOKENS_PER_CHAR = 0.25  # Approximate: 1 token ≈ 4 characters (conservative estimate)
    MIN_TOKENS_PER_SOURCE = 1_000  # Minimum tokens to keep per source
    
    # Legacy char-based limits (kept for backward compatibility, but token-based is preferred)
    MAX_SOURCE_CHARS = 80_000
    MAX_ADDITIONAL_CHARS = 40_000
    PER_PIECE_LIMIT = 15_000

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        Estimate token count from text.
        Uses conservative estimate: 1 token ≈ 4 characters.
        For more accuracy, could use tiktoken library, but this is simpler.
        """
        if not text:
            return 0
        # Conservative estimate: 1 token per 4 characters
        return int(len(text) * LectureService.TOKENS_PER_CHAR)

    @staticmethod
    def _chars_from_tokens(tokens: int) -> int:
        """Convert token count to approximate character count."""
        return int(tokens / LectureService.TOKENS_PER_CHAR)

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        """Truncate text to character limit."""
        if not text or limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        suffix = "... [TRUNCATED]"
        return text[: max(0, limit - len(suffix))] + suffix

    @staticmethod
    def _truncate_text_by_tokens(text: str, max_tokens: int) -> str:
        """Truncate text to approximate token limit."""
        if not text or max_tokens <= 0:
            return ""
        max_chars = LectureService._chars_from_tokens(max_tokens)
        return LectureService._truncate_text(text, max_chars)

    @staticmethod
    def _manage_content_tokens(
        primary_contents: list[dict],
        additional_pieces: list[str],
        selected_chapters: list = None,
    ) -> tuple[str, dict]:
        """
        Intelligently manage content tokens with prioritization.
        
        Priority order:
        1. Selected chapters from first document (if specified)
        2. Remaining content from first document
        3. Other primary documents
        4. Additional sources (extra documents, texts, files)
        
        Args:
            primary_contents: List of dicts with 'content', 'title', 'type', 'is_first'
            additional_pieces: List of additional text pieces
            selected_chapters: List of selected chapter names (applies to first doc)
            
        Returns:
            Tuple of (combined_content, metadata_dict)
        """
        # Estimate tokens for all content
        content_sources = []
        total_tokens = 0
        
        # Process primary documents with priority
        for idx, doc_content in enumerate(primary_contents):
            content_text = doc_content.get("content", "")
            tokens = LectureService._estimate_tokens(content_text)
            priority = 1 if idx == 0 else 3  # First doc gets priority 1, others get 3
            
            content_sources.append({
                "text": content_text,
                "tokens": tokens,
                "priority": priority,
                "title": doc_content.get("title", f"Document {idx + 1}"),
                "type": doc_content.get("type", "UNKNOWN"),
                "is_first": idx == 0,
            })
            total_tokens += tokens
        
        # Process additional pieces (lowest priority)
        for piece in additional_pieces:
            tokens = LectureService._estimate_tokens(piece)
            content_sources.append({
                "text": piece,
                "tokens": tokens,
                "priority": 4,  # Lowest priority
                "title": "Additional Source",
                "type": "EXTRA",
                "is_first": False,
            })
            total_tokens += tokens
        
        # Check if we need to truncate
        if total_tokens <= LectureService.MAX_INPUT_TOKENS:
            # No truncation needed - combine all content
            combined_parts = []
            for source in content_sources:
                combined_parts.append(source["text"])
            
            return "\n\n".join(combined_parts), {
                "total_tokens": total_tokens,
                "truncated": False,
                "sources_included": len(content_sources),
            }
        
        # Need to truncate - prioritize intelligently
        # Strategy: Truncate additional pieces (priority 4) first, then selected documents (priority 1) if needed
        logger.warning(
            f"Content exceeds token limit ({total_tokens} > {LectureService.MAX_INPUT_TOKENS}). "
            f"Applying intelligent truncation: truncating additional documents first, then selected chapters if needed."
        )
        
        # Separate sources by priority
        priority_1_sources = [s for s in content_sources if s["priority"] == 1]  # Selected chapters
        priority_3_sources = [s for s in content_sources if s["priority"] == 3]  # Other primary documents
        priority_4_sources = [s for s in content_sources if s["priority"] == 4]  # Additional pieces (truncate first)
        
        available_tokens = LectureService.MAX_INPUT_TOKENS
        included_sources = []
        truncated_sources = []
        
        # Step 1: Process priority 1 sources (selected chapters) first - keep as much as possible
        for source in priority_1_sources:
            source_tokens = source["tokens"]
            if available_tokens >= source_tokens:
                included_sources.append(source)
                available_tokens -= source_tokens
            elif available_tokens >= LectureService.MIN_TOKENS_PER_SOURCE:
                # Truncate selected chapters if needed
                truncated_text = LectureService._truncate_text_by_tokens(
                    source["text"], available_tokens
                )
                source["text"] = truncated_text
                source["tokens"] = LectureService._estimate_tokens(truncated_text)
                included_sources.append(source)
                available_tokens = 0
                break
            else:
                # Can't fit even minimum - truncate heavily or skip
                if available_tokens > 0:
                    truncated_text = LectureService._truncate_text_by_tokens(
                        source["text"], available_tokens
                    )
                    source["text"] = truncated_text
                    source["tokens"] = LectureService._estimate_tokens(truncated_text)
                    included_sources.append(source)
                    available_tokens = 0
                else:
                    truncated_sources.append(source)
                break
        
        # Step 2: Process priority 3 sources (other primary documents) with remaining tokens
        for source in priority_3_sources:
            source_tokens = source["tokens"]
            if available_tokens >= source_tokens:
                included_sources.append(source)
                available_tokens -= source_tokens
            elif available_tokens >= LectureService.MIN_TOKENS_PER_SOURCE:
                truncated_text = LectureService._truncate_text_by_tokens(
                    source["text"], available_tokens
                )
                source["text"] = truncated_text
                source["tokens"] = LectureService._estimate_tokens(truncated_text)
                included_sources.append(source)
                available_tokens = 0
                break
            else:
                truncated_sources.append(source)
        
        # Step 3: Process priority 4 sources (additional pieces) last - truncate aggressively
        # These get whatever tokens are left after priority 1 and 3
        for source in priority_4_sources:
            if available_tokens > 0:
                tokens_to_use = min(available_tokens, source["tokens"])
                if tokens_to_use >= LectureService.MIN_TOKENS_PER_SOURCE:
                    truncated_text = LectureService._truncate_text_by_tokens(
                        source["text"], tokens_to_use
                    )
                    source["text"] = truncated_text
                    source["tokens"] = LectureService._estimate_tokens(truncated_text)
                    included_sources.append(source)
                    available_tokens -= source["tokens"]
                else:
                    # Not enough tokens for minimum - skip this additional piece
                    truncated_sources.append(source)
            else:
                # No tokens left - skip all remaining additional pieces
                truncated_sources.append(source)
        
        # Combine included sources
        combined_parts = []
        final_tokens = 0
        for source in included_sources:
            combined_parts.append(source["text"])
            final_tokens += source["tokens"]
        
        metadata = {
            "total_tokens": final_tokens,
            "original_tokens": total_tokens,
            "truncated": True,
            "sources_included": len(included_sources),
            "sources_truncated": len(truncated_sources),
            "truncated_source_titles": [s["title"] for s in truncated_sources],
        }
        
        logger.info(
            f"Content management: {len(included_sources)} sources included, "
            f"{len(truncated_sources)} truncated. "
            f"Tokens: {final_tokens}/{total_tokens} ({final_tokens/total_tokens*100:.1f}%)"
        )
        
        return "\n\n".join(combined_parts), metadata

    @staticmethod
    def _flatten_parsed_content(parsed: dict) -> str:
        """
        Convert parsed document JSON (from DocumentParser) into a flat text string.
        Handles both chapter/section dicts (PDF) and heading-based dicts (DOCX).
        """
        try:
            content = parsed.get("content")
            if isinstance(content, dict):
                parts = []
                for key, value in content.items():
                    parts.append(f"\n=== {key} ===\n")
                    if isinstance(value, dict):
                        for sub_key, sub_val in value.items():
                            if isinstance(sub_val, (str, int, float)):
                                parts.append(f"\n{sub_key}\n{sub_val}\n")
                            elif isinstance(sub_val, list):
                                parts.append("\n".join(str(v.get("text", v)) for v in sub_val))
                            else:
                                parts.append(str(sub_val))
                    elif isinstance(value, list):
                        parts.append("\n".join(str(v.get("text", v)) for v in value))
                    else:
                        parts.append(str(value))
                return "\n".join(parts)
            elif isinstance(content, (str, int, float)):
                return str(content)
            else:
                # Fallback to full JSON if unknown shape
                return json.dumps(parsed, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to flatten parsed content: {e}")
            return json.dumps(parsed, ensure_ascii=False)

    @staticmethod
    async def _fetch_bytes(url: str, timeout: int = 30) -> bytes:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")
                    return await resp.read()
        except Exception as e:
            logger.warning(f"Failed to download extra file url '{url}': {e}")
            return b""

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
        additional_text: str = None,
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

            # Note: Token management is handled before this function is called
            # No need to truncate here as content is already managed
            logger.info(f"Source text length: {len(source_text)} characters ({LectureService._estimate_tokens(source_text)} tokens)")

            # Build learning outcomes section if provided
            learning_outcomes_section = ""
            if learning_outcomes:
                learning_outcomes_section = f"""

LEARNING OUTCOMES FOR STUDENTS:
========================================
{learning_outcomes}

"""

            # Note: Additional sources are already included in document_content
            # via token management, so additional_text should be None
            additional_sources_section = ""
            if additional_text:
                # This should rarely happen now, but keep for backward compatibility
                logger.warning("Additional text provided directly - should be included in managed content")
                additional_sources_section = f"""

ADDITIONAL TRANSIENT SOURCES (NOT SAVED):
========================================
{additional_text}

"""

            # Create prompt for lecture generation
            # Build learning outcomes instruction if provided
            learning_outcomes_instruction = ""
            if learning_outcomes:
                learning_outcomes_instruction = f"""
**CRITICAL - LEARNING OUTCOMES (HIGHEST PRIORITY):**
The lecture MUST be structured to achieve these specific learning outcomes. Every section of the lecture should directly contribute to helping students achieve these outcomes:
{learning_outcomes}

Ensure that by the end of the lecture, students will have acquired the knowledge and skills specified in these learning outcomes.
"""

            prompt = f"""You are an expert educational content creator and lecturer. Generate a **comprehensive, engaging, and descriptive lecture script** based **PRIMARILY on the SOURCE MATERIAL provided below**.

**ABSOLUTE RULES - FOLLOW STRICTLY:**
1. **START THE LECTURE IMMEDIATELY** - Begin directly with the lecture content. Do NOT include any preamble, introduction about yourself, or meta-commentary.
2. **NO APOLOGIES OR DISCLAIMERS** - Never write things like "I cannot meet...", "I'm sorry but...", "This is not feasible...", "I will try to...", or any similar statements.
3. **NO META-COMMENTARY** - Do not discuss the task, the word count, the limitations, or what you will/won't do. Just produce the lecture.
4. **OUTPUT ONLY THE LECTURE** - The response should contain ONLY the lecture script that a teacher can read directly to students.

**CRITICAL INSTRUCTION: The lecture content MUST be derived from and based on the SOURCE MATERIAL and ADDITIONAL SOURCES provided. Do NOT generate generic content based solely on the title or description. Extract, explain, and elaborate on the actual concepts, facts, theories, and information present in the source material.**

The lecture should be written **as if the teacher is speaking to the class**, guiding students through concepts, examples, and explanations in a natural, instructive tone.

**LECTURE QUALITY REQUIREMENTS:**
- **Engaging** - Capture and maintain student attention throughout
- **Informative** - Provide substantial educational value
- **Self-explanatory** - Concepts should be explained fully without requiring external references
- **Clearly understandable** - Use accessible language appropriate for undergraduate students
- **Rich in examples and analogies** - Use concrete examples and meaningful analogies to help students grasp abstract concepts
- **Visually engaging** - Use emojis, tables, and flowcharts where they enhance understanding (see VISUAL FORMATTING below)

**VISUAL FORMATTING (USE WHERE IT IMPROVES CLARITY):**

1. **EMOJIS** — Use sparingly to add visual cues. Suggested usage:
   - 🎯 Learning objectives, key goals
   - 📌 Important points to remember
   - 💡 Key insights, "aha" moments, tips
   - ⚠️ Warnings, common mistakes, things to watch out for
   - 📊 Data/statistics being introduced
   - 🔬 Experiments, scientific procedures
   - ❓ Thought-provoking questions ("Ask yourself" sections)
   - ✅ Correct examples, confirmed facts
   - 🧠 Brainstorming/thinking activities
   - 📝 Summary/recap sections
   Use 1 emoji per relevant header or callout — DO NOT overuse them.

2. **MARKDOWN TABLES** — Use when comparing items, listing properties, showing classifications, or organizing structured data. Output the table DIRECTLY in your response — do NOT wrap it in backtick code fences. Format:

   | Column 1 | Column 2 | Column 3 |
   |----------|----------|----------|
   | Value A  | Value B  | Value C  |
   | Value D  | Value E  | Value F  |

   Tables MUST be in this exact markdown format with pipe separators and a header divider row. Never wrap a table in ``` backticks.

3. **MERMAID FLOWCHARTS** — Use for processes, decision trees, hierarchies, cycles, or system overviews. Wrap in fenced code blocks with `mermaid` language tag:
   ```mermaid
   flowchart TD
       A[Start] --> B{{Decision}}
       B -->|Yes| C[Action 1]
       B -->|No| D[Action 2]
       C --> E[End]
       D --> E
   ```
   Use mermaid syntax: `flowchart TD` (top-down), `flowchart LR` (left-right), `graph`, etc. Keep diagrams simple — 5-10 nodes max for readability.
   **CRITICAL mermaid rules to avoid render errors:**
   - Keep node labels SHORT and SIMPLE (2-5 words max).
   - DO NOT use parentheses `()`, brackets `[]`, braces `{{}}`, ampersands `&`, slashes `/`, semicolons `;`, or quotes inside node labels — these break mermaid rendering.
   - If you must include special characters, wrap the entire label in double quotes: `A["Label with (special) chars"]`
   - Avoid line breaks inside labels.
   - Each line must be a complete edge or node definition.

**WHEN TO USE VISUALS:**
- Insert **at least 1-2 tables** if the topic involves comparisons, classifications, properties, or structured data
- Insert **at least 1 flowchart** if the topic involves processes, cycles, mechanisms, or step-by-step procedures
- Use emojis at section headers and key callouts throughout
- Place visuals AFTER the relevant explanation, not before

**IMPORTANT: This lecture should be designed for approximately 45 minutes of delivery time.** The content should be substantial, detailed, and comprehensive enough to fill this duration when spoken at a natural teaching pace.

---

## PRIMARY SOURCE MATERIAL (BASE YOUR LECTURE ON THIS):
========================================
{source_text}
========================================
{additional_sources_section}
{learning_outcomes_instruction}
**Lecture Title:** {title}

**Teacher's Guidance/Context:**
{description}
{learning_outcomes_section}

---

### Instructions for the Lecture Script:

**CONTENT PRIORITY (Follow this order):**
1. **SOURCE MATERIAL IS PRIMARY** — The lecture content MUST be extracted from and based on the source material provided above. Cover the key concepts, theories, facts, and examples found in the source material.
2. **LEARNING OUTCOMES ARE MANDATORY** — If learning outcomes are provided, structure the entire lecture to ensure students achieve those specific outcomes. Every section should contribute to at least one learning outcome.
3. **ADDITIONAL SOURCES SUPPLEMENT** — Use any additional sources to enrich and expand on the primary source material.
4. **Teacher's description provides CONTEXT ONLY** — Use the description to understand the tone, focus areas, and depth expected, but do NOT generate content from the description alone.

**STYLE AND DELIVERY:**
1. **Write in a teacher's spoken voice** — the tone should be clear, conversational, and engaging, as though the teacher is explaining concepts live in class.  
2. **Be descriptive and vivid** — elaborate extensively on key points from the source material, provide rich context, and help students visualize or deeply understand the topic. **Expand on concepts with detailed explanations.**
3. **Structure clearly**:
   - Introduction (set learning objectives based on provided outcomes, connect with prior knowledge, provide context)
   - Main Sections (each covering specific topics FROM THE SOURCE MATERIAL with detailed explanations, transitions, and subtopics)
   - Examples and Illustrations (use examples from the source material AND add real-world applications)
   - Summary / Conclusion (recap key ideas from the source material, verify learning outcomes are addressed)
4. **Integrate the source material naturally** — explain and expand on its content instead of simply restating it. **Add substantial depth and elaboration while staying true to the source.**
5. **Use extensive educational techniques**:
   - **Multiple analogies and examples** — For each major concept FROM THE SOURCE, provide 2-3 analogies or real-world examples to help students understand from different angles
   - **Thinking and brainstorming activities** — Include 3-5 moments throughout the lecture where you pause and ask students to think, brainstorm, or reflect (e.g., "Take a moment to think about...", "Let's brainstorm together...", "Before I continue, consider this scenario...")
   - **"Ask yourself" questions** — Include 5-8 unmarked, thought-provoking questions throughout the lecture (no answers provided, just food for thought). Format these as: "Ask yourself: [question]" or "Consider this: [question]"
   - Questions to prompt student thinking  
   - Emphasis and pauses (use phrases like "Let's think about this for a moment…" or "Now, this part is really important…")
6. **Length and depth**: The lecture should be comprehensive enough to fill approximately 45 minutes when delivered. This means:
   - Extensive elaboration on concepts FROM THE SOURCE MATERIAL
   - Multiple examples and analogies for each major point
   - Detailed explanations that go beyond surface-level coverage
   - Rich context and background information
   - Multiple thinking activities and reflection points
7. **Content expansion**: If the source material is limited, expand with narratives, case studies, comparisons, and reflective prompts that relate to the source content. Include `[Estimated duration: ~X minutes]` callouts at the start of each major section to reinforce pacing.
8. Maintain **academic accuracy** and logical flow, but keep it accessible for students.
9. The final output should be a **ready-to-deliver lecture script**, not just notes or bullet points. It should be detailed enough that a teacher can read it naturally and fill 45 minutes.
10. **VERIFY LEARNING OUTCOMES**: Before concluding, mentally check that each learning outcome (if provided) has been adequately addressed in the lecture content.

---

**REMEMBER: Start the lecture immediately. No preamble, no apologies, no meta-commentary. Output ONLY the lecture script.**

BEGIN THE LECTURE NOW:
"""

            # Call OpenAI API
            client = LectureService.get_openai_client()
            response = client.chat.completions.create(
                model="gpt-5-mini",  # Using gpt-5-mini for lecture generation
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational content creator specializing in generating high-quality academic lectures at an undergraduate level. You create comprehensive, detailed lectures designed for 45-minute delivery. The lectures you create are engaging, informative, self-explanatory, clearly understandable, and include examples and analogies to meaningfully explain concepts to students. IMPORTANT: Base your lecture content PRIMARILY on the source material provided, NOT on generic knowledge about the topic. If learning outcomes are provided, ensure the lecture achieves all of them. CRITICAL: Always output ONLY the lecture content. Never include apologies, disclaimers, meta-commentary about the task, or statements like 'I cannot...' or 'I will try...'. Start directly with the lecture script.",
                    },
                    {"role": "user", "content": prompt},
                ],
                # temperature=0.7,
                # max_tokens=16384,  # Increased to allow for longer, more comprehensive lectures
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
    def _normalize_text_for_pdf(text: str) -> str:
        """
        Normalize text for PDF rendering by replacing Unicode characters
        that may not be supported by standard PDF fonts (like Helvetica).
        
        This prevents "black box" rendering issues with special characters.
        """
        if not text:
            return text
        
        # Character replacements for PDF compatibility
        replacements = {
            # Dashes
            '\u2013': '-',  # en-dash
            '\u2014': '-',  # em-dash  
            '\u2015': '-',  # horizontal bar
            '\u2010': '-',  # hyphen
            '\u2011': '-',  # non-breaking hyphen
            '\u2012': '-',  # figure dash
            '\u2212': '-',  # minus sign
            
            # Quotes
            '\u2018': "'",  # left single quote
            '\u2019': "'",  # right single quote (apostrophe)
            '\u201A': "'",  # single low-9 quote
            '\u201B': "'",  # single high-reversed-9 quote
            '\u2032': "'",  # prime
            '\u2035': "'",  # reversed prime
            
            '\u201C': '"',  # left double quote
            '\u201D': '"',  # right double quote
            '\u201E': '"',  # double low-9 quote
            '\u201F': '"',  # double high-reversed-9 quote
            '\u2033': '"',  # double prime
            '\u2036': '"',  # reversed double prime
            '\u00AB': '"',  # left-pointing double angle quote
            '\u00BB': '"',  # right-pointing double angle quote
            
            # Spaces
            '\u00A0': ' ',  # non-breaking space
            '\u2002': ' ',  # en space
            '\u2003': ' ',  # em space
            '\u2004': ' ',  # three-per-em space
            '\u2005': ' ',  # four-per-em space
            '\u2006': ' ',  # six-per-em space
            '\u2007': ' ',  # figure space
            '\u2008': ' ',  # punctuation space
            '\u2009': ' ',  # thin space
            '\u200A': ' ',  # hair space
            '\u200B': '',   # zero-width space
            '\u202F': ' ',  # narrow no-break space
            '\u205F': ' ',  # medium mathematical space
            '\u3000': ' ',  # ideographic space
            
            # Ellipsis
            '\u2026': '...',  # horizontal ellipsis
            
            # Bullets
            '\u2022': '*',  # bullet
            '\u2023': '>',  # triangular bullet
            '\u2043': '-',  # hyphen bullet
            '\u204C': '<',  # black leftwards bullet
            '\u204D': '>',  # black rightwards bullet
            '\u2219': '*',  # bullet operator
            
            # Other common problematic characters
            '\u00B7': '*',  # middle dot
            '\u2024': '.',  # one dot leader
            '\u2027': '-',  # hyphenation point
            '\u00AD': '',   # soft hyphen (remove)
            '\uFEFF': '',   # BOM (remove)
            '\u2028': '\n', # line separator
            '\u2029': '\n\n', # paragraph separator
        }
        
        for unicode_char, replacement in replacements.items():
            text = text.replace(unicode_char, replacement)
        
        return text

    @staticmethod
    def _sanitize_mermaid(mermaid_code: str) -> str:
        """
        Auto-fix common mermaid rendering issues by wrapping problematic node labels in quotes.

        Mermaid breaks on `()`, `&`, `;`, `/` inside `[label]`, `{label}`, or `(label)`.
        We detect such labels and wrap their inner text in double quotes.
        """
        problem_chars = re.compile(r'[()&;/]')

        def fix_label(match):
            opener = match.group(1)  # [, {, or (
            label = match.group(2)
            closer = match.group(3)
            # Already quoted? Skip
            if label.startswith('"') and label.endswith('"'):
                return match.group(0)
            # Has problematic chars? Wrap in quotes
            if problem_chars.search(label):
                # Escape any existing double quotes
                safe_label = label.replace('"', "'")
                return f'{opener}"{safe_label}"{closer}'
            return match.group(0)

        # Match node labels: A[label], B{label}, C(label), C((label)), C{{label}}
        # We handle the simple cases: [...], {...}, (...)
        # Use non-greedy to handle multiple nodes on same line
        for pattern in [
            r'(\[)([^\[\]\n"]+?)(\])',
            r'(\{)([^\{\}\n"]+?)(\})',
            r'(\()([^\(\)\n"]+?)(\))',
        ]:
            mermaid_code = re.sub(pattern, fix_label, mermaid_code)

        return mermaid_code

    @staticmethod
    def _fetch_mermaid_image(mermaid_code: str) -> bytes | None:
        """
        Convert a mermaid diagram to PNG bytes using mermaid.ink public API.

        Tries the original code first; if it fails with 400, sanitizes the code
        (wraps labels with special chars in quotes) and retries.
        """
        def _try_fetch(code: str) -> tuple[int, bytes | None]:
            try:
                encoded = base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")
                url = f"https://mermaid.ink/img/{encoded}?type=png&bgColor=FFFFFF"
                response = httpx.get(url, timeout=20)
                return response.status_code, response.content if response.status_code == 200 else None
            except Exception as e:
                logger.warning(f"Mermaid fetch error: {e}")
                return 0, None

        status_code, content = _try_fetch(mermaid_code)
        if content:
            return content

        # Retry with sanitization if first attempt failed with a client error
        if status_code in (400, 422):
            sanitized = LectureService._sanitize_mermaid(mermaid_code)
            if sanitized != mermaid_code:
                logger.info("Retrying mermaid render with sanitized labels")
                status_code, content = _try_fetch(sanitized)
                if content:
                    return content

        logger.warning(f"Mermaid render failed: status={status_code}")
        return None

    @staticmethod
    def _parse_markdown_table(table_text: str) -> list[list[str]] | None:
        """
        Parse a markdown table into a list of rows.

        Returns None if the text isn't a valid markdown table.
        """
        lines = [l.strip() for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return None

        # Validate: must have header and divider with pipes
        if "|" not in lines[0] or "|" not in lines[1]:
            return None
        # Divider line should be like |---|---|
        if not re.match(r"^\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$", lines[1]):
            return None

        rows = []
        for i, line in enumerate(lines):
            if i == 1:  # Skip divider
                continue
            # Strip leading/trailing pipes, then split
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
        return rows if rows else None

    @staticmethod
    def _build_reportlab_table(rows: list[list[str]], font_regular: str, font_bold: str) -> Table:
        """Build a styled ReportLab Table from parsed rows."""
        # Wrap each cell in a Paragraph for proper text wrapping
        cell_style = ParagraphStyle(
            "TableCell",
            fontName=font_regular,
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#333333"),
        )
        header_style = ParagraphStyle(
            "TableHeader",
            fontName=font_bold,
            fontSize=10,
            leading=12,
            textColor=colors.white,
            alignment=TA_CENTER,
        )
        wrapped_rows = []
        for i, row in enumerate(rows):
            style = header_style if i == 0 else cell_style
            wrapped_rows.append([
                Paragraph(_markdown_inline_to_html(cell), style) for cell in row
            ])

        # Compute column widths to fit page
        page_width = 6.5 * inch  # letter width minus margins
        col_count = max(len(r) for r in rows)
        col_width = page_width / col_count

        table = Table(wrapped_rows, colWidths=[col_width] * col_count, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdc3c7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    @staticmethod
    def _split_content_into_blocks(content: str) -> list[dict]:
        """
        Split lecture content into typed blocks: text, table, mermaid.

        Returns a list of {"type": "text|table|mermaid", "content": str} dicts.
        """
        blocks = []
        # Pattern for fenced code blocks (mermaid) and tables
        # Mermaid: ```mermaid\n...\n```
        mermaid_pattern = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
        # Table: lines starting with | and containing a divider row
        table_pattern = re.compile(
            r"(^\|.+\|\s*$\n^\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$\n(?:^\|.+\|\s*$\n?)+)",
            re.MULTILINE,
        )

        # Find all special blocks with their positions
        special_blocks = []
        for m in mermaid_pattern.finditer(content):
            special_blocks.append((m.start(), m.end(), "mermaid", m.group(1).strip()))
        for m in table_pattern.finditer(content):
            special_blocks.append((m.start(), m.end(), "table", m.group(1).strip()))

        # Sort by start position
        special_blocks.sort(key=lambda x: x[0])

        # Walk through content, alternating text and special blocks
        cursor = 0
        for start, end, btype, text in special_blocks:
            if start > cursor:
                text_chunk = content[cursor:start].strip()
                if text_chunk:
                    blocks.append({"type": "text", "content": text_chunk})
            blocks.append({"type": btype, "content": text})
            cursor = end

        if cursor < len(content):
            remaining = content[cursor:].strip()
            if remaining:
                blocks.append({"type": "text", "content": remaining})

        if not blocks:
            blocks.append({"type": "text", "content": content})
        return blocks

    @staticmethod
    def create_pdf(title: str, content: str) -> bytes:
        """
        Create a PDF from lecture content with support for tables,
        mermaid flowcharts, and emojis.

        Args:
            title: Lecture title
            content: Lecture content (markdown-style)

        Returns:
            PDF file as bytes
        """
        try:
            logger.info("Creating PDF from lecture content")

            # Register Tahoma fonts for emoji support
            _register_pdf_fonts()
            font_regular = "Tahoma" if _FONTS_REGISTERED else "Helvetica"
            font_bold = "TahomaBold" if _FONTS_REGISTERED else "Helvetica-Bold"

            # Normalize text to prevent black box rendering of special characters
            title = LectureService._normalize_text_for_pdf(title)
            content = LectureService._normalize_text_for_pdf(content)

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

            elements = []
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                "CustomTitle",
                parent=styles["Heading1"],
                fontSize=24,
                textColor=colors.HexColor("#1a1a1a"),
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName=font_bold,
            )
            heading_style = ParagraphStyle(
                "CustomHeading",
                parent=styles["Heading2"],
                fontSize=16,
                textColor=colors.HexColor("#2c3e50"),
                spaceAfter=12,
                spaceBefore=12,
                fontName=font_bold,
            )
            subheading_style = ParagraphStyle(
                "CustomSubheading",
                parent=styles["Heading3"],
                fontSize=13,
                textColor=colors.HexColor("#34495e"),
                spaceAfter=8,
                spaceBefore=10,
                fontName=font_bold,
            )
            body_style = ParagraphStyle(
                "CustomBody",
                parent=styles["BodyText"],
                fontSize=11,
                textColor=colors.HexColor("#333333"),
                alignment=TA_JUSTIFY,
                spaceAfter=12,
                leading=15,
                fontName=font_regular,
            )

            # Title
            elements.append(Paragraph(_markdown_inline_to_html(title), title_style))
            elements.append(Spacer(1, 0.2 * inch))

            timestamp = datetime.utcnow().strftime("%B %d, %Y")
            elements.append(Paragraph(f"<i>Generated on {timestamp}</i>", styles["Italic"]))
            elements.append(Spacer(1, 0.3 * inch))

            # Split content into typed blocks
            blocks = LectureService._split_content_into_blocks(content)

            for block in blocks:
                btype = block["type"]
                btext = block["content"]

                if btype == "mermaid":
                    img_bytes = LectureService._fetch_mermaid_image(btext)
                    if img_bytes:
                        try:
                            img = Image(BytesIO(img_bytes))
                            # Scale to fit BOTH page width and height (with margin headroom)
                            max_width = 6.0 * inch
                            max_height = 8.0 * inch  # Leave room for margins on letter (11" tall)
                            iw, ih = img.imageWidth, img.imageHeight

                            # Compute scale ratios for width and height; pick the smaller (most restrictive)
                            width_ratio = max_width / iw if iw > max_width else 1.0
                            height_ratio = max_height / ih if ih > max_height else 1.0
                            scale = min(width_ratio, height_ratio)

                            if scale < 1.0:
                                img.drawWidth = iw * scale
                                img.drawHeight = ih * scale
                            else:
                                img.drawWidth = iw
                                img.drawHeight = ih

                            elements.append(Spacer(1, 0.15 * inch))
                            elements.append(img)
                            elements.append(Spacer(1, 0.15 * inch))
                        except Exception as e:
                            logger.warning(f"Could not embed mermaid image: {e}")
                            # Fallback: render as code block
                            elements.append(Paragraph(
                                f"<font name='Courier' size='9'>[Diagram]<br/>{_escape_xml(btext).replace(chr(10), '<br/>')}</font>",
                                body_style,
                            ))
                    else:
                        # Fallback: show mermaid source
                        elements.append(Paragraph(
                            f"<font name='Courier' size='9'>[Diagram]<br/>{_escape_xml(btext).replace(chr(10), '<br/>')}</font>",
                            body_style,
                        ))

                elif btype == "table":
                    rows = LectureService._parse_markdown_table(btext)
                    if rows:
                        elements.append(Spacer(1, 0.1 * inch))
                        elements.append(LectureService._build_reportlab_table(rows, font_regular, font_bold))
                        elements.append(Spacer(1, 0.15 * inch))
                    else:
                        elements.append(Paragraph(_escape_xml(btext), body_style))

                else:  # text
                    paragraphs = btext.split("\n\n")
                    for para in paragraphs:
                        para = para.strip()
                        if not para:
                            continue

                        # Markdown headings
                        if para.startswith("###"):
                            elements.append(Paragraph(
                                _markdown_inline_to_html(para.lstrip("#").strip()),
                                subheading_style,
                            ))
                        elif para.startswith("##"):
                            elements.append(Paragraph(
                                _markdown_inline_to_html(para.lstrip("#").strip()),
                                heading_style,
                            ))
                        elif para.startswith("#"):
                            elements.append(Paragraph(
                                _markdown_inline_to_html(para.lstrip("#").strip()),
                                heading_style,
                            ))
                        elif len(para) < 100 and para.endswith(":") and "\n" not in para:
                            elements.append(Paragraph(
                                _markdown_inline_to_html(para),
                                heading_style,
                            ))
                        else:
                            html_para = _markdown_inline_to_html(para).replace("\n", "<br/>")
                            elements.append(Paragraph(html_para, body_style))

                        elements.append(Spacer(1, 0.05 * inch))

            doc.build(elements)
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
    def get_next_lecture_number(
        db,
        topic: str,
        course_id,  # Can be int or str
        semester_id,  # Can be int or str
    ) -> int:
        """
        Get the next lecture number for a given topic within a course and semester.
        
        Args:
            db: Database instance
            topic: Topic name (e.g., "CLUSTERING", "PREDICTION", "REGRESSION")
            course_id: Course ID (int or str)
            semester_id: Semester ID (int or str)
            
        Returns:
            Next lecture number (starts from 1)
        """
        try:
            if not topic:
                return None
            
            # Ensure course_id and semester_id are integers for database query
            course_int_id = course_id if isinstance(course_id, int) else int(course_id)
            semester_int_id = semester_id if isinstance(semester_id, int) else int(semester_id)
                
            # Query existing lectures for this topic, course, and semester
            response = (
                db.admin_client.table("lecture")
                .select("lecture_number")
                .eq("topic", topic)
                .eq("course_id", course_int_id)
                .eq("semester_id", semester_int_id)
                .not_.is_("lecture_number", "null")
                .order("lecture_number", desc=True)
                .limit(1)
                .execute()
            )
            
            if response.data and len(response.data) > 0:
                max_number = response.data[0].get("lecture_number", 0)
                return max_number + 1
            else:
                # First lecture for this topic
                return 1
                
        except Exception as e:
            logger.warning(f"Error calculating next lecture number: {str(e)}")
            return None

    @staticmethod
    async def generate_and_save_lecture(
        db,
        document_id: str = None,
        document_ids: list = None,
        teacher_id: str = None,
        course_id: str = None,
        semester_id: str = None,
        lecture_title: str = None,
        lecture_description: str = None,
        learning_outcomes: str = None,
        selected_chapters: list = None,
        topic: str = None,
        extra_document_ids: list = None,
        extra_texts: list = None,
        extra_file_urls: list = None,
        extra_uploads: list = None,
    ) -> dict:
        """
        Complete workflow: generate lecture from document(s) and save to storage.

        Args:
            db: Database instance
            document_id: ID of a single source document (deprecated, use document_ids)
            document_ids: List of IDs of source documents (PDF/PPTX) - supports multiple documents
            teacher_id: Teacher ID
            course_id: Course ID
            semester_id: Semester ID
            lecture_title: Title for the lecture
            lecture_description: Description/overview from teacher
            learning_outcomes: Learning outcomes for students (optional)
            selected_chapters: List of chapter names to include (None = all chapters) - applies to first document if multiple

        Returns:
            Dictionary with lecture information and storage path
        """
        try:
            # Normalize document_ids: support both single document_id (backward compat) and document_ids list
            if document_ids:
                primary_document_ids = document_ids
            elif document_id:
                primary_document_ids = [document_id]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either document_id or document_ids must be provided",
                )

            logger.info(f"Starting lecture generation for {len(primary_document_ids)} document(s): {primary_document_ids}")

            # 1. Fetch all documents from database and verify access
            primary_document_contents = []
            first_document_data = None
            
            for doc_id in primary_document_ids:
                document_data = db.get_record_by_id("documents", doc_id)
                if not document_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Document not found: {doc_id}",
                    )

                # Verify document belongs to teacher
                # Both teacher_id and document_data.get("teacher_id") should be integers
                # Ensure both are integers for comparison
                doc_teacher_id = document_data.get("teacher_id")
                
                # Convert teacher_id to integer for comparison
                # Handle both UUID strings and integer IDs
                teacher_id_int = teacher_id
                if isinstance(teacher_id, int):
                    teacher_id_int = teacher_id
                elif isinstance(teacher_id, str):
                    if IDConverter.is_uuid(teacher_id):
                        teacher_id_int = await IDConverter.uuid_to_int(db, "teacher", teacher_id)
                        if not teacher_id_int:
                            raise HTTPException(
                                status_code=status.HTTP_404_NOT_FOUND,
                                detail="Teacher not found",
                            )
                    else:
                        try:
                            teacher_id_int = int(teacher_id)
                        except ValueError:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Invalid teacher_id format",
                            )
                else:
                    # Try to convert to string first, then process
                    teacher_id_str = str(teacher_id)
                    if IDConverter.is_uuid(teacher_id_str):
                        teacher_id_int = await IDConverter.uuid_to_int(db, "teacher", teacher_id_str)
                        if not teacher_id_int:
                            raise HTTPException(
                                status_code=status.HTTP_404_NOT_FOUND,
                                detail="Teacher not found",
                            )
                    else:
                        try:
                            teacher_id_int = int(teacher_id_str)
                        except ValueError:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Invalid teacher_id format: {teacher_id}",
                            )
                
                # doc_teacher_id from database should be an integer, but ensure it is
                if doc_teacher_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Document {doc_id} has no teacher_id",
                    )
                
                # Convert doc_teacher_id to integer - handle UUID strings
                doc_teacher_id_int = doc_teacher_id
                if isinstance(doc_teacher_id, str):
                    if IDConverter.is_uuid(doc_teacher_id):
                        doc_teacher_id_int = await IDConverter.uuid_to_int(db, "teacher", doc_teacher_id)
                        if not doc_teacher_id_int:
                            raise HTTPException(
                                status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Teacher not found for document {doc_id}",
                            )
                    else:
                        try:
                            doc_teacher_id_int = int(doc_teacher_id)
                        except ValueError:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Invalid teacher_id format in document {doc_id}: {doc_teacher_id}",
                            )
                elif not isinstance(doc_teacher_id, int):
                    try:
                        doc_teacher_id_int = int(doc_teacher_id)
                    except (ValueError, TypeError):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid teacher_id format in document {doc_id}: {doc_teacher_id}",
                        )
                
                if doc_teacher_id_int != teacher_id_int:
                    logger.warning(
                        f"Teacher ID mismatch for document {doc_id}: "
                        f"document teacher_id={doc_teacher_id_int}, "
                        f"requested teacher_id={teacher_id_int}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Access denied to document: {doc_id}",
                    )

                # Store first document for backward compatibility (lecture.document_id)
                if first_document_data is None:
                    first_document_data = document_data

                logger.info(f"Document found: {document_data['title']} ({document_data.get('document_type', 'UNKNOWN')})")

                # 2. Fetch document JSON content from Supabase
                document_content = await LectureService.fetch_document_json(
                    document_data["content_json_path"]
                )

                # 3. Filter content by selected chapters (only for first document if multiple)
                if selected_chapters and doc_id == primary_document_ids[0]:
                    logger.info(f"Filtering content to {len(selected_chapters)} chapters for first document")
                    document_content = LectureService.extract_chapters_content(
                        document_content, selected_chapters
                    )

                # Flatten the content
                flattened_content = LectureService._flatten_parsed_content(document_content)
                
                # Add document metadata
                doc_title = document_data.get("title", "Untitled")
                doc_type = document_data.get("document_type", "UNKNOWN")
                combined_content = f"\n\n=== DOCUMENT: {doc_title} ({doc_type}) ===\n\n{flattened_content}"
                
                primary_document_contents.append({
                    "content": combined_content,
                    "title": doc_title,
                    "type": doc_type,
                    "is_first": doc_id == primary_document_ids[0],
                })
            
            # Get document titles for metadata
            document_titles = []
            for doc_id in primary_document_ids:
                doc = db.get_record_by_id("documents", doc_id)
                if doc:
                    document_titles.append(doc.get("title", "Untitled"))

            # Build additional transient sources from extra documents and raw texts (not saved)
            additional_pieces: list[str] = []

            # Include extra documents (validate access)
            try:
                if extra_document_ids:
                    for extra_doc_id in extra_document_ids:
                        extra_doc = db.get_record_by_id("documents", extra_doc_id)
                        if not extra_doc:
                            logger.warning(f"Extra document not found: {extra_doc_id}")
                            continue
                        if extra_doc.get("teacher_id") != teacher_id:
                            logger.warning(
                                f"Access denied to extra document {extra_doc_id} for teacher {teacher_id}"
                            )
                            continue
                        try:
                            extra_json = await LectureService.fetch_document_json(
                                extra_doc["content_json_path"]
                            )
                            # Extract text similar to main doc
                            if "content" in extra_json:
                                if isinstance(extra_json["content"], str):
                                    extra_text = extra_json["content"]
                                elif isinstance(extra_json["content"], list):
                                    extra_text = "\n".join(
                                        str(item) for item in extra_json["content"]
                                    )
                                else:
                                    extra_text = str(extra_json["content"])
                            elif "text" in extra_json:
                                extra_text = extra_json["text"]
                            else:
                                extra_text = json.dumps(extra_json, indent=2)
                            title = extra_doc.get("title") or "Untitled"
                            additional_pieces.append(
                                f"=== {title} ===\n{extra_text}"
                            )
                        except Exception as extra_fetch_err:
                            logger.warning(
                                f"Failed to fetch/parse extra document {extra_doc_id}: {extra_fetch_err}"
                            )
            except Exception as extras_err:
                logger.warning(f"Error while processing extra documents: {extras_err}")

            # Include any raw text snippets
            try:
                if extra_texts:
                    for idx, txt in enumerate(extra_texts, start=1):
                        if not txt:
                            continue
                        additional_pieces.append(f"=== EXTRA TEXT {idx} ===\n{str(txt)}")
            except Exception as extra_txt_err:
                logger.warning(f"Error while processing extra texts: {extra_txt_err}")

            # Include extra remote files (txt, pdf, docx)
            try:
                if extra_file_urls:
                    for url in extra_file_urls:
                        if not url:
                            continue
                        url_lower = url.lower()
                        file_bytes = await LectureService._fetch_bytes(url)
                        if not file_bytes:
                            continue
                        piece_text = ""
                        try:
                            if url_lower.endswith(".txt"):
                                piece_text = file_bytes.decode("utf-8", errors="ignore")
                            elif url_lower.endswith(".pdf"):
                                parsed = await DocumentParser.parse_document(
                                    file_bytes, DocumentType.PDF, url.split("/")[-1]
                                )
                                piece_text = LectureService._flatten_parsed_content(parsed)
                            elif url_lower.endswith(".docx"):
                                parsed = await DocumentParser.parse_document(
                                    file_bytes, DocumentType.DOCX, url.split("/")[-1]
                                )
                                piece_text = LectureService._flatten_parsed_content(parsed)
                            else:
                                # Unsupported extension - best effort: try text
                                piece_text = file_bytes.decode("utf-8", errors="ignore")
                        except Exception as parse_err:
                            logger.warning(f"Failed to parse extra file url '{url}': {parse_err}")
                            continue

                        if piece_text:
                            # Per-piece limit
                            clipped = LectureService._truncate_text(
                                piece_text, LectureService.PER_PIECE_LIMIT
                            )
                            additional_pieces.append(f"=== {url} ===\n{clipped}")
            except Exception as extra_url_err:
                logger.warning(f"Error while processing extra file urls: {extra_url_err}")

            # Include uploaded files (txt, pdf, docx)
            try:
                if extra_uploads:
                    for item in extra_uploads:
                        try:
                            filename = (item.get("filename") or "upload").lower()
                            content_type = (item.get("content_type") or "").lower()
                            file_bytes: bytes = item.get("bytes") or b""
                            if not file_bytes:
                                continue

                            piece_text = ""
                            if filename.endswith(".txt") or content_type.startswith("text/"):
                                piece_text = file_bytes.decode("utf-8", errors="ignore")
                            elif filename.endswith(".pdf") or "pdf" in content_type:
                                parsed = await DocumentParser.parse_document(
                                    file_bytes, DocumentType.PDF, filename
                                )
                                piece_text = LectureService._flatten_parsed_content(parsed)
                            elif filename.endswith(".docx") or "wordprocessingml" in content_type:
                                parsed = await DocumentParser.parse_document(
                                    file_bytes, DocumentType.DOCX, filename
                                )
                                piece_text = LectureService._flatten_parsed_content(parsed)
                            else:
                                # Best-effort fallback
                                piece_text = file_bytes.decode("utf-8", errors="ignore")

                            if piece_text:
                                clipped = LectureService._truncate_text(
                                    piece_text, LectureService.PER_PIECE_LIMIT
                                )
                                additional_pieces.append(f"=== {filename} ===\n{clipped}")
                        except Exception as upload_err:
                            logger.warning(f"Failed to parse uploaded file: {upload_err}")
            except Exception as extra_uploads_err:
                logger.warning(f"Error while processing uploaded files: {extra_uploads_err}")

            # 4. Use intelligent token management to combine all content
            managed_content, content_metadata = LectureService._manage_content_tokens(
                primary_contents=primary_document_contents,
                additional_pieces=additional_pieces,
                selected_chapters=selected_chapters,
            )
            
            # Log token management results
            if content_metadata.get("truncated"):
                logger.warning(
                    f"Content was truncated due to token limits. "
                    f"Original: {content_metadata.get('original_tokens', 0)} tokens, "
                    f"Final: {content_metadata.get('total_tokens', 0)} tokens. "
                    f"Truncated sources: {content_metadata.get('truncated_source_titles', [])}"
                )
            else:
                logger.info(
                    f"All content fits within token limits: "
                    f"{content_metadata.get('total_tokens', 0)} tokens from "
                    f"{content_metadata.get('sources_included', 0)} sources"
                )
            
            # Create unified document structure for AI prompt
            document_content = {
                "content": managed_content,
                "metadata": {
                    "total_documents": len(primary_document_ids),
                    "document_titles": document_titles,
                    "token_management": content_metadata,
                }
            }

            # 5. Generate lecture content using AI (with managed content)
            generated_content = await LectureService.generate_lecture_content(
                document_content,
                lecture_description,
                lecture_title,
                learning_outcomes,
                additional_text=None,  # Already included in managed_content
            )

            # 6. Create PDF from generated content
            pdf_bytes = LectureService.create_pdf(lecture_title, generated_content)

            # 7. Convert UUIDs to integer IDs for database (do this before storage path and lecture number)
            # Initialize with None to ensure we always convert
            course_int_id = None
            semester_int_id = None
            teacher_int_id = None
            primary_document_int_id = None
            
            # Convert course_id - handle None, string (UUID or int string), or int
            if course_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="course_id is required",
                )
            elif isinstance(course_id, int):
                course_int_id = course_id
            elif isinstance(course_id, str):
                if IDConverter.is_uuid(course_id):
                    course_int_id = await IDConverter.uuid_to_int(db, "course", course_id)
                    if not course_int_id:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Course not found",
                        )
                else:
                    try:
                        course_int_id = int(course_id)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid course_id format: {course_id}",
                        )
            else:
                # Try to convert to string first, then process
                course_id_str = str(course_id)
                if IDConverter.is_uuid(course_id_str):
                    course_int_id = await IDConverter.uuid_to_int(db, "course", course_id_str)
                    if not course_int_id:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Course not found",
                        )
                else:
                    try:
                        course_int_id = int(course_id_str)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid course_id format: {course_id}",
                        )
            
            # Convert semester_id - handle None, string (UUID or int string), or int
            if semester_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="semester_id is required",
                )
            elif isinstance(semester_id, int):
                semester_int_id = semester_id
            elif isinstance(semester_id, str):
                if IDConverter.is_uuid(semester_id):
                    semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id)
                    if not semester_int_id:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Semester not found",
                        )
                else:
                    try:
                        semester_int_id = int(semester_id)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid semester_id format: {semester_id}",
                        )
            else:
                # Try to convert to string first, then process
                semester_id_str = str(semester_id)
                if IDConverter.is_uuid(semester_id_str):
                    semester_int_id = await IDConverter.uuid_to_int(db, "semester", semester_id_str)
                    if not semester_int_id:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Semester not found",
                        )
                else:
                    try:
                        semester_int_id = int(semester_id_str)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid semester_id format: {semester_id}",
                        )
            
            # Convert teacher_id - handle None, string (UUID or int string), or int
            if teacher_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="teacher_id is required",
                )
            elif isinstance(teacher_id, int):
                teacher_int_id = teacher_id
            elif isinstance(teacher_id, str):
                if IDConverter.is_uuid(teacher_id):
                    teacher_int_id = await IDConverter.uuid_to_int(db, "teacher", teacher_id)
                    if not teacher_int_id:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Teacher not found",
                        )
                else:
                    try:
                        teacher_int_id = int(teacher_id)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid teacher_id format: {teacher_id}",
                        )
            else:
                # Try to convert to string first, then process
                teacher_id_str = str(teacher_id)
                if IDConverter.is_uuid(teacher_id_str):
                    teacher_int_id = await IDConverter.uuid_to_int(db, "teacher", teacher_id_str)
                    if not teacher_int_id:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Teacher not found",
                        )
                else:
                    try:
                        teacher_int_id = int(teacher_id_str)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid teacher_id format: {teacher_id}",
                        )
            
            # Convert primary document_id
            primary_document_id = primary_document_ids[0] if primary_document_ids else None
            if primary_document_id:
                if isinstance(primary_document_id, str):
                    if IDConverter.is_uuid(primary_document_id):
                        primary_document_int_id = await IDConverter.uuid_to_int(db, "documents", primary_document_id)
                    else:
                        try:
                            primary_document_int_id = int(primary_document_id)
                        except ValueError:
                            primary_document_int_id = None
                else:
                    primary_document_int_id = primary_document_id

            # 8. Save PDF to Supabase storage
            # Use sanitized lecture title as filename
            # Storage path can use UUID for course_id (it's just a string in the path)
            sanitized_title = LectureService.sanitize_filename(lecture_title)
            pdf_filename = f"{sanitized_title}.pdf"
            
            # Convert all IDs to strings for storage path (storage path accepts strings)
            university_id_str = str(first_document_data["university_id"])
            teacher_id_str = str(teacher_int_id)
            course_id_str = str(course_int_id)
            
            storage_path = await LectureService.save_lecture_pdf(
                pdf_bytes,
                university_id_str,
                teacher_id_str,
                course_id_str,
                pdf_filename,
            )

            # 9. Lecture plan is now generated separately via POST /{lecture_id}/generate-plan endpoint
            # This allows frontend to call lecture generation and plan generation independently
            lecture_plan = None

            # 10. Calculate lecture number if topic is provided (using integer IDs)
            lecture_number = None
            if topic:
                lecture_number = LectureService.get_next_lecture_number(
                    db, topic, course_int_id, semester_int_id
                )
                logger.info(f"Assigned lecture number {lecture_number} for topic '{topic}'")

            # 11. Create lecture record in database
            # Ensure all IDs are integers (defensive check)
            if not isinstance(course_int_id, int):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Invalid course_id type: {type(course_int_id)}, value: {course_int_id}",
                )
            if not isinstance(semester_int_id, int):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Invalid semester_id type: {type(semester_int_id)}, value: {semester_int_id}",
                )
            if not isinstance(teacher_int_id, int):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Invalid teacher_id type: {type(teacher_int_id)}, value: {teacher_int_id}",
                )
            
            lecture_data = {
                "title": lecture_title,
                "description": lecture_description,
                "learning_outcomes": learning_outcomes,
                "content": generated_content,
                "lecture_type": "AI_GENERATED",
                "status": "GENERATED",
                "course_id": course_int_id,  # Use integer ID
                "semester_id": semester_int_id,  # Use integer ID
                "teacher_id": teacher_int_id,  # Use integer ID
                "document_id": primary_document_int_id,  # Use integer ID (can be None)
                "lecture_plan": lecture_plan,
                "topic": topic,
                "lecture_number": lecture_number,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            lecture_record = db.create_record("lecture", lecture_data)
            logger.info(f"Lecture record created: {lecture_record['id']}")

            # Get integer lecture_id for lecture_content
            # db.create_record returns UUID in 'id' field, but we need integer ID for foreign key
            lecture_uuid = lecture_record.get("id") or lecture_record.get("uuid")
            if not lecture_uuid:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to get lecture UUID from created record",
                )
            
            # Convert UUID back to integer ID for foreign key
            lecture_int_id_for_content = await IDConverter.uuid_to_int(db, "lecture", lecture_uuid)
            if not lecture_int_id_for_content:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to convert lecture UUID to integer ID: {lecture_uuid}",
                )

            # 11. Create lecture content record (PDF metadata)
            lecture_content_data = {
                "lecture_id": lecture_int_id_for_content,  # Use integer ID
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

            # 12. Use UUID for response (already in lecture_record['id'] after db.create_record conversion)
            lecture_id = lecture_record.get("id") or lecture_record.get("uuid")

            # 13. Return lecture information (include token management metadata)
            result = {
                "lecture_id": lecture_id if isinstance(lecture_id, str) else str(lecture_id),
                "title": lecture_title,
                "description": lecture_description,
                "status": "GENERATED",
                "pdf_storage_path": storage_path,
                "pdf_filename": pdf_filename,
                "content_length": len(generated_content),
                "pdf_size": len(pdf_bytes),
                "created_at": lecture_record["created_at"],
                "token_management": content_metadata,  # Include token management info
            }

            logger.info(
                f"✅ Lecture generation completed successfully: {result['lecture_id']}"
            )
            return result

        except HTTPException:
            raise
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Error in lecture generation workflow: {str(e)}")
            logger.error(f"Traceback: {error_traceback}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate lecture: {str(e)}",
            )

    @staticmethod
    def generate_unique_versioned_title(
        db,
        base_title: str,
        teacher_id: str,
        course_id: str,
        university_id: str,
    ) -> str:
        """
        Generate a unique versioned title for a lecture when a duplicate exists.
        
        If "My Lecture" exists, returns "My Lecture (1)".
        If "My Lecture (1)" also exists, returns "My Lecture (2)", etc.
        
        Args:
            db: Database instance
            base_title: The original title that has a duplicate
            teacher_id: Teacher ID
            course_id: Course ID
            university_id: University ID for storage path
            
        Returns:
            A unique versioned title string
        """
        import re
        
        # Extract base title without any existing version number
        # Match patterns like "Title (1)", "Title (2)", etc.
        version_pattern = r'^(.+?)\s*\((\d+)\)\s*$'
        match = re.match(version_pattern, base_title)
        
        if match:
            # Title already has a version number, use the base part
            clean_base_title = match.group(1).strip()
        else:
            clean_base_title = base_title.strip()
        
        # Find all existing versions of this title
        version = 1
        max_attempts = 100  # Prevent infinite loop
        
        while version <= max_attempts:
            # Generate candidate title
            candidate_title = f"{clean_base_title} ({version})"
            sanitized_title = LectureService.sanitize_filename(candidate_title)
            pdf_filename = f"{sanitized_title}.pdf"
            expected_storage_path = f"university_{university_id}/teacher_{teacher_id}/course_{course_id}/generated_lectures/{pdf_filename}"
            
            # Check if this storage path already exists
            lecture_contents = db.get_records(
                "lecture_content", {"storage_path": expected_storage_path}
            )
            
            if not lecture_contents:
                # This version is available!
                logger.info(f"Generated unique versioned title: '{candidate_title}'")
                return candidate_title
            
            version += 1
        
        # Fallback: add timestamp to ensure uniqueness
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        fallback_title = f"{clean_base_title} ({timestamp})"
        logger.warning(f"Exceeded max version attempts, using timestamp fallback: '{fallback_title}'")
        return fallback_title

    @staticmethod
    async def check_for_duplicate_lecture(
        db,
        teacher_id: str,
        course_id,  # Can be int or str (UUID)
        semester_id,  # Can be int or str (UUID)
        title: str,
        document_id = None,  # Can be int or str (UUID)
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
            # teacher_id might be string (UUID or integer string) or integer, convert if needed
            teacher_int_id = teacher_id
            if isinstance(teacher_id, str):
                if teacher_id.isdigit():
                    # It's a string representation of an integer
                    teacher_int_id = int(teacher_id)
                else:
                    # It's a UUID, convert to integer
                    teacher_int_id = await IDConverter.uuid_to_int(db, "teacher", teacher_id)
                    if not teacher_int_id:
                        logger.warning(f"Teacher not found: {teacher_id}")
                        return {
                            "has_duplicate": False,
                            "duplicate_lecture": None,
                            "message": "No duplicate found",
                        }
            
            teacher_data = db.get_record_by_id("teacher", teacher_int_id)
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
            expected_storage_path = f"university_{university_id}/teacher_{teacher_int_id}/course_{course_id}/generated_lectures/{pdf_filename}"

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
                
                # Convert IDs to integers for database query
                doc_id_int = document_id
                if isinstance(document_id, str):
                    if IDConverter.is_uuid(document_id):
                        doc_id_int = await IDConverter.uuid_to_int(db, "documents", document_id)
                        if not doc_id_int:
                            logger.warning(f"Document not found: {document_id}")
                            doc_id_int = None
                    else:
                        try:
                            doc_id_int = int(document_id)
                        except ValueError:
                            logger.warning(f"Invalid document_id format: {document_id}")
                            doc_id_int = None
                elif not isinstance(document_id, int):
                    try:
                        doc_id_int = int(document_id)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid document_id format: {document_id}")
                        doc_id_int = None
                
                course_id_int = course_id
                if isinstance(course_id, str):
                    if IDConverter.is_uuid(course_id):
                        course_id_int = await IDConverter.uuid_to_int(db, "course", course_id)
                        if not course_id_int:
                            logger.warning(f"Course not found: {course_id}")
                            course_id_int = None
                    else:
                        try:
                            course_id_int = int(course_id)
                        except ValueError:
                            logger.warning(f"Invalid course_id format: {course_id}")
                            course_id_int = None
                elif not isinstance(course_id, int):
                    try:
                        course_id_int = int(course_id)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid course_id format: {course_id}")
                        course_id_int = None
                
                semester_id_int = semester_id
                if isinstance(semester_id, str):
                    if IDConverter.is_uuid(semester_id):
                        semester_id_int = await IDConverter.uuid_to_int(db, "semester", semester_id)
                        if not semester_id_int:
                            logger.warning(f"Semester not found: {semester_id}")
                            semester_id_int = None
                    else:
                        try:
                            semester_id_int = int(semester_id)
                        except ValueError:
                            logger.warning(f"Invalid semester_id format: {semester_id}")
                            semester_id_int = None
                elif not isinstance(semester_id, int):
                    try:
                        semester_id_int = int(semester_id)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid semester_id format: {semester_id}")
                        semester_id_int = None
                
                # Check if a lecture already exists with this document_id + course_id + semester_id combination
                # Using admin_client to query with multiple filters (only if all IDs are valid)
                if doc_id_int and course_id_int and semester_id_int:
                    try:
                        response = db.admin_client.table("lecture").select("*").eq(
                            "document_id", doc_id_int
                        ).eq(
                            "course_id", course_id_int
                        ).eq(
                            "semester_id", semester_id_int
                        ).execute()
                        
                        if response.data and len(response.data) > 0:
                            duplicate_lecture = response.data[0]
                            duplicate_reason = "A lecture has already been generated from this document for this course and semester"
                            logger.info(f"Found document-based duplicate. Lecture ID: {duplicate_lecture['id']}")
                    except Exception as query_error:
                        logger.warning(f"Error querying for document-based duplicate: {query_error}")
                else:
                    logger.warning(f"Skipping document-based duplicate check due to invalid IDs")

            # ========== If no duplicate found, return success ==========
            if not duplicate_lecture:
                logger.info("No duplicate found - lecture can be created")
                return {
                    "has_duplicate": False,
                    "duplicate_lecture": None,
                    "message": "No duplicate found",
                    "suggested_title": None,
                }

            # ========== Duplicate found! Generate a unique versioned title ==========
            suggested_title = LectureService.generate_unique_versioned_title(
                db=db,
                base_title=title,
                teacher_id=teacher_int_id,
                course_id=course_id,
                university_id=university_id,
            )
            
            lecture_id = duplicate_lecture["id"]
            # lecture_id from database is already an integer, so use it directly
            lecture_int_id = lecture_id if isinstance(lecture_id, int) else lecture_id
            
            # Convert lecture integer ID to UUID for response
            lecture_uuid = await IDConverter.int_to_uuid(db, "lecture", lecture_int_id)
            
            # Get lecture content for download URL
            lecture_contents = db.get_records("lecture_content", {"lecture_id": lecture_int_id})
            
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
                "lecture_id": lecture_uuid if lecture_uuid else str(lecture_int_id),
                "title": duplicate_lecture["title"],
                "description": duplicate_lecture.get("description"),
                "learning_outcomes": duplicate_lecture.get("learning_outcomes"),
                "status": duplicate_lecture["status"],
                "created_at": duplicate_lecture["created_at"],
                "download_url": download_url,
                "file_name": file_name,
                "file_size": file_size,
                "lecture_content": duplicate_lecture.get("content"),
            }

            logger.info(
                f"Duplicate found: Lecture '{duplicate_lecture['title']}' - "
                f"Reason: {duplicate_reason} - Suggested new title: '{suggested_title}'"
            )

            # Return with suggested_title so frontend can proceed with versioned name
            return {
                "has_duplicate": True,
                "duplicate_lecture": duplicate_info,
                "message": f"{duplicate_reason}. You can create a new version as '{suggested_title}'.",
                "suggested_title": suggested_title,
            }

        except Exception as e:
            logger.error(f"Error checking for duplicate lecture: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to check for duplicates: {str(e)}",
            )

    @staticmethod
    async def get_lecture_download_url(
        db,
        lecture_id: str,
        teacher_id: str | None = None,
    ) -> str:
        """
        Get download URL for a generated lecture PDF.

        Args:
            db: Database instance
            lecture_id: Lecture ID (UUID string or integer)
            teacher_id: Teacher ID (for authorization)

        Returns:
            Public download URL for the PDF
        """
        try:
            logger.info(f"Fetching download URL for lecture: {lecture_id}")

            # Convert UUID to integer ID if needed
            lecture_int_id = lecture_id
            if isinstance(lecture_id, str):
                if IDConverter.is_uuid(lecture_id):
                    lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", lecture_id)
                    if not lecture_int_id:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Lecture not found",
                        )
                else:
                    try:
                        lecture_int_id = int(lecture_id)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid lecture_id format",
                        )

            # 1. Fetch lecture record
            lecture_data = db.get_record_by_id("lecture", lecture_int_id)
            if not lecture_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )

            # Verify lecture belongs to teacher if teacher_id is provided
            if teacher_id is not None:
                # Convert teacher_id to integer if needed
                teacher_int_id = teacher_id
                if isinstance(teacher_id, str):
                    if IDConverter.is_uuid(teacher_id):
                        teacher_int_id = await IDConverter.uuid_to_int(db, "teacher", teacher_id)
                    else:
                        try:
                            teacher_int_id = int(teacher_id)
                        except ValueError:
                            teacher_int_id = None
                
                if teacher_int_id and lecture_data.get("teacher_id") != teacher_int_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied to this lecture",
                    )

            # 2. Fetch lecture content records using integer ID
            lecture_contents = db.get_records(
                "lecture_content", {"lecture_id": lecture_int_id}
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

    @staticmethod
    async def generate_lecture_plan(
        db,
        lecture_id: str,
        teacher_id: str,
    ) -> dict:
        """
        Generate a comprehensive teaching plan for an existing lecture.
        
        This method generates a detailed plan including activities, quizzes,
        discussion questions, time allocations, and pedagogical strategies.
        
        Args:
            db: Database instance
            lecture_id: ID of the lecture
            teacher_id: Teacher ID (for authorization)
            
        Returns:
            Dictionary with lecture plan data
        """
        try:
            logger.info(f"Generating lecture plan for lecture: {lecture_id}")

            # 1. Fetch lecture record
            lecture_data = db.get_record_by_id("lecture", lecture_id)
            if not lecture_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )

            # 2. Verify lecture belongs to teacher
            if lecture_data.get("teacher_id") != teacher_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this lecture",
                )

            # 3. Get lecture content
            lecture_content = lecture_data.get("content")
            if not lecture_content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Lecture has no content. Please generate the lecture first.",
                )

            # 4. Generate the lecture plan using LecturePlanningService
            from services.lecture_planning_service import LecturePlanningService

            logger.info(f"Calling LecturePlanningService for lecture: {lecture_data.get('title')}")
            
            plan_data = await LecturePlanningService.generate_lecture_plan(
                lecture_content=lecture_content,
                lecture_title=lecture_data.get("title", "Untitled"),
                lecture_description=lecture_data.get("description"),
                learning_outcomes=lecture_data.get("learning_outcomes"),
            )

            # 5. Save the plan to the lecture record
            lecture_plan_json = json.dumps(plan_data)
            db.update_record(
                "lecture",
                lecture_id,
                {
                    "lecture_plan": lecture_plan_json,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )

            logger.info(f"✅ Lecture plan generated and saved for lecture: {lecture_id}")

            return {
                "lecture_id": lecture_id,
                "lecture_title": lecture_data.get("title"),
                "plan": plan_data,
                "message": "Lecture plan generated successfully",
                "created_at": datetime.utcnow().isoformat(),
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating lecture plan: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate lecture plan: {str(e)}",
            )

    @staticmethod
    async def modify_lecture(
        db,
        lecture_id: str,
        teacher_id: str,
        title: str = None,
        description: str = None,
        learning_outcomes: str = None,
        content: str = None,
        topic: str = None,
        lecture_number: int = None,
        regenerate_pdf: bool = False,
    ) -> dict:
        """
        Modify an existing generated lecture.
        
        Allows teachers to update lecture metadata and content.
        If content is changed or regenerate_pdf is True, a new PDF will be generated.
        
        Args:
            db: Database instance
            lecture_id: ID of the lecture to modify
            teacher_id: Teacher ID (for authorization)
            title: New title (optional)
            description: New description (optional)
            learning_outcomes: New learning outcomes (optional)
            content: New lecture content (optional, triggers PDF regeneration)
            topic: New topic for grouping (optional)
            lecture_number: New lecture number within topic (optional)
            regenerate_pdf: Force PDF regeneration even if content unchanged
            
        Returns:
            Dictionary with updated lecture information
        """
        try:
            logger.info(f"Modifying lecture: {lecture_id}")

            # 1. Fetch lecture record
            lecture_data = db.get_record_by_id("lecture", lecture_id)
            if not lecture_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lecture not found",
                )

            # 2. Verify lecture belongs to teacher
            if lecture_data.get("teacher_id") != teacher_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this lecture",
                )

            # 3. Build update data
            update_data = {
                "updated_at": datetime.utcnow().isoformat(),
                "version": lecture_data.get("version", 1) + 1,
            }

            # Track what was changed
            changes = []

            if title is not None and title != lecture_data.get("title"):
                update_data["title"] = title
                changes.append("title")

            if description is not None and description != lecture_data.get("description"):
                update_data["description"] = description
                changes.append("description")

            if learning_outcomes is not None and learning_outcomes != lecture_data.get("learning_outcomes"):
                update_data["learning_outcomes"] = learning_outcomes
                changes.append("learning_outcomes")

            if content is not None and content != lecture_data.get("content"):
                update_data["content"] = content
                changes.append("content")

            if topic is not None and topic != lecture_data.get("topic"):
                update_data["topic"] = topic
                changes.append("topic")

            if lecture_number is not None and lecture_number != lecture_data.get("lecture_number"):
                update_data["lecture_number"] = lecture_number
                changes.append("lecture_number")

            # 4. Update lecture record
            db.update_record("lecture", lecture_id, update_data)
            logger.info(f"Updated lecture fields: {changes}")

            # 5. Regenerate PDF if content changed or explicitly requested
            pdf_regenerated = False
            pdf_storage_path = None

            should_regenerate = regenerate_pdf or "content" in changes or "title" in changes

            if should_regenerate:
                logger.info(f"Regenerating PDF for lecture: {lecture_id}")

                # Get the final content (either new or existing)
                final_content = content if content is not None else lecture_data.get("content")
                final_title = title if title is not None else lecture_data.get("title")

                # Create new PDF
                pdf_bytes = LectureService.create_pdf(final_title, final_content)

                # Convert UUID to integer ID if needed for filter
                lecture_int_id = lecture_id
                if IDConverter.is_uuid(str(lecture_id)):
                    lecture_int_id = await IDConverter.uuid_to_int(db, "lecture", str(lecture_id))
                    if not lecture_int_id:
                        lecture_int_id = lecture_id  # Fallback
                elif isinstance(lecture_id, int):
                    lecture_int_id = lecture_id

                # Get storage info from existing lecture content
                lecture_contents = db.get_records("lecture_content", {"lecture_id": lecture_int_id})
                
                if lecture_contents:
                    old_pdf_content = lecture_contents[0]
                    storage_bucket = old_pdf_content["storage_bucket"]
                    old_storage_path = old_pdf_content["storage_path"]

                    # Delete old PDF from storage
                    try:
                        supabase.delete_file(storage_bucket, old_storage_path)
                        logger.info(f"Deleted old PDF: {old_storage_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete old PDF: {e}")

                    # Generate new storage path with updated title
                    sanitized_title = LectureService.sanitize_filename(final_title)
                    pdf_filename = f"{sanitized_title}.pdf"
                    
                    # Extract path components from old storage path
                    # Format: university_{id}/teacher_{id}/course_{id}/generated_lectures/{filename}
                    path_parts = old_storage_path.rsplit("/", 1)
                    base_path = path_parts[0] if len(path_parts) > 1 else ""
                    new_storage_path = f"{base_path}/{pdf_filename}"

                    # Upload new PDF
                    bucket = supabase.get_storage_bucket(storage_bucket)
                    bucket.upload(
                        new_storage_path,
                        pdf_bytes,
                        {"content-type": "application/pdf"}
                    )
                    logger.info(f"Uploaded new PDF: {new_storage_path}")

                    # Update lecture content record
                    db.update_record(
                        "lecture_content",
                        old_pdf_content["id"],
                        {
                            "file_name": pdf_filename,
                            "file_size": len(pdf_bytes),
                            "storage_path": new_storage_path,
                        }
                    )

                    pdf_regenerated = True
                    pdf_storage_path = new_storage_path
                else:
                    logger.warning(f"No existing PDF found for lecture: {lecture_id}")

            # 6. Fetch updated lecture data
            updated_lecture = db.get_record_by_id("lecture", lecture_id)

            # Build message
            if not changes and not pdf_regenerated:
                message = "No changes were made to the lecture."
            else:
                change_parts = []
                if changes:
                    change_parts.append(f"Updated: {', '.join(changes)}")
                if pdf_regenerated:
                    change_parts.append("PDF regenerated")
                message = "Lecture modified successfully. " + ". ".join(change_parts) + "."

            logger.info(f"✅ Lecture modification completed: {lecture_id}")

            return {
                "lecture_id": lecture_id,
                "title": updated_lecture.get("title"),
                "description": updated_lecture.get("description"),
                "learning_outcomes": updated_lecture.get("learning_outcomes"),
                "status": updated_lecture.get("status"),
                "version": updated_lecture.get("version"),
                "pdf_regenerated": pdf_regenerated,
                "pdf_storage_path": pdf_storage_path,
                "updated_at": updated_lecture.get("updated_at"),
                "message": message,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error modifying lecture: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to modify lecture: {str(e)}",
            )
