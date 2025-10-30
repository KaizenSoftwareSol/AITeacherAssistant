# services/flashcard_service.py
"""
Service for generating flashcards from lecture content.
"""

import json

from logger import logger
from openai import AsyncOpenAI
from settings import settings


class FlashcardService:
    """Service for creating flashcards from lecture content."""
    
    def __init__(self, db=None):
        """Initialize the flashcard service."""
        self.db = db
    
    async def generate_flashcards_from_lecture(
        self,
        lecture_content: str,
        num_cards: int = 15,
        difficulty_mix: bool = True
    ) -> list[dict]:
        """
        Generate flashcards from lecture content using AI.
        
        Args:
            lecture_content: Full text content of the lecture
            num_cards: Number of flashcards to generate (default: 15)
            difficulty_mix: Mix of easy/medium/hard cards (default: True)
            
        Returns:
            List of flashcard dictionaries with question, answer, difficulty, topic
        """
        try:
            logger.info(f"Generating {num_cards} flashcards from lecture content")
            
            # Build prompt for flashcard generation
            prompt = self._build_flashcard_prompt(
                lecture_content=lecture_content,
                num_cards=num_cards,
                difficulty_mix=difficulty_mix
            )
            
            # Generate flashcards using OpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",  # Use mini for cost efficiency
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert educational content creator.
Create 6 flashcards for the lecture.
Create clear, concise flashcards that:
- Test key concepts and understanding
- Have focused, single-concept questions
- Provide clear, brief answers (2-3 sentences max)
- Use active recall principles
- Include a mix of difficulties if requested
- Cover different topics from the lecture
- Return valid JSON format"""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            flashcards_data = json.loads(response.choices[0].message.content)
            flashcards = flashcards_data.get("flashcards", [])
            
            logger.info(f"Generated {len(flashcards)} flashcards")
            
            return flashcards
        
        except Exception as e:
            logger.error(f"Error generating flashcards: {str(e)}")
            raise
    
    def _build_flashcard_prompt(
        self,
        lecture_content: str,
        num_cards: int,
        difficulty_mix: bool
    ) -> str:
        """Build the prompt for flashcard generation."""
        
        # Truncate content if too long (keep first 4000 chars for context)
        max_content_length = 4000
        if len(lecture_content) > max_content_length:
            content_sample = lecture_content[:max_content_length] + "..."
        else:
            content_sample = lecture_content
        
        difficulty_instruction = ""
        if difficulty_mix:
            difficulty_instruction = """
- Create a mix of difficulties:
  * ~40% EASY (basic facts, definitions)
  * ~40% MEDIUM (application, understanding)
  * ~20% HARD (analysis, synthesis)
"""
        
        prompt = f"""Generate {num_cards} flashcards from this lecture content.

LECTURE CONTENT:
{content_sample}

REQUIREMENTS:
- Create exactly {num_cards} flashcards
- Each question should be clear and focused on ONE concept
- Answers should be concise (2-3 sentences maximum)
- Cover the main topics from the lecture
- Questions should test understanding, not just memorization
{difficulty_instruction}
- Assign a topic/category to each card for grouping

Return JSON in this EXACT format:
{{
  "flashcards": [
    {{
      "question": "Clear, focused question here?",
      "answer": "Concise answer in 2-3 sentences maximum.",
      "difficulty": "EASY|MEDIUM|HARD",
      "topic": "Topic name"
    }}
  ]
}}

IMPORTANT:
- Keep answers SHORT and to the point
- Questions should be answerable from lecture content
- Use clear, simple language
- Each card should stand alone"""
        
        return prompt

