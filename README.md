# Repix — AI GitHub Repository Assistant

> An AI-powered GitHub Repository Assistant that helps developers understand, search, and chat with codebases using Retrieval-Augmented Generation (RAG), semantic search, vector embeddings, and an LLM.

## Overview

Repix is a full-stack application designed to make unfamiliar GitHub repositories easier to understand.

Instead of manually opening files and searching through a codebase, a user provides a GitHub repository URL. Repix clones the repository, reads supported source files, breaks the content into smaller code chunks, generates semantic embeddings, stores those embeddings in ChromaDB, and then retrieves relevant code when the user asks a question.

The retrieved repository context is passed through the application's AI answering pipeline so that responses are grounded in the analyzed codebase.

The project also includes persistent chat sessions and messages backed by PostgreSQL.

## Problem Statement

Understanding an unfamiliar codebase can be time-consuming. Developers often need to:

- locate relevant files manually;
- understand relationships between modules;
- search for specific implementation details;
- repeatedly inspect the same source files;
- remember previous questions and answers.

Repix addresses this by turning a repository into a searchable AI knowledge base that can be queried using natural language.

## Core Workflow

```text
GitHub Repository URL
        │
        ▼
Repository Validation
        │
        ▼
Clone Repository
        │
        ▼
Read Source Files
        │
        ▼
Create Code Chunks
        │
        ▼
Generate Embeddings
        │
        ▼
Store Embeddings in ChromaDB
        │
        ▼
User Question
        │
        ▼
Semantic Retrieval
        │
        ▼
Relevant Repository Context
        │
        ▼
Gemini-based Answer Generation
        │
        ▼
Chat Session + Message Storage
        │
        ▼
Answer in React UI
```

## Features

### Repository Analysis

- Accepts a GitHub repository URL.
- Validates the repository URL before cloning.
- Clones repositories using GitPython.
- Uses a shallow clone (`depth=1`) to reduce unnecessary repository history.
- Detects the dominant programming language from source-file extensions.
- Detects common license types from repository license files.
- Detects the active Git branch.

### Code Processing

- Reads repository source files.
- Ignores directories such as `.git`, `node_modules`, virtual environments, build directories, and Python cache directories.
- Splits source code into smaller chunks.
- Preserves useful file and chunk metadata.

### Semantic Search / RAG

- Generates embeddings with `sentence-transformers`.
- Uses the `all-MiniLM-L6-v2` embedding model.
- Stores embeddings and metadata in ChromaDB.
- Retrieves semantically relevant chunks for user questions.
- Passes retrieved context into the repository-answer generation pipeline.

### AI Chat

- Natural-language questions about an analyzed repository.
- Repository-aware answers based on retrieved code context.
- Persistent chat sessions.
- Persistent user and assistant messages.
- Chat titles generated from the first question.
- Sidebar support for previously created sessions.

### Web Application

- React + Vite frontend.
- FastAPI backend.
- Repository analysis loading sequence.
- Repository metadata display.
- Chat interface.
- Responsive component-based UI.
- Configurable frontend-to-backend API URL through Vite environment variables.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, JavaScript |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Vector Database | ChromaDB |
| Embeddings | Sentence Transformers |
| Embedding Model | `all-MiniLM-L6-v2` |
| LLM | Google Gemini |
| Repository Operations | GitPython |
| Authentication / Security | JWT, Passlib, bcrypt |
| Validation | Pydantic / Pydantic Settings |
| API Server | Uvicorn |

## Project Structure

```text
AI-GitHub-Repository-Assistant/
│
├── Backend/
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   │
│   ├── app/
│   │   ├── config/
│   │   ├── models/
│   │   ├── routes/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── auth.py
│   │   ├── database.py
│   │   ├── main.py
│   │   └── security.py
│   │
│   ├── requirements.txt
│   └── ...
│
├── Frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   ├── assets/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
│
├── Project Notes/
│   ├── 01_Project_Idea.md
│   ├── 02_Features.md
│   ├── 03_Tech_Stack.md
│   ├── 04_Database.md
│   ├── 05_API_Design.md
│   ├── 06_UI_Design.md
│   ├── 07_Architecture.md
│   └── 08_Tasks.md
│
├── .gitignore
├── LICENSE
└── README.md
```

## Backend Architecture

The backend is organized into several responsibilities.

### Routes

The route layer exposes API endpoints for:

- user operations;
- repository analysis;
- chat;
- chat sessions;
- chat messages;
- health checks.

### Services

The service layer separates repository processing and AI operations into focused modules, including:

- GitHub repository handling;
- repository reading;
- code chunking;
- embedding generation;
- vector database operations;
- retrieval;
- prompt construction;
- Gemini answer generation;
- orchestration.

### Data Models

The PostgreSQL layer currently contains models for users, chat sessions, and chat messages.

A `ChatSession` belongs to a user and repository and contains multiple `ChatMessage` records.

## Database Design

### Users

The user model contains:

- `id`
- `username`
- `email`
- `github_id`
- `hashed_password`
- `created_at`

### Chat Sessions

A chat session contains:

- `id`
- `user_id`
- `repository_name`
- `title`
- `created_at`
- `updated_at`

### Chat Messages

Messages belong to a chat session and store:

- session ID;
- role;
- message content;
- creation timestamp.

The current implementation uses SQLAlchemy relationships and Alembic migrations for database schema management.

## API Overview

The current backend exposes functionality including:

| Endpoint | Purpose |
|---|---|
| `POST /chat` | Create/continue a repository chat and generate an answer |
| `GET /chat/sessions` | Retrieve chat sessions for a repository |
| `GET /chat/sessions/{session_id}` | Retrieve messages from a chat session |
| `POST /analyze-repository` | Analyze and index a GitHub repository |
| User/authentication endpoints | Registration and authentication |
| `GET /health` | Backend health check |

Refer to the route implementations under `Backend/app/routes/` for the current request and response schemas.

## Environment Variables

### Backend

Create `Backend/.env` locally:

```env
DATABASE_URL=your_postgresql_connection_string
SECRET_KEY=your_secret_key
GEMINI_API_KEY=your_gemini_api_key
FRONTEND_URL=http://localhost:5173
```

Do not commit the real `.env` file or API keys.

### Frontend

Create `Frontend/.env` locally:

```env
VITE_API_URL=http://localhost:8000
```

The repository contains `Frontend/.env.example` as a safe template.

## Local Setup

### 1. Clone the project

```bash
git clone https://github.com/Akshitagupta299/AI-GitHub-Repository-Assistant.git
cd AI-GitHub-Repository-Assistant
```

### 2. Backend setup

```bash
cd Backend
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure `Backend/.env`.

Run database migrations:

```bash
alembic upgrade head
```

Start FastAPI:

```bash
uvicorn app.main:app --reload
```

The backend runs locally on:

```text
http://127.0.0.1:8000
```

### 3. Frontend setup

Open a second terminal:

```bash
cd Frontend
npm install
```

Create `Frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

Start the frontend:

```bash
npm run dev
```

Vite will display the local frontend URL in the terminal.

## Using Repix

1. Start PostgreSQL.
2. Start the FastAPI backend.
3. Start the React frontend.
4. Open the frontend in a browser.
5. Enter a public GitHub repository URL.
6. Start repository analysis.
7. Wait for the repository to be cloned, read, chunked, embedded, and indexed.
8. Open the chat interface.
9. Ask questions about the repository.
10. Continue conversations through saved chat sessions.

## Example Questions

After indexing a repository, a user can ask questions such as:

```text
How is authentication implemented?
```

```text
Where is the database connection configured?
```

```text
Explain the main backend architecture.
```

```text
How does the repository analysis pipeline work?
```

```text
Which files are responsible for generating embeddings?
```

The quality of the answer depends on the repository contents, chunking strategy, retrieved context, and LLM response.

## Current Status

Repix is currently a working local full-stack application.

The repository contains the backend, frontend, database models/migrations, semantic retrieval pipeline, AI answer generation pipeline, and repository analysis flow.

Public cloud deployment is planned as a future phase. The current repository should therefore be treated as a locally runnable project rather than as a production-hosted service.

## Current Limitations

- Local ChromaDB persistence is used for vector storage.
- Cloned repositories are stored locally during analysis.
- Production persistence for repository files and vector data still needs to be designed.
- The current chat route uses a fixed user identifier for session ownership and should be replaced by the authenticated user context before production multi-user deployment.
- Production deployment configuration is not yet included.
- The application currently focuses on repository understanding and question answering rather than autonomous code modification.

## Future Improvements

- Complete production deployment.
- Replace the fixed chat user ID with authenticated user identity.
- Improve repository and vector-store persistence for cloud environments.
- Add better repository lifecycle management and cleanup.
- Support more advanced code-aware chunking.
- Add richer file and symbol-level retrieval.
- Improve answer citations with exact repository file references.
- Add streaming AI responses.
- Add automated tests and CI.
- Add repository re-indexing and update detection.
- Improve authentication and GitHub OAuth integration.
- Add monitoring and structured logging.

## Development Notes

The `Project Notes/` directory contains the project's design and development documentation:

- project idea;
- feature definition;
- technology decisions;
- database design;
- API design;
- UI design;
- architecture;
- task/roadmap tracking.

These documents are intended to make the project easier to understand and continue developing.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Author / Project

**Repix — AI GitHub Repository Assistant**