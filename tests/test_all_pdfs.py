"""
Test parser on all PDFs in test_pdfs directory.
"""

import asyncio
from pathlib import Path

from services.document_parser import DocumentParser


async def test_pdf(pdf_path):
    """Test parsing a single PDF."""
    print(f"\n{'='*80}")
    print(f"TESTING: {pdf_path.name}")
    print(f"{'='*80}\n")

    with open(pdf_path, "rb") as f:
        pdf_content = f.read()

    print(f"Size: {len(pdf_content):,} bytes")
    print("Parsing...")

    try:
        result = await DocumentParser.parse_document(
            pdf_content,
            "pdf",  # document_type (string or enum)
            pdf_path.name,  # filename
        )

        # Save to JSON
        import json

        output_filename = f"output_{pdf_path.stem.replace(' ', '_')}.json"
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # Show summary
        chapters = result.get("content", {})
        print(f"\n✅ SUCCESS!")
        print(f"   Chapters found: {len(chapters)}")
        print(f"   Saved to: {output_filename}")

        for i, (chapter_key, sections) in enumerate(list(chapters.items())[:5], 1):
            if isinstance(sections, dict):
                section_count = len(sections)
                print(f"   {i}. {chapter_key} ({section_count} sections)")
            else:
                print(f"   {i}. {chapter_key} (no sections)")

        if len(chapters) > 5:
            print(f"   ... and {len(chapters) - 5} more chapters")

        return True

    except Exception as e:
        print(f"\n❌ FAILED!")
        print(f"   Error: {str(e)[:200]}")
        return False


async def main():
    """Test all PDFs."""
    test_pdfs_dir = Path("test_pdfs")
    pdf_files = list(test_pdfs_dir.glob("*.pdf"))

    print(f"\n{'='*80}")
    print(f"TESTING {len(pdf_files)} PDFs")
    print(f"{'='*80}")

    results = {}
    for pdf_file in pdf_files:
        success = await test_pdf(pdf_file)
        results[pdf_file.name] = success

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")

    for name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")

    passed = sum(1 for s in results.values() if s)
    print(f"\nPassed: {passed}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
