# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AITeacherAssistant is a Python FastAPI backend for an AI-powered education platform. Teachers upload documents, generate AI lectures, and publish them. Students access published lectures, take quizzes, chat with AI using RAG, and study flashcards.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API server (port 8001)
python run.py

# Run with uvicorn directly (port 8000)
uvicorn main:app --reload

# Docker build and run
docker build -t ai-teacher:latest .
docker run -p 8005:8005 --env-file .env ai-teacher:latest

# Lint and format
ruff check .
ruff format .
```

## Architecture

### Tech Stack
- **Framework:** FastAPI with async/await throughout
- **Database:** Supabase (PostgreSQL + pgvector for vector search)
- **ORM:** SQLModel (SQLAlchemy-based), models in `/models/`
- **Auth:** JWT (HS256), HTTPBearer, 1-day expiry
- **AI:** OpenAI GPT-4o (lecture generation), GPT-4o-mini (summaries/quizzes/flashcards), text-embedding-3-small (RAG)
- **Storage:** Supabase Storage buckets: `USER_UPLOADS` (parsed docs), `GENERATED_CONTENT` (PDFs)
- **Caching:** Redis (preferred) or in-memory LRU fallback, max 10,000 entries
- **Logging:** loguru with file rotation in `logs/`

### API Structure
All routes are prefixed `/api/v1` and registered in `routes_config.py`:

| Prefix | Module |
|---|---|
| `/auth` | Login, register, password change |
| `/users` | User profile management |
| `/courses` | Course CRUD |
| `/documents` | Document upload and parsing |
| `/lectures` | Lecture generation and management |
| `/student` | Quiz, summary, AI chat, flashcards |
| `/teacher` | Teacher-facing resources |
| `/notifications` | In-app and email notifications |
| `/admin` | Course and teacher management |
| `/system` | Universities and system admin users |

Health endpoints (no auth): `GET /api/v1/health`, `GET /api/v1/ready`

### Database Access Pattern
All DB operations go through `SupabaseDB` class in `utils/db.py`. It exposes two Supabase clients:
- `self.client` — anonymous key (user-level RLS)
- `self.admin_client` — service role key (bypasses RLS)

Nearly all application code uses `admin_client` to bypass RLS, relying on application-level access control instead.

### Auth and Dependencies
`dependencies.py` provides the `get_current_user()` FastAPI dependency, which validates the JWT and injects the current user. Role-based access is checked inline in route handlers. Roles: `TEACHER`, `STUDENT`, `ADMIN`, `SYSTEM`.

### Caching Strategy
`services/cache_service.py` provides TTL-based caching. Cache keys are invalidated explicitly after mutations. Auth/user/course/lecture caches have 1440s TTL. Cache stats are available at `GET /api/v1/cache/stats` (admin only).

### Lecture Lifecycle
1. Teacher uploads a document → `document_service.py` parses it (PDF/PPTX/DOCX) and stores JSON in Supabase Storage
2. Teacher triggers lecture generation → `lecture_service.py` calls GPT-4o, status = `GENERATED`
3. Teacher publishes lecture → status = `PUBLISHED`, which auto-triggers generation of summary, quiz (10 questions), and flashcards (15 cards) via background tasks

### RAG / AI Chat
- `embedding_service.py` generates vector embeddings using text-embedding-3-small and stores them in Supabase (pgvector)
- Embeddings are generated once per lecture (one-time ~20s operation triggered by the student)
- `rag_service.py` performs similarity search then calls GPT-4o-mini with retrieved context

### Configuration
All settings are in `settings.py` using Pydantic `BaseSettings`, loaded from `.env`. Required env vars:

```
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
SECRET_KEY          # JWT signing key
OPENAI_API_KEY
ELEVENLABS_API_KEY  # Optional: text-to-speech
REDIS_URL           # Optional: falls back to in-memory cache
EMAIL_SERVICE_TYPE  # "smtp" or "sendgrid"
FRONTEND_URL        # Used in email templates
```

### Key Large Files
- `utils/db.py` (29KB) — all database query methods
- `services/lecture_service.py` (107KB) — lecture generation, status management, AI orchestration
- `services/document_parser.py` (70KB) — PDF/PPTX/DOCX parsing logic
- `services/cache_service.py` (17KB) — caching with stats and cleanup

### Performance Middleware Stack (applied in `main.py`)
Request ID injection → Performance monitoring (slow request detection) → Response caching → Route handlers

Metrics endpoint: `GET /api/v1/metrics` (Prometheus-compatible)

### Database Migrations
SQL migration files are in `/migrations/`. Apply them manually via Supabase SQL editor or psql. Schema and data backups: `schema_backup.sql`, `data_backup.sql`. Optimized indexes: `SQL_OPTIMIZATION_QUERIES.sql`.
