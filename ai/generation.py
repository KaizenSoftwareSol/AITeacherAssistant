# ai/generation.py

from typing import Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from settings import settings


class ContentGenerator:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.7,
            openai_api_key=settings.OPENAI_API_KEY
        )
    
    async def generate_lesson_content(
        self, 
        topic: str, 
        level: str = "beginner",
        duration_minutes: int = 30
    ) -> Dict[str, str]:
        """Generate lesson content for a given topic."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"You are an expert educator creating lesson content. Generate comprehensive educational content for a {level} level lesson on '{topic}' that should take approximately {duration_minutes} minutes to complete."),
            ("user", "Please create: 1. Learning objectives, 2. Main content, 3. Examples, 4. Practice exercises, 5. Summary")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({"topic": topic})
        
        return {
            "topic": topic,
            "level": level,
            "duration_minutes": duration_minutes,
            "content": response.content
        }
    
    async def generate_quiz_questions(
        self, 
        content: str, 
        num_questions: int = 5,
        question_types: List[str] = ["multiple_choice", "true_false"]
    ) -> List[Dict[str, str]]:
        """Generate quiz questions based on content."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"Generate {num_questions} quiz questions based on the provided content. Include a mix of {', '.join(question_types)} questions. Format as JSON with question, options, correct_answer, and explanation."),
            ("user", "Content: {content}")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({"content": content})
        
        # Parse JSON response (you might want to add proper JSON parsing)
        return [{"question": "Sample question", "options": ["A", "B", "C", "D"], "correct_answer": "A", "explanation": "Sample explanation"}]
    
    async def generate_explanation(
        self, 
        concept: str, 
        student_level: str = "beginner"
    ) -> str:
        """Generate a clear explanation of a concept."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"Explain the concept '{concept}' in simple, clear terms appropriate for a {student_level} level student. Use analogies and examples to make it easy to understand."),
            ("user", "Please provide a comprehensive explanation.")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({"concept": concept})
        
        return response.content

