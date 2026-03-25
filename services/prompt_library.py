"""
Prompt Library for LLM-based PDF Parser - v2.0

Comprehensive library with prompts for 27+ book types covering:
- Medical textbooks (Physiology, Anatomy, Pharmacology, Pathology, etc.)
- Law textbooks
- Technical/CS books

Structure:
1. SPECIALIZED PROMPTS - Book-specific prompts
2. CATEGORY PROMPTS - Generic prompts for book categories
3. FINGERPRINT FUNCTIONS - Detection functions
4. BOOK_PATTERNS - Registry of all patterns
5. GENERALIZED FALLBACK - For unknown book types
"""

from typing import Dict, Optional, Callable, List, Tuple
import re

from logger import logger


# ==============================================================================
# SPECIALIZED PROMPTS - For specific well-known books
# ==============================================================================

# ----- ALREADY TESTED & WORKING -----

MEDICAL_PHYSIOLOGY_PRACTICAL_PROMPT = """Analyze this MEDICAL TEXTBOOK's Table of Contents.

This book uses a SPECIFIC structure:
- SECTION ONE, SECTION TWO, etc. (major divisions)
- Under each Section: Chapters numbered as "1-1", "1-2", "2-1", "2-2" etc.
  (First digit = Section number, Second = Chapter within section)

EXAMPLE from this book:
SECTION ONE: HEMATOLOGY
  1-1 The Compound Microscope.........1
  1-2 Hemocytometry: WBC Count.......15
SECTION TWO: HUMAN EXPERIMENTS
  2-1 Examination of Urine...........89

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
      "type": "section",
      "number": "1",
      "title": "SECTION ONE: HEMATOLOGY",
      "book_page": 1,
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

EXAMPLE:
SECTION 1: CELLS, TISSUES AND SYSTEMS
  1 Basic structure and function of cells.......1
  2 Integrating cells into tissues............35
SECTION 2: EMBRYOLOGY AND DEVELOPMENT
  8 Preimplantation development..............185

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
      "type": "section",
      "number": "1",
      "title": "CELLS, TISSUES AND SYSTEMS",
      "book_page": 1,
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

EXAMPLE structure:
SECTION I: CELLULAR & MOLECULAR BASIS FOR MEDICAL PHYSIOLOGY
  CHAPTER 1 General Principles & Energy Production....1
  CHAPTER 2 Overview of Cellular Physiology.........35
SECTION II: PHYSIOLOGY OF NERVE & MUSCLE CELLS
  CHAPTER 4 Excitable Tissue: Nerve................77

YOUR TASK:
1. Extract ALL sections (there are ~7 sections)
2. Extract ALL chapters under each section (~39 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 20,
  "structure": [
    {
      "type": "section",
      "number": "I",
      "title": "CELLULAR & MOLECULAR BASIS",
      "book_page": 1,
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
- Part I, Part II, etc. (Roman numerals)
- Under each Part: Chapter 1, Chapter 2, etc.

EXAMPLE structure:
Part I. The Fundamentals of Machine Learning
  1. The Machine Learning Landscape.........3
  2. End-to-End Machine Learning Project....35
Part II. Neural Networks and Deep Learning
  10. Introduction to ANNs with Keras......275

YOUR TASK:
1. Extract ALL Parts with their titles
2. Extract ALL Chapters under each Part with page numbers
3. Calculate page_offset = (PDF page of Chapter 1) - (book page of Chapter 1)

Return ONLY valid JSON:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 25,
  "structure": [
    {
      "type": "part",
      "number": "I",
      "title": "The Fundamentals of Machine Learning",
      "book_page": 3,
      "children": [
        {"type": "chapter", "number": "1", "title": "The Machine Learning Landscape", "book_page": 3, "children": []},
        {"type": "chapter", "number": "2", "title": "End-to-End Machine Learning", "book_page": 35, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

# ----- MEDICAL BOOKS -----

GUYTON_HALL_PROMPT = """Analyze this MEDICAL PHYSIOLOGY TEXTBOOK's Table of Contents.

Guyton and Hall Textbook of Medical Physiology uses:
- UNIT I, UNIT II, UNIT III, etc. (major divisions)
- Under each Unit: Chapter 1, Chapter 2, etc.
- Total of ~85 chapters across ~15 units

EXAMPLE structure:
UNIT I - Introduction to Physiology
  1. Functional Organization of the Human Body....3
  2. The Cell and Its Functions..................15
UNIT II - Membrane Physiology, Nerve, Muscle
  4. Transport of Substances....................45

YOUR TASK:
1. Extract ALL units (there are ~15 units)
2. Extract ALL chapters under each unit (~85 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Units > Chapters",
  "page_offset": 20,
  "structure": [
    {
      "type": "unit",
      "number": "I",
      "title": "Introduction to Physiology",
      "book_page": 3,
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

EXAMPLE:
SECTION I: Structures & Functions of Proteins & Enzymes
  1 Biochemistry & Medicine..........1
  2 Water & pH......................6
SECTION II: Enzymes: Kinetics
  7 Enzymes: Mechanism of Action....50

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
      "type": "section",
      "number": "I",
      "title": "Structures & Functions of Proteins",
      "book_page": 1,
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
- SECTION 1, SECTION 2, etc. (Arabic numerals or Roman)
- Under each Section: Chapter 1, Chapter 2, etc.
- Total of ~55 chapters across multiple sections

EXAMPLE:
SECTION 1: GENERAL PRINCIPLES
  1. What is pharmacology?..........1
  2. How drugs act: general principles....10
SECTION 2: CHEMICAL MEDIATORS
  15. Local hormones................150

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
      "type": "section",
      "number": "1",
      "title": "GENERAL PRINCIPLES",
      "book_page": 1,
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

Katzung's Pharmacology Examination & Board Review uses:
- Part I, Part II, etc. (with Roman numerals)
- Under each Part: Chapter 1, Chapter 2, etc.
- Total of ~61 chapters across ~10 parts

EXAMPLE:
PART I: BASIC PRINCIPLES
  1. Introduction to Autonomic Pharmacology....1
  2. Pharmacodynamics.........................10
PART II: AUTONOMIC DRUGS
  6. Introduction to Autonomic Pharmacology....47

YOUR TASK:
1. Extract ALL parts (~10 parts)
2. Extract ALL chapters (~61 total)
3. Look for Appendices at the end
4. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 10,
  "structure": [
    {
      "type": "part",
      "number": "I",
      "title": "BASIC PRINCIPLES",
      "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Introduction", "book_page": 1, "children": []},
        {"type": "chapter", "number": "2", "title": "Pharmacodynamics", "book_page": 10, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

BRS_PHYSIOLOGY_PROMPT = """Analyze this BOARD REVIEW TEXTBOOK's Table of Contents.

BRS Physiology (Board Review Series) uses:
- Simple chapter structure (no parts/sections)
- Chapter 1, Chapter 2, etc.
- ~7 chapters covering major physiology systems
- Comprehensive Examination at the end

EXAMPLE:
1. CELL PHYSIOLOGY..........1
2. NEUROPHYSIOLOGY.........31
3. CARDIOVASCULAR PHYSIOLOGY....64
Comprehensive Examination....280

YOUR TASK:
1. Extract ALL chapters (~7 chapters)
2. Include the Comprehensive Examination
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Chapters only",
  "page_offset": 10,
  "structure": [
    {"type": "chapter", "number": "1", "title": "CELL PHYSIOLOGY", "book_page": 1, "children": []},
    {"type": "chapter", "number": "2", "title": "NEUROPHYSIOLOGY", "book_page": 31, "children": []},
    {"type": "chapter", "number": "Exam", "title": "Comprehensive Examination", "book_page": 280, "children": []}
  ]
}

TEXT FROM PDF:
"""

ROBBINS_PATHOLOGY_PROMPT = """Analyze this PATHOLOGY TEXTBOOK's Table of Contents.

Robbins Basic Pathology uses:
- Simple chapter structure (Chapters only, no parts)
- Chapter 1, Chapter 2, etc.
- ~22 chapters covering pathological processes and organ systems

EXAMPLE:
1. Cell Injury, Cell Death, and Adaptations....1
2. Inflammation and Repair..................25
3. Hemodynamic Disorders...................57

YOUR TASK:
1. Extract ALL chapters (~22 chapters)
2. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Chapters only",
  "page_offset": 15,
  "structure": [
    {"type": "chapter", "number": "1", "title": "Cell Injury, Cell Death, and Adaptations", "book_page": 1, "children": []},
    {"type": "chapter", "number": "2", "title": "Inflammation and Repair", "book_page": 25, "children": []},
    {"type": "chapter", "number": "3", "title": "Hemodynamic Disorders", "book_page": 57, "children": []}
  ]
}

TEXT FROM PDF:
"""

LANGMAN_EMBRYOLOGY_PROMPT = """Analyze this EMBRYOLOGY TEXTBOOK's Table of Contents.

Langman's Medical Embryology uses:
- Part 1, Part 2, Part 3 (Three main parts)
- Under each Part: Chapter 1, Chapter 2, etc.
- ~21 chapters total

EXAMPLE:
Part 1: General Embryology
  Chapter 1 / Introduction to Molecular Regulation....3
  Chapter 2 / Gametogenesis.......................10
Part 2: Systems-Based Embryology
  Chapter 12 / Skeletal System....................133

YOUR TASK:
1. Extract ALL parts (3 parts)
2. Extract ALL chapters (~21 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 15,
  "structure": [
    {
      "type": "part",
      "number": "1",
      "title": "General Embryology",
      "book_page": 3,
      "children": [
        {"type": "chapter", "number": "1", "title": "Introduction to Molecular Regulation", "book_page": 3, "children": []},
        {"type": "chapter", "number": "2", "title": "Gametogenesis", "book_page": 10, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

WHEATERS_HISTOLOGY_PROMPT = """Analyze this HISTOLOGY TEXTBOOK's Table of Contents.

Wheater's Functional Histology uses:
- Part I, Part II, Part III (Three main parts)
- Under each Part: numbered chapters
- ~21 chapters total
- Appendices with glossary

EXAMPLE:
PART I: THE CELL
  1 Cell structure and function.........2
  2 Cell cycle and replication.........33
PART II: BASIC TISSUE TYPES
  3 Epithelial tissues................42

YOUR TASK:
1. Extract ALL parts (3 parts)
2. Extract ALL chapters (~21 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 10,
  "structure": [
    {
      "type": "part",
      "number": "I",
      "title": "THE CELL",
      "book_page": 2,
      "children": [
        {"type": "chapter", "number": "1", "title": "Cell structure and function", "book_page": 2, "children": []},
        {"type": "chapter", "number": "2", "title": "Cell cycle and replication", "book_page": 33, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

SNELL_ANATOMY_PROMPT = """Analyze this CLINICAL ANATOMY TEXTBOOK's Table of Contents.

Snell's Clinical Anatomy by Regions uses:
- Simple chapter structure (no parts)
- Chapter 1, Chapter 2, etc. (by body regions)
- ~12 chapters

EXAMPLE:
CHAPTER 1    Introduction
CHAPTER 2    The Back
CHAPTER 3    Upper Limb
CHAPTER 4    Thorax, Part I: Thoracic Wall

YOUR TASK:
1. Extract ALL chapters (~12 chapters)
2. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Chapters only",
  "page_offset": 15,
  "structure": [
    {"type": "chapter", "number": "1", "title": "Introduction", "book_page": 1, "children": []},
    {"type": "chapter", "number": "2", "title": "The Back", "book_page": 20, "children": []},
    {"type": "chapter", "number": "3", "title": "Upper Limb", "book_page": 50, "children": []}
  ]
}

TEXT FROM PDF:
"""

VISHRAM_SINGH_ANATOMY_PROMPT = """Analyze this ANATOMY TEXTBOOK's Table of Contents.

Vishram Singh's Textbook of Anatomy uses:
- Section I, Section II (Two main sections by body region)
- Under each Section: Chapter 1, Chapter 2, etc.
- ~36 chapters total

EXAMPLE:
Section I. Abdomen
  1. Introduction and overview of the abdomen....1
  2. Anterior abdominal wall....................15
Section II. Lower Limb
  21. Introduction and overview of the lower limb....200

YOUR TASK:
1. Extract ALL sections (2 sections)
2. Extract ALL chapters (~36 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 15,
  "structure": [
    {
      "type": "section",
      "number": "I",
      "title": "Abdomen",
      "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Introduction and overview", "book_page": 1, "children": []},
        {"type": "chapter", "number": "2", "title": "Anterior abdominal wall", "book_page": 15, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

K_PARK_PREVENTIVE_MED_PROMPT = """Analyze this PREVENTIVE MEDICINE TEXTBOOK's Table of Contents.

K Park's Textbook of Preventive and Social Medicine uses:
- Major topic divisions (not numbered as parts)
- Multiple chapters under each topic
- 30+ chapters covering public health topics

EXAMPLE TOC structure:
EPIDEMIOLOGY OF COMMUNICABLE DISEASES
  Respiratory Infections...............100
  Intestinal Infections................150
HEALTH PROGRAMMES IN INDIA
  National Health Programmes...........400

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
      "type": "topic",
      "number": "",
      "title": "EPIDEMIOLOGY OF COMMUNICABLE DISEASES",
      "book_page": 100,
      "children": [
        {"type": "chapter", "number": "", "title": "Respiratory Infections", "book_page": 100, "children": []},
        {"type": "chapter", "number": "", "title": "Intestinal Infections", "book_page": 150, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

NETTERS_FLASH_CARDS_PROMPT = """Analyze this PHYSIOLOGY FLASH CARDS book's Table of Contents.

Netter's Physiology Flash Cards uses:
- SECTION 1, SECTION 2, etc. (major divisions)
- Under each Section: cards numbered as "1-1", "1-2", "2-1", etc.
  (First digit = Section, Second = Card number)
- ~7 sections, 200+ cards

EXAMPLE:
SECTION 1: Cell Physiology and Fluid Homeostasis
  1-1 Membrane Proteins
  1-2 Body Fluid Compartments
SECTION 2: Neurophysiology
  2-1 Peripheral Nervous System

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
      "type": "section",
      "number": "1",
      "title": "Cell Physiology and Fluid Homeostasis",
      "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1-1", "title": "Membrane Proteins", "book_page": 1, "children": []},
        {"type": "chapter", "number": "1-2", "title": "Body Fluid Compartments", "book_page": 3, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

MEDICAL_PHYSIOLOGY_BORON_PROMPT = """Analyze this MEDICAL PHYSIOLOGY TEXTBOOK's Table of Contents.

Medical Physiology (Boron & Boulpaep) uses:
- Section I, Section II, etc. (Roman numerals)
- Under each Section: Chapter 1, Chapter 2, etc.
- ~62 chapters across ~10 sections

EXAMPLE:
Section I: Introduction
  Chapter 1 Foundations of Physiology........1
Section II: Physiology of Cells and Molecules
  Chapter 2 Functional Organization of the Cell....15
  Chapter 3 Signal Transduction..................30

YOUR TASK:
1. Extract ALL sections (~10 sections)
2. Extract ALL chapters (~62 total)
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Sections > Chapters",
  "page_offset": 20,
  "structure": [
    {
      "type": "section",
      "number": "I",
      "title": "Introduction",
      "book_page": 1,
      "children": [
        {"type": "chapter", "number": "1", "title": "Foundations of Physiology", "book_page": 1, "children": []}
      ]
    },
    {
      "type": "section",
      "number": "II",
      "title": "Physiology of Cells and Molecules",
      "book_page": 15,
      "children": [
        {"type": "chapter", "number": "2", "title": "Functional Organization", "book_page": 15, "children": []},
        {"type": "chapter", "number": "3", "title": "Signal Transduction", "book_page": 30, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

# ----- URINARY INCONTINENCE BOOKS (Medical Specialty) -----

URINARY_INCONTINENCE_PARTS_PROMPT = """Analyze this MEDICAL SPECIALTY TEXTBOOK's Table of Contents.

This Urinary Incontinence textbook uses:
- Part I, Part II, etc. (major divisions)
- Under each Part: Chapter 1, Chapter 2, etc.

EXAMPLE:
Part I: Diagnosis and Etiology
  1 Epidemiology, Definitions...........3
  2 Anatomy and Physiology.............19
Part II: Treatment
  5 Conservative Treatment.............80

YOUR TASK:
1. Extract ALL parts
2. Extract ALL chapters with page numbers
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Parts > Chapters",
  "page_offset": 10,
  "structure": [
    {
      "type": "part",
      "number": "I",
      "title": "Diagnosis and Etiology",
      "book_page": 3,
      "children": [
        {"type": "chapter", "number": "1", "title": "Epidemiology, Definitions", "book_page": 3, "children": []},
        {"type": "chapter", "number": "2", "title": "Anatomy and Physiology", "book_page": 19, "children": []}
      ]
    }
  ]
}

TEXT FROM PDF:
"""

# ----- LAW BOOKS -----

ETHICS_FOR_LAWYERS_PROMPT = """Analyze this ETHICS FOR LAWYERS booklet's Table of Contents.

This "Booklet on Ethics for Lawyers" uses:
- Simple numbered chapters (Chapter 1, Chapter 2, etc.) or unnumbered sections
- May have topics/sections within chapters
- Typically 15-25 chapters or sections
- Focus on legal ethics, professional conduct, rules of professional responsibility

EXAMPLE STRUCTURE:
Chapter 1: Introduction to Legal Ethics........1
Chapter 2: Conflicts of Interest.............15
Chapter 3: Client Confidentiality.............32
OR
1. Introduction to Legal Ethics..............1
2. Conflicts of Interest.....................15
3. Client Confidentiality....................32

YOUR TASK:
1. Extract ALL chapters/sections with page numbers
2. If chapters have subsections, include them as children
3. Calculate page_offset accurately
4. Keep chapter titles concise (max 60 chars)

Return ONLY valid JSON:
{
  "structure_type": "Chapters only",
  "page_offset": 8,
  "offset_explanation": "First chapter on book page 1 is on PDF page 9, offset = 8",
  "structure": [
    {"type": "chapter", "number": "1", "title": "Introduction to Legal Ethics", "book_page": 1, "children": []},
    {"type": "chapter", "number": "2", "title": "Conflicts of Interest", "book_page": 15, "children": []},
    {"type": "chapter", "number": "3", "title": "Client Confidentiality", "book_page": 32, "children": []}
  ]
}

CRITICAL: Extract EVERY chapter. Do not skip any. Look for numbered items, chapter headings, or major topic divisions.

TEXT FROM PDF:
"""

LAW_TEXTBOOK_CHAPTERS_PROMPT = """Analyze this LAW TEXTBOOK's Table of Contents.

This law book uses a simple structure:
- Chapter 1, Chapter 2, etc. (no parts)
- Some books have numbered sections within chapters (1.1, 1.2)
- May include Table of Cases, Table of Statutes

EXAMPLE:
1 Law and society..........1
2 Law and morality........26
3 Law and regulation......68

YOUR TASK:
1. Extract ALL chapters with page numbers
2. Include Table of Cases/Statutes if present
3. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Chapters only",
  "page_offset": 10,
  "structure": [
    {"type": "chapter", "number": "1", "title": "Law and society", "book_page": 1, "children": []},
    {"type": "chapter", "number": "2", "title": "Law and morality", "book_page": 26, "children": []},
    {"type": "chapter", "number": "3", "title": "Law and regulation", "book_page": 68, "children": []}
  ]
}

TEXT FROM PDF:
"""

LAW_VSI_PROMPT = """Analyze this SHORT INTRODUCTION book's Table of Contents.

This "Very Short Introduction" book uses:
- Simple numbered chapters (1, 2, 3...)
- ~6 chapters
- References, Further reading, Index at end

EXAMPLE:
1 Law's roots.........1
2 Law's branches.....36
3 Law and morality...67
References
Further reading
Index

YOUR TASK:
1. Extract ALL chapters
2. Calculate page_offset

Return ONLY valid JSON:
{
  "structure_type": "Chapters only",
  "page_offset": 7,
  "structure": [
    {"type": "chapter", "number": "1", "title": "Law's roots", "book_page": 1, "children": []},
    {"type": "chapter", "number": "2", "title": "Law's branches", "book_page": 36, "children": []},
    {"type": "chapter", "number": "3", "title": "Law and morality", "book_page": 67, "children": []}
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
    """A Textbook of Practical Physiology - Section > X-Y chapters"""
    text_lower = text.lower()
    patterns = [
        "practical physiology" in text_lower,
        "section one" in text_lower and re.search(r'\b\d-\d\b', text),
        "hematology" in text_lower and "hemocytometry" in text_lower,
    ]
    return sum(bool(p) for p in patterns) >= 2


def is_grays_anatomy(text: str, meta: Dict) -> bool:
    """Gray's Anatomy"""
    text_lower = text.lower()
    return ("gray's anatomy" in text_lower or "grays anatomy" in text_lower or
            ("anatomy" in text_lower and meta.get("total_pages", 0) > 2000))


def is_ganong_review(text: str, meta: Dict) -> bool:
    """Ganong's Review of Medical Physiology"""
    text_lower = text.lower()
    return "ganong" in text_lower or "review of medical physiology" in text_lower


def is_guyton_hall(text: str, meta: Dict) -> bool:
    """Guyton and Hall Textbook of Medical Physiology"""
    text_lower = text.lower()
    return ("guyton" in text_lower and "hall" in text_lower) or \
           ("unit i" in text_lower and "physiology" in text_lower and meta.get("total_pages", 0) > 900)


def is_harpers_biochemistry(text: str, meta: Dict) -> bool:
    """Harper's Illustrated Biochemistry"""
    text_lower = text.lower()
    return "harper" in text_lower and "biochemistry" in text_lower


def is_rang_dale_pharmacology(text: str, meta: Dict) -> bool:
    """Rang and Dale's Pharmacology"""
    text_lower = text.lower()
    return ("rang" in text_lower and "dale" in text_lower) or \
           ("pharmacology" in text_lower and "general principles" in text_lower and meta.get("total_pages", 0) > 700)


def is_katzung_pharmacology(text: str, meta: Dict) -> bool:
    """Katzung Pharmacology"""
    text_lower = text.lower()
    return "katzung" in text_lower or \
           ("pharmacology" in text_lower and "board review" in text_lower)


def is_brs_physiology(text: str, meta: Dict) -> bool:
    """BRS Physiology (Board Review Series)"""
    text_lower = text.lower()
    return ("brs" in text_lower and "physiology" in text_lower) or \
           ("board review series" in text_lower and "physiology" in text_lower)


def is_robbins_pathology(text: str, meta: Dict) -> bool:
    """Robbins Basic Pathology"""
    text_lower = text.lower()
    return "robbins" in text_lower and ("pathology" in text_lower or "kumar" in text_lower)


def is_langman_embryology(text: str, meta: Dict) -> bool:
    """Langman's Medical Embryology"""
    text_lower = text.lower()
    return "langman" in text_lower and "embryology" in text_lower


def is_wheaters_histology(text: str, meta: Dict) -> bool:
    """Wheater's Functional Histology"""
    text_lower = text.lower()
    return "wheater" in text_lower and "histology" in text_lower


def is_snell_anatomy(text: str, meta: Dict) -> bool:
    """Snell's Clinical Anatomy"""
    text_lower = text.lower()
    return "snell" in text_lower and "anatomy" in text_lower


def is_vishram_singh_anatomy(text: str, meta: Dict) -> bool:
    """Vishram Singh Textbook of Anatomy"""
    text_lower = text.lower()
    return "vishram singh" in text_lower or \
           ("anatomy" in text_lower and ("abdomen" in text_lower or "lower limb" in text_lower) and "section i" in text_lower)


def is_k_park_preventive(text: str, meta: Dict) -> bool:
    """K Park's Preventive and Social Medicine"""
    text_lower = text.lower()
    return ("park" in text_lower and "preventive" in text_lower) or \
           ("social medicine" in text_lower and "epidemiology" in text_lower)


def is_netters_flash_cards(text: str, meta: Dict) -> bool:
    """Netter's Physiology Flash Cards"""
    text_lower = text.lower()
    return ("netter" in text_lower and "flash" in text_lower) or \
           ("netter" in text_lower and "physiology" in text_lower)


def is_medical_physiology_boron(text: str, meta: Dict) -> bool:
    """Medical Physiology by Boron"""
    text_lower = text.lower()
    return ("boron" in text_lower and "physiology" in text_lower) or \
           ("medical physiology" in text_lower and meta.get("total_pages", 0) > 3000)


def is_urinary_incontinence_book(text: str, meta: Dict) -> bool:
    """Urinary Incontinence specialty books"""
    text_lower = text.lower()
    return "urinary incontinence" in text_lower and "part i" in text_lower


def is_machine_learning_book(text: str, meta: Dict) -> bool:
    """ML/Technical books with Parts > Chapters"""
    text_lower = text.lower()
    return ("machine learning" in text_lower or "scikit-learn" in text_lower or
            "tensorflow" in text_lower or "keras" in text_lower) and \
           re.search(r'Part\s+I[I]*\.?\s+', text)


def is_law_vsi(text: str, meta: Dict) -> bool:
    """Very Short Introduction law books"""
    text_lower = text.lower()
    return "very short introduction" in text_lower and "law" in text_lower


def is_ethics_for_lawyers(text: str, meta: Dict) -> bool:
    """Booklet on Ethics for Lawyers"""
    text_lower = text.lower()
    filename_lower = meta.get("filename", "").lower()
    
    # Check filename first (most reliable)
    if "booklet on ethics for lawyers" in filename_lower or "ethics for lawyers" in filename_lower:
        return True
    
    # Check text content
    patterns = [
        "ethics for lawyers" in text_lower,
        "booklet on ethics" in text_lower,
        ("ethics" in text_lower and "lawyer" in text_lower and ("booklet" in text_lower or "guide" in text_lower)),
        ("professional conduct" in text_lower and "legal" in text_lower and "ethics" in text_lower),
        ("rules of professional responsibility" in text_lower),
        ("legal ethics" in text_lower and meta.get("total_pages", 0) < 100),  # Booklet is typically shorter
    ]
    return sum(bool(p) for p in patterns) >= 2


def is_law_textbook(text: str, meta: Dict) -> bool:
    """General law textbooks"""
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
    """Human Anatomy Color Atlas"""
    text_lower = text.lower()
    return ("human anatomy" in text_lower and "color atlas" in text_lower) or \
           ("anatomy" in text_lower and "colour atlas" in text_lower)


# ==============================================================================
# BOOK PATTERNS REGISTRY
# Order matters - more specific patterns should come first
# ==============================================================================

BOOK_PATTERNS: List[Dict] = [
    # Specific medical books (most specific first)
    {"name": "Practical Physiology", "fingerprint": is_medical_physiology_practical, "prompt": MEDICAL_PHYSIOLOGY_PRACTICAL_PROMPT, "description": "Section > X-Y chapters"},
    {"name": "Gray's Anatomy", "fingerprint": is_grays_anatomy, "prompt": GRAYS_ANATOMY_PROMPT, "description": "Sections > Chapters (large anatomy)"},
    {"name": "Ganong's Review", "fingerprint": is_ganong_review, "prompt": GANONG_MEDICAL_PROMPT, "description": "Sections > Chapters"},
    {"name": "Guyton & Hall", "fingerprint": is_guyton_hall, "prompt": GUYTON_HALL_PROMPT, "description": "Units > Chapters"},
    {"name": "Harper's Biochemistry", "fingerprint": is_harpers_biochemistry, "prompt": HARPERS_BIOCHEMISTRY_PROMPT, "description": "Sections > Chapters"},
    {"name": "Rang & Dale Pharmacology", "fingerprint": is_rang_dale_pharmacology, "prompt": RANG_DALE_PHARMACOLOGY_PROMPT, "description": "Sections > Chapters"},
    {"name": "Katzung Pharmacology", "fingerprint": is_katzung_pharmacology, "prompt": KATZUNG_PHARMACOLOGY_PROMPT, "description": "Parts > Chapters"},
    {"name": "BRS Physiology", "fingerprint": is_brs_physiology, "prompt": BRS_PHYSIOLOGY_PROMPT, "description": "Chapters only (review)"},
    {"name": "Robbins Pathology", "fingerprint": is_robbins_pathology, "prompt": ROBBINS_PATHOLOGY_PROMPT, "description": "Chapters only"},
    {"name": "Langman's Embryology", "fingerprint": is_langman_embryology, "prompt": LANGMAN_EMBRYOLOGY_PROMPT, "description": "Parts > Chapters"},
    {"name": "Wheater's Histology", "fingerprint": is_wheaters_histology, "prompt": WHEATERS_HISTOLOGY_PROMPT, "description": "Parts > Chapters"},
    {"name": "Snell's Anatomy", "fingerprint": is_snell_anatomy, "prompt": SNELL_ANATOMY_PROMPT, "description": "Chapters only (regions)"},
    {"name": "Vishram Singh Anatomy", "fingerprint": is_vishram_singh_anatomy, "prompt": VISHRAM_SINGH_ANATOMY_PROMPT, "description": "Sections > Chapters"},
    {"name": "K Park's Preventive Med", "fingerprint": is_k_park_preventive, "prompt": K_PARK_PREVENTIVE_MED_PROMPT, "description": "Topics > Chapters"},
    {"name": "Netter's Flash Cards", "fingerprint": is_netters_flash_cards, "prompt": NETTERS_FLASH_CARDS_PROMPT, "description": "Sections > X-Y format"},
    {"name": "Medical Physiology (Boron)", "fingerprint": is_medical_physiology_boron, "prompt": MEDICAL_PHYSIOLOGY_BORON_PROMPT, "description": "Sections > Chapters"},
    {"name": "Human Anatomy Atlas", "fingerprint": is_human_anatomy_atlas, "prompt": GENERALIZED_PROMPT, "description": "Chapters only"},

    # Urinary incontinence books
    {"name": "Urinary Incontinence", "fingerprint": is_urinary_incontinence_book, "prompt": URINARY_INCONTINENCE_PARTS_PROMPT, "description": "Parts > Chapters"},

    # Technical books
    {"name": "Machine Learning/Technical", "fingerprint": is_machine_learning_book, "prompt": MACHINE_LEARNING_PROMPT, "description": "Parts > Chapters"},

    # Law books (specific first, then general)
    {"name": "Ethics for Lawyers", "fingerprint": is_ethics_for_lawyers, "prompt": ETHICS_FOR_LAWYERS_PROMPT, "description": "Chapters only (ethics booklet)"},
    {"name": "Law VSI", "fingerprint": is_law_vsi, "prompt": LAW_VSI_PROMPT, "description": "Simple chapters"},
    {"name": "Law Textbook", "fingerprint": is_law_textbook, "prompt": LAW_TEXTBOOK_CHAPTERS_PROMPT, "description": "Chapters only"},
]


# ==============================================================================
# MAIN FUNCTIONS
# ==============================================================================

def get_prompt_for_book(pages_text: str, metadata: Dict = None) -> Tuple[str, str]:
    """
    Detect book type and return appropriate prompt.

    Args:
        pages_text: Combined text from first ~35 pages of PDF
        metadata: Optional metadata about the PDF (total_pages, filename, etc.)

    Returns:
        tuple: (prompt_template, pattern_name)
    """
    if metadata is None:
        metadata = {}

    for pattern in BOOK_PATTERNS:
        try:
            if pattern["fingerprint"](pages_text, metadata):
                logger.info(f"Detected book type: {pattern['name']} ({pattern['description']})")
                return pattern["prompt"], pattern["name"]
        except Exception as e:
            continue

    logger.info("No specific pattern matched - using generalized prompt")
    return GENERALIZED_PROMPT, "Generalized"


def list_available_patterns() -> List[Dict]:
    """List all available book patterns."""
    return [{"name": p["name"], "description": p["description"]} for p in BOOK_PATTERNS]


def get_all_prompts() -> Dict[str, str]:
    """Get all prompts as a dictionary."""
    return {p["name"]: p["prompt"] for p in BOOK_PATTERNS}


# ==============================================================================
# CLI for testing
# ==============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PROMPT LIBRARY - Available Book Patterns")
    print("=" * 60)
    for i, pattern in enumerate(list_available_patterns(), 1):
        print(f"{i:2}. {pattern['name']:<30} - {pattern['description']}")
    print(f"\nTotal patterns: {len(BOOK_PATTERNS)}")
    print("Plus: Generalized fallback for unknown books")
