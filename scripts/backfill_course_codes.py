#!/usr/bin/env python3
"""
Script to backfill course codes for existing courses.

This script:
1. Finds courses without valid codes
2. Generates unique codes based on course names
3. Handles duplicate codes
4. Updates the database

Usage:
    python scripts/backfill_course_codes.py
    python scripts/backfill_course_codes.py --dry-run
    python scripts/backfill_course_codes.py --course-id UUID
"""

import argparse
import re
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from logger import logger
from utils.db import get_db


def generate_course_code(course_name: str, existing_codes: set, prefix: str = "") -> str:
    """
    Generate a unique course code from course name.
    
    Args:
        course_name: Name of the course
        existing_codes: Set of existing codes to avoid duplicates
        prefix: Optional prefix (e.g., department code)
    
    Returns:
        Unique course code (e.g., "ITCS101", "PHYS102")
    """
    # Remove special characters and split into words
    words = re.findall(r'\b\w+\b', course_name.upper())
    
    # Filter out short words (to, of, and, etc.)
    significant_words = [w for w in words if len(w) > 2]
    
    if not significant_words:
        significant_words = words
    
    # Take first letter of first 4 significant words
    if len(significant_words) >= 4:
        base_code = ''.join(w[0] for w in significant_words[:4])
    elif len(significant_words) >= 2:
        # Take first 2 letters of first 2 words
        base_code = ''.join(w[:2] for w in significant_words[:2])
    else:
        # Take first 4 letters of course name
        clean_name = re.sub(r'[^A-Z0-9]', '', course_name.upper())
        base_code = clean_name[:4].ljust(4, 'X')
    
    # Add prefix if provided
    if prefix:
        base_code = prefix + base_code
    
    # Limit to 4-6 characters
    base_code = base_code[:6]
    
    # Try with 101, 102, etc.
    counter = 101
    while True:
        code = f"{base_code}{counter}"
        if code not in existing_codes:
            return code
        counter += 1
        if counter > 999:
            # Fallback: add random suffix
            import random
            code = f"{base_code}{random.randint(1000, 9999)}"
            if code not in existing_codes:
                return code


def backfill_course_code(course_id: str, dry_run: bool = False) -> dict:
    """
    Generate and set a course code for a specific course.
    
    Args:
        course_id: UUID of the course
        dry_run: If True, don't actually update the database
    
    Returns:
        Dictionary with old_code, new_code, and course info
    """
    db = get_db()
    
    # Get course info
    result = db.admin_client.table("course").select("*").eq("id", course_id).execute()
    
    if not result.data:
        logger.error(f"Course {course_id} not found")
        return None
    
    course = result.data[0]
    old_code = course.get("code", "")
    
    # Get all existing codes for this university
    all_courses = db.admin_client.table("course").select("code").eq("university_id", course["university_id"]).execute()
    existing_codes = {c["code"] for c in all_courses.data if c.get("code")}
    
    # Generate new code
    new_code = generate_course_code(course["name"], existing_codes)
    
    result_dict = {
        "course_id": course_id,
        "course_name": course["name"],
        "old_code": old_code,
        "new_code": new_code,
        "university_id": course["university_id"],
    }
    
    if not dry_run:
        # Update the course
        db.admin_client.table("course").update({
            "code": new_code,
        }).eq("id", course_id).execute()
        
        logger.info(f"✅ Updated course '{course['name']}': '{old_code}' -> '{new_code}'")
    else:
        logger.info(f"[DRY RUN] Would update course '{course['name']}': '{old_code}' -> '{new_code}'")
    
    return result_dict


def backfill_all_courses(dry_run: bool = False) -> dict:
    """
    Backfill course codes for all courses that need them.
    
    Args:
        dry_run: If True, don't actually update the database
    
    Returns:
        Dictionary with statistics
    """
    db = get_db()
    
    logger.info("Fetching courses...")
    
    # Get all courses
    result = db.admin_client.table("course").select("id, name, code, university_id").order("university_id, created_at").execute()
    
    if not result.data:
        logger.info("No courses found")
        return {"total": 0, "updated": 0, "skipped": 0}
    
    courses = result.data
    logger.info(f"Found {len(courses)} courses")
    
    # Track statistics
    stats = {
        "total": len(courses),
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }
    
    # Group by university
    by_university = {}
    for course in courses:
        univ_id = course["university_id"]
        if univ_id not in by_university:
            by_university[univ_id] = []
        by_university[univ_id].append(course)
    
    # Process each university
    for univ_id, univ_courses in by_university.items():
        logger.info(f"\nProcessing university {univ_id} ({len(univ_courses)} courses)")
        
        # Get existing codes for this university
        existing_codes = {c["code"] for c in univ_courses if c.get("code") and c["code"].strip()}
        
        # Find courses needing codes
        needs_code = [c for c in univ_courses if not c.get("code") or not c["code"].strip()]
        
        if not needs_code:
            logger.info(f"All courses in this university already have codes ✓")
            stats["skipped"] += len(univ_courses)
            continue
        
        logger.info(f"Found {len(needs_code)} courses without codes")
        
        # Generate codes for courses that need them
        for course in needs_code:
            try:
                # Generate unique code
                new_code = generate_course_code(course["name"], existing_codes)
                existing_codes.add(new_code)  # Add to set to avoid duplicates
                
                result_dict = {
                    "course_id": course["id"],
                    "course_name": course["name"],
                    "old_code": course.get("code", ""),
                    "new_code": new_code,
                }
                
                if not dry_run:
                    # Update the course
                    db.admin_client.table("course").update({
                        "code": new_code,
                    }).eq("id", course["id"]).execute()
                    
                    logger.info(f"✅ Updated: '{course['name']}' -> {new_code}")
                    stats["updated"] += 1
                else:
                    logger.info(f"[DRY RUN] Would update: '{course['name']}' -> {new_code}")
                    stats["updated"] += 1
            
            except Exception as e:
                logger.error(f"❌ Error updating course {course['id']}: {str(e)}")
                stats["errors"] += 1
    
    # Check for duplicates
    logger.info("\nChecking for duplicate codes...")
    
    all_courses_updated = db.admin_client.table("course").select("id, name, code, university_id").execute()
    
    # Group by university and check for duplicates
    for univ_id, univ_courses in by_university.items():
        codes_seen = {}
        for course in univ_courses:
            code = course.get("code", "").strip().upper()
            if not code:
                continue
            
            if code in codes_seen:
                logger.warning(f"⚠️  Duplicate code '{code}' found:")
                logger.warning(f"   - {codes_seen[code]}")
                logger.warning(f"   - {course['name']}")
            else:
                codes_seen[code] = course['name']
    
    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill course codes for existing courses"
    )
    parser.add_argument(
        "--course-id",
        type=str,
        help="Update a specific course (UUID)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without actually updating"
    )
    
    args = parser.parse_args()
    
    logger.info("="*60)
    logger.info("Course Code Backfill Script")
    logger.info("="*60)
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    
    try:
        if args.course_id:
            # Update specific course
            logger.info(f"Processing course: {args.course_id}")
            result = backfill_course_code(args.course_id, args.dry_run)
            
            if result:
                logger.info("\n" + "="*60)
                logger.info("Result:")
                logger.info(f"  Course: {result['course_name']}")
                logger.info(f"  Old Code: {result['old_code'] or '(none)'}")
                logger.info(f"  New Code: {result['new_code']}")
                logger.info("="*60)
        else:
            # Update all courses
            logger.info("Processing all courses...")
            stats = backfill_all_courses(args.dry_run)
            
            logger.info("\n" + "="*60)
            logger.info("Summary:")
            logger.info(f"  Total courses: {stats['total']}")
            logger.info(f"  ✅ Updated: {stats['updated']}")
            logger.info(f"  ⏭️  Skipped (already had codes): {stats['skipped']}")
            logger.info(f"  ❌ Errors: {stats['errors']}")
            logger.info("="*60)
            
            if not args.dry_run and stats['updated'] > 0:
                logger.info("\n✨ Course codes have been backfilled!")
                logger.info("Teachers can now share these codes with students.")
            elif args.dry_run:
                logger.info("\nRun without --dry-run to apply these changes.")
    
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

