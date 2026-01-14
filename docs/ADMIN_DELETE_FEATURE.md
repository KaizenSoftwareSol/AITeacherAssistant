# Admin Delete Feature - Frontend Integration Guide

## Overview

Admins can now delete teachers and students from their university through the admin interface. This feature allows university admins to manage their institution's user base by removing teachers and students when needed.

## New API Endpoints

### Delete Teacher

**Endpoint:** `DELETE /api/v1/admin/teachers/{user_id}`

**Authentication:** Required (Admin only)

**Description:** Deletes a teacher from the admin's university. This action is permanent and will cascade delete the teacher's profile and related data.

**Path Parameters:**
- `user_id` (string, UUID): The user ID of the teacher to delete

**Response:**
```json
{
  "message": "Teacher deleted successfully"
}
```

**Error Responses:**
- `404 Not Found`: User not found or teacher profile not found
- `400 Bad Request`: User is not a teacher
- `403 Forbidden`: Teacher does not belong to admin's university
- `500 Internal Server Error`: Failed to delete teacher

**Example Request:**
```javascript
const response = await fetch('/api/v1/admin/teachers/123e4567-e89b-12d3-a456-426614174000', {
  method: 'DELETE',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});

const result = await response.json();
```

---

### Delete Student

**Endpoint:** `DELETE /api/v1/admin/students/{user_id}`

**Authentication:** Required (Admin only)

**Description:** Deletes a student from the admin's university. This action is permanent and will cascade delete the student's profile, enrollments, and related data.

**Path Parameters:**
- `user_id` (string, UUID): The user ID of the student to delete

**Response:**
```json
{
  "message": "Student deleted successfully",
  "student_id": "STU12345"
}
```

**Error Responses:**
- `404 Not Found`: User not found or student profile not found
- `400 Bad Request`: User is not a student
- `403 Forbidden`: Student does not belong to admin's university
- `500 Internal Server Error`: Failed to delete student

**Example Request:**
```javascript
const response = await fetch('/api/v1/admin/students/123e4567-e89b-12d3-a456-426614174000', {
  method: 'DELETE',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});

const result = await response.json();
```

## Security & Validation

- **University Scoping**: Admins can only delete teachers and students from their own university. Attempts to delete users from other universities will return a `403 Forbidden` error.
- **Role Verification**: The system verifies that the user being deleted is actually a teacher or student before proceeding.
- **Cascade Deletion**: Deleting a user will automatically remove:
  - User account
  - Teacher/Student profile
  - For students: All course enrollments
  - Related data (cascade handled by database)

## Frontend Implementation Recommendations

### 1. Confirmation Dialog

**Important:** Always show a confirmation dialog before deleting, as this action is permanent and cannot be undone.

```javascript
const handleDeleteTeacher = async (teacherUserId) => {
  const confirmed = window.confirm(
    'Are you sure you want to delete this teacher? This action cannot be undone and will remove all associated data.'
  );
  
  if (!confirmed) return;
  
  try {
    const response = await deleteTeacher(teacherUserId);
    // Show success message
    // Refresh teacher list
  } catch (error) {
    // Show error message
  }
};
```

### 2. Error Handling

Handle all error cases appropriately:

```javascript
try {
  await deleteTeacher(userId);
} catch (error) {
  if (error.status === 403) {
    showError('You can only delete users from your own university');
  } else if (error.status === 404) {
    showError('User not found');
  } else if (error.status === 400) {
    showError('Invalid user type');
  } else {
    showError('Failed to delete user. Please try again.');
  }
}
```

### 3. UI Updates

After successful deletion:
- Remove the deleted user from the current list/view
- Show a success notification
- Optionally refresh the list to ensure consistency

### 4. Loading States

Show loading indicators during the delete operation:

```javascript
const [deleting, setDeleting] = useState(false);

const handleDelete = async (userId) => {
  setDeleting(true);
  try {
    await deleteTeacher(userId);
    // Success handling
  } finally {
    setDeleting(false);
  }
};
```

## Integration Points

These endpoints should be integrated into:
- **Teacher Management Page**: Add a delete button/action for each teacher in the list
- **Student Management Page**: Add a delete button/action for each student in the list
- **Student Search Results**: Allow deletion from search results if needed

## Notes

- The `user_id` parameter should be the UUID from the user record (not the teacher/student profile ID)
- You can get the `user_id` from the existing teacher/student list endpoints (`GET /api/v1/admin/teachers` and `GET /api/v1/admin/students`)
- Consider adding a "soft delete" or "archive" feature in the future if you need to preserve deleted user data

## Testing Checklist

- [ ] Delete teacher from same university (should succeed)
- [ ] Delete student from same university (should succeed)
- [ ] Attempt to delete teacher from different university (should fail with 403)
- [ ] Attempt to delete student from different university (should fail with 403)
- [ ] Attempt to delete non-existent user (should fail with 404)
- [ ] Verify cascade deletion works (enrollments, etc.)
- [ ] Test with proper authentication token
- [ ] Test with invalid/expired token (should fail)

---

**Questions?** Contact the backend team for clarification or additional support.
