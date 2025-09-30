# AI Teacher Assistant

Intelligent Learning Platform with AI-powered document ingestion, lecture management, and comprehensive parsing capabilities.

## 🚀 Features

- 📄 **Document Ingestion**: Parse PDF, PPTX, DOCX with comprehensive extraction
- 🌐 **Website Parsing**: Extract clean content from web URLs
- 🔐 **JWT Authentication**: Secure Bearer token authentication
- 👨‍🏫 **Multi-University Support**: Teachers, students, courses
- 📊 **Analytics**: Track engagement and performance
- 🎓 **Course Management**: Lectures, assessments, enrollments

## 🛠️ Tech Stack

- **Backend**: FastAPI 0.117.1
- **Database**: Supabase (PostgreSQL)
- **Storage**: Supabase Storage
- **Auth**: JWT with passlib/bcrypt
- **Parsing**: PyPDF2, python-pptx, python-docx
- **ORM**: SQLModel

## 📦 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Setup

Create `.env` file:

```env
# Supabase
SUPABASE_URL=your_project_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Auth
SECRET_KEY=your-secret-jwt-key

# AI APIs (optional)
OPENAI_API_KEY=your_key
GROQ_API_KEY=your_key
```

### 3. Database Setup

See **DEPLOYMENT_GUIDE.md** for:
- Creating documents table
- Setting up storage buckets
- Configuring RLS policies

### 4. Run Server

```bash
uvicorn main:app --reload
```

### 5. Access API

- **Swagger UI**: http://localhost:8000/api/v1/docs
- **ReDoc**: http://localhost:8000/api/v1/redocs

## 🔐 Test Credentials

```
Email: sarah.johnson@harvard.edu
Password: Password123!
Role: ADMIN (with Teacher profile)
```

## 📄 API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Get JWT token
- `GET /api/v1/auth/me` - Get current user
- `PUT /api/v1/auth/me` - Update user

### Document Ingestion
- `POST /api/v1/documents/upload/file` - Upload PDF/PPTX/DOCX
- `POST /api/v1/documents/upload/website` - Upload website URL
- `GET /api/v1/documents` - List all documents
- `GET /api/v1/documents/{id}` - Get single document
- `PUT /api/v1/documents/{id}` - Update document
- `DELETE /api/v1/documents/{id}` - Delete document

## 📊 Document Parsing

### PDF Parser
- ✅ Page-by-page extraction
- ✅ Text, lines, word count
- ✅ Page dimensions & rotation
- ✅ Comprehensive metadata

### PPTX Parser
- ✅ Slide-by-slide content
- ✅ Images, tables, notes
- ✅ Shape positions & sizes
- ✅ Text formatting

### DOCX Parser
- ✅ Heading-based organization
- ✅ Paragraphs with formatting
- ✅ Tables & images
- ✅ Rich text styles

### Website Parser
- ✅ Clean content extraction
- ✅ Metadata (title, author, keywords)
- ✅ Word count

## 📁 Storage Structure

Documents are stored as parsed JSON only (original files NOT stored):

```
university_{id}/teacher_{id}/{type}/{year}/{month}/
  └── {uuid}.json  (parsed content)
```

Example:
```
university_e4a21c44/teacher_6bf5fec8/PDF/2024/12/
  └── abc-123-def.json
```

## 🗄️ Database Schema

All tables use **UUID primary keys**:
- `users` - User accounts with roles
- `teacher` - Teacher profiles
- `student` - Student profiles
- `university` - Universities
- `course` - Courses
- `semester` - Academic periods
- `lecture` - Lectures
- `documents` - Uploaded documents
- `enrollment` - Student enrollments
- `assessment` - Quizzes/exams
- `ai_conversation` - Chat history
- `job_queue` - Async job processing


## 🔧 Development

```bash
# Run with auto-reload
uvicorn main:app --reload

# Check logs
tail -f logs/app.log
```


## 📝 License

MIT License
