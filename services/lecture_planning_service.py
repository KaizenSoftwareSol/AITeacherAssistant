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

You create teaching plans for lectures that need to be engaging, informative, 
self-explanatory, clearly understandable, and include examples and analogies 
to meaningfully explain concepts to students at an undergraduate level.

Your plans should be:
- Actionable and specific - teachers should be able to follow directly
- Time-conscious and realistic with specific timing for each phase
- Engaging and interactive with a mix of individual, pair, and group activities
- Aligned with learning objectives and outcomes
- Include diverse teaching methods and differentiation strategies
- Provide suggested answers with examples and analogies for discussion questions
- Include specific teaching notes, bullet points, and examples teachers can use
- Return valid JSON format

CRITICAL: Always output complete, valid JSON. Never truncate the response.""",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=16000,
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
who will deliver the following lecture at an undergraduate level. The teacher needs 
a structured plan with activities, quizzes, discussion questions, timing, and 
pedagogical strategies. The lecture needs to be engaging, informative, self-explanatory, 
clearly understandable, and shall include examples and analogies to meaningfully 
explain concepts to the students.

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
      "teaching_notes": [
        {{
          "tip": "Brief teaching tip or suggestion",
          "key_bullet_points": [
            "Clear, concise bullet point the teacher can use to explain the concept",
            "Another bullet point covering a different aspect",
            "Additional point with specific detail or fact"
          ],
          "expandable_examples": [
            {{
              "context": "When to use this example",
              "example": "Detailed, specific real-world example the teacher can share with students",
              "analogy": "Optional: a relatable analogy to help students understand",
              "cultural_context": "Optional: cultural/regional context if applicable"
            }}
          ]
        }}
      ],
      "talking_points": [
        {{
          "point": "Key concept or idea to emphasize",
          "explanation": "How to explain this point clearly and thoroughly",
          "bullet_points_for_teacher": [
            "Specific fact or detail to mention",
            "Another key point to cover",
            "Additional information that adds clarity"
          ],
          "analogies": [
            {{
              "analogy": "A relatable analogy that makes the concept easier to understand",
              "how_to_present": "How the teacher should introduce this analogy"
            }}
          ],
          "concrete_examples": [
            {{
              "title": "Example title/label",
              "description": "Specific, detailed example illustrating this point (e.g., 'Alcohol is legal in Western countries but considered Haram and illegal in many Islamic nations like Saudi Arabia and Iran')",
              "why_it_helps": "Why this example aids understanding",
              "discussion_prompt": "Optional question to engage students about this example"
            }}
          ]
        }}
      ]
    }}
  ],
  "discussion_questions": [
    {{
      "question": "Thought-provoking question that promotes critical thinking",
      "purpose": "Why ask this question and what thinking it promotes",
      "expected_depth": "surface/medium/deep",
      "suggested_answer": {{
        "key_points": ["Main points the answer should cover"],
        "example_response": "A model answer that demonstrates good critical thinking",
        "examples_and_analogies": [
          "Specific example or analogy to help contextualize the students' thinking pattern",
          "Another example from a different perspective or context"
        ],
        "follow_up_prompts": ["Questions to deepen the discussion if needed"]
      }}
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
   follow it directly without additional preparation
2. Include **specific timing** for each phase and activity (in minutes)
3. Provide **at least 5-8 quiz questions** covering the main concepts with 
   clear explanations of correct answers
4. Include **at least 3-5 engaging activities** (mix of individual, pair, 
   and group work) with step-by-step instructions
5. Add **5-8 discussion questions** that promote critical thinking. For each 
   question, **suggest answers which include examples and analogies** to help 
   contextualize the students' thinking patterns
6. Suggest **formative assessments** throughout the lecture to check understanding
7. Include **differentiation strategies** for diverse learners (struggling, 
   advanced, and different learning styles)
8. Provide **specific teaching notes and tips**, which also include **bullet 
   points or examples the teacher can give** to explain a certain concept 
   thoroughly and clearly
9. Align everything with the lecture content and learning outcomes
10. Make sure the total duration is reasonable (typically 45-90 minutes)

**CRITICAL - EXPANDABLE EXAMPLES IN TEACHING NOTES:**

11. For EACH phase in lesson_structure, provide **detailed talking_points** with 
    **concrete_examples** that teachers can expand/reveal and share with students.
    
12. These examples MUST be:
    - **Specific and detailed** - not generic suggestions like "use examples from 
      different cultures" but actual examples like:
      * "Alcohol is legal and socially accepted in Western countries, but in 
        Islamic nations like Saudi Arabia and Iran, it is considered Haram 
        (forbidden) and is illegal"
      * "Same-sex marriage is recognized as a fundamental right in many Western 
        democracies, but is prohibited under Islamic law in countries like 
        Pakistan and Malaysia"
      * "Capital punishment is abolished in most of Europe but actively practiced 
        in the United States, China, and Saudi Arabia"
    - **Culturally diverse** - include examples from different regions, religions, 
      legal systems, and perspectives
    - **Ready to use** - teachers should be able to read them directly to students
    - **Discussion-provoking** - include optional prompts to engage students

13. Each teaching_note should have the structure:
    - "tip": Brief advice for the teacher
    - "expandable_examples": Array of specific examples the teacher can reveal/expand

14. Each talking_point should include:
    - "point": The key concept
    - "explanation": How to explain it
    - "concrete_examples": Array of 2-3 specific, detailed, ready-to-use examples

Generate a complete, detailed teaching plan now in valid JSON format.
"""
        
        return prompt

