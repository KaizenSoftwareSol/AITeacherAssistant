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
from utils.id_converter import IDConverter


class EmbeddingService:
    """Service for creating and managing lecture embeddings."""
    
    def __init__(self, db=None):
        """Initialize the embedding service."""
        self.db = db
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dimension = 1536
        self.chunk_size = 1000  # characters
        self.chunk_overlap = 200  # characters
    
    async def generate_embeddings_for_lecture(
        self, 
        lecture_id: str, 
        lecture_content: str,
        include_source_material: bool = True
    ) -> dict:
        """
        Generate embeddings for a lecture by chunking the content and creating vectors.
        
        OPTIMIZED VERSION:
        - Batch embedding API calls (up to 100 texts per call vs 1)
        - Larger database batch inserts (100 vs 10)
        - Reduced logging overhead
        
        This generates embeddings for BOTH:
        1. The generated lecture content
        2. The original source material (PDFs/documents) the lecture was based on
        
        Args:
            lecture_id: UUID of the lecture
            lecture_content: Full text content of the lecture
            include_source_material: Whether to also embed source documents (default True)
            
        Returns:
            Dictionary with chunk and embedding counts
        """
        try:
            # Convert UUID to integer ID if needed
            lecture_int_id = lecture_id
            if IDConverter.is_uuid(lecture_id):
                lecture_int_id = await IDConverter.uuid_to_int(self.db, "lecture", lecture_id)
                if not lecture_int_id:
                    raise ValueError(f"Lecture {lecture_id} not found")
            
            logger.info(f"Starting embedding generation for lecture {lecture_id}")
            
            # Chunk the generated lecture content
            lecture_chunks = self._chunk_text(lecture_content)
            # Tag these as LECTURE_CONTENT
            for chunk in lecture_chunks:
                chunk["type"] = "LECTURE_CONTENT"
            logger.info(f"Created {len(lecture_chunks)} lecture content chunks")
            
            # Also get and chunk the source material if requested
            source_chunks = []
            if include_source_material and self.db:
                source_chunks = await self._get_source_material_chunks(lecture_id)
                logger.info(f"Created {len(source_chunks)} source material chunks")
            
            # Combine all chunks
            chunks = lecture_chunks + source_chunks
            total_chunks = len(chunks)
            logger.info(f"Total chunks to embed: {total_chunks}")
            
            if total_chunks == 0:
                logger.warning("No chunks to embed")
                return {
                    "lecture_id": lecture_id,
                    "chunks_created": 0,
                    "embeddings_created": 0,
                    "embedding_model": self.embedding_model,
                }
            
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            # OPTIMIZATION 1: Generate all chunk records first (with IDs)
            now = datetime.utcnow().isoformat()
            chunk_records = []
            chunk_id_map = {}  # Map chunk index to chunk_id
            
            for idx, chunk_data in enumerate(chunks):
                chunk_uuid = str(uuid4())
                chunk_id_map[idx] = chunk_uuid
                chunk_records.append({
                    "uuid": chunk_uuid,  # Store UUID for external use
                    "lecture_id": lecture_int_id,  # Integer FK
                    "chunk_index": idx,
                    "content": chunk_data["content"],
                    "chunk_type": chunk_data.get("type", "CONTENT"),
                    "tokens_count": chunk_data.get("tokens", 0),
                    "chunk_metadata": json.dumps(chunk_data.get("metadata", {})),
                    "created_at": now,
                    "updated_at": now,
                })
            
            # OPTIMIZATION 2: Batch embedding API calls (100 texts per call)
            # OpenAI allows up to 2048 inputs, but 100 is a good balance
            EMBEDDING_BATCH_SIZE = 100
            all_embeddings = []
            
            logger.info(f"Generating embeddings in batches of {EMBEDDING_BATCH_SIZE}...")
            
            for i in range(0, total_chunks, EMBEDDING_BATCH_SIZE):
                batch_texts = [chunks[j]["content"] for j in range(i, min(i + EMBEDDING_BATCH_SIZE, total_chunks))]
                
                response = await client.embeddings.create(
                    model=self.embedding_model,
                    input=batch_texts,
                )
                
                # Extract embeddings in order
                for emb_data in response.data:
                    all_embeddings.append(emb_data.embedding)
                
                batch_num = (i // EMBEDDING_BATCH_SIZE) + 1
                total_batches = (total_chunks + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE
                logger.info(f"Generated embedding batch {batch_num}/{total_batches} ({len(batch_texts)} embeddings)")
            
            # Create embedding records
            embedding_records = []
            for idx, embedding_vector in enumerate(all_embeddings):
                embedding_uuid = str(uuid4())
                # chunk_id_map contains UUIDs, but we need integer chunk_id for FK
                # Get the chunk record to find its integer ID
                chunk_uuid = chunk_id_map[idx]
                embedding_records.append({
                    "uuid": embedding_uuid,  # Store UUID for external use
                    "lecture_id": lecture_int_id,  # Integer FK
                    "chunk_id": chunk_uuid,  # Will be converted to integer by database or use UUID lookup
                    "embedding": embedding_vector,
                    "embedding_model": self.embedding_model,
                    "created_at": now,
                })
            
            # OPTIMIZATION 3: Larger database batch inserts
            if self.db:
                DB_BATCH_SIZE = 100  # Increased from 10 to 100
                
                # Insert all chunks in larger batches and get their integer IDs
                logger.info(f"Inserting {len(chunk_records)} chunks...")
                chunk_uuid_to_int_id = {}  # Map UUID to integer ID
                for i in range(0, len(chunk_records), DB_BATCH_SIZE):
                    batch = chunk_records[i:i + DB_BATCH_SIZE]
                    result = self.db.admin_client.table("lecture_chunk").insert(batch).execute()
                    # Map UUIDs to integer IDs from inserted records
                    for record in result.data:
                        chunk_uuid = record.get("uuid")
                        chunk_int_id = record.get("id")
                        if chunk_uuid and chunk_int_id:
                            chunk_uuid_to_int_id[chunk_uuid] = chunk_int_id
                
                logger.info(f"Inserted {len(chunk_records)} chunks")
                
                # Update embedding records with integer chunk_ids
                for emb_record in embedding_records:
                    chunk_uuid = emb_record["chunk_id"]
                    chunk_int_id = chunk_uuid_to_int_id.get(chunk_uuid)
                    if chunk_int_id:
                        emb_record["chunk_id"] = chunk_int_id  # Use integer FK
                    else:
                        logger.warning(f"Could not find integer ID for chunk UUID {chunk_uuid}")
                
                # Insert all embeddings in larger batches
                logger.info(f"Inserting {len(embedding_records)} embeddings...")
                for i in range(0, len(embedding_records), DB_BATCH_SIZE):
                    batch = embedding_records[i:i + DB_BATCH_SIZE]
                    self.db.admin_client.table("lecture_embedding").insert(batch).execute()
                
                logger.info(f"Inserted {len(embedding_records)} embeddings")
                
                # Update lecture has_embeddings flag
                self.db.admin_client.table("lecture").update({
                    "has_embeddings": True,
                    "updated_at": now
                }).eq("id", lecture_int_id).execute()
            
            logger.info(f"Completed embedding generation for lecture {lecture_id}")
            
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
    
    async def _get_source_material_chunks(self, lecture_id: str) -> List[dict]:
        """
        Get and chunk the source material (original documents) for a lecture.
        
        This retrieves the original PDF/document content that the lecture was
        generated from, allowing the AI to answer based on both the lecture
        AND the source material.
        
        Args:
            lecture_id: UUID of the lecture
            
        Returns:
            List of chunk dictionaries from source documents
        """
        source_chunks = []
        
        try:
            # Convert UUID to integer ID if needed
            lecture_int_id = lecture_id
            if IDConverter.is_uuid(lecture_id):
                lecture_int_id = await IDConverter.uuid_to_int(self.db, "lecture", lecture_id)
                if not lecture_int_id:
                    logger.warning(f"Lecture {lecture_id} not found for source material extraction")
                    return []
            
            # Get the lecture to find the source document(s)
            lecture_result = (
                self.db.admin_client.table("lecture")
                .select("document_id, title, description")
                .eq("id", lecture_int_id)
                .execute()
            )
            
            if not lecture_result.data:
                logger.warning(f"Lecture {lecture_id} not found for source material extraction")
                return []
            
            lecture = lecture_result.data[0]
            document_id = lecture.get("document_id")
            lecture_title = lecture.get("title", "Unknown")
            
            logger.info(f"Lecture '{lecture_title}' (id: {lecture_id}) has document_id: {document_id}")
            
            if not document_id:
                logger.info(f"No source document linked to lecture '{lecture_title}' (id: {lecture_id}) - lecture may have been created from text input")
                return []
            
            # Convert document_id to integer if it's a UUID
            document_int_id = document_id
            if IDConverter.is_uuid(str(document_id)):
                document_int_id = await IDConverter.uuid_to_int(self.db, "documents", str(document_id))
                if not document_int_id:
                    logger.warning(f"Document {document_id} not found")
                    return []
            
            logger.info(f"Fetching source document {document_id} for lecture '{lecture_title}'")
            
            # Get the document and its content
            doc_result = (
                self.db.admin_client.table("documents")
                .select("id, title, content_json_path")
                .eq("id", document_int_id)
                .execute()
            )
            
            if not doc_result.data:
                logger.warning(f"Document {document_id} not found in database")
                return []
            
            document = doc_result.data[0]
            content_json_path = document.get("content_json_path")
            doc_title = document.get("title", "Unknown")
            
            logger.info(f"Document '{doc_title}': content_json_path={content_json_path}")
            
            if not content_json_path:
                logger.warning(f"No content_json_path for document {document_id} ('{doc_title}')")
                return []
            
            # Fetch the parsed content JSON from storage
            try:
                from supabase_config import supabase, BUCKETS
                import json as json_module
                
                logger.info(f"Downloading content from storage bucket '{BUCKETS['USER_UPLOADS']}': {content_json_path}")
                
                # Download the content JSON from storage (documents are stored in USER_UPLOADS bucket)
                bucket = supabase.get_storage_bucket(BUCKETS["USER_UPLOADS"])
                content_bytes = bucket.download(content_json_path)
                content_data = json_module.loads(content_bytes.decode('utf-8'))
                
                logger.info(f"Downloaded content JSON, keys: {list(content_data.keys()) if isinstance(content_data, dict) else 'not a dict'}")
                
                # Extract text content from the parsed document
                source_text = self._extract_text_from_document_content(content_data)
                
                if source_text:
                    logger.info(f"Extracted {len(source_text)} characters of text from document")
                    # Chunk the source material
                    raw_chunks = self._chunk_text(source_text)
                    
                    # Tag these chunks as SOURCE_MATERIAL
                    for chunk in raw_chunks:
                        chunk["type"] = "SOURCE_MATERIAL"
                        chunk["metadata"]["source_document_id"] = document_id
                        chunk["metadata"]["source_document_title"] = doc_title
                    
                    source_chunks.extend(raw_chunks)
                    logger.info(f"Extracted {len(raw_chunks)} chunks from source document '{doc_title}'")
                else:
                    logger.warning(f"No text could be extracted from document content (document: {document_id})")
                
            except Exception as storage_error:
                logger.warning(f"Could not fetch source document content from storage: {storage_error}")
                import traceback
                logger.debug(f"Storage error traceback: {traceback.format_exc()}")
        
        except Exception as e:
            logger.error(f"Error getting source material chunks: {str(e)}")
            import traceback
            logger.debug(f"Error traceback: {traceback.format_exc()}")
        
        return source_chunks
    
    def _extract_text_from_document_content(self, content_data: dict) -> str:
        """
        Extract plain text from parsed document content JSON.
        
        Args:
            content_data: Parsed document content (chapters, sections, etc.)
            
        Returns:
            Combined text content as a single string
        """
        text_parts = []
        
        try:
            # Handle different document content formats
            if isinstance(content_data, dict):
                # Check for chapters list structure
                if "chapters" in content_data and isinstance(content_data["chapters"], list):
                    for chapter in content_data.get("chapters", []):
                        if isinstance(chapter, dict):
                            # Add chapter title
                            if chapter.get("title"):
                                text_parts.append(f"\n\n## {chapter['title']}\n")
                            # Add chapter content
                            if chapter.get("content") and isinstance(chapter["content"], str):
                                text_parts.append(chapter["content"])
                            # Add sections
                            for section in chapter.get("sections", []):
                                if isinstance(section, dict):
                                    if section.get("title"):
                                        text_parts.append(f"\n### {section['title']}\n")
                                    if section.get("content") and isinstance(section["content"], str):
                                        text_parts.append(section["content"])
                
                # Check for pages structure (common in PDF parsing)
                elif "pages" in content_data:
                    for page in content_data.get("pages", []):
                        if isinstance(page, dict) and page.get("content"):
                            text_parts.append(page["content"])
                        elif isinstance(page, str):
                            text_parts.append(page)
                
                # Check for sections structure
                elif "sections" in content_data:
                    for section in content_data.get("sections", []):
                        if isinstance(section, dict):
                            if section.get("title"):
                                text_parts.append(f"\n### {section['title']}\n")
                            if section.get("content") and isinstance(section["content"], str):
                                text_parts.append(section["content"])
                
                # Check for content field that is a dict of chapters (chapter_name -> {content: "..."})
                # Structure: {"content": {"Chapter 1: Title": {"content": "text..."}, ...}}
                elif "content" in content_data and isinstance(content_data["content"], dict):
                    content_dict = content_data["content"]
                    for chapter_name, chapter_data in content_dict.items():
                        # Add chapter title
                        text_parts.append(f"\n\n## {chapter_name}\n")
                        # Extract content from nested structure
                        if isinstance(chapter_data, dict):
                            if chapter_data.get("content") and isinstance(chapter_data["content"], str):
                                text_parts.append(chapter_data["content"])
                            elif chapter_data.get("text") and isinstance(chapter_data["text"], str):
                                text_parts.append(chapter_data["text"])
                        elif isinstance(chapter_data, str):
                            text_parts.append(chapter_data)
                
                # Check for raw content as string
                elif "content" in content_data and isinstance(content_data["content"], str):
                    text_parts.append(content_data["content"])
                
                # Check for text field
                elif "text" in content_data and isinstance(content_data["text"], str):
                    text_parts.append(content_data["text"])
            
            elif isinstance(content_data, str):
                text_parts.append(content_data)
            
            elif isinstance(content_data, list):
                for item in content_data:
                    if isinstance(item, str):
                        text_parts.append(item)
                    elif isinstance(item, dict) and item.get("content") and isinstance(item["content"], str):
                        text_parts.append(item["content"])
        
        except Exception as e:
            logger.error(f"Error extracting text from document content: {str(e)}")
        
        return "\n\n".join(text_parts)
    
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
            # Convert UUID to integer ID if needed
            lecture_int_id = lecture_id
            if IDConverter.is_uuid(lecture_id):
                lecture_int_id = await IDConverter.uuid_to_int(self.db, "lecture", lecture_id)
                if not lecture_int_id:
                    raise ValueError(f"Lecture {lecture_id} not found")
            elif isinstance(lecture_id, str):
                try:
                    lecture_int_id = int(lecture_id)
                except ValueError:
                    raise ValueError(f"Invalid lecture_id format: {lecture_id}")
            
            # Check if embeddings exist for this lecture
            embedding_count = (
                self.db.admin_client.table("lecture_embedding")
                .select("id", count="exact")
                .eq("lecture_id", lecture_int_id)
                .execute()
            )
            
            if embedding_count.count == 0:
                logger.warning(f"No embeddings found for lecture {lecture_id} (int_id: {lecture_int_id}). Embeddings must be generated first.")
                return []
            
            logger.info(f"Found {embedding_count.count} embeddings for lecture {lecture_id}, searching for similar chunks...")
            
            # Generate query embedding
            query_embedding = await self.generate_query_embedding(query)
            
            # Use PostgreSQL function for similarity search
            # Note: The search_lecture_chunks function expects integer lecture_id
            result = self.db.admin_client.rpc(
                "search_lecture_chunks",
                {
                    "p_lecture_id": lecture_int_id,  # Use integer ID
                    "p_query_embedding": query_embedding,
                    "p_limit": top_k,
                }
            ).execute()
            
            chunks_found = result.data if result.data else []
            logger.info(f"Found {len(chunks_found)} similar chunks for query: {query[:50]}...")
            return chunks_found
        
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
            # Convert UUID to integer ID if needed
            lecture_int_id = lecture_id
            if IDConverter.is_uuid(lecture_id):
                lecture_int_id = await IDConverter.uuid_to_int(self.db, "lecture", lecture_id)
                if not lecture_int_id:
                    logger.warning(f"Lecture {lecture_id} not found")
                    return
            
            # Delete embeddings (chunks will cascade)
            self.db.admin_client.table("lecture_embedding").delete().eq("lecture_id", lecture_int_id).execute()
            self.db.admin_client.table("lecture_chunk").delete().eq("lecture_id", lecture_int_id).execute()
            
            # Update lecture flag
            self.db.admin_client.table("lecture").update({
                "has_embeddings": False,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", lecture_int_id).execute()
            
            logger.info(f"Deleted embeddings for lecture {lecture_id}")
        
        except Exception as e:
            logger.error(f"Error deleting lecture embeddings: {str(e)}")
            raise

