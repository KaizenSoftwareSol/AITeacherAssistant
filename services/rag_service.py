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
        self.top_k_chunks = 5
    
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
                logger.warning(f"No chunks found for lecture {lecture_id}")
                return {
                    "answer": "I don't have enough information from this lecture to answer that question. Could you rephrase or ask about something else covered in the lecture?",
                    "sources": [],
                    "similarity_scores": [],
                }
            
            # Build context from chunks
            context_parts = []
            sources = []
            similarity_scores = []
            
            for chunk in similar_chunks:
                context_parts.append(chunk["chunk_content"])
                sources.append({
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": chunk["chunk_index"],
                    "preview": chunk["chunk_content"][:200] + "...",
                })
                similarity_scores.append(chunk["similarity_score"])
            
            context = "\n\n---\n\n".join(context_parts)
            
            # Get conversation history if available
            conversation_history = []
            if conversation_id:
                history_result = (
                    self.db.admin_client.table("chat_message")
                    .select("role, content")
                    .eq("conversation_id", conversation_id)
                    .order("created_at")
                    .limit(10)  # Last 10 messages
                    .execute()
                )
                
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
                    "content": """You are a helpful AI teaching assistant. Your role is to help students understand lecture content by answering their questions based on the provided lecture material.

Guidelines:
- Answer questions based primarily on the provided lecture context
- Be clear, concise, and educational in your explanations
- If the context doesn't contain enough information, acknowledge this and suggest the student ask their teacher
- Use examples and analogies when helpful
- Encourage critical thinking
- If you see quiz results in the conversation history, focus on helping with weak areas
- Be patient and supportive"""
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
                max_tokens=1000,
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

