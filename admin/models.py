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


class BulkStudentSignupItem(BaseModel):
    """Individual student data for bulk signup."""
    
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    student_id: str  # University student ID
    year_of_study: Optional[int] = None


class BulkStudentSignupRequest(BaseModel):
    """Request model for bulk student signup with activation links."""
    
    students: List[BulkStudentSignupItem]
    default_password: str  # Temporary password for all students (they'll change it via activation link)


class BulkEnrollmentItem(BaseModel):
    """Individual enrollment data for bulk enrollment."""
    
    student_id: str  # University student ID
    email: Optional[EmailStr] = None  # Optional, will be fetched if not provided


class BulkEnrollmentRequest(BaseModel):
    """Request model for bulk student enrollment with enrollment links."""
    
    course_id: str
    semester_id: str
    students: List[BulkEnrollmentItem]


class BulkOperationResult(BaseModel):
    """Result of a bulk operation."""
    
    total: int
    successful: int
    failed: int
    errors: List[str] = []


class BulkSignupResponse(BaseModel):
    """Response model for bulk signup operation."""
    
    result: BulkOperationResult
    created_students: List[dict] = []  # List of created student info
    failed_students: List[dict] = []  # List of failed student info with errors


class BulkEnrollmentResponse(BaseModel):
    """Response model for bulk enrollment operation."""
    
    result: BulkOperationResult
    enrolled_students: List[dict] = []  # List of enrolled student info
    failed_students: List[dict] = []  # List of failed student info with errors


class SemesterCreateRequest(BaseModel):
    """Request model for creating a semester by admin."""
    
    name: str  # e.g., "Fall 2024", "Spring 2025"
    start_date: datetime
    end_date: datetime


class SemesterUpdateRequest(BaseModel):
    """Request model for updating a semester by admin."""
    
    name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class SemesterResponse(BaseModel):
    """Response model for semester."""
    
    id: str
    name: str
    start_date: datetime
    end_date: datetime
    university_id: str
    course_id: Optional[str] = None
    module_count: int = 0
    created_at: datetime
    updated_at: datetime


class LogoUploadResponse(BaseModel):
    """Response model for logo upload."""
    
    message: str
    logo_url: str
    logo_path: Optional[str] = None


class LogoGetResponse(BaseModel):
    """Response model for getting logo."""
    
    logo_url: Optional[str] = None
    has_custom_logo: bool
    default_logo_url: Optional[str] = None


class LogoDeleteResponse(BaseModel):
    """Response model for logo deletion."""
    
    message: str


# Update forward references
TeacherSummary.model_rebuild()
CourseSummary.model_rebuild()
StudentSummary.model_rebuild()
EnrollmentSummary.model_rebuild()
