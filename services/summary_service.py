# services/summary_service.py
"""
Service for generating lecture summaries.
"""

from logger import logger
from settings import settings


class SummaryService:
    """Service for generating lecture summaries."""
    
    async def generate_lecture_summary(self, lecture_content: str, max_length: int = 500) -> str:
        """
        Generate a concise summary of lecture content using AI.
        
        Args:
            lecture_content: Full text content of the lecture
            max_length: Maximum length of summary in words
            
        Returns:
            Summary text
        """
        try:
            logger.info("Generating lecture summary")
            
            # Truncate content if too long (keep first ~3000 words)
            words = lecture_content.split()
            if len(words) > 3000:
                truncated_content = " ".join(words[:3000]) + "\n\n[Content truncated...]"
            else:
                truncated_content = lecture_content
            
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            prompt = f"""Generate a clear and concise summary of the following lecture content. The summary should:
- Be approximately {max_length} words
- Cover the main topics and key concepts
- Be well-organized with bullet points or short paragraphs
- Help students quickly understand what the lecture covers
- Include the most important takeaways

Lecture Content:
{truncated_content}

Generate the summary:"""
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating clear, concise educational summaries that help students understand lecture content."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800,
            )
            
            summary = response.choices[0].message.content.strip()
            
            logger.info("Successfully generated lecture summary")
            return summary
        
        except Exception as e:
            logger.error(f"Error generating lecture summary: {str(e)}")
            raise
    
    async def generate_chapter_summary(self, chapter_content: str, chapter_name: str) -> str:
        """
        Generate a summary for a specific chapter or section.
        
        Args:
            chapter_content: Content of the chapter
            chapter_name: Name of the chapter
            
        Returns:
            Chapter summary
        """
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            prompt = f"""Summarize the following chapter in 2-3 concise paragraphs:

Chapter: {chapter_name}

Content:
{chapter_content}

Summary:"""
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating educational chapter summaries."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=400,
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"Error generating chapter summary: {str(e)}")
            raise
    
    async def generate_key_points(self, lecture_content: str, num_points: int = 5) -> list:
        """
        Extract key points from lecture content.
        
        Args:
            lecture_content: Full text content of the lecture
            num_points: Number of key points to extract
            
        Returns:
            List of key points
        """
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            # Truncate content if too long
            words = lecture_content.split()
            if len(words) > 2000:
                truncated_content = " ".join(words[:2000])
            else:
                truncated_content = lecture_content
            
            prompt = f"""Extract exactly {num_points} key points from the following lecture content. Each point should be:
- A single, clear sentence
- Capture an important concept or takeaway
- Be actionable or memorable for students

Lecture Content:
{truncated_content}

Return ONLY a JSON array of strings, like: ["Point 1", "Point 2", ...]"""
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You extract key educational points from lectures."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            # Handle different response formats
            if isinstance(result, dict) and "points" in result:
                return result["points"][:num_points]
            elif isinstance(result, dict) and "key_points" in result:
                return result["key_points"][:num_points]
            elif isinstance(result, list):
                return result[:num_points]
            else:
                return list(result.values())[:num_points]
        
        except Exception as e:
            logger.error(f"Error generating key points: {str(e)}")
            return []

