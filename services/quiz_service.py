# services/quiz_service.py
"""
Service for generating and grading quizzes from lecture content.
"""

import json
from typing import Dict, List, Optional

from logger import logger
from settings import settings


class QuizService:
    """Service for quiz generation and grading."""
    
    def __init__(self, db):
        """Initialize the quiz service."""
        self.db = db
    
    async def generate_quiz_from_lecture(
        self,
        lecture_id: str,
        lecture_content: str,
        num_questions: int = 10,
        question_types: Optional[List[str]] = None,
        difficulty: str = "MEDIUM",
        focus_areas: Optional[List[str]] = None,
    ) -> dict:
        """
        Generate a quiz from lecture content using AI.
        
        Args:
            lecture_id: UUID of the lecture
            lecture_content: Full text content of the lecture
            num_questions: Number of questions to generate
            question_types: List of question types (e.g., ["MULTIPLE_CHOICE", "TRUE_FALSE"])
            difficulty: Difficulty level (EASY, MEDIUM, HARD)
            focus_areas: Specific topics to focus on
            
        Returns:
            Dictionary with quiz questions
        """
        try:
            logger.info(f"Generating quiz for lecture {lecture_id}, {num_questions} questions")
            
            # Default to multiple choice if not specified
            if not question_types:
                question_types = ["MULTIPLE_CHOICE"]
            
            # Build prompt for quiz generation
            prompt = self._build_quiz_generation_prompt(
                lecture_content=lecture_content,
                num_questions=num_questions,
                question_types=question_types,
                difficulty=difficulty,
                focus_areas=focus_areas,
            )
            
            # Generate quiz using OpenAI
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert educational assessment creator. Generate high-quality quiz questions that:
- Test understanding, not just memorization
- Are clear and unambiguous
- Have plausible distractors for multiple choice
- Cover key concepts from the material
- Match the requested difficulty level
- Return valid JSON format"""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )
            
            quiz_data = json.loads(response.choices[0].message.content)
            
            logger.info(f"Generated {len(quiz_data.get('questions', []))} questions for lecture {lecture_id}")
            
            return quiz_data
        
        except Exception as e:
            logger.error(f"Error generating quiz: {str(e)}")
            raise
    
    def _build_quiz_generation_prompt(
        self,
        lecture_content: str,
        num_questions: int,
        question_types: List[str],
        difficulty: str,
        focus_areas: Optional[List[str]],
    ) -> str:
        """Build the prompt for quiz generation."""
        
        # Truncate lecture content if too long (keep first ~4000 words)
        words = lecture_content.split()
        if len(words) > 4000:
            truncated_content = " ".join(words[:4000]) + "\n\n[Content truncated...]"
        else:
            truncated_content = lecture_content
        
        prompt = f"""Generate a {difficulty.lower()} difficulty quiz with {num_questions} questions based on the following lecture content.

Lecture Content:
{truncated_content}

Requirements:
- Generate exactly {num_questions} questions
- Question types: {', '.join(question_types)}
- Difficulty: {difficulty}
"""
        
        if focus_areas:
            prompt += f"- Focus on these topics: {', '.join(focus_areas)}\n"
        
        prompt += """
Return a JSON object with this structure:
{
  "questions": [
    {
      "question_text": "The question text",
      "question_type": "MULTIPLE_CHOICE",
      "points": 1.0,
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Option B",
      "explanation": "Brief explanation of why this is correct"
    }
  ]
}

For TRUE_FALSE questions, use options: ["True", "False"]
For SHORT_ANSWER questions, omit the options field and provide a sample correct answer.
"""
        
        return prompt
    
    def grade_submission(
        self,
        questions: List[dict],
        student_answers: Dict[str, str],
    ) -> dict:
        """
        Grade a quiz submission.
        
        Args:
            questions: List of question dictionaries from database
            student_answers: Dictionary mapping question_id to student's answer
            
        Returns:
            Dictionary with grading results
        """
        try:
            total_questions = len(questions)
            correct_count = 0
            total_points = 0
            earned_points = 0
            question_results = []
            topic_performance = {}  # Track performance by topic
            
            # Normalize student_answers keys: keep original + add int and str variants
            # so that {"333": "True"} matches question id 333 regardless of type
            normalized_answers = {}
            for k, v in student_answers.items():
                normalized_answers[str(k)] = v  # string key
                try:
                    normalized_answers[int(k)] = v  # int key
                except (ValueError, TypeError):
                    pass

            for question in questions:
                question_uuid = question.get("uuid") or ""
                question_int_id = question.get("id", "")
                question_id = question_int_id  # Keep integer ID for response

                correct_answer = question["correct_answer"]
                # Try all possible key forms: int id, string id, uuid
                student_answer = (
                    normalized_answers.get(question_int_id, "")
                    or normalized_answers.get(str(question_int_id), "")
                    or normalized_answers.get(str(question_uuid), "")
                )
                points = question.get("points", 1.0)
                total_points += points
                
                # Check if answer is correct
                is_correct = self._check_answer(
                    student_answer=student_answer,
                    correct_answer=correct_answer,
                    question_type=question["question_type"],
                )
                
                if is_correct:
                    correct_count += 1
                    earned_points += points
                
                # Parse options for display
                options = None
                if question.get("options"):
                    try:
                        options = json.loads(question["options"]) if isinstance(question["options"], str) else question["options"]
                    except:
                        options = None
                
                # Use UUID in response if available, otherwise use integer ID as string
                response_question_id = question.get("uuid") or str(question_id) if question_id else ""
                
                question_result = {
                    "question_id": response_question_id,
                    "question_text": question["question_text"],
                    "question_type": question["question_type"],
                    "student_answer": student_answer,
                    "correct_answer": correct_answer,
                    "is_correct": is_correct,
                    "points_earned": points if is_correct else 0,
                    "points_possible": points,
                    "explanation": question.get("explanation"),
                    "options": options,
                }
                question_results.append(question_result)
                
                # Track topic performance (extract from question text - simplified)
                # In a real app, you'd have topics stored with questions
                if not is_correct:
                    # Extract first few words as "topic" for weak areas
                    words = question["question_text"].split()[:5]
                    topic = " ".join(words) + "..."
                    topic_performance[topic] = topic_performance.get(topic, 0) + 1
            
            # Identify weak areas (topics with wrong answers)
            weak_areas = [
                {"topic": topic, "wrong_count": count}
                for topic, count in sorted(
                    topic_performance.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]  # Top 5 weak areas
            ]
            
            return {
                "total_questions": total_questions,
                "correct_count": correct_count,
                "score": earned_points,
                "max_score": total_points,
                "percentage": (earned_points / total_points * 100) if total_points > 0 else 0,
                "question_results": question_results,
                "weak_areas": weak_areas,
            }
        
        except Exception as e:
            logger.error(f"Error grading submission: {str(e)}")
            raise
    
    def _check_answer(
        self,
        student_answer: str,
        correct_answer: str,
        question_type: str,
    ) -> bool:
        """
        Check if a student's answer is correct.
        
        Args:
            student_answer: The student's answer
            correct_answer: The correct answer
            question_type: Type of question
            
        Returns:
            True if answer is correct
        """
        # Normalize answers for comparison
        student_answer = str(student_answer).strip().lower()
        correct_answer = str(correct_answer).strip().lower()
        
        if question_type in ["MULTIPLE_CHOICE", "TRUE_FALSE"]:
            # Exact match for multiple choice and true/false
            return student_answer == correct_answer
        
        elif question_type == "SHORT_ANSWER":
            # For short answer, check if key terms are present
            # This is simplified - in production, you'd use NLP or manual grading
            return student_answer == correct_answer or correct_answer in student_answer
        
        elif question_type == "FILL_IN_BLANK":
            # Exact match for fill in blank
            return student_answer == correct_answer
        
        else:
            # Default to exact match
            return student_answer == correct_answer
    
    async def analyze_quiz_performance(
        self,
        student_id: str,
        lecture_id: str,
    ) -> dict:
        """
        Analyze a student's quiz performance for a lecture.
        
        Args:
            student_id: UUID of the student
            lecture_id: UUID of the lecture
            
        Returns:
            Dictionary with performance analytics
        """
        try:
            # Convert UUIDs to integer IDs for database queries
            from utils.id_converter import IDConverter
            
            student_int_id = student_id
            if isinstance(student_id, str):
                if IDConverter.is_uuid(student_id):
                    student_int_id = await IDConverter.uuid_to_int(self.db, "student", student_id)
                else:
                    try:
                        student_int_id = int(student_id)
                    except ValueError:
                        student_int_id = None
            
            lecture_int_id = lecture_id
            if isinstance(lecture_id, str):
                if IDConverter.is_uuid(lecture_id):
                    lecture_int_id = await IDConverter.uuid_to_int(self.db, "lecture", lecture_id)
                else:
                    try:
                        lecture_int_id = int(lecture_id)
                    except ValueError:
                        lecture_int_id = None
            
            if not student_int_id or not lecture_int_id:
                return {
                    "total_attempts": 0,
                    "best_score": 0,
                    "average_score": 0,
                    "improvement": 0,
                }
            
            # Get all quiz submissions for this student and lecture
            submissions = (
                self.db.admin_client.table("assessment_submission")
                .select("*, assessment!inner(lecture_id)")
                .eq("student_id", student_int_id)  # Use integer ID
                .eq("assessment.lecture_id", lecture_int_id)  # Use integer ID
                .eq("is_graded", True)
                .order("submitted_at", desc=True)
                .execute()
            )
            
            if not submissions.data:
                return {
                    "total_attempts": 0,
                    "best_score": 0,
                    "average_score": 0,
                    "improvement": 0,
                }
            
            scores = [sub["score"] / sub["max_score"] * 100 for sub in submissions.data]
            
            return {
                "total_attempts": len(submissions.data),
                "best_score": max(scores),
                "average_score": sum(scores) / len(scores),
                "latest_score": scores[0] if scores else 0,
                "improvement": scores[0] - scores[-1] if len(scores) > 1 else 0,
            }
        
        except Exception as e:
            logger.error(f"Error analyzing quiz performance: {str(e)}")
            return {}

