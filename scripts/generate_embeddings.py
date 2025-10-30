#!/usr/bin/env python3
"""
Script to generate embeddings for all lectures that don't have them yet.

Usage:
    python scripts/generate_embeddings.py

Options:
    --lecture-id UUID    Generate embeddings for a specific lecture
    --force             Regenerate embeddings even if they exist
    --batch-size N      Process N lectures at a time (default: 10)
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.append(str(Path(__file__).parent.parent))

from logger import logger
from services.embedding_service import EmbeddingService
from utils.db import get_db


async def generate_embeddings_for_lecture(
    lecture_id: str,
    force: bool = False
):
    """
    Generate embeddings for a single lecture.
    
    Args:
        lecture_id: UUID of the lecture
        force: If True, regenerate even if embeddings exist
    """
    db = get_db()
    embedding_service = EmbeddingService(db)
    
    try:
        # Get lecture
        result = db.admin_client.table("lecture").select("id, title, content, has_embeddings").eq("id", lecture_id).execute()
        
        if not result.data:
            logger.error(f"Lecture {lecture_id} not found")
            return False
        
        lecture = result.data[0]
        
        if lecture["has_embeddings"] and not force:
            logger.info(f"Lecture '{lecture['title']}' already has embeddings. Use --force to regenerate.")
            return True
        
        # Delete existing embeddings if force
        if force and lecture["has_embeddings"]:
            logger.info(f"Deleting existing embeddings for lecture '{lecture['title']}'...")
            await embedding_service.delete_lecture_embeddings(lecture_id)
        
        # Generate embeddings
        logger.info(f"Generating embeddings for lecture '{lecture['title']}'...")
        result = await embedding_service.generate_embeddings_for_lecture(
            lecture_id=lecture_id,
            lecture_content=lecture["content"]
        )
        
        logger.info(f"✅ Generated {result['chunks_created']} chunks and {result['embeddings_created']} embeddings")
        return True
    
    except Exception as e:
        logger.error(f"❌ Error generating embeddings for lecture {lecture_id}: {str(e)}")
        return False


async def generate_all_embeddings(
    force: bool = False,
    batch_size: int = 10
):
    """
    Generate embeddings for all lectures that don't have them.
    
    Args:
        force: If True, regenerate even if embeddings exist
        batch_size: Number of lectures to process at a time
    """
    db = get_db()
    
    try:
        # Get lectures without embeddings
        if force:
            query = db.admin_client.table("lecture").select("id, title, content, has_embeddings")
        else:
            query = db.admin_client.table("lecture").select("id, title, content, has_embeddings").eq("has_embeddings", False)
        
        result = query.execute()
        
        if not result.data:
            logger.info("✅ All lectures already have embeddings!")
            return
        
        lectures = result.data
        total = len(lectures)
        
        logger.info(f"Found {total} lecture(s) to process")
        
        success_count = 0
        error_count = 0
        
        # Process in batches
        for i in range(0, total, batch_size):
            batch = lectures[i:i + batch_size]
            
            logger.info(f"\nProcessing batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size}")
            
            # Process batch concurrently
            tasks = [
                generate_embeddings_for_lecture(lecture["id"], force)
                for lecture in batch
            ]
            
            results = await asyncio.gather(*tasks)
            
            success_count += sum(results)
            error_count += len(results) - sum(results)
            
            logger.info(f"Batch complete. Success: {sum(results)}/{len(results)}")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Embedding generation complete!")
        logger.info(f"Total lectures: {total}")
        logger.info(f"✅ Success: {success_count}")
        logger.info(f"❌ Errors: {error_count}")
        logger.info(f"{'='*60}")
    
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate embeddings for lectures to enable RAG-based chatbot"
    )
    parser.add_argument(
        "--lecture-id",
        type=str,
        help="Generate embeddings for a specific lecture (UUID)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate embeddings even if they already exist"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of lectures to process concurrently (default: 10)"
    )
    
    args = parser.parse_args()
    
    logger.info("Starting embedding generation...")
    logger.info(f"Force regenerate: {args.force}")
    
    if args.lecture_id:
        # Generate for specific lecture
        logger.info(f"Processing single lecture: {args.lecture_id}")
        success = await generate_embeddings_for_lecture(args.lecture_id, args.force)
        
        if success:
            logger.info("✅ Embedding generation complete!")
            sys.exit(0)
        else:
            logger.error("❌ Embedding generation failed!")
            sys.exit(1)
    else:
        # Generate for all lectures
        logger.info(f"Processing all lectures (batch size: {args.batch_size})")
        await generate_all_embeddings(args.force, args.batch_size)
        logger.info("✅ Batch processing complete!")


if __name__ == "__main__":
    asyncio.run(main())

