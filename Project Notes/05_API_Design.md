# API Design

Repix uses FastAPI to expose the backend application.

The route modules are located under:

```text
Backend/app/routes/
```

## Health Check

### `GET /health`

Used to verify that the backend application is running.

## Repository Analysis

### `POST /analyze-repository`

Starts repository analysis.

The processing pipeline includes:

1. validate repository URL;
2. clone repository;
3. extract repository metadata;
4. read files;
5. create chunks;
6. generate embeddings;
7. create/reuse a ChromaDB collection;
8. store embeddings.

The frontend uses the returned analysis information to update the UI.

## Chat

### `POST /chat`

Creates a new chat session or continues an existing session and generates an answer.

The request includes repository and question information and can include an existing session ID.

High-level flow:

```text
Request
  ↓
Find existing session
  ↓
Create session if required
  ↓
Save user message
  ↓
Retrieve relevant repository context
  ↓
Generate AI answer
  ↓
Save assistant message
  ↓
Return answer + session ID
```

## Chat Sessions

### `GET /chat/sessions`

Returns chat sessions associated with a repository.

Sessions are ordered by update time.

## Chat Messages

### `GET /chat/sessions/{session_id}`

Returns the messages belonging to a chat session.

Messages are ordered chronologically.

## User Routes

The user route module contains endpoints related to:

- user registration;
- authentication/login;
- repository analysis initiation.

The exact request and response schemas should be treated as the source of truth when extending the API.

## Schemas

Pydantic schemas are stored under:

```text
Backend/app/schemas/
```

They separate API validation and serialization from SQLAlchemy database models.

## API Design Principles

The backend separates:

```text
Routes
  ↓
Schemas
  ↓
Services
  ↓
Database / Vector Store / LLM
```

This keeps request handling separate from business logic.

## Future API Improvements

- authenticated user context for all chat operations;
- API versioning;
- structured error responses;
- request logging;
- rate limiting;
- streaming responses;
- repository re-indexing endpoints.
