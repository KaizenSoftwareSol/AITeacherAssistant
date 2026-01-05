#!/usr/bin/env python3
"""
Script to regenerate embeddings for existing lecture chunks.
This is useful when chunks exist but embeddings failed due to timeout.

Usage:
    python scripts/regenerate_lecture_embeddings.py <lecture_id>
    
Example:
    python scripts/regenerate_lecture_embeddings.py 2104f557-23dd-4df8-9ead-2c21e554537a
"""

import asyncio
import sys
import os
from uuid import uuid4
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI
from supabase_config import supabase
from settings import settings
from logger import logger


EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 10


async def regenerate_embeddings(lecture_id: str):
    """
    Regenerate embeddings for existing chunks of a lecture.
    
    This fetches all chunks for a lecture, generates embeddings via OpenAI,
    and saves them to the lecture_embedding table in batches.
    """
    print(f"\n{'='*60}")
    print(f"Regenerating embeddings for lecture: {lecture_id}")
    print(f"{'='*60}\n")
    
    # 1. Check if lecture exists
    lecture_result = supabase.admin_client.table("lecture").select("id, title, has_embeddings").eq("id", lecture_id).execute()
    
    if not lecture_result.data:
        print(f"ERROR: Lecture {lecture_id} not found!")
        return
    
    lecture = lecture_result.data[0]
    print(f"Lecture found: {lecture['title']}")
    print(f"Current has_embeddings: {lecture['has_embeddings']}")
    
    # 2. Get existing chunks
    chunks_result = supabase.admin_client.table("lecture_chunk").select("id, content, chunk_index").eq("lecture_id", lecture_id).order("chunk_index").execute()
    
    if not chunks_result.data:
        print(f"ERROR: No chunks found for lecture {lecture_id}!")
        print("You need to regenerate the lecture or run the full embedding generation.")
        return
    
    chunks = chunks_result.data
    print(f"Found {len(chunks)} existing chunks")
    
    # 3. Check existing embeddings
    existing_embeddings_result = supabase.admin_client.table("lecture_embedding").select("chunk_id").eq("lecture_id", lecture_id).execute()
    existing_chunk_ids = {e["chunk_id"] for e in (existing_embeddings_result.data or [])}
    print(f"Found {len(existing_chunk_ids)} existing embeddings")
    
    # Filter chunks that don't have embeddings yet
    chunks_to_embed = [c for c in chunks if c["id"] not in existing_chunk_ids]
    print(f"Chunks needing embeddings: {len(chunks_to_embed)}")
    
    if not chunks_to_embed:
        print("\nAll chunks already have embeddings!")
        # Update has_embeddings flag just in case
        supabase.admin_client.table("lecture").update({
            "has_embeddings": True,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", lecture_id).execute()
        print("Updated has_embeddings flag to True")
        return
    
    # 4. Generate embeddings
    print(f"\nGenerating embeddings using model: {EMBEDDING_MODEL}")
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    embedding_records = []
    
    for idx, chunk in enumerate(chunks_to_embed):
        print(f"  Generating embedding for chunk {idx + 1}/{len(chunks_to_embed)} (index: {chunk['chunk_index']})...", end=" ")
        
        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=chunk["content"],
            )
            
            embedding_vector = response.data[0].embedding
            
            embedding_record = {
                "id": str(uuid4()),
                "lecture_id": lecture_id,
                "chunk_id": chunk["id"],
                "embedding": embedding_vector,
                "embedding_model": EMBEDDING_MODEL,
                "created_at": datetime.utcnow().isoformat(),
            }
            embedding_records.append(embedding_record)
            print("✓")
            
        except Exception as e:
            print(f"✗ Error: {e}")
            continue
    
    print(f"\nGenerated {len(embedding_records)} embeddings")
    
    # 5. Insert embeddings in batches
    if embedding_records:
        print(f"\nInserting embeddings in batches of {BATCH_SIZE}...")
        
        for i in range(0, len(embedding_records), BATCH_SIZE):
            batch = embedding_records[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(embedding_records) + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"  Inserting batch {batch_num}/{total_batches} ({len(batch)} records)...", end=" ")
            
            try:
                supabase.admin_client.table("lecture_embedding").insert(batch).execute()
                print("✓")
            except Exception as e:
                print(f"✗ Error: {e}")
                continue
        
        print(f"\nSuccessfully inserted {len(embedding_records)} embeddings")
    
    # 6. Update lecture has_embeddings flag
    supabase.admin_client.table("lecture").update({
        "has_embeddings": True,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", lecture_id).execute()
    
    print(f"\n{'='*60}")
    print(f"DONE! Lecture '{lecture['title']}' now has embeddings.")
    print(f"Total chunks: {len(chunks)}")
    print(f"Total embeddings: {len(existing_chunk_ids) + len(embedding_records)}")
    print(f"{'='*60}\n")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/regenerate_lecture_embeddings.py <lecture_id>")
        print("\nExample:")
        print("  python scripts/regenerate_lecture_embeddings.py 2104f557-23dd-4df8-9ead-2c21e554537a")
        sys.exit(1)
    
    lecture_id = sys.argv[1]
    await regenerate_embeddings(lecture_id)


if __name__ == "__main__":
    asyncio.run(main())

