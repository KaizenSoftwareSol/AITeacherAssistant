#!/usr/bin/env python3
"""
Script to delete an orphaned student by student_id.

This script finds and deletes a student record that may have been partially created
but failed to complete, leaving an orphaned record in the database.

Usage:
    python scripts/delete_orphaned_student.py <student_id> [university_id]

Example:
    python scripts/delete_orphaned_student.py TEST1234
"""

import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import get_db
from logger import logger


def delete_orphaned_student(student_id: str, university_id: str = None):
    """Delete an orphaned student by student_id."""
    db = get_db()
    
    try:
        # Find the student record
        filters = {"student_id": student_id}
        if university_id:
            filters["university_id"] = university_id
        
        students = db.get_records("student", filters, use_cache=False)
        
        if not students:
            print(f"❌ No student found with student_id: {student_id}")
            if university_id:
                print(f"   (in university: {university_id})")
            return False
        
        if len(students) > 1:
            print(f"⚠️  Warning: Found {len(students)} students with student_id: {student_id}")
            if not university_id:
                print("   Please specify university_id to delete the correct one")
                for s in students:
                    print(f"   - Student ID: {s.get('id')}, University: {s.get('university_id')}")
                return False
        
        student = students[0]
        student_db_id = student.get("id")
        user_id = student.get("user_id")
        student_university_id = student.get("university_id")
        
        print(f"Found student:")
        print(f"  - Database ID: {student_db_id}")
        print(f"  - Student ID: {student_id}")
        print(f"  - User ID: {user_id}")
        print(f"  - University ID: {student_university_id}")
        
        # Check if user exists
        if user_id:
            user_data = db.get_user_by_id(user_id, use_cache=False)
            if user_data:
                print(f"  - User Email: {user_data.get('email')}")
                print(f"  - User Role: {user_data.get('role')}")
            else:
                print("  - User: NOT FOUND (orphaned)")
        
        # Check for enrollments
        enrollments = (
            db.admin_client.table("enrollment")
            .select("id, course_id")
            .eq("student_id", str(student_db_id))
            .execute()
        )
        
        if enrollments.data:
            print(f"  - Enrollments: {len(enrollments.data)} found")
            for enr in enrollments.data:
                print(f"    * Enrollment ID: {enr.get('id')}, Course: {enr.get('course_id')}")
        else:
            print("  - Enrollments: None")
        
        # Confirm deletion
        print("\n⚠️  WARNING: This will delete:")
        print("  - Student profile")
        if user_id:
            print("  - User account")
        if enrollments.data:
            print(f"  - {len(enrollments.data)} enrollment(s)")
        
        confirm = input("\nAre you sure you want to delete this student? (yes/no): ")
        if confirm.lower() != "yes":
            print("❌ Deletion cancelled")
            return False
        
        # Delete enrollments first
        if enrollments.data:
            print("\nDeleting enrollments...")
            for enr in enrollments.data:
                try:
                    db.admin_client.table("enrollment").delete().eq("id", enr.get("id")).execute()
                    print(f"  ✓ Deleted enrollment {enr.get('id')}")
                except Exception as e:
                    print(f"  ✗ Error deleting enrollment {enr.get('id')}: {e}")
        
        # Delete student profile
        print("\nDeleting student profile...")
        try:
            db.delete_record("student", student_db_id)
            print(f"  ✓ Deleted student profile {student_db_id}")
        except Exception as e:
            print(f"  ✗ Error deleting student profile: {e}")
            return False
        
        # Delete user if exists
        if user_id:
            print("\nDeleting user account...")
            try:
                success = db.delete_user(user_id)
                if success:
                    print(f"  ✓ Deleted user account {user_id}")
                else:
                    print(f"  ✗ Failed to delete user account {user_id}")
            except Exception as e:
                print(f"  ✗ Error deleting user account: {e}")
        
        print("\n✅ Student deletion completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting orphaned student: {e!s}")
        print(f"\n❌ Error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/delete_orphaned_student.py <student_id> [university_id]")
        print("\nExample:")
        print("  python scripts/delete_orphaned_student.py TEST1234")
        sys.exit(1)
    
    student_id = sys.argv[1]
    university_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"Deleting orphaned student: {student_id}")
    if university_id:
        print(f"University ID: {university_id}")
    print()
    
    success = delete_orphaned_student(student_id, university_id)
    sys.exit(0 if success else 1)
