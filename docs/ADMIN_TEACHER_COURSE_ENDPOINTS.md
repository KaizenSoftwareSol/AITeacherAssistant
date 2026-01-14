# Admin Teacher & Course Endpoints - Frontend Integration Guide

## Overview

We've added two new endpoints for admins:
1. **Create Teacher** - Allows admins to add new teachers to their university
2. **List University Courses** - Allows admins to view all courses in their university (for filtering students by course)

## New API Endpoints

### 1. Create Teacher

**Endpoint:** `POST /api/v1/admin/teachers/create`

**Authentication:** Required (Admin only)

**Description:** Create a new teacher account in the admin's university. Admin can sign up teachers and share credentials with them.

**Request Body:**
```json
{
  "email": "teacher@university.edu",
  "username": "teacher_username",
  "password": "secure_password",
  "first_name": "John",
  "last_name": "Doe",
  "department": "Computer Science",  // Optional
  "specialization": "Machine Learning"  // Optional
}
```

**Response (201 Created):**
```json
{
  "message": "Teacher account created successfully",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "teacher@university.edu",
  "username": "teacher_username"
}
```

**Error Responses:**
- `400 Bad Request`: Email or username already exists, or validation error
- `500 Internal Server Error`: Failed to create teacher account

**Example Request:**
```javascript
const response = await fetch('/api/v1/admin/teachers/create', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    email: 'teacher@university.edu',
    username: 'teacher_username',
    password: 'secure_password',
    first_name: 'John',
    last_name: 'Doe',
    department: 'Computer Science',
    specialization: 'Machine Learning'
  })
});

const result = await response.json();
```

---

### 2. List University Courses

**Endpoint:** `GET /api/v1/admin/courses`

**Authentication:** Required (Admin only)

**Description:** Get all courses in the admin's university. This endpoint is specifically designed for admins to view all courses for filtering students by course. Returns courses with enrollment counts.

**Query Parameters:** None (uses admin's university from authentication)

**Response:**
```json
[
  {
    "id": "course-uuid",
    "name": "Introduction to Computer Science",
    "code": "CS101",
    "description": "Basic computer science concepts",
    "curriculum_content": "...",
    "university_id": "university-uuid",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "total_enrollments": 45
  },
  {
    "id": "course-uuid-2",
    "name": "Data Structures",
    "code": "CS201",
    "description": "Advanced data structures",
    "curriculum_content": "...",
    "university_id": "university-uuid",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "total_enrollments": 32
  }
]
```

**Error Responses:**
- `500 Internal Server Error`: Error fetching courses

**Example Request:**
```javascript
const response = await fetch('/api/v1/admin/courses', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});

const courses = await response.json();
```

---

## Important Notes

### For Student Filtering Page

**Problem Solved:** The frontend was calling `/api/v1/teacher/courses` from an admin session, which was returning 404 because:
- That endpoint requires a teacher profile
- Admins don't have teacher profiles

**Solution:** Use the new `/api/v1/admin/courses` endpoint instead. This endpoint:
- Works specifically for admins
- Returns all courses in the admin's university
- Includes enrollment counts for each course
- Can be used for filtering students by course

### Implementation Example

```javascript
// In your admin student page component
const [courses, setCourses] = useState([]);
const [selectedCourse, setSelectedCourse] = useState(null);

// Fetch courses on component mount
useEffect(() => {
  const fetchCourses = async () => {
    try {
      const response = await fetch('/api/v1/admin/courses', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await response.json();
      setCourses(data);
    } catch (error) {
      console.error('Error fetching courses:', error);
    }
  };
  
  fetchCourses();
}, []);

// Filter students by course
const filteredStudents = selectedCourse
  ? students.filter(student => 
      student.enrollments.some(e => e.course_id === selectedCourse.id)
    )
  : students;
```

## Integration Points

### Create Teacher Endpoint
- **Teacher Management Page**: Add a "Create Teacher" button/form
- **Modal/Dialog**: Use a form similar to the student creation form
- **Success Handling**: Show success message and refresh teacher list

### List Courses Endpoint
- **Student Management Page**: Use for course filter dropdown
- **Student Filtering**: Filter students by selected course
- **Course Selection**: Display course name and enrollment count in filter

## Testing Checklist

### Create Teacher
- [ ] Create teacher with all fields (should succeed)
- [ ] Create teacher with optional fields missing (should succeed)
- [ ] Attempt to create teacher with existing email (should fail with 400)
- [ ] Attempt to create teacher with existing username (should fail with 400)
- [ ] Verify teacher appears in teacher list after creation

### List Courses
- [ ] Fetch courses as admin (should return all university courses)
- [ ] Verify courses include enrollment counts
- [ ] Test filtering students by course
- [ ] Verify empty array if no courses exist
- [ ] Test with proper authentication token
- [ ] Test with invalid/expired token (should fail)

---

**Questions?** Contact the backend team for clarification or additional support.
