"""
Book Structure Analyzer

Quick tool to analyze a PDF's structure without full parsing.
Useful for understanding new book formats before creating prompts.

Usage:
    python tests/analyze_book_structure.py "path/to/book.pdf"
"""

import asyncio
import io
import json
import os
import sys
from pathlib import Path

import PyPDF2
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def analyze_book(pdf_path: str) -> dict:
    """
    Analyze a book's structure to help create a specialized prompt.
    Returns structure info without full content extraction.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found")
        return None

    client = AsyncOpenAI(api_key=api_key)

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        return None

    print(f"\n{'='*60}")
    print(f"Analyzing: {pdf_path.name}")
    print(f"{'='*60}")

    # Extract first 40 pages
    print("\n[1] Extracting text from first 40 pages...")
    with open(pdf_path, "rb") as f:
        pdf_reader = PyPDF2.PdfReader(f)
        total_pages = len(pdf_reader.pages)
        print(f"    Total pages in PDF: {total_pages}")

        toc_text = ""
        for i, page in enumerate(pdf_reader.pages[:40]):
            try:
                text = page.extract_text() or ""
                text = text.encode("utf-8", errors="ignore").decode("utf-8")
                toc_text += f"\n\n=== PDF PAGE {i+1} ===\n"
                toc_text += text[:3000]
            except Exception as e:
                print(f"    Warning: Could not extract page {i+1}: {e}")

    # Analyze with LLM
    print("\n[2] Analyzing structure with LLM...")

    prompt = f"""Analyze this book's Table of Contents and describe its structure.

I need to create a specialized parsing prompt for this book. Please tell me:

1. **Book Type**: What kind of book is this? (Medical textbook, Law book, Technical manual, etc.)

2. **Hierarchy Structure**: What levels does this book use?
   - Examples: "Parts > Chapters", "Sections > Chapters", "Chapters only"
   - Be specific about naming conventions (Part I, SECTION ONE, Chapter 1, 1-1, etc.)

3. **Numbering System**: How are chapters/sections numbered?
   - Roman numerals (I, II, III)
   - Arabic numerals (1, 2, 3)
   - Special format (1-1, 1-2 for Section-Chapter)
   - Letters (A, B, C)

4. **Page Number Format**: How do page numbers appear in the TOC?
   - With dots (Chapter 1.....15)
   - Plain (Chapter 1  15)
   - Other format

5. **Estimated Counts**:
   - How many top-level divisions (Parts/Sections)?
   - How many chapters total?

6. **Special Features**:
   - Any appendices, indices, glossaries?
   - Any unusual structure elements?

7. **Sample TOC Entry**: Copy 2-3 example entries exactly as they appear.

8. **Recommended Fingerprint**: What unique text patterns could identify this book type?
   - Look for distinctive phrases in title, TOC, or early pages
   - Example: "Review of Medical Physiology" or "SECTION ONE: HEMATOLOGY"

TEXT FROM FIRST 40 PAGES:
{toc_text}
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a book structure analyst. Analyze the TOC and describe the book's organization clearly and concisely.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=2000,
        )

        analysis = response.choices[0].message.content.strip()

        print("\n" + "="*60)
        print("STRUCTURE ANALYSIS")
        print("="*60)
        print(analysis)

        # Save analysis
        output_path = pdf_path.parent / f"{pdf_path.stem}_analysis.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Book: {pdf_path.name}\n")
            f.write(f"Total Pages: {total_pages}\n")
            f.write("="*60 + "\n\n")
            f.write(analysis)

        print(f"\n\nAnalysis saved to: {output_path}")

        return {
            "book_name": pdf_path.name,
            "total_pages": total_pages,
            "analysis": analysis,
            "output_path": str(output_path),
        }

    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return None


async def batch_analyze(folder_path: str):
    """Analyze all PDFs in a folder."""
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Error: Folder not found: {folder}")
        return

    pdfs = list(folder.glob("*.pdf"))
    print(f"\nFound {len(pdfs)} PDFs in {folder}")

    results = []
    for pdf in pdfs:
        result = await analyze_book(str(pdf))
        if result:
            results.append(result)
        print("\n" + "-"*60 + "\n")

    # Summary
    print("\n" + "="*60)
    print("BATCH ANALYSIS COMPLETE")
    print("="*60)
    print(f"Analyzed {len(results)} books:")
    for r in results:
        print(f"  - {r['book_name']} ({r['total_pages']} pages)")
        print(f"    Analysis: {r['output_path']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single book:  python analyze_book_structure.py path/to/book.pdf")
        print("  Batch:        python analyze_book_structure.py path/to/folder/")
        sys.exit(1)

    target = sys.argv[1]

    if Path(target).is_dir():
        asyncio.run(batch_analyze(target))
    else:
        asyncio.run(analyze_book(target))
