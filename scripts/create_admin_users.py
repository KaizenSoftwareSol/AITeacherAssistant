#!/usr/bin/env python3
"""
Script to create admin users for Stanford University and Zia Uddin University.

Usage:
    python scripts/create_admin_users.py

Requirements:
    - SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables must be set
    - Or configure in settings.py
"""

import asyncio
import sys
import traceback
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import all models first to ensure SQLAlchemy relationships are properly initialized
# This prevents relationship errors when creating User objects
from auth.models import UserCreate
from auth.service import AuthService
from models import (  # noqa: F401
    Lecture,
    LectureChunk,
    LectureEmbedding,
    User,
)
from models.user import UserRole
from utils.db import get_db

# Admin user configurations
ADMIN_USERS = [
    {
        "university_name": "Stanford University",
        "university_location": "Stanford, California, USA",
        "email": "admin@stanford.edu",
        "username": "stanford_admin",
        "password": "StanfordAdmin2026!",  # Change this to a secure password
        "first_name": "Stanford",
        "last_name": "Administrator",
    },
    {
        "university_name": "Zia Uddin University",
        "university_location": None,  # Add location if known
        "email": "admin@ziauddin.edu",
        "username": "ziauddin_admin",
        "password": "ZiaUddinAdmin2026!",  # Change this to a secure password
        "first_name": "Zia Uddin",
        "last_name": "Administrator",
    },
]


async def delete_existing_admin(db, config: dict) -> bool:
    """Delete existing admin user for a university if it exists."""
    university_name = config["university_name"]

    try:
        # Check if user already exists
        existing_user = db.get_user_by_email(config["email"], use_cache=False)
        if existing_user:
            user_id = existing_user.get("id")
            user_role = existing_user.get("role")

            # Check if they're an admin for this university
            if user_role == "ADMIN":
                university = db.get_record_by_id(
                    "university", existing_user.get("university_id")
                )
                if university and university.get("name") == university_name:
                    print("   Deleting existing admin user...")

                    # Delete the user (this will cascade delete related records)
                    success = db.delete_user(user_id)
                    if success:
                        print("   ✓ Deleted existing admin user")
                        return True
                    else:
                        print("   ⚠️  Failed to delete user")
                        return False

        # Also check by username
        existing_users = db.get_records(
            "users", {"username": config["username"]}, use_cache=False
        )
        if existing_users:
            for user in existing_users:
                if user.get("role") == "ADMIN":
                    university = db.get_record_by_id(
                        "university", user.get("university_id")
                    )
                    if university and university.get("name") == university_name:
                        print("   Deleting existing admin user (by username)...")
                        success = db.delete_user(user.get("id"))
                        if success:
                            print("   ✓ Deleted existing admin user")
                            return True

        return False
    except Exception as e:
        print(f"   ⚠️  Error checking/deleting existing user: {e!s}")
        return False


async def create_admin_user(db, config: dict):
    """Create an admin user for a university."""
    university_name = config["university_name"]
    print(f"\n{'=' * 60}")
    print(f"Processing: {university_name}")
    print(f"{'=' * 60}")

    try:
        # Delete existing admin user if it exists
        deleted = await delete_existing_admin(db, config)
        if deleted:
            print("   Waiting a moment for database to process deletion...")
            await asyncio.sleep(1)  # Brief pause to ensure deletion is processed

        # Check if user still exists (should not after deletion)
        existing_user = db.get_user_by_email(config["email"], use_cache=False)
        if existing_user:
            print(
                f"⚠️  User with email '{config['email']}' "
                "still exists after deletion attempt."
            )
            print(f"   User ID: {existing_user.get('id')}")
            return None

        # Check if username still exists
        existing_users = db.get_records(
            "users", {"username": config["username"]}, use_cache=False
        )
        if existing_users:
            print(
                f"⚠️  Username '{config['username']}' "
                "still exists after deletion attempt."
            )
            return None

        # Create user using AuthService
        print("Creating new admin user...")
        user_create = UserCreate(
            email=config["email"],
            username=config["username"],
            password=config["password"],
            first_name=config["first_name"],
            last_name=config["last_name"],
            role=UserRole.ADMIN,
            university_name=university_name,
            university_location=config.get("university_location"),
        )

        user = await AuthService.create_user(db, user_create)

        print("✓ Successfully created admin user!")
        print(f"   User ID: {user.id}")
        print(f"   Email: {user.email}")
        print(f"   Username: {user.username}")
        print(f"   Name: {user.first_name} {user.last_name}")
        print(f"   Role: {user.role.value}")
        print(f"   University: {university_name}")
        print("\n   Login Credentials:")
        print(f"   Email: {config['email']}")
        print(f"   Password: {config['password']}")
        print("\n   ⚠️  IMPORTANT: Save these credentials securely!")

        return user

    except ValueError as e:
        print(f"❌ Error: {e!s}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e!s}")
        traceback.print_exc()
        return None


async def main():
    """Main function to delete and create admin users."""
    print("\n" + "=" * 60)
    print("Admin User Creation Script")
    print("=" * 60)
    print("\nThis script will DELETE existing and CREATE NEW admin users for:")
    for config in ADMIN_USERS:
        print(f"  - {config['university_name']}")
    print("\n⚠️  WARNING: Existing admin users will be deleted!")

    # Get database instance
    db = get_db()

    # Check if database is initialized
    if not db.admin_client:
        print("\n❌ Error: Supabase admin client not initialized!")
        print("   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        print("   environment variables or configure in settings.py")
        return

    print("\n✓ Database connection established")

    # Create admin users
    results = []
    for config in ADMIN_USERS:
        result = await create_admin_user(db, config)
        results.append((config["university_name"], result is not None))

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for university_name, success in results:
        status = "✓ Created/Exists" if success else "❌ Failed"
        print(f"{status}: {university_name}")

    print("\n" + "=" * 60)
    print("Script completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
