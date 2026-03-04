# services/branding_service.py

import os
from typing import Optional
from uuid import uuid4
from io import BytesIO

from fastapi import HTTPException, UploadFile, status

from logger import logger
from supabase_config import BUCKETS, supabase

# Optional PIL import for image validation
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None


class BrandingService:
    """Service for managing university branding (logos)."""

    # Allowed image formats
    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
    ALLOWED_MIME_TYPES = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/svg+xml",
        "image/webp",
    }

    # File size limits (5MB)
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes

    # Image dimension limits (optional, for validation)
    MAX_WIDTH = 2000
    MAX_HEIGHT = 2000

    @staticmethod
    def _get_file_extension(filename: str) -> Optional[str]:
        """Extract file extension from filename."""
        if not filename:
            return None
        ext = os.path.splitext(filename.lower())[1]
        return ext if ext else None

    @staticmethod
    def _validate_file_type(filename: str, content_type: Optional[str]) -> tuple[str, str]:
        """
        Validate file type and return extension and normalized content type.
        
        Returns:
            Tuple of (extension, normalized_content_type)
        """
        ext = BrandingService._get_file_extension(filename)
        if not ext or ext not in BrandingService.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type. Allowed formats: PNG, JPG, JPEG, SVG, WEBP",
            )

        # Normalize content type
        normalized_content_type = content_type or "application/octet-stream"
        if content_type and content_type not in BrandingService.ALLOWED_MIME_TYPES:
            # Try to infer from extension
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".svg": "image/svg+xml",
                ".webp": "image/webp",
            }
            normalized_content_type = mime_map.get(ext, "image/png")
        else:
            normalized_content_type = content_type

        return ext, normalized_content_type

    @staticmethod
    def _validate_file_size(file_size: int) -> None:
        """Validate file size."""
        if file_size > BrandingService.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {BrandingService.MAX_FILE_SIZE / (1024 * 1024):.1f}MB",
            )

    @staticmethod
    async def _validate_image_dimensions(file_content: bytes, ext: str) -> None:
        """
        Validate image dimensions (optional validation).
        Only validates for non-SVG images.
        """
        if ext == ".svg":
            # Skip dimension validation for SVG
            return

        if not PIL_AVAILABLE:
            # Skip dimension validation if PIL is not available
            logger.warning("PIL/Pillow not available, skipping image dimension validation")
            return

        try:
            image = Image.open(BytesIO(file_content))
            width, height = image.size

            if width > BrandingService.MAX_WIDTH or height > BrandingService.MAX_HEIGHT:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Image dimensions exceed maximum allowed size of {BrandingService.MAX_WIDTH}x{BrandingService.MAX_HEIGHT}px",
                )
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            # If image validation fails (e.g., corrupted image), log warning but don't fail
            logger.warning(f"Could not validate image dimensions: {str(e)}")

    @staticmethod
    def _get_logo_storage_path(university_id: str, extension: str) -> str:
        """Generate storage path for logo."""
        return f"uploads/branding/{university_id}/logo{extension}"

    @staticmethod
    async def upload_logo(
        university_id: str, file: UploadFile, existing_logo_url: Optional[str] = None
    ) -> str:
        """
        Upload a logo for a university. Replaces existing logo if one exists.

        Args:
            university_id: ID of the university
            file: Uploaded logo file
            existing_logo_url: Optional existing logo URL from database (for cleanup)

        Returns:
            Public URL of the uploaded logo
        """
        try:
            if not file.filename:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No file provided",
                )

            # Read file content
            file_content = await file.read()
            file_size = len(file_content)

            # Validate file size
            BrandingService._validate_file_size(file_size)

            # Validate file type
            ext, content_type = BrandingService._validate_file_type(
                file.filename, file.content_type
            )

            # Validate image dimensions (optional)
            await BrandingService._validate_image_dimensions(file_content, ext)

            # Generate storage path
            storage_path = BrandingService._get_logo_storage_path(university_id, ext)

            # Delete old logo if it exists (cleanup)
            try:
                bucket = supabase.get_storage_bucket(BUCKETS["USER_UPLOADS"])
                
                # First, try to delete the specific existing logo if we have its URL
                if existing_logo_url:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(existing_logo_url)
                        old_path = parsed.path.lstrip("/")
                        # Remove bucket prefix if present (e.g., "USER_UPLOADS/")
                        if old_path.startswith("USER_UPLOADS/"):
                            old_path = old_path.replace("USER_UPLOADS/", "", 1)
                        bucket.remove([old_path])
                        logger.info(f"Deleted existing logo: {old_path}")
                    except Exception as specific_delete_err:
                        logger.warning(f"Could not delete specific existing logo: {str(specific_delete_err)}")
                
                # Also try to delete all possible logo extensions (fallback cleanup)
                old_logo_paths = [
                    f"uploads/branding/{university_id}/logo.png",
                    f"uploads/branding/{university_id}/logo.jpg",
                    f"uploads/branding/{university_id}/logo.jpeg",
                    f"uploads/branding/{university_id}/logo.svg",
                    f"uploads/branding/{university_id}/logo.webp",
                ]
                for old_path in old_logo_paths:
                    try:
                        bucket.remove([old_path])
                    except Exception:
                        # Ignore errors if file doesn't exist
                        pass
            except Exception as cleanup_err:
                logger.warning(f"Error cleaning up old logo: {str(cleanup_err)}")

            # Upload new logo
            bucket = supabase.get_storage_bucket(BUCKETS["USER_UPLOADS"])
            bucket.upload(
                storage_path,
                file_content,
                file_options={"content-type": content_type},
            )

            # Get public URL
            public_url = bucket.get_public_url(storage_path)

            logger.info(
                f"Logo uploaded successfully for university {university_id}: {public_url}"
            )

            return public_url

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error uploading logo: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload logo: {str(e)}",
            ) from e

    @staticmethod
    async def delete_logo(university_id: str) -> None:
        """
        Delete a logo for a university.

        Args:
            university_id: ID of the university
        """
        try:
            # Try to delete all possible logo extensions
            logo_paths = [
                f"uploads/branding/{university_id}/logo.png",
                f"uploads/branding/{university_id}/logo.jpg",
                f"uploads/branding/{university_id}/logo.jpeg",
                f"uploads/branding/{university_id}/logo.svg",
                f"uploads/branding/{university_id}/logo.webp",
            ]

            bucket = supabase.get_storage_bucket(BUCKETS["USER_UPLOADS"])
            deleted = False

            for path in logo_paths:
                try:
                    bucket.remove([path])
                    deleted = True
                    logger.info(f"Deleted logo file: {path}")
                except Exception:
                    # Ignore errors if file doesn't exist
                    pass

            if not deleted:
                logger.warning(f"No logo found to delete for university {university_id}")

            logger.info(f"Logo deletion completed for university {university_id}")

        except Exception as e:
            logger.error(f"Error deleting logo: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete logo: {str(e)}",
            ) from e
