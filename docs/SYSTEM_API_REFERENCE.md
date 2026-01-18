# System User API Reference

Complete API documentation for System User endpoints. System users manage universities and create admin users.

**Base URL:** `/api/v1/system`  
**Authentication:** All endpoints require `Authorization: Bearer <token>` header with a SYSTEM role user.

---

## Table of Contents

1. [University Endpoints](#university-endpoints)
   - [Create University](#1-create-university)
   - [List All Universities](#2-list-all-universities)
   - [Get University Details](#3-get-university-details)
   - [Delete University](#4-delete-university)

2. [Admin User Endpoints](#admin-user-endpoints)
   - [Create Admin User](#5-create-admin-user-for-university)
   - [List All Admins](#6-list-all-admins)
   - [Delete Admin User](#7-delete-admin-user)

---

## University Endpoints

### 1. Create University

**Endpoint:** `POST /api/v1/system/universities`

**Description:** Create/onboard a new university.

**Request Body:**
```json
{
  "name": "Stanford University",
  "location": "Stanford, California, USA"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | University name (must be unique) |
| `location` | string | No | University location/address |

**Response (201 Created):**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "Stanford University",
  "location": "Stanford, California, USA",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

**Error Responses:**
- `400 Bad Request`: University name already exists
- `401 Unauthorized`: Invalid or missing authentication token
- `403 Forbidden`: User is not a SYSTEM user
- `500 Internal Server Error`: Server error

---

### 2. List All Universities

**Endpoint:** `GET /api/v1/system/universities`

**Description:** Get a list of all universities with admin counts and admin user details.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Number of records to skip (pagination) |
| `limit` | integer | 100 | Maximum number of records to return |

**Response (200 OK):**
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "Stanford University",
    "location": "Stanford, California, USA",
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00",
    "admin_count": 2,
    "admin_users": [
      {
        "user_id": "456e7890-e89b-12d3-a456-426614174001",
        "email": "admin@stanford.edu",
        "username": "stanford_university_admin",
        "first_name": "Stanford",
        "last_name": "Administrator",
        "university_id": "123e4567-e89b-12d3-a456-426614174000",
        "university_name": "Stanford University",
        "is_active": true,
        "created_at": "2024-01-15T10:35:00"
      }
    ]
  }
]
```

**Error Responses:**
- `401 Unauthorized`: Invalid or missing authentication token
- `403 Forbidden`: User is not a SYSTEM user
- `500 Internal Server Error`: Server error

---

### 3. Get University Details

**Endpoint:** `GET /api/v1/system/universities/{university_id}`

**Description:** Get detailed information about a specific university, including all admin users.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `university_id` | string (UUID) | Yes | Unique identifier of the university |

**Response (200 OK):**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "Stanford University",
  "location": "Stanford, California, USA",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00",
  "admin_count": 2,
  "admin_users": [
    {
      "user_id": "456e7890-e89b-12d3-a456-426614174001",
      "email": "admin@stanford.edu",
      "username": "stanford_university_admin",
      "first_name": "Stanford",
      "last_name": "Administrator",
      "university_id": "123e4567-e89b-12d3-a456-426614174000",
      "university_name": "Stanford University",
      "is_active": true,
      "created_at": "2024-01-15T10:35:00"
    }
  ]
}
```

**Error Responses:**
- `404 Not Found`: University not found
- `401 Unauthorized`: Invalid or missing authentication token
- `403 Forbidden`: User is not a SYSTEM user
- `500 Internal Server Error`: Server error

---

### 4. Delete University

**Endpoint:** `DELETE /api/v1/system/universities/{university_id}`

**Description:** Delete a university and all associated data (users, courses, lectures, etc.).

**⚠️ WARNING:** This is a **destructive operation**. All data associated with the university will be permanently deleted.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `university_id` | string (UUID) | Yes | Unique identifier of the university |

**Response (200 OK):**
```json
{
  "message": "University deleted successfully",
  "university_name": "Stanford University",
  "deleted_users": 15
}
```

**Error Responses:**
- `404 Not Found`: University not found
- `401 Unauthorized`: Invalid or missing authentication token
- `403 Forbidden`: User is not a SYSTEM user
- `500 Internal Server Error`: Failed to delete university

---

## Admin User Endpoints

### 5. Create Admin User for University

**Endpoint:** `POST /api/v1/system/universities/{university_id}/admins`

**Description:** Create a default admin user for a university. Username and password are auto-generated.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `university_id` | string (UUID) | Yes | Unique identifier of the university |

**Request Body:**
```json
{
  "email": "admin@stanford.edu"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string (email) | Yes | Email address for the admin user |

**Response (201 Created):**
```json
{
  "user_id": "456e7890-e89b-12d3-a456-426614174001",
  "email": "admin@stanford.edu",
  "username": "stanford_university_admin",
  "password": "Xy9$mK2#pQwR",
  "university_id": "123e4567-e89b-12d3-a456-426614174000",
  "university_name": "Stanford University",
  "message": "Admin user created successfully for Stanford University"
}
```

**Important Notes:**
- **Username Format:** `{sanitized_university_name}_admin` (e.g., `stanford_university_admin`)
- **Password:** Secure random 12-character string (alphanumeric + special characters)
- **⚠️ CRITICAL:** The password is shown **ONLY ONCE** in this response. Save it immediately!
- The password should be shared securely with the admin user
- Username format ensures uniqueness per university

**Error Responses:**
- `400 Bad Request`: 
  - Email already exists
  - Invalid email format
- `404 Not Found`: University not found
- `401 Unauthorized`: Invalid or missing authentication token
- `403 Forbidden`: User is not a SYSTEM user
- `500 Internal Server Error`: Failed to create admin user

---

### 6. List All Admins

**Endpoint:** `GET /api/v1/system/admins`

**Description:** Get a list of all admin users across all universities.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Number of records to skip (pagination) |
| `limit` | integer | 100 | Maximum number of records to return |

**Response (200 OK):**
```json
[
  {
    "user_id": "456e7890-e89b-12d3-a456-426614174001",
    "email": "admin@stanford.edu",
    "username": "stanford_university_admin",
    "first_name": "Stanford",
    "last_name": "Administrator",
    "university_id": "123e4567-e89b-12d3-a456-426614174000",
    "university_name": "Stanford University",
    "is_active": true,
    "created_at": "2024-01-15T10:35:00"
  }
]
```

**Error Responses:**
- `401 Unauthorized`: Invalid or missing authentication token
- `403 Forbidden`: User is not a SYSTEM user
- `500 Internal Server Error`: Server error

---

### 7. Delete Admin User

**Endpoint:** `DELETE /api/v1/system/admins/{user_id}`

**Description:** Delete an admin user from the system.

**⚠️ WARNING:** This will permanently delete the admin user and all associated data.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string (UUID) | Yes | Unique identifier of the admin user |

**Response (200 OK):**
```json
{
  "message": "Admin user deleted successfully",
  "email": "admin@stanford.edu"
}
```

**Error Responses:**
- `400 Bad Request`: User is not an admin
- `404 Not Found`: User not found
- `401 Unauthorized`: Invalid or missing authentication token
- `403 Forbidden`: User is not a SYSTEM user
- `500 Internal Server Error`: Failed to delete admin user

---

## Authentication

### Login

System users use the standard authentication endpoint:

**Endpoint:** `POST /api/v1/auth/login`

**Request Body (Form Data):**
```
username: Kaizensoftwaresol@gmail.com
password: Kaizen786!
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Using the Token:**
Include the token in the `Authorization` header for all system endpoints:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Data Models

### UniversityResponse
```typescript
interface UniversityResponse {
  id: string;
  name: string;
  location: string | null;
  created_at: string;
  updated_at: string;
}
```

### UniversityDetail
```typescript
interface UniversityDetail {
  id: string;
  name: string;
  location: string | null;
  created_at: string;
  updated_at: string;
  admin_count: number;
  admin_users: AdminSummary[];
}
```

### AdminSummary
```typescript
interface AdminSummary {
  user_id: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  university_id: string;
  university_name: string;
  is_active: boolean;
  created_at: string;
}
```

### AdminCreateRequest
```typescript
interface AdminCreateRequest {
  email: string; // Email format
}
```

### AdminCreateResponse
```typescript
interface AdminCreateResponse {
  user_id: string;
  email: string;
  username: string;
  password: string; // ⚠️ Save immediately - shown only once!
  university_id: string;
  university_name: string;
  message: string;
}
```

### UniversityCreateRequest
```typescript
interface UniversityCreateRequest {
  name: string;
  location?: string; // Optional
}
```

---

## Example API Calls

### Using Fetch API

```javascript
const BASE_URL = '/api/v1/system';
const token = 'your-jwt-token-here';

// Create University
const createUniversity = async (name, location) => {
  const response = await fetch(`${BASE_URL}/universities`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ name, location })
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create university');
  }
  
  return response.json();
};

// List Universities
const listUniversities = async (skip = 0, limit = 100) => {
  const response = await fetch(
    `${BASE_URL}/universities?skip=${skip}&limit=${limit}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  return response.json();
};

// Create Admin User
const createAdmin = async (universityId, email) => {
  const response = await fetch(
    `${BASE_URL}/universities/${universityId}/admins`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ email })
    }
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create admin');
  }
  
  const result = await response.json();
  
  // ⚠️ IMPORTANT: Save credentials immediately!
  console.log('Admin Credentials (SAVE NOW!):');
  console.log('Email:', result.email);
  console.log('Username:', result.username);
  console.log('Password:', result.password);
  
  return result;
};

// Delete University
const deleteUniversity = async (universityId) => {
  const confirmed = confirm(
    '⚠️ WARNING: This will delete the university and ALL associated data. ' +
    'This action cannot be undone. Are you sure?'
  );
  
  if (!confirmed) return;
  
  const response = await fetch(
    `${BASE_URL}/universities/${universityId}`,
    {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  return response.json();
};
```

### Using Axios

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1/system',
  headers: {
    'Authorization': `Bearer ${token}`
  }
});

// Create University
const createUniversity = (name, location) => {
  return api.post('/universities', { name, location });
};

// List Universities
const listUniversities = (skip = 0, limit = 100) => {
  return api.get('/universities', { params: { skip, limit } });
};

// Get University Details
const getUniversity = (universityId) => {
  return api.get(`/universities/${universityId}`);
};

// Delete University
const deleteUniversity = (universityId) => {
  return api.delete(`/universities/${universityId}`);
};

// Create Admin User
const createAdmin = (universityId, email) => {
  return api.post(`/universities/${universityId}/admins`, { email });
};

// List All Admins
const listAdmins = (skip = 0, limit = 100) => {
  return api.get('/admins', { params: { skip, limit } });
};

// Delete Admin User
const deleteAdmin = (userId) => {
  return api.delete(`/admins/${userId}`);
};
```

---

## Error Handling

All endpoints return standard HTTP status codes:

| Status Code | Description |
|-------------|-------------|
| `200 OK` | Request successful |
| `201 Created` | Resource created successfully |
| `400 Bad Request` | Invalid request data |
| `401 Unauthorized` | Missing or invalid authentication token |
| `403 Forbidden` | User does not have SYSTEM role |
| `404 Not Found` | Resource not found |
| `500 Internal Server Error` | Server error |

**Error Response Format:**
```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Best Practices

1. **Password Security**: Always save auto-generated passwords immediately when creating admin users. They cannot be retrieved later.

2. **Delete Confirmations**: Always show confirmation dialogs before deleting universities or admin users.

3. **Error Handling**: Implement proper error handling for all API calls and display user-friendly error messages.

4. **Loading States**: Show loading indicators during API calls for better UX.

5. **Token Refresh**: Handle token expiration gracefully and prompt users to re-login.

6. **Pagination**: Use `skip` and `limit` parameters for large datasets to improve performance.

---

## Testing

### Test Credentials

**System User:**
- Email: `Kaizensoftwaresol@gmail.com`
- Password: `Kaizen786!`

### Test Checklist

- [ ] System user can log in successfully
- [ ] Can create a new university
- [ ] Can view list of universities
- [ ] Can view university details
- [ ] Can create admin user for a university
- [ ] Can view auto-generated credentials after admin creation
- [ ] Can list all admins
- [ ] Can delete admin user
- [ ] Can delete university (with proper confirmation)
- [ ] Non-system users cannot access system endpoints
- [ ] Error messages display correctly

---

**Last Updated:** 2024-01-15  
**Version:** 1.0.0
