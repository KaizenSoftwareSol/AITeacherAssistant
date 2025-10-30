# services/embedding_service.py
"""
Service for generating and managing lecture embeddings for RAG.
"""

import json
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from logger import logger
from settings import settings


class EmbeddingService:
    """Service for creating and managing lecture embeddings."""
    
    def __init__(self, db=None):
        """Initialize the embedding service."""
        self.db = db
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dimension = 1536
        self.chunk_size = 1000  # characters
        self.chunk_overlap = 200  # characters
    
    async def generate_embeddings_for_lecture(self, lecture_id: str, lecture_content: str) -> dict:
        """
        Generate embeddings for a lecture by chunking the content and creating vectors.
        
        Args:
            lecture_id: UUID of the lecture
            lecture_content: Full text content of the lecture
            
        Returns:
            Dictionary with chunk and embedding counts
        """
        try:
            logger.info(f"Starting embedding generation for lecture {lecture_id}")
            
            # Chunk the lecture content
            chunks = self._chunk_text(lecture_content)
            logger.info(f"Created {len(chunks)} chunks for lecture {lecture_id}")
            
            # Generate embeddings for each chunk
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            chunk_records = []
            embedding_records = []
            
            for idx, chunk_data in enumerate(chunks):
                # Create chunk record
                chunk_id = str(uuid4())
                chunk_record = {
                    "id": chunk_id,
                    "lecture_id": lecture_id,
                    "chunk_index": idx,
                    "content": chunk_data["content"],
                    "chunk_type": chunk_data.get("type", "CONTENT"),
                    "tokens_count": chunk_data.get("tokens", 0),
                    "chunk_metadata": json.dumps(chunk_data.get("metadata", {})),
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
                chunk_records.append(chunk_record)
                
                # Generate embedding
                response = await client.embeddings.create(
                    model=self.embedding_model,
                    input=chunk_data["content"],
                )
                
                embedding_vector = response.data[0].embedding
                
                # Create embedding record
                embedding_record = {
                    "id": str(uuid4()),
                    "lecture_id": lecture_id,
                    "chunk_id": chunk_id,
                    "embedding": embedding_vector,  # pgvector will handle the conversion
                    "embedding_model": self.embedding_model,
                    "created_at": datetime.utcnow().isoformat(),
                }
                embedding_records.append(embedding_record)
            
            # Insert chunks and embeddings into database
            if self.db:
                # Insert chunks
                self.db.admin_client.table("lecture_chunk").insert(chunk_records).execute()
                logger.info(f"Inserted {len(chunk_records)} chunks for lecture {lecture_id}")
                
                # Insert embeddings
                self.db.admin_client.table("lecture_embedding").insert(embedding_records).execute()
                logger.info(f"Inserted {len(embedding_records)} embeddings for lecture {lecture_id}")
                
                # Update lecture has_embeddings flag
                self.db.admin_client.table("lecture").update({
                    "has_embeddings": True,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", lecture_id).execute()
            
            return {
                "lecture_id": lecture_id,
                "chunks_created": len(chunk_records),
                "embeddings_created": len(embedding_records),
                "embedding_model": self.embedding_model,
            }
        
        except Exception as e:
            logger.error(f"Error generating embeddings for lecture {lecture_id}: {str(e)}")
            raise
    
    def _chunk_text(self, text: str) -> List[dict]:
        """
        Split text into overlapping chunks for embedding.
        
        Args:
            text: Full text content to chunk
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []
        text_length = len(text)
        start = 0
        
        while start < text_length:
            # Calculate end position
            end = start + self.chunk_size
            
            # If this is not the last chunk, try to break at a sentence boundary
            if end < text_length:
                # Look for sentence endings near the chunk boundary
                sentence_ends = ['.', '!', '?', '\n\n']
                best_break = end
                
                # Search backwards from end for a good break point
                for i in range(end, max(start + self.chunk_size - 100, start), -1):
                    if i < text_length and text[i] in sentence_ends:
                        best_break = i + 1
                        break
                
                end = best_break
            
            # Extract chunk
            chunk_content = text[start:end].strip()
            
            if chunk_content:
                # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
                tokens = len(chunk_content) // 4
                
                chunks.append({
                    "content": chunk_content,
                    "type": "CONTENT",
                    "tokens": tokens,
                    "metadata": {
                        "start_pos": start,
                        "end_pos": end,
                        "length": len(chunk_content),
                    }
                })
            
            # Move to next chunk with overlap
            start = end - self.chunk_overlap
            if start >= text_length:
                break
        
        return chunks
    
    async def generate_query_embedding(self, query: str) -> List[float]:
        """
        Generate embedding for a query string.
        
        Args:
            query: Query text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = await client.embeddings.create(
                model=self.embedding_model,
                input=query,
            )
            
            return response.data[0].embedding
        
        except Exception as e:
            logger.error(f"Error generating query embedding: {str(e)}")
            raise
    
    async def search_similar_chunks(
        self,
        lecture_id: str,
        query: str,
        top_k: int = 5
    ) -> List[dict]:
        """
        Search for the most similar chunks to a query using vector similarity.
        
        Args:
            lecture_id: UUID of the lecture to search in
            query: Query text
            top_k: Number of top results to return
            
        Returns:
            List of chunk dictionaries with similarity scores
        """
        try:
            # Generate query embedding
            query_embedding = await self.generate_query_embedding(query)
            
            # Use PostgreSQL function for similarity search
            # Note: The search_lecture_chunks function was created in the migration
            result = self.db.admin_client.rpc(
                "search_lecture_chunks",
                {
                    "p_lecture_id": lecture_id,
                    "p_query_embedding": query_embedding,
                    "p_limit": top_k,
                }
            ).execute()
            
            return result.data if result.data else []
        
        except Exception as e:
            logger.error(f"Error searching similar chunks: {str(e)}")
            raise
    
    async def delete_lecture_embeddings(self, lecture_id: str):
        """
        Delete all embeddings and chunks for a lecture.
        
        Args:
            lecture_id: UUID of the lecture
        """
        try:
            # Delete embeddings (chunks will cascade)
            self.db.admin_client.table("lecture_embedding").delete().eq("lecture_id", lecture_id).execute()
            self.db.admin_client.table("lecture_chunk").delete().eq("lecture_id", lecture_id).execute()
            
            # Update lecture flag
            self.db.admin_client.table("lecture").update({
                "has_embeddings": False,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", lecture_id).execute()
            
            logger.info(f"Deleted embeddings for lecture {lecture_id}")
        
        except Exception as e:
            logger.error(f"Error deleting lecture embeddings: {str(e)}")
            raise

