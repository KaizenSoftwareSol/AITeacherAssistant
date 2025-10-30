# AI Teacher Assistant

Intelligent Learning Platform with AI-powered document ingestion, lecture generation, and comprehensive student learning tools.

## 🚀 Features

### 📚 For Teachers
- 📄 **Document Ingestion**: Parse PDF, PPTX, DOCX, and websites
- 🤖 **AI Lecture Generation**: Generate comprehensive lectures from documents using GPT-4o
- 📑 **PDF Creation**: Automatically create formatted lecture PDFs
- 🎯 **Lecture Management**: Publish/unpublish/delete lectures with intuitive UI
- ⚡ **Auto-Generation on Publish**: When publishing a lecture, automatically generates:
  - 📝 **Summary**: AI-generated lecture summary
  - 📊 **Quiz**: 10-question default quiz with explanations
  - 🗂️ **Flashcards**: 15 flashcards for student review (EASY/MEDIUM/HARD)

### 🎓 For Students
- 📖 **Lecture Access**: View published lectures with rich content
- 📝 **Summaries**: Quick overview of lecture key points
- 💬 **AI Chat Assistant**: RAG-powered chatbot for Q&A about lecture content
- 🔍 **On-Demand Embeddings**: Generate embeddings for AI chat with one click
- 📊 **Interactive Quizzes**: 
  - Take default quizzes with instant grading
  - Generate practice quizzes (results not saved)
  - View detailed results with explanations
- 🗂️ **Flashcards**: Interactive flip cards for quick review
  - Filter by difficulty (EASY/MEDIUM/HARD)
  - Study at your own pace
  - Track progress through topics
- 🎨 **Modern UI**: Streamlit-based interface for seamless learning

### 🔧 System Features
- 🔐 **JWT Authentication**: Secure Bearer token authentication
- 👨‍🏫 **Multi-University Support**: Teachers, students, courses
- 📊 **Analytics**: Track engagement and performance
- 🗄️ **Vector Search**: RAG system with embeddings for intelligent chat

## 🛠️ Tech Stack

- **Backend**: FastAPI 0.117.1
- **Frontend**: Streamlit (Teacher & Student UI)
- **Database**: Supabase (PostgreSQL with pgvector)
- **Storage**: Supabase Storage
- **Auth**: JWT with passlib/bcrypt
- **Parsing**: PyPDF2, python-pptx, python-docx, BeautifulSoup4
- **AI Models**: 
  - OpenAI GPT-4o (lecture generation)
  - GPT-4o-mini (summaries, quizzes, flashcards)
  - text-embedding-3-small (vector embeddings for RAG)
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

### 5. Run Database Migrations

Run the migration scripts in order:

```bash
# In Supabase SQL Editor, run:
migrations/001_add_lecture_embeddings.sql
migrations/002_add_default_quiz.sql
migrations/003_add_flashcards.sql
```

### 6. Run Server

```bash
# Backend API
uvicorn main:app --reload

# Streamlit UI (in a separate terminal)
cd streamlit_app
streamlit run app.py
```

### 7. Access Application

- **Streamlit UI**: http://localhost:8501 (Primary Interface)
- **API Swagger**: http://localhost:8000/api/v1/docs
- **API ReDoc**: http://localhost:8000/api/v1/redocs

## 🔐 Test Credentials

**Teacher Account:**
```
Email: michael.chen@stanford.edu
Password: Password123!
Role: TEACHER
```

**Student Account:**
```
Email: emma.wilson@stanford.edu
Password: Password123!
Role: STUDENT
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

### Lecture Management (Teachers)
- `POST /api/v1/lectures/generate` - Generate lecture from document
- `GET /api/v1/lectures/{id}/download` - Get lecture PDF download link
- `GET /api/v1/lectures` - List teacher's lectures
- `PATCH /api/v1/lectures/{id}/publish` - Publish lecture (auto-generates summary/quiz/flashcards)
- `PATCH /api/v1/lectures/{id}/unpublish` - Unpublish lecture
- `DELETE /api/v1/lectures/{id}` - Delete lecture (cascading delete)

### Student Features
- `GET /api/v1/student/courses/{course_id}/lectures` - Get published lectures
- `GET /api/v1/student/lectures/{lecture_id}/summary` - Get lecture summary
- `GET /api/v1/student/lectures/{lecture_id}/quiz` - Get saved quiz
- `POST /api/v1/student/lectures/{lecture_id}/generate-quiz` - Generate practice quiz (temporary)
- `GET /api/v1/student/lectures/{lecture_id}/flashcards` - Get flashcards
- `POST /api/v1/student/lectures/{lecture_id}/generate-embeddings` - Trigger embedding generation
- `POST /api/v1/student/lectures/{lecture_id}/chat` - Chat with AI about lecture (RAG)
- `POST /api/v1/student/assessments/{assessment_id}/submit` - Submit quiz answers

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
- `lecture` - Lecture records with status (DRAFT/GENERATED/PUBLISHED/DELIVERED)
- `lecture_content` - Lecture file metadata (PDFs, slides, etc.)
- `lecture_chunk` - Text chunks for vector search
- `lecture_embedding` - Vector embeddings (pgvector) for RAG
- `flashcard` - Flashcards for each lecture (question/answer pairs)
- `documents` - Ingested document metadata
- `enrollment` - Student enrollments
- `assessment` - Quizzes/exams (with is_default flag)
- `question` - Quiz questions with options and correct answers
- `assessment_submission` - Student quiz submissions with scores
- `ai_conversation` - Chat history with quiz results
- `student_engagement` - Tracking student activity
- `job_queue` - Async job processing


## 🤖 Complete Workflow

### Teacher Workflow

1. **Upload Document** (PDF, PPTX, DOCX, or website)
   - Document is parsed and stored as JSON in Supabase Storage

2. **Generate Lecture**
   ```json
   POST /api/v1/lectures/generate
   {
     "document_id": "uuid-of-document",
     "course_id": "uuid-of-course",
     "title": "Introduction to Machine Learning",
     "description": "Focus on supervised learning"
   }
   ```
   - Status: `GENERATED` (not visible to students yet)

3. **Publish Lecture** (via Streamlit UI or API)
   ```
   PATCH /api/v1/lectures/{id}/publish
   ```
   - Status: `PUBLISHED` (visible to students)
   - **Auto-generates in ~30-45 seconds:**
     - ✅ Summary (AI-generated)
     - ✅ Default quiz (10 questions)
     - ✅ Flashcards (15 cards, mixed difficulty)

4. **Manage Lectures**
   - View all lectures grouped by status
   - Unpublish if needed
   - Delete with full cascade (removes all related data)

### Student Workflow

1. **Access Published Lectures**
   - View lectures in enrolled courses
   - See lecture summary

2. **Study with Flashcards**
   - 15 cards per lecture
   - Filter by difficulty (EASY/MEDIUM/HARD)
   - Flip cards to test knowledge

3. **Take Quiz**
   - **Saved Quiz**: Results recorded, graded automatically
   - **Practice Quiz**: Generate new quizzes anytime (not saved)
   - View detailed results with explanations

4. **Chat with AI**
   - Click "Enable AI Chat" to generate embeddings (one-time, ~20 seconds)
   - Ask questions about lecture content
   - AI uses RAG to provide accurate answers from lecture
   - Chat remembers quiz results and weak areas

### Technical Flow: Auto-Generation on Publish

```
Teacher clicks "Publish"
        ↓
Status: GENERATED → PUBLISHED
        ↓
    Parallel Generation:
    ├─ Summary (GPT-4o-mini, 5-10s)
    ├─ Quiz (GPT-4o-mini, 10-15s)
    │   ├─ Create assessment record
    │   ├─ Generate 10 questions
    │   └─ Save to database
    └─ Flashcards (GPT-4o-mini, 10-15s)
        ├─ Generate 15 cards
        └─ Save to database
        ↓
Students can access:
✅ Lecture content
✅ Summary
✅ Quiz (saved)
✅ Flashcards
✅ Chat (after generating embeddings)
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

### Run Application

```bash
# Terminal 1: Backend API
uvicorn main:app --reload

# Terminal 2: Streamlit UI
cd streamlit_app
streamlit run app.py
```

### Check Logs

```bash
# Application logs
tail -f logs/app.log

# Check for errors
grep ERROR logs/app.log
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

## 🎯 Key Features Explained

### 1. Auto-Generation on Publish

When a teacher publishes a lecture, the system automatically:
- Generates a concise summary (2-3 paragraphs)
- Creates 10-question quiz with explanations
- Produces 15 flashcards (40% EASY, 40% MEDIUM, 20% HARD)
- All saved to database for instant student access
- Uses cost-efficient GPT-4o-mini model (~$0.001 per lecture)

### 2. RAG-Powered Chat

- Students trigger embedding generation (one-time, ~20 seconds)
- Lecture content chunked and embedded using OpenAI embeddings
- Vector search finds relevant context for questions
- AI provides accurate answers based on lecture content
- Chat remembers quiz results to focus on weak areas

### 3. Flashcard System

- **Question/Answer Format**: Simple and effective
- **Difficulty Levels**: Progressive learning (EASY → MEDIUM → HARD)
- **Topics**: Auto-categorized for organization
- **Interactive UI**: Click to flip, filter by difficulty
- **Concise**: Answers limited to 2-3 sentences

### 4. Quiz System

**Saved Quizzes:**
- Auto-generated when lecture published
- Same for all students
- Results recorded and graded
- Added to chat context for personalized help

**Practice Quizzes:**
- Generated on-demand
- Configurable (5-20 questions, difficulty)
- Results NOT saved (practice only)
- Can regenerate unlimited times

### 5. Lecture Status System

- `DRAFT`: Initial state
- `GENERATED`: Lecture created, not public
- `PUBLISHED`: Visible to students, all features enabled
- `DELIVERED`: Legacy status for backward compatibility

## 🔒 Security Notes

- All database operations use **admin client** (service role key) to bypass RLS
- JWT tokens required for all authenticated endpoints
- Role-based access control (TEACHER/STUDENT)
- Students can only access lectures they're enrolled in
- Teachers can only manage their own lectures
- Cascading deletes ensure no orphaned data
- Secure token storage in Streamlit session state

## 💰 Cost Estimation

### Per Lecture (when published):
- **Summary**: GPT-4o-mini (~$0.0003)
- **Quiz** (10 questions): GPT-4o-mini (~$0.0005)
- **Flashcards** (15 cards): GPT-4o-mini (~$0.001)
- **Total**: ~$0.002 per lecture

### Per Student (one-time):
- **Embeddings**: text-embedding-3-small (~$0.0001 per lecture)

### Monthly Estimate:
- 100 lectures published: ~$0.20
- 1000 students × 10 lectures: ~$1.00
- **Total**: ~$1.20/month for 100 lectures, 1000 students

**Highly cost-efficient for educational use!** 🎓

## 📊 Database Migrations

Run migrations in order:

1. **001_add_lecture_embeddings.sql**
   - Adds `lecture_chunk` and `lecture_embedding` tables
   - Enables pgvector for similarity search
   - Adds triggers for automatic embedding tracking

2. **002_add_default_quiz.sql**
   - Adds `is_default` flag to `assessment` table
   - Distinguishes saved quizzes from temporary ones

3. **003_add_flashcards.sql**
   - Creates `flashcard` table
   - Indexes for efficient queries
   - Foreign keys with CASCADE delete

## 📝 License

MIT License
