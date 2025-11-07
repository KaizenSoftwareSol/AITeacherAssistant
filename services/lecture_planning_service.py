# services/lecture_planning_service.py

import json
from typing import Optional

from openai import AsyncOpenAI

from logger import logger
from settings import settings


class LecturePlanningService:
    """
    Service for generating comprehensive lecture plans for teachers.
    
    This service takes generated lecture content and creates a detailed
    teaching plan including activities, quizzes, discussion questions,
    time allocations, and pedagogical strategies.
    """

    @staticmethod
    async def generate_lecture_plan(
        lecture_content: str,
        lecture_title: str,
        lecture_description: Optional[str] = None,
        learning_outcomes: Optional[str] = None,
    ) -> dict:
        """
        Generate a comprehensive lecture plan for teachers.
        
        Args:
            lecture_content: The full generated lecture content
            lecture_title: Title of the lecture
            lecture_description: Teacher's description/overview (optional)
            learning_outcomes: Learning outcomes for students (optional)
            
        Returns:
            Dictionary containing structured lecture plan with activities,
            quizzes, timing, and teaching strategies
        """
        try:
            logger.info(
                f"Generating lecture plan for: {lecture_title}"
            )
            
            # Build the prompt for lecture planning
            prompt = LecturePlanningService._build_planning_prompt(
                lecture_content,
                lecture_title,
                lecture_description,
                learning_outcomes,
            )
            
            # Call OpenAI API
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert educational consultant and 
instructional designer specializing in creating comprehensive, 
practical teaching plans for university and school teachers.

Your plans should be:
- Actionable and specific
- Time-conscious and realistic
- Engaging and interactive
- Aligned with learning objectives
- Include diverse teaching methods
- Return valid JSON format""",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            
            plan_data = json.loads(response.choices[0].message.content)
            
            logger.info(
                f"Successfully generated lecture plan for: {lecture_title}"
            )
            
            return plan_data
            
        except Exception as e:
            logger.error(f"Error generating lecture plan: {str(e)}")
            raise
    
    @staticmethod
    def _build_planning_prompt(
        lecture_content: str,
        lecture_title: str,
        lecture_description: Optional[str],
        learning_outcomes: Optional[str],
    ) -> str:
        """Build the prompt for lecture planning generation."""
        
        # Add optional sections
        description_section = ""
        if lecture_description:
            description_section = f"""
**Lecture Description/Overview:**
{lecture_description}
"""
        
        outcomes_section = ""
        if learning_outcomes:
            outcomes_section = f"""
**Learning Outcomes:**
{learning_outcomes}
"""
        
        # Truncate lecture content if too long (keep first 15000 chars)
        truncated_content = lecture_content[:15000]
        if len(lecture_content) > 15000:
            truncated_content += "\n\n[... content truncated ...]"
        
        prompt = f"""You are creating a comprehensive teaching plan for a teacher 
who will deliver the following lecture. The teacher needs a structured plan 
with activities, quizzes, discussion questions, timing, and pedagogical strategies.

---

**Lecture Title:** {lecture_title}
{description_section}{outcomes_section}
**Full Lecture Content:**
{truncated_content}

---

Based on this lecture, create a comprehensive **Lecture Teaching Plan** in JSON 
format with the following structure:

```json
{{
  "lecture_title": "Title of the lecture",
  "estimated_duration_minutes": 60,
  "overview": "Brief 2-3 sentence overview of the teaching plan",
  "preparation": {{
    "materials_needed": ["List of materials, handouts, or resources needed"],
    "pre_class_preparation": ["Tasks teacher should do before class"],
    "student_prerequisites": ["What students should know/do before class"]
  }},
  "lesson_structure": [
    {{
      "phase": "Introduction/Warm-up/Main Content/Activity/Assessment/Conclusion",
      "duration_minutes": 10,
      "objectives": ["What this phase aims to achieve"],
      "activities": [
        {{
          "title": "Activity name",
          "description": "Detailed description of the activity",
          "instructions": "Step-by-step instructions for the teacher",
          "student_interaction": "How students participate",
          "time_allocation": "5 minutes"
        }}
      ],
      "teaching_notes": ["Tips and suggestions for the teacher"]
    }}
  ],
  "discussion_questions": [
    {{
      "question": "Thought-provoking question",
      "purpose": "Why ask this question",
      "expected_depth": "surface/medium/deep"
    }}
  ],
  "formative_assessments": [
    {{
      "type": "Quick Quiz/Poll/Think-Pair-Share/Exit Ticket",
      "description": "What and how to assess",
      "timing": "When to use it during the lecture",
      "questions": ["Specific questions to ask"]
    }}
  ],
  "suggested_activities": [
    {{
      "activity_name": "Name of the activity",
      "activity_type": "Individual/Pair/Group/Class Discussion/Hands-on",
      "description": "Full description",
      "duration": "10-15 minutes",
      "learning_objective": "What students will learn/practice",
      "materials": ["What's needed"],
      "instructions": "Step-by-step guide"
    }}
  ],
  "quiz_questions": [
    {{
      "question": "Multiple choice or short answer question",
      "type": "multiple_choice/short_answer/true_false",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Correct option or answer",
      "explanation": "Why this is the correct answer",
      "difficulty": "easy/medium/hard",
      "covers_topic": "Which part of lecture this tests"
    }}
  ],
  "differentiation_strategies": [
    {{
      "for_struggling_students": ["Strategies to support struggling learners"],
      "for_advanced_students": ["Ways to challenge advanced learners"],
      "for_diverse_learners": ["Adaptations for different learning styles"]
    }}
  ],
  "homework_suggestions": [
    {{
      "assignment": "Description of homework",
      "purpose": "Why assign this",
      "estimated_time": "How long it should take",
      "resources": ["Links or materials needed"]
    }}
  ],
  "key_takeaways": ["Main points students should remember"],
  "common_misconceptions": [
    {{
      "misconception": "What students often get wrong",
      "correction": "How to address it"
    }}
  ],
  "additional_resources": [
    {{
      "resource_type": "Video/Article/Book/Website/Interactive Tool",
      "title": "Resource name",
      "description": "What it offers",
      "recommended_use": "How and when to use it"
    }}
  ],
  "reflection_prompts": [
    "Questions for teacher to reflect on after class"
  ]
}}
```

---

**Important Instructions:**

1. Make the plan **realistic and actionable** - teachers should be able to 
   follow it directly
2. Include **specific timing** for each phase and activity
3. Provide **at least 5-8 quiz questions** covering the main concepts
4. Include **at least 3-5 engaging activities** (mix of individual, pair, 
   and group work)
5. Add **5-8 discussion questions** that promote critical thinking
6. Suggest **formative assessments** throughout the lecture
7. Include **differentiation strategies** for diverse learners
8. Provide **specific teaching notes and tips**
9. Align everything with the lecture content and learning outcomes
10. Make sure the total duration is reasonable (typically 45-90 minutes)

Generate a complete, detailed teaching plan now in valid JSON format.
"""
        
        return prompt

