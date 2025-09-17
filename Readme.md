# AI Teacher

An intelligent learning platform built with FastAPI, featuring AI-powered content generation, personalized learning paths, and interactive educational tools.

## Features

- **User Authentication & Authorization**: JWT-based auth with role-based access control
- **AI-Powered Content Generation**: Create lessons and explanations using OpenAI
- **RAG System**: Knowledge base with ChromaDB for intelligent content retrieval
- **User Progress Tracking**: Monitor learning progress and course completion
- **Interactive Chat**: AI assistant for answering questions and providing guidance
- **Course Management**: Create and manage educational courses and lessons

## Project Structure

```
AI_Teacher/
├── ai/                    # AI-related modules
│   ├── agent.py          # AI agent for chat and assistance
│   ├── generation.py     # Content generation utilities
│   └── rag.py           # RAG system for knowledge retrieval
├── auth/                 # Authentication module
│   ├── models.py        # User and auth models
│   ├── routes.py        # Auth endpoints
│   └── service.py       # Auth business logic
├── user/                # User management module
│   ├── models.py        # User profile and progress models
│   ├── routes.py        # User endpoints
│   └── service.py       # User business logic
├── utils/               # Utility modules
│   ├── db.py           # Database utilities
│   └── responses.py    # Standardized response helpers
├── static/             # Static files
├── logs/               # Application logs
├── chroma_store/       # ChromaDB vector store
├── main.py            # FastAPI application entry point
├── settings.py        # Application settings
├── dependencies.py    # FastAPI dependencies
├── routes_config.py   # Router configuration
├── logger.py          # Logging configuration
├── requirements.txt   # Python dependencies
├── pyproject.toml     # Project configuration
└── Dockerfile         # Docker configuration
```

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd AI_Teacher
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp env.example .env
   # Edit .env with your API keys and configuration
   ```

5. **Run the application**:
   ```bash
   uvicorn main:app --reload
   ```

## API Documentation

Once the application is running, you can access:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redocs

## Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key for AI features
- `GROQ_API_KEY`: Your Groq API key (optional)
- `SECRET_KEY`: JWT secret key (change in production)
- `SQLITE_DATABASE_URL`: Database connection string

## Docker

To run with Docker:

```bash
docker build -t ai-teacher .
docker run -p 8000:8000 ai-teacher
```

## Development

The project uses:
- **FastAPI** for the web framework
- **SQLModel** for database models and ORM
- **LangChain** for AI integration
- **ChromaDB** for vector storage
- **Pydantic** for data validation
- **Loguru** for logging

## License

This project is licensed under the MIT License.

