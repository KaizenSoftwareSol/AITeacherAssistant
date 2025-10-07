# AI Teacher Assistant

Intelligent Learning Platform with AI-powered document ingestion, lecture management, and comprehensive parsing capabilities.

## 🚀 Features

- 📄 **Document Ingestion**: Parse PDF, PPTX, DOCX with comprehensive extraction
- 🌐 **Website Parsing**: Extract clean content from web URLs
- 🤖 **AI-Powered Lecture Generation**: Generate lectures from documents using GPT-4o
- 📑 **PDF Creation**: Automatically create formatted lecture PDFs
- 🔐 **JWT Authentication**: Secure Bearer token authentication
- 👨‍🏫 **Multi-University Support**: Teachers, students, courses
- 📊 **Analytics**: Track engagement and performance
- 🎓 **Course Management**: Lectures, assessments, enrollments

## 🛠️ Tech Stack

- **Backend**: FastAPI 0.117.1
- **Database**: Supabase (PostgreSQL)
- **Storage**: Supabase Storage
- **Auth**: JWT with passlib/bcrypt
- **Parsing**: PyPDF2, python-pptx, python-docx, BeautifulSoup4
- **AI**: OpenAI GPT-4o
- **PDF Generation**: ReportLab
- **ORM**: SQLModel

## 📦 Quick Start

### 1. Create Virtual Environment

**Windows:**
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate
```

**macOS/Linux:**
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Setup

Create `.env` file:

```env
# Supabase
SUPABASE_URL=your_project_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Auth
SECRET_KEY=your-secret-jwt-key

# AI APIs
OPENAI_API_KEY=your_openai_key  # Required for lecture generation
```

### 4. Database Setup

See **DEPLOYMENT_GUIDE.md** for:
- Creating documents table
- Setting up storage buckets
- Configuring RLS policies

### 5. Run Server

```bash
# Using uvicorn directly
uvicorn main:app --reload

# Or using the run script
python run.py
```

### 6. Access API

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

### Document Management
- `POST /api/v1/documents/upload/file` - Upload PDF/PPTX/DOCX
- `POST /api/v1/documents/upload/website` - Upload website URL
- `GET /api/v1/documents` - List all documents
- `GET /api/v1/documents/{id}` - Get single document
- `PUT /api/v1/documents/{id}` - Update document
- `DELETE /api/v1/documents/{id}` - Delete document

### Lecture Generation (AI-Powered)
- `POST /api/v1/lectures/generate` - Generate lecture from document
- `GET /api/v1/lectures/{id}/download` - Get lecture PDF download link

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

### Ingested Documents (USER_UPLOADS bucket)
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

### Generated Lectures (GENERATED_CONTENT bucket)
AI-generated lecture PDFs are stored with organized structure:

```
university_{id}/teacher_{id}/course_{id}/generated_lectures/
  └── {uuid}.pdf  (generated lecture PDF)
```

Example:
```
university_e4a21c44/teacher_6bf5fec8/course_a1b2c3d4/generated_lectures/
  └── lecture-xyz-789.pdf
```

## 🗄️ Database Schema

All tables use **UUID primary keys**:
- `users` - User accounts with roles
- `teacher` - Teacher profiles
- `student` - Student profiles
- `university` - Universities
- `course` - Courses
- `semester` - Academic periods
- `lecture` - Lecture records (AI-generated or teacher-recorded)
- `lecture_content` - Lecture file metadata (PDFs, slides, etc.)
- `documents` - Ingested document metadata
- `enrollment` - Student enrollments
- `assessment` - Quizzes/exams
- `ai_conversation` - Chat history
- `job_queue` - Async job processing


## 🤖 AI Lecture Generation Workflow

1. **Teacher uploads document** (PDF, PPTX, DOCX, or website)
   - Document is parsed and stored as JSON in Supabase Storage

2. **Teacher requests lecture generation**
   ```json
   POST /api/v1/lectures/generate
   {
     "document_id": "uuid-of-document",
     "course_id": "uuid-of-course",
     "semester_id": "uuid-of-semester",
     "title": "Introduction to Machine Learning",
     "description": "Focus on supervised learning algorithms with practical examples"
   }
   ```

3. **System generates lecture**
   - Fetches document JSON from storage
   - Sends content + description to OpenAI GPT-4o
   - AI generates comprehensive lecture content
   - Creates formatted PDF with ReportLab
   - Saves PDF to GENERATED_CONTENT bucket
   - Creates lecture record in database

4. **Teacher downloads lecture**
   ```json
   GET /api/v1/lectures/{lecture_id}/download
   Response:
   {
     "lecture_id": "uuid",
     "title": "Introduction to Machine Learning",
     "download_url": "https://supabase.co/storage/...",
     "file_name": "lecture.pdf",
     "file_size": 245678,
     "created_at": "2025-10-07T21:00:00Z"
   }
   ```

## 🔧 Development

### Activate Virtual Environment

**Always activate your virtual environment before running:**

```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### Run Server

```bash
# Run with auto-reload
uvicorn main:app --reload

# Or use the run script
python run.py

# Check logs
tail -f logs/app.log
```

### Deactivate Virtual Environment

```bash
deactivate
```

### Install New Packages

```bash
# Make sure venv is activated first
pip install package-name

# Update requirements.txt
pip freeze > requirements.txt
```

## 🔒 Security Notes

- All database operations use **admin client** (service role key) to bypass RLS
- RLS policies should still be configured in Supabase for direct access
- JWT tokens required for all authenticated endpoints
- Documents are scoped to teachers - only owners can access their documents
- Lectures are scoped to teachers - only creators can access their lectures

## 📝 License

MIT License
