"""
Prompt Library for LLM-based PDF Parser - v2.0

Comprehensive library with prompts for 27+ book types covering:
- Medical textbooks (Physiology, Anatomy, Pharmacology, Pathology, etc.)
- Law textbooks
- Technical/CS books

How it works:
1. Fingerprint functions detect book type from first ~35 pages of text
2. If matched, return a specialized prompt
3. If no match, return the generalized fallback prompt
"""

from typing import Dict, List, Tuple
import re


# ==============================================================================
# SPECIALIZED PROMPTS
# ==============================================================================

MEDICAL_PHYSIOLOGY_PRACTICAL_PROMPT = """Analyze this MEDICAL TEXTBOOK's Table of Contents.

This book uses a SPECIFIC structure:
- SECTION ONE, SECTION TWO, etc. (major divisions)
- Under each Section: Chapters numbered as "1-1", "1-2", "2-1", "2-2" etc.

EXAMPLE:
SECTION ONE: HEMATOLOGY
  1-1 The Compound Microscope.........1
  1-2 Hemocytometry: WBC Count.......15

YOUR TASK:
1. Extract ALL sections with their full titles
2. Extract ALL chapters (1-1, 1-2, 2-1, etc.) with page numbers
3. Calculate page_offset = (PDF page of first chapter) - (book page of first chapter)

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters (X-Y format)",
  "page_offset": 15,
  "offset_explanation": "Chapter 1-1 on book page 1 is on PDF page 16, offset = 15",
  "structure": [
    {
      "type": "section", "number": "1", "title": "SECTION ONE: HEMATOLOGY", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1-1", "title": "The Compound Microscope", "book_page": 1, "children": []},
        {"type": "chapter", "number": "1-2", "title": "Hemocytometry", "book_page": 15, "children": []}
      ]
    }
  ]
}

IMPORTANT: Extract EVERY chapter. Do not skip any.

TEXT FROM PDF:
"""

GRAYS_ANATOMY_PROMPT = """Analyze this ANATOMY TEXTBOOK's Table of Contents.

Gray's Anatomy uses:
- SECTION 1, SECTION 2, etc. (body regions/systems)
- Under each Section: multiple chapters numbered 1, 2, 3...
- Very large book (2000+ pages, 70+ chapters)

YOUR TASK:
1. Extract ALL sections (there are ~9 sections)
2. Extract ALL chapters (there are 80+ chapters)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 28,
  "structure": [
    {
      "type": "section", "number": "1", "title": "CELLS, TISSUES AND SYSTEMS", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Basic structure and function of cells", "book_page": 1, "children": []},
        {"type": "chapter", "number": "2", "title": "Integrating cells into tissues", "book_page": 35, "children": []}
      ]
    }
  ]
}

CRITICAL: Extract EVERY chapter - there are 80+ chapters.

TEXT FROM PDF:
"""

GANONG_MEDICAL_PROMPT = """Analyze this MEDICAL REVIEW TEXTBOOK's Table of Contents.

Ganong's Review of Medical Physiology uses:
- SECTION I, SECTION II, etc. (Roman numerals)
- Under each Section: Chapter 1, Chapter 2, etc.
- Total of 37+ chapters across ~7 sections

YOUR TASK:
1. Extract ALL sections (~7 sections)
2. Extract ALL chapters under each section (~39 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 20,
  "structure": [
    {
      "type": "section", "number": "I", "title": "CELLULAR & MOLECULAR BASIS", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "General Principles", "book_page": 1, "children": []},
        {"type": "chapter", "number": "2", "title": "Overview of Cellular Physiology", "book_page": 35, "children": []}
      ]
    }
  ]
}

IMPORTANT: Extract ALL 39 chapters!

TEXT FROM PDF:
"""

MACHINE_LEARNING_PROMPT = """Analyze this TECHNICAL/ML TEXTBOOK's Table of Contents.

This book uses:
- Part I, Part II (Roman numerals)
- Under each Part: Chapter 1, Chapter 2, etc.

YOUR TASK:
1. Extract ALL Parts with their titles
2. Extract ALL Chapters under each Part with page numbers
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 25,
  "structure": [
    {
      "type": "part", "number": "I", "title": "The Fundamentals of Machine Learning", "book_page": 3,
      "children": [
        {"type": "chapter", "number": "1", "title": "The Machine Learning Landscape", "book_page": 3, "children": []},
        {"type": "chapter", "number": "2", "title": "End-to-End ML Project", "book_page": 35, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

GUYTON_HALL_PROMPT = """Analyze this MEDICAL PHYSIOLOGY TEXTBOOK's Table of Contents.

Guyton and Hall uses:
- UNIT I, UNIT II, UNIT III, etc. (major divisions)
- Under each Unit: Chapter 1, Chapter 2, etc.
- Total of ~85 chapters across ~15 units

YOUR TASK:
1. Extract ALL units (~15 units)
2. Extract ALL chapters under each unit (~85 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Units > Chapters",
  "page_offset": 20,
  "structure": [
    {
      "type": "unit", "number": "I", "title": "Introduction to Physiology", "book_page": 3,
      "children": [
        {"type": "chapter", "number": "1", "title": "Functional Organization", "book_page": 3, "children": []},
        {"type": "chapter", "number": "2", "title": "The Cell and Its Functions", "book_page": 15, "children": []}
      ]
    }
  ]
}

IMPORTANT: Extract ALL 85 chapters across all units!

TEXT FROM PDF:
"""

HARPERS_BIOCHEMISTRY_PROMPT = """Analyze this BIOCHEMISTRY TEXTBOOK's Table of Contents.

Harper's Illustrated Biochemistry uses:
- SECTION I, SECTION II, etc. (Roman numerals, ~11 sections)
- Under each Section: Chapter 1, Chapter 2, etc.
- Total of ~58 chapters

YOUR TASK:
1. Extract ALL sections (~11 sections)
2. Extract ALL chapters (~58 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 15,
  "structure": [
    {
      "type": "section", "number": "I", "title": "Structures & Functions of Proteins", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Biochemistry & Medicine", "book_page": 1, "children": []},
        {"type": "chapter", "number": "2", "title": "Water & pH", "book_page": 6, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

RANG_DALE_PHARMACOLOGY_PROMPT = """Analyze this PHARMACOLOGY TEXTBOOK's Table of Contents.

Rang & Dale's Pharmacology uses:
- SECTION 1, SECTION 2, etc.
- Under each Section: Chapter 1, Chapter 2, etc.
- Total of ~55 chapters across multiple sections

YOUR TASK:
1. Extract ALL sections
2. Extract ALL chapters (~55 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 15,
  "structure": [
    {
      "type": "section", "number": "1", "title": "GENERAL PRINCIPLES", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "What is pharmacology?", "book_page": 1, "children": []},
        {"type": "chapter", "number": "2", "title": "How drugs act", "book_page": 10, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

KATZUNG_PHARMACOLOGY_PROMPT = """Analyze this PHARMACOLOGY TEXTBOOK's Table of Contents.

Katzung's Pharmacology uses:
- Part I, Part II, etc. (Roman numerals)
- Under each Part: Chapter 1, Chapter 2, etc.
- ~61 chapters across ~10 parts

YOUR TASK:
1. Extract ALL parts (~10 parts)
2. Extract ALL chapters (~61 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 10,
  "structure": [
    {
      "type": "part", "number": "I", "title": "BASIC PRINCIPLES", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Introduction", "book_page": 1, "children": []},
        {"type": "chapter", "number": "2", "title": "Pharmacodynamics", "book_page": 10, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

# Simple chapter-only prompts for various books
SIMPLE_CHAPTERS_PROMPT = """Analyze this TEXTBOOK's Table of Contents.

This book uses simple chapter structure (no parts/sections):
- Chapter 1, Chapter 2, etc.

YOUR TASK:
1. Extract ALL chapters with page numbers
2. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Chapters only",
  "page_offset": 10,
  "structure": [
    {"type": "chapter", "number": "1", "title": "Chapter Title", "book_page": 1, "children": []},
    {"type": "chapter", "number": "2", "title": "Chapter Title", "book_page": 25, "children": []}
  ]
}

TEXT FROM PDF:
"""

PARTS_CHAPTERS_PROMPT = """Analyze this TEXTBOOK's Table of Contents.

This book uses Parts > Chapters structure:
- Part I, Part II, etc. (major divisions)
- Under each Part: Chapter 1, Chapter 2, etc.

YOUR TASK:
1. Extract ALL parts
2. Extract ALL chapters under each part
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 10,
  "structure": [
    {
      "type": "part", "number": "I", "title": "Part Title", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Chapter Title", "book_page": 3, "children": []},
        {"type": "chapter", "number": "2", "title": "Chapter Title", "book_page": 19, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

SECTIONS_CHAPTERS_PROMPT = """Analyze this TEXTBOOK's Table of Contents.

This book uses Sections > Chapters structure:
- Section I, Section II, etc. (major divisions)
- Under each Section: Chapter 1, Chapter 2, etc.

YOUR TASK:
1. Extract ALL sections
2. Extract ALL chapters under each section
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 15,
  "structure": [
    {
      "type": "section", "number": "I", "title": "Section Title", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Chapter Title", "book_page": 1, "children": []},
        {"type": "chapter", "number": "2", "title": "Chapter Title", "book_page": 35, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

NETTERS_FLASH_CARDS_PROMPT = """Analyze this PHYSIOLOGY FLASH CARDS book's Table of Contents.

Netter's Physiology Flash Cards uses:
- SECTION 1, SECTION 2, etc.
- Under each Section: cards numbered as "1-1", "1-2", "2-1", etc.
- ~7 sections, 200+ cards

YOUR TASK:
1. Extract ALL sections (~7 sections)
2. Extract chapter/card entries with X-Y numbering
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters (X-Y format)",
  "page_offset": 10,
  "structure": [
    {
      "type": "section", "number": "1", "title": "Cell Physiology", "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1-1", "title": "Membrane Proteins", "book_page": 1, "children": []},
        {"type": "chapter", "number": "1-2", "title": "Body Fluid Compartments", "book_page": 3, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

K_PARK_PREVENTIVE_MED_PROMPT = """Analyze this PREVENTIVE MEDICINE TEXTBOOK's Table of Contents.

K Park's Textbook uses major topic divisions (not numbered parts):
- Multiple chapters under each topic
- 30+ chapters covering public health topics

YOUR TASK:
1. Identify major topic divisions
2. Extract ALL chapters with page numbers
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Topics > Chapters",
  "page_offset": 15,
  "structure": [
    {
      "type": "topic", "number": "", "title": "EPIDEMIOLOGY OF COMMUNICABLE DISEASES", "book_page": 100,
      "children": [
        {"type": "chapter", "number": "", "title": "Respiratory Infections", "book_page": 100, "children": []},
        {"type": "chapter", "number": "", "title": "Intestinal Infections", "book_page": 150, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

LAW_TEXTBOOK_PROMPT = """Analyze this LAW TEXTBOOK's Table of Contents.

This law book uses simple chapter structure:
- Chapter 1, Chapter 2, etc. (no parts)
- May include Table of Cases, Table of Statutes

YOUR TASK:
1. Extract ALL chapters with page numbers
2. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Chapters only",
  "page_offset": 10,
  "structure": [
    {"type": "chapter", "number": "1", "title": "Law and society", "book_page": 1, "children": []},
    {"type": "chapter", "number": "2", "title": "Law and morality", "book_page": 26, "children": []}
  ]
}

TEXT FROM PDF:
"""

# ==============================================================================
# GENERALIZED FALLBACK PROMPT
# ==============================================================================

GENERALIZED_PROMPT = """Analyze this book's Table of Contents and extract its COMPLETE structure.

IMPORTANT: Books have DIFFERENT structures. Examples:
- Textbook: "Part I > Chapter 1 > Section 1.1"
- Medical book: "SECTION ONE > Chapter 1" or "Unit I > Chapter 1"
- Simple: "Chapter 1: Title" (no divisions)

YOUR TASK:
1. Identify what hierarchy this book uses
2. Extract ALL main divisions (Parts/Sections/Units if present)
3. Extract ALL chapters with page numbers
4. Calculate page_offset (PDF page of first content - book page of first content)

CRITICAL RULES:
1. Extract EVERY chapter - do not skip any
2. For books with Parts/Sections/Units, include them AND all chapters within
3. Keep titles short (max 50 chars)
4. page_offset = (PDF page where chapter starts) - (book page shown in TOC)

Return ONLY a JSON object (no markdown):

{
  "structure_type": "Parts > Chapters" or "Sections > Chapters" or "Chapters only",
  "page_offset": 15,
  "offset_explanation": "Chapter 1 on book page 1 is PDF page 16, offset = 15",
  "structure": [
    {
      "type": "part/section/unit/chapter",
      "number": "1 or I or 1-1",
      "title": "Title Here (max 50 chars)",
      "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Chapter Title", "book_page": 5, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""


# ==============================================================================
# FINGERPRINT FUNCTIONS
# ==============================================================================

def is_medical_physiology_practical(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    patterns = [
        "practical physiology" in text_lower,
        "section one" in text_lower and re.search(r'\b\d-\d\b', text),
        "hematology" in text_lower and "hemocytometry" in text_lower,
    ]
    return sum(bool(p) for p in patterns) >= 2

def is_grays_anatomy(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("gray's anatomy" in text_lower or "grays anatomy" in text_lower or
            ("anatomy" in text_lower and meta.get("total_pages", 0) > 2000))

def is_ganong_review(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "ganong" in text_lower or "review of medical physiology" in text_lower

def is_guyton_hall(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("guyton" in text_lower and "hall" in text_lower) or \
           ("unit i" in text_lower and "physiology" in text_lower and meta.get("total_pages", 0) > 900)

def is_harpers_biochemistry(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "harper" in text_lower and "biochemistry" in text_lower

def is_rang_dale_pharmacology(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("rang" in text_lower and "dale" in text_lower) or \
           ("pharmacology" in text_lower and "general principles" in text_lower and meta.get("total_pages", 0) > 700)

def is_katzung_pharmacology(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "katzung" in text_lower or \
           ("pharmacology" in text_lower and "board review" in text_lower)

def is_brs_physiology(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("brs" in text_lower and "physiology" in text_lower) or \
           ("board review series" in text_lower and "physiology" in text_lower)

def is_robbins_pathology(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "robbins" in text_lower and ("pathology" in text_lower or "kumar" in text_lower)

def is_langman_embryology(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "langman" in text_lower and "embryology" in text_lower

def is_wheaters_histology(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "wheater" in text_lower and "histology" in text_lower

def is_snell_anatomy(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "snell" in text_lower and "anatomy" in text_lower

def is_vishram_singh_anatomy(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "vishram singh" in text_lower or \
           ("anatomy" in text_lower and ("abdomen" in text_lower or "lower limb" in text_lower) and "section i" in text_lower)

def is_k_park_preventive(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("park" in text_lower and "preventive" in text_lower) or \
           ("social medicine" in text_lower and "epidemiology" in text_lower)

def is_netters_flash_cards(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("netter" in text_lower and "flash" in text_lower) or \
           ("netter" in text_lower and "physiology" in text_lower)

def is_medical_physiology_boron(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("boron" in text_lower and "physiology" in text_lower) or \
           ("medical physiology" in text_lower and meta.get("total_pages", 0) > 3000)

def is_urinary_incontinence_book(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "urinary incontinence" in text_lower and "part i" in text_lower

def is_machine_learning_book(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("machine learning" in text_lower or "scikit-learn" in text_lower or
            "tensorflow" in text_lower or "keras" in text_lower) and \
           bool(re.search(r'Part\s+I[I]*\.?\s+', text))

def is_law_vsi(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return "very short introduction" in text_lower and "law" in text_lower

def is_law_textbook(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    patterns = [
        "introduction to law" in text_lower,
        "legal rules" in text_lower,
        "table of cases" in text_lower,
        "table of statutes" in text_lower,
        "law and society" in text_lower,
    ]
    return sum(bool(p) for p in patterns) >= 2

def is_human_anatomy_atlas(text: str, meta: Dict) -> bool:
    text_lower = text.lower()
    return ("human anatomy" in text_lower and "color atlas" in text_lower) or \
           ("anatomy" in text_lower and "colour atlas" in text_lower)


# ==============================================================================
# BOOK PATTERNS REGISTRY (order matters - most specific first)
# ==============================================================================

BOOK_PATTERNS: List[Dict] = [
    # Specific medical books
    {"name": "Practical Physiology", "fingerprint": is_medical_physiology_practical, "prompt": MEDICAL_PHYSIOLOGY_PRACTICAL_PROMPT, "description": "Section > X-Y chapters"},
    {"name": "Gray's Anatomy", "fingerprint": is_grays_anatomy, "prompt": GRAYS_ANATOMY_PROMPT, "description": "Sections > Chapters (large anatomy)"},
    {"name": "Ganong's Review", "fingerprint": is_ganong_review, "prompt": GANONG_MEDICAL_PROMPT, "description": "Sections > Chapters"},
    {"name": "Guyton & Hall", "fingerprint": is_guyton_hall, "prompt": GUYTON_HALL_PROMPT, "description": "Units > Chapters"},
    {"name": "Harper's Biochemistry", "fingerprint": is_harpers_biochemistry, "prompt": HARPERS_BIOCHEMISTRY_PROMPT, "description": "Sections > Chapters"},
    {"name": "Rang & Dale Pharmacology", "fingerprint": is_rang_dale_pharmacology, "prompt": RANG_DALE_PHARMACOLOGY_PROMPT, "description": "Sections > Chapters"},
    {"name": "Katzung Pharmacology", "fingerprint": is_katzung_pharmacology, "prompt": KATZUNG_PHARMACOLOGY_PROMPT, "description": "Parts > Chapters"},
    {"name": "BRS Physiology", "fingerprint": is_brs_physiology, "prompt": SIMPLE_CHAPTERS_PROMPT, "description": "Chapters only (review)"},
    {"name": "Robbins Pathology", "fingerprint": is_robbins_pathology, "prompt": SIMPLE_CHAPTERS_PROMPT, "description": "Chapters only"},
    {"name": "Langman's Embryology", "fingerprint": is_langman_embryology, "prompt": PARTS_CHAPTERS_PROMPT, "description": "Parts > Chapters"},
    {"name": "Wheater's Histology", "fingerprint": is_wheaters_histology, "prompt": PARTS_CHAPTERS_PROMPT, "description": "Parts > Chapters"},
    {"name": "Snell's Anatomy", "fingerprint": is_snell_anatomy, "prompt": SIMPLE_CHAPTERS_PROMPT, "description": "Chapters only (regions)"},
    {"name": "Vishram Singh Anatomy", "fingerprint": is_vishram_singh_anatomy, "prompt": SECTIONS_CHAPTERS_PROMPT, "description": "Sections > Chapters"},
    {"name": "K Park's Preventive Med", "fingerprint": is_k_park_preventive, "prompt": K_PARK_PREVENTIVE_MED_PROMPT, "description": "Topics > Chapters"},
    {"name": "Netter's Flash Cards", "fingerprint": is_netters_flash_cards, "prompt": NETTERS_FLASH_CARDS_PROMPT, "description": "Sections > X-Y format"},
    {"name": "Medical Physiology (Boron)", "fingerprint": is_medical_physiology_boron, "prompt": SECTIONS_CHAPTERS_PROMPT, "description": "Sections > Chapters"},
    {"name": "Human Anatomy Atlas", "fingerprint": is_human_anatomy_atlas, "prompt": SIMPLE_CHAPTERS_PROMPT, "description": "Chapters only"},
    # Specialty medical
    {"name": "Urinary Incontinence", "fingerprint": is_urinary_incontinence_book, "prompt": PARTS_CHAPTERS_PROMPT, "description": "Parts > Chapters"},
    # Technical
    {"name": "Machine Learning/Technical", "fingerprint": is_machine_learning_book, "prompt": MACHINE_LEARNING_PROMPT, "description": "Parts > Chapters"},
    # Law
    {"name": "Law VSI", "fingerprint": is_law_vsi, "prompt": LAW_TEXTBOOK_PROMPT, "description": "Simple chapters"},
    {"name": "Law Textbook", "fingerprint": is_law_textbook, "prompt": LAW_TEXTBOOK_PROMPT, "description": "Chapters only"},
]


# ==============================================================================
# MAIN FUNCTIONS
# ==============================================================================

def get_prompt_for_book(pages_text: str, metadata: Dict = None) -> Tuple[str, str]:
    """
    Detect book type and return appropriate prompt.

    Returns:
        tuple: (prompt_template, pattern_name)
    """
    if metadata is None:
        metadata = {}

    for pattern in BOOK_PATTERNS:
        try:
            if pattern["fingerprint"](pages_text, metadata):
                return pattern["prompt"], pattern["name"]
        except Exception:
            continue

    return GENERALIZED_PROMPT, "Generalized"


def list_available_patterns() -> List[Dict]:
    """List all available book patterns."""
    return [{"name": p["name"], "description": p["description"]} for p in BOOK_PATTERNS]
