# Admin Course Creation - Frontend Integration Guide

## Overview

Admins can now create courses for their university, in addition to their existing capabilities of assigning courses to teachers and enrolling students. This provides complete course management functionality for university administrators.

## New Capability

**Admins can create courses** using the same endpoint that teachers use. The course will be created with `created_by_teacher_id = NULL` (since admins don't have teacher profiles), and admins can then assign these courses to teachers as needed.

## API Endpoint

### Create Course (Admin & Teacher)

**Endpoint:** `POST /api/v1/courses`

**Authentication:** Required (Teacher or Admin)

**Description:** Create a new course for the user's university. Available to both teachers and admins.

**Request Body:**
```json
{
  "name": "Introduction to Computer Science",
  "code": "CS101",  // Optional, 4-10 alphanumeric characters
  "description": "Basic computer science concepts",  // Optional
  "curriculum_content": "Full curriculum outline...",  // Optional
  "semester_name": "Fall 2024",  // Optional
  "semester_start_date": "2024-09-01",  // Optional, ISO date format
  "semester_end_date": "2024-12-15"  // Optional, ISO date format
}
```

**Response (201 Created):**
```json
{
  "message": "Course created successfully",
  "course": {
    "id": "course-uuid",
    "name": "Introduction to Computer Science",
    "code": "CS101",
    "description": "Basic computer science concepts",
    "curriculum_content": "Full curriculum outline...",
    "university_id": "university-uuid",
    "created_by_teacher_id": null,  // NULL for admin-created courses
    "created_at": "2024-01-14T10:00:00Z",
    "updated_at": "2024-01-14T10:00:00Z"
  },
  "semester": {  // Only if semester_name was provided
    "id": "semester-uuid",
    "name": "Fall 2024",
    "start_date": "2024-09-01",
    "end_date": "2024-12-15",
    "course_id": "course-uuid"
  }
}
```

**Error Responses:**
- `400 Bad Request`: 
  - Invalid course code format
  - Course code already exists
  - Admin not associated with a university
  - Teacher profile not found (for teachers)
- `500 Internal Server Error`: Failed to create course

**Example Request:**
```javascript
const response = await fetch('/api/v1/courses', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'Introduction to Computer Science',
    code: 'CS101',
    description: 'Basic computer science concepts',
    curriculum_content: 'Full curriculum outline...',
    semester_name: 'Fall 2024',
    semester_start_date: '2024-09-01',
    semester_end_date: '2024-12-15'
  })
});

const result = await response.json();
```

## Differences: Admin vs Teacher

### Admin-Created Courses
- `created_by_teacher_id` = `null`
- Course appears in admin's course list (`GET /api/v1/admin/courses`)
- Admin must assign course to teacher(s) for them to see it
- Use `POST /api/v1/admin/courses/assign` to assign to teachers

### Teacher-Created Courses
- `created_by_teacher_id` = `teacher.id`
- Course appears immediately in teacher's course list (`GET /api/v1/courses`)
- Teacher can start creating lectures right away

## Workflow for Admins

### Option 1: Create and Assign
1. Admin creates course → `POST /api/v1/courses`
2. Admin assigns course to teacher(s) → `POST /api/v1/admin/courses/assign`
3. Teacher sees course in their list and can start creating lectures

### Option 2: Create for Future Assignment
1. Admin creates course → `POST /api/v1/courses`
2. Course exists but not assigned to any teacher yet
3. Admin can assign later when teacher is ready

## Frontend Implementation Recommendations

### 1. Course Creation Form

Create a reusable course creation form that works for both admins and teachers:

```javascript
const CourseCreationForm = ({ userRole, onSuccess }) => {
  const [formData, setFormData] = useState({
    name: '',
    code: '',
    description: '',
    curriculum_content: '',
    semester_name: '',
    semester_start_date: '',
    semester_end_date: ''
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    try {
      const response = await fetch('/api/v1/courses', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create course');
      }

      const result = await response.json();
      
      // Show success message
      showSuccess('Course created successfully!');
      
      // If admin, optionally show assignment prompt
      if (userRole === 'ADMIN') {
        showInfo('Course created. You can now assign it to teachers.');
      }
      
      onSuccess(result);
    } catch (error) {
      showError(error.message);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Form fields */}
    </form>
  );
};
```

### 2. Admin-Specific UI Flow

After admin creates a course, provide options:

```javascript
const handleCourseCreated = (courseData) => {
  if (userRole === 'ADMIN') {
    // Show modal with options
    showModal({
      title: 'Course Created Successfully',
      message: 'What would you like to do next?',
      actions: [
        {
          label: 'Assign to Teacher',
          onClick: () => navigateToAssignment(courseData.id)
        },
        {
          label: 'View Course',
          onClick: () => navigateToCourse(courseData.id)
        },
        {
          label: 'Create Another',
          onClick: () => resetForm()
        }
      ]
    });
  } else {
    // Teacher flow - just navigate to course
    navigateToCourse(courseData.id);
  }
};
```

### 3. Integration Points

**Admin Dashboard:**
- Add "Create Course" button/action
- Show created courses in the courses list
- Provide quick access to assign courses to teachers

**Course Management Page:**
- Show all courses (created by admin or assigned to teachers)
- Filter by: All, Created by Me, Assigned to Teachers
- Quick actions: Assign, View, Edit (if implemented)

### 4. Error Handling

Handle specific error cases:

```javascript
try {
  await createCourse(courseData);
} catch (error) {
  if (error.status === 400) {
    if (error.detail.includes('code already exists')) {
      showError('Course code already exists. Please choose a different code.');
    } else if (error.detail.includes('university')) {
      showError('You must be associated with a university to create courses.');
    } else {
      showError(error.detail);
    }
  } else {
    showError('Failed to create course. Please try again.');
  }
}
```

### 5. Validation

**Client-Side Validation:**
- Course name: Required, 3-120 characters
- Course code: Optional, 4-10 alphanumeric characters (auto-uppercase)
- Semester dates: End date must be after start date

```javascript
const validateCourseCode = (code) => {
  if (!code) return true; // Optional
  if (!/^[A-Z0-9]+$/.test(code.toUpperCase())) {
    return 'Course code must contain only letters and numbers';
  }
  if (code.length < 4 || code.length > 10) {
    return 'Course code must be between 4 and 10 characters';
  }
  return true;
};
```

## Testing Checklist

- [ ] Admin can create course with all fields
- [ ] Admin can create course with minimal fields (name only)
- [ ] Admin can create course with semester information
- [ ] Course appears in admin's course list after creation
- [ ] Admin-created course has `created_by_teacher_id = null`
- [ ] Admin can assign created course to teacher
- [ ] Teacher sees assigned course in their list
- [ ] Validation errors display correctly
- [ ] Duplicate course code error handled
- [ ] Test with admin not associated with university (should fail)
- [ ] Test with teacher (should work as before)

## Related Endpoints

- `GET /api/v1/admin/courses` - List all courses in admin's university
- `POST /api/v1/admin/courses/assign` - Assign course to teacher
- `GET /api/v1/courses` - List courses (for teachers, shows assigned/created courses)
- `GET /api/v1/courses/{course_id}` - Get course details

## Notes

- **Course Code**: If not provided, the system will auto-generate a unique 6-character code
- **Semester**: Optional - can be added later if not provided during course creation
- **Cache**: Course lists are cached for 2 minutes. New courses may take a moment to appear
- **Permissions**: Admins can only create courses for their own university
- **Assignment**: Admin-created courses won't appear in teacher lists until assigned

## Example: Complete Admin Course Creation Flow

```javascript
// 1. Admin creates course
const course = await createCourse({
  name: 'Data Structures',
  code: 'CS201',
  description: 'Advanced data structures course',
  semester_name: 'Spring 2024'
});

// 2. Admin assigns to teacher
await assignCourseToTeacher({
  course_id: course.id,
  teacher_user_id: 'teacher-user-uuid'
});

// 3. Teacher now sees course in their list
// 4. Teacher can start creating lectures for the course
```

---

**Questions?** Contact the backend team for clarification or additional support.
