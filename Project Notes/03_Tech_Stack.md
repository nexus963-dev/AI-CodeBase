# Technology Stack

## Frontend

### React

Used to build the interactive user interface from reusable components.

### Vite

Used as the frontend development and build tool.

### JavaScript

Used for frontend application logic.

## Backend

### Python

Primary backend language.

### FastAPI

Used to expose REST API endpoints and organize backend request handling.

### Uvicorn

Used to run the FastAPI application.

## Database

### PostgreSQL

Used for persistent relational application data such as users, chat sessions, and chat messages.

### SQLAlchemy

Used as the ORM for database models and relationships.

### Alembic

Used for database migrations.

## AI / RAG

### Sentence Transformers

Used to generate semantic vector embeddings for repository chunks.

### all-MiniLM-L6-v2

The embedding model currently used by the embedding service.

### ChromaDB

Used as the vector store for embeddings and repository chunks.

### Google Gemini

Used by the answer-generation service to generate responses from retrieved repository context.

## Repository Processing

### GitPython

Used to clone GitHub repositories and inspect Git information.

## Authentication / Security

The backend includes:

- JWT utilities;
- password hashing;
- Passlib;
- bcrypt;
- Pydantic validation.

## Configuration

### Pydantic Settings

Used to load environment-based configuration.

## Dependency Management

### pip

Python dependencies are listed in:

```text
Backend/requirements.txt
```

### npm

Frontend dependencies are listed in:

```text
Frontend/package.json
```

## Why These Technologies?

The stack separates the system into clear layers:

```text
React/Vite
    ↓
FastAPI
    ↓
Repository + AI Services
    ↓
PostgreSQL + ChromaDB
    ↓
Gemini / Sentence Transformers
```

This makes the project easier to develop incrementally and provides clear boundaries between UI, API, persistence, retrieval, and generation.