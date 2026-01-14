# admin/models.py

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr


class DashboardStats(BaseModel):
    """Dashboard statistics for admin."""
    
    total_teachers: int
    total_students: int
    total_courses: int
    total_lectures: int


class TeacherSummary(BaseModel):
    """Summary of a teacher with course and lecture counts."""
    
    teacher_id: str
    user_id: str
    first_name: str
    last_name: str
    email: str
    department: Optional[str] = None
    specialization: Optional[str] = None
    total_courses: int
    total_lectures: int
    courses: List["CourseSummary"] = []


class CourseSummary(BaseModel):
    """Summary of a course with lecture count."""
    
    course_id: str
    course_name: str
    course_code: str
    total_lectures: int
    total_enrollments: int


class StudentSummary(BaseModel):
    """Summary of a student."""
    
    student_id: str  # University student ID
    user_id: str
    first_name: str
    last_name: str
    email: str
    year_of_study: Optional[int] = None
    total_enrollments: int
    enrollments: List["EnrollmentSummary"] = []


class EnrollmentSummary(BaseModel):
    """Summary of a student enrollment."""
    
    enrollment_id: str
    course_id: str
    course_name: str
    course_code: str
    semester_name: Optional[str] = None
    enrolled_at: datetime
    is_active: bool


class StudentCreateRequest(BaseModel):
    """Request model for creating a student by admin."""
    
    email: EmailStr
    username: str
    password: str
    first_name: str
    last_name: str
    student_id: str  # University student ID
    year_of_study: Optional[int] = None


class TeacherCreateRequest(BaseModel):
    """Request model for creating a teacher by admin."""
    
    email: EmailStr
    username: str
    password: str
    first_name: str
    last_name: str
    department: Optional[str] = None
    specialization: Optional[str] = None


class StudentEnrollmentRequest(BaseModel):
    """Request model for enrolling a student in a course."""
    
    student_id: str  # University student ID (not user_id)
    course_id: str
    semester_id: str


class StudentSearchResponse(BaseModel):
    """Response model for student search."""
    
    student: Optional[StudentSummary] = None
    found: bool


class CourseAssignmentRequest(BaseModel):
    """Request model for assigning a course to a teacher."""
    
    course_id: str
    teacher_user_id: str  # User ID of the teacher (not teacher profile ID)


# Update forward references
TeacherSummary.model_rebuild()
CourseSummary.model_rebuild()
StudentSummary.model_rebuild()
EnrollmentSummary.model_rebuild()
