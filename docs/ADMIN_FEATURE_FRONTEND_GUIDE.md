# Admin/Institute Management Feature - Frontend Integration Guide

## Overview

We've implemented a comprehensive **Admin/Institute Management** feature that allows university administrators to manage teachers, students, and courses within their institution. This document provides all the information needed for frontend integration.

## Feature Description

Each university can have one or more **Admin users** who can:

- View dashboard statistics (total teachers, students, courses, lectures)
- View and manage all teachers in their university
- View teacher details including their courses and lecture counts
- View and manage all students in their university
- Search students by their university student ID
- Create new student accounts
- Enroll students in courses
- View course enrollments

**Important**: All admin operations are scoped to the admin's university. Admins can only see and manage data from their own university.

---

## Authentication & Authorization

### Requirements

1. **User Role**: The user must have `role: "ADMIN"` in their user profile
2. **University Association**: The admin user must have a `university_id` associated with their account
3. **JWT Token**: All endpoints require a valid JWT token in the Authorization header

### Authentication Header

All requests must include:

```
Authorization: Bearer <access_token>
```

### Error Responses

- **401 Unauthorized**: Invalid or missing token
- **403 Forbidden**: User is not an admin or doesn't have university association
- **400 Bad Request**: Admin user missing university_id

---

## API Endpoints

All admin endpoints are prefixed with: `/api/v1/admin`

### Base URL

```
/api/v1/admin
```

---

## 1. Dashboard Statistics

Get overview statistics for the admin's university.

### Endpoint

```
GET /api/v1/admin/dashboard/stats
```

### Response

```json
{
  "total_teachers": 15,
  "total_students": 250,
  "total_courses": 12,
  "total_lectures": 180
}
```

### Response Model

```typescript
interface DashboardStats {
  total_teachers: number;
  total_students: number;
  total_courses: number;
  total_lectures: number;
}
```

---

## 2. List Teachers

Get all teachers in the admin's university with their course and lecture information.

### Endpoint

```
GET /api/v1/admin/teachers?skip=0&limit=100
```

### Query Parameters

- `skip` (optional, default: 0): Number of records to skip
- `limit` (optional, default: 100): Maximum number of records to return

### Response

```json
[
  {
    "teacher_id": "uuid",
    "user_id": "uuid",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@university.edu",
    "department": "Computer Science",
    "specialization": "Machine Learning",
    "total_courses": 3,
    "total_lectures": 25,
    "courses": [
      {
        "course_id": "uuid",
        "course_name": "Introduction to AI",
        "course_code": "CS101",
        "total_lectures": 10,
        "total_enrollments": 45
      },
      {
        "course_id": "uuid",
        "course_name": "Advanced Machine Learning",
        "course_code": "CS401",
        "total_lectures": 15,
        "total_enrollments": 30
      }
    ]
  }
]
```

### Response Model

```typescript
interface TeacherSummary {
  teacher_id: string;
  user_id: string;
  first_name: string;
  last_name: string;
  email: string;
  department: string | null;
  specialization: string | null;
  total_courses: number;
  total_lectures: number;
  courses: CourseSummary[];
}

interface CourseSummary {
  course_id: string;
  course_name: string;
  course_code: string;
  total_lectures: number;
  total_enrollments: number;
}
```

---

## 3. List Students

Get all students in the admin's university with their enrollment information.

### Endpoint

```
GET /api/v1/admin/students?skip=0&limit=100
```

### Query Parameters

- `skip` (optional, default: 0): Number of records to skip
- `limit` (optional, default: 100): Maximum number of records to return

### Response

```json
[
  {
    "student_id": "STU2024001",
    "user_id": "uuid",
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane.smith@university.edu",
    "year_of_study": 2,
    "total_enrollments": 4,
    "enrollments": [
      {
        "enrollment_id": "uuid",
        "course_id": "uuid",
        "course_name": "Introduction to AI",
        "course_code": "CS101",
        "semester_name": "Fall 2024",
        "enrolled_at": "2024-09-01T10:00:00Z",
        "is_active": true
      }
    ]
  }
]
```

### Response Model

```typescript
interface StudentSummary {
  student_id: string; // University student ID (not UUID)
  user_id: string;
  first_name: string;
  last_name: string;
  email: string;
  year_of_study: number | null;
  total_enrollments: number;
  enrollments: EnrollmentSummary[];
}

interface EnrollmentSummary {
  enrollment_id: string;
  course_id: string;
  course_name: string;
  course_code: string;
  semester_name: string | null;
  enrolled_at: string; // ISO 8601 datetime
  is_active: boolean;
}
```

---

## 4. Search Student by ID

Search for a specific student by their university student ID.

### Endpoint

```
GET /api/v1/admin/students/search/{student_id}
```

### Path Parameters

- `student_id` (required): The university student ID (e.g., "STU2024001")

### Response (Found)

```json
{
  "found": true,
  "student": {
    "student_id": "STU2024001",
    "user_id": "uuid",
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane.smith@university.edu",
    "year_of_study": 2,
    "total_enrollments": 4,
    "enrollments": [
      // ... enrollment details
    ]
  }
}
```

### Response (Not Found)

```json
{
  "found": false,
  "student": null
}
```

### Response Model

```typescript
interface StudentSearchResponse {
  student: StudentSummary | null;
  found: boolean;
}
```

### Error Responses

- **404 Not Found**: Student not found in admin's university

---

## 5. Create Student Account

Create a new student account in the admin's university. The admin can then share the credentials with the student.

### Endpoint

```
POST /api/v1/admin/students/create
```

### Request Body

```json
{
  "email": "new.student@university.edu",
  "username": "newstudent",
  "password": "securePassword123",
  "first_name": "New",
  "last_name": "Student",
  "student_id": "STU2024002",
  "year_of_study": 1
}
```

### Request Model

```typescript
interface StudentCreateRequest {
  email: string;
  username: string;
  password: string;
  first_name: string;
  last_name: string;
  student_id: string; // University student ID (must be unique)
  year_of_study?: number | null; // Optional
}
```

### Response

```json
{
  "message": "Student account created successfully",
  "user_id": "uuid",
  "student_id": "STU2024002",
  "email": "new.student@university.edu",
  "username": "newstudent"
}
```

### Error Responses

- **400 Bad Request**: 
  - Student ID already exists in the university
  - Email or username already exists
  - Invalid input data

### Notes

- The student will be automatically associated with the admin's university
- The `student_id` must be unique within the university
- The password should be securely shared with the student (consider implementing a secure credential sharing mechanism)

---

## 6. Enroll Student in Course

Enroll a student in a course. Admin can enroll students from their university in any course from their university.

### Endpoint

```
POST /api/v1/admin/enrollments/create
```

### Request Body

```json
{
  "student_id": "STU2024001",
  "course_id": "uuid",
  "semester_id": "uuid"
}
```

### Request Model

```typescript
interface StudentEnrollmentRequest {
  student_id: string; // University student ID (not UUID)
  course_id: string; // Course UUID
  semester_id: string; // Semester UUID
}
```

### Response (New Enrollment)

```json
{
  "message": "Student enrolled in course successfully",
  "enrollment_id": "uuid",
  "course_name": "Introduction to AI",
  "course_code": "CS101"
}
```

### Response (Already Enrolled)

```json
{
  "message": "Student is already enrolled in this course",
  "enrollment_id": "uuid",
  "course_name": "Introduction to AI",
  "course_code": "CS101"
}
```

### Response (Re-enrolled)

```json
{
  "message": "Student re-enrolled in course successfully",
  "enrollment_id": "uuid",
  "course_name": "Introduction to AI",
  "course_code": "CS101"
}
```

### Error Responses

- **404 Not Found**: 
  - Student not found in admin's university
  - Course not found in admin's university
  - Semester not found for the course

### Notes

- If the student is already enrolled and active, returns success with existing enrollment
- If the student was previously enrolled but inactive, the enrollment is reactivated
- The `student_id` is the university student ID, not the database UUID

---

## 7. Get Course Enrollments

Get all students enrolled in a specific course.

### Endpoint

```
GET /api/v1/admin/courses/{course_id}/enrollments
```

### Path Parameters

- `course_id` (required): The course UUID

### Response

```json
[
  {
    "student_id": "STU2024001",
    "user_id": "uuid",
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane.smith@university.edu",
    "year_of_study": 2,
    "total_enrollments": 4,
    "enrollments": [
      // ... all enrollments for this student
    ]
  }
]
```

### Response Model

Returns an array of `StudentSummary` objects (same as List Students endpoint).

### Error Responses

- **404 Not Found**: Course not found in admin's university

---

## Error Handling

### Standard Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common HTTP Status Codes

- **200 OK**: Request successful
- **201 Created**: Resource created successfully
- **400 Bad Request**: Invalid input or business logic error
- **401 Unauthorized**: Invalid or missing authentication token
- **403 Forbidden**: User doesn't have required permissions
- **404 Not Found**: Resource not found
- **500 Internal Server Error**: Server error

---

## Frontend Implementation Recommendations

### 1. Admin Dashboard Page

Create a dashboard that displays:
- Statistics cards (teachers, students, courses, lectures)
- Quick actions (create student, enroll student)
- Recent activity or summary widgets

### 2. Teacher Management Page

- Table/list view of all teachers
- Expandable rows showing teacher's courses
- Filter/search functionality
- View teacher details modal/page

### 3. Student Management Page

- Table/list view of all students
- Search by student ID functionality
- Filter by year of study
- View student details with enrollments
- Create new student button/modal

### 4. Student Creation Form

Form fields:
- Email (required, must be valid email)
- Username (required, unique)
- Password (required, should enforce strength)
- First Name (required)
- Last Name (required)
- Student ID (required, unique within university)
- Year of Study (optional)

After creation, display credentials to admin for sharing with student.

### 5. Enrollment Management

- Course selection dropdown
- Semester selection (filtered by course)
- Student search/selection
- Bulk enrollment capability (future enhancement)

### 6. Course Enrollments View

- Display all enrolled students for a course
- Show student details and their other enrollments
- Option to remove enrollment (if needed in future)

---

## Example API Calls

### JavaScript/TypeScript Example

```typescript
// Get dashboard stats
const getDashboardStats = async (token: string) => {
  const response = await fetch('/api/v1/admin/dashboard/stats', {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  return response.json();
};

// List teachers
const listTeachers = async (token: string, skip = 0, limit = 100) => {
  const response = await fetch(
    `/api/v1/admin/teachers?skip=${skip}&limit=${limit}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  return response.json();
};

// Search student
const searchStudent = async (token: string, studentId: string) => {
  const response = await fetch(
    `/api/v1/admin/students/search/${studentId}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  return response.json();
};

// Create student
const createStudent = async (token: string, studentData: StudentCreateRequest) => {
  const response = await fetch('/api/v1/admin/students/create', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(studentData)
  });
  return response.json();
};

// Enroll student
const enrollStudent = async (token: string, enrollmentData: StudentEnrollmentRequest) => {
  const response = await fetch('/api/v1/admin/enrollments/create', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(enrollmentData)
  });
  return response.json();
};
```

---

## Important Notes

1. **University Scoping**: All admin operations are automatically scoped to the admin's university. Admins cannot see or manage data from other universities.

2. **Student ID vs User ID**: 
   - `student_id` refers to the university student ID (e.g., "STU2024001")
   - `user_id` refers to the database UUID
   - When enrolling or searching, use `student_id` (university ID)

3. **Semester Requirement**: When enrolling a student, you must provide a `semester_id`. You may need to fetch available semesters for a course first.

4. **Password Security**: When creating students, ensure passwords are:
   - Securely transmitted (HTTPS)
   - Stored securely if sharing with students
   - Consider implementing a secure credential sharing mechanism

5. **Pagination**: List endpoints support pagination with `skip` and `limit` parameters. Consider implementing infinite scroll or pagination controls.

6. **Error Handling**: Always handle errors gracefully and display user-friendly messages. Check for 401/403 errors to redirect to login if needed.

---

## Testing

### Test Admin User

To test the admin features, you'll need:
1. A user with `role: "ADMIN"`
2. The user must have a `university_id` set
3. Valid JWT token from login

### Test Scenarios

1. **Dashboard**: Verify statistics are accurate
2. **List Teachers**: Verify all teachers from university are shown
3. **List Students**: Verify all students from university are shown
4. **Search Student**: Test with valid and invalid student IDs
5. **Create Student**: Test with valid data and duplicate student IDs
6. **Enroll Student**: Test with valid and invalid course/semester combinations
7. **Course Enrollments**: Verify only students from the university are shown

---

## Support

If you have questions or encounter issues during integration, please contact the backend team.

---

## Changelog

- **2024**: Initial implementation of Admin/Institute Management feature
