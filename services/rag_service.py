# services/rag_service.py
"""
RAG (Retrieval-Augmented Generation) service for lecture chatbot.
"""

import json
from typing import List, Optional

from logger import logger
from services.embedding_service import EmbeddingService
from settings import settings


class RAGService:
    """Service for RAG-based question answering about lectures."""
    
    def __init__(self, db):
        """Initialize the RAG service."""
        self.db = db
        self.embedding_service = EmbeddingService(db)
        self.top_k_chunks = 8  # Increased to include both lecture content and source material chunks
    
    async def generate_response(
        self,
        lecture_id: str,
        query: str,
        conversation_id: Optional[str] = None,
    ) -> dict:
        """
        Generate a response to a query about a lecture using RAG.
        
        Args:
            lecture_id: UUID of the lecture
            query: Student's question
            conversation_id: Optional conversation ID for context
            
        Returns:
            Dictionary with answer and source information
        """
        try:
            logger.info(f"Generating RAG response for lecture {lecture_id}, query: {query[:50]}...")
            
            # Retrieve relevant chunks
            similar_chunks = await self.embedding_service.search_similar_chunks(
                lecture_id=lecture_id,
                query=query,
                top_k=self.top_k_chunks,
            )
            
            if not similar_chunks:
                logger.warning(f"No chunks found for lecture {lecture_id}. This usually means embeddings haven't been generated yet.")
                return {
                    "answer": "I don't have enough information from this lecture to answer that question. The lecture embeddings may not have been generated yet. Please ask your teacher to generate embeddings for this lecture, or try asking about something else covered in the lecture.",
                    "sources": [],
                    "similarity_scores": [],
                }
            
            # Build context from chunks
            context_parts = []
            sources = []
            similarity_scores = []
            
            for chunk in similar_chunks:
                # Get chunk type (LECTURE_CONTENT or SOURCE_MATERIAL)
                chunk_type = chunk.get("chunk_type", "LECTURE_CONTENT")
                
                # Add context label for the AI
                if chunk_type == "SOURCE_MATERIAL":
                    context_parts.append(f"[SOURCE MATERIAL]\n{chunk['chunk_content']}")
                else:
                    context_parts.append(f"[LECTURE CONTENT]\n{chunk['chunk_content']}")
                
                sources.append({
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": chunk["chunk_index"],
                    "chunk_type": chunk_type,  # Track whether from lecture or source
                    "preview": chunk["chunk_content"][:200] + "...",
                })
                similarity_scores.append(chunk["similarity_score"])
            
            context = "\n\n---\n\n".join(context_parts)
            
            # Get conversation history if available
            conversation_history = []
            if conversation_id:
                # conversation_id can be integer or UUID string
                conversation_int_id = conversation_id
                if isinstance(conversation_id, str):
                    from utils.id_converter import IDConverter
                    if IDConverter.is_uuid(conversation_id):
                        conversation_int_id = await IDConverter.uuid_to_int(self.db, "ai_conversation", conversation_id)
                    else:
                        try:
                            conversation_int_id = int(conversation_id)
                        except ValueError:
                            conversation_int_id = None
                
                if conversation_int_id:
                    history_result = (
                        self.db.admin_client.table("chat_message")
                        .select("role, content")
                        .eq("conversation_id", conversation_int_id)  # Use integer ID
                        .order("created_at")
                        .limit(10)  # Last 10 messages
                        .execute()
                    )
                else:
                    history_result = type('obj', (object,), {'data': []})()
                
                if history_result.data:
                    conversation_history = [
                        {"role": msg["role"].lower(), "content": msg["content"]}
                        for msg in history_result.data
                    ]
            
            # Generate response using OpenAI
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            # Build messages for the chat completion
            messages = [
                {
                    "role": "system",
                    "content": """You are a helpful AI teaching assistant. Your role is to help students understand lecture content by answering their questions based on BOTH the generated lecture material AND the original source documents the lecture was based on.

CRITICAL: Keep your responses CONCISE and to the point. Aim for 2-4 sentences for simple questions, and no more than 2-3 short paragraphs for complex questions. Students prefer quick, direct answers.

Guidelines:
- Answer questions based on the provided context, which includes:
  * LECTURE_CONTENT: The generated lecture as delivered by the teacher
  * SOURCE_MATERIAL: The original textbooks, PDFs, and documents the lecture was based on
- Be BRIEF and direct - get to the answer quickly without unnecessary elaboration
- If a question can be answered in one sentence, do so. Only expand if the question requires deeper explanation
- You can provide deeper information from source materials that may not be explicitly covered in the lecture, but keep it brief
- If the context doesn't contain enough information, briefly acknowledge this and suggest the student ask their teacher
- Use examples and analogies when helpful, but keep them short (1-2 sentences max)
- When information comes from source material that goes beyond the lecture, briefly mention "The source material also explains..." or "According to the textbook..."
- Encourage critical thinking with brief prompts
- If you see quiz results in the conversation history, focus on helping with weak areas concisely
- Be patient and supportive, but keep responses short and actionable

Remember: Students want quick answers. Be helpful but brief."""
                }
            ]
            
            # Add conversation history
            for msg in conversation_history[-6:]:  # Last 6 messages for context
                if msg["role"] in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            # Add current query with context
            messages.append({
                "role": "user",
                "content": f"""Based on the following lecture content, please answer my question.

Lecture Context:
{context}

My Question: {query}"""
            })
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",  # Use gpt-4o-mini for cost efficiency
                messages=messages,
                temperature=0.7,
                max_tokens=500,  # Reduced to encourage more concise responses
            )
            
            answer = response.choices[0].message.content
            
            logger.info(f"Generated RAG response for lecture {lecture_id}")
            
            return {
                "answer": answer,
                "sources": sources,
                "similarity_scores": similarity_scores,
                "chunks_used": len(similar_chunks),
            }
        
        except Exception as e:
            logger.error(f"Error generating RAG response: {str(e)}")
            raise
    
    async def generate_follow_up_suggestions(
        self,
        lecture_id: str,
        current_query: str,
        response: str,
    ) -> List[str]:
        """
        Generate suggested follow-up questions based on the current conversation.
        
        Args:
            lecture_id: UUID of the lecture
            current_query: The student's current question
            response: The AI's response
            
        Returns:
            List of suggested follow-up questions
        """
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            prompt = f"""Based on this Q&A exchange about a lecture, suggest 3 relevant follow-up questions the student might want to ask:

Student Question: {current_query}

AI Response: {response}

Generate 3 specific, relevant follow-up questions that would deepen the student's understanding. Return them as a JSON array of strings."""
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an educational AI that helps generate relevant follow-up questions for students."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=300,
            )
            
            suggestions_text = response.choices[0].message.content
            suggestions = json.loads(suggestions_text)
            
            return suggestions[:3]  # Return up to 3 suggestions
        
        except Exception as e:
            logger.error(f"Error generating follow-up suggestions: {str(e)}")
            return []

