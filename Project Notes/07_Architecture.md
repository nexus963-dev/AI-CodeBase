# System Architecture

## High-Level Architecture

Repix follows a layered full-stack architecture.

```text
┌──────────────────────────────────────────────┐
│                 React Frontend               │
│                                              │
│ Repository Input → Loading → Chat Workspace  │
└──────────────────────┬───────────────────────┘
                       │ HTTP
                       ▼
┌──────────────────────────────────────────────┐
│                 FastAPI Backend               │
│                                              │
│ Routes → Schemas → Services → Data/AI Layer │
└──────────────┬───────────────┬───────────────┘
               │               │
               ▼               ▼
        ┌────────────┐   ┌──────────────┐
        │ PostgreSQL │   │   ChromaDB   │
        │            │   │              │
        │ Users      │   │ Embeddings   │
        │ Sessions   │   │ Chunks       │
        │ Messages   │   │ Metadata     │
        └────────────┘   └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ Gemini LLM   │
                         │              │
                         │ Answer       │
                         │ Generation   │
                         └──────────────┘
```

## Repository Analysis Pipeline

### 1. Input

The user provides a GitHub repository URL.

### 2. Validation

The backend checks that the URL is a GitHub HTTPS repository URL.

### 3. Cloning

GitPython clones the repository locally using a shallow clone.

### 4. Metadata Extraction

The system determines:

- language;
- branch;
- license.

### 5. File Reading

Relevant source files are read while common generated/build/cache directories are ignored.

### 6. Chunking

Large files are split into smaller chunks.

The chunks retain metadata such as file path, name, chunk type, and chunk number.

### 7. Embedding Generation

Sentence Transformers converts each chunk into a semantic vector.

```text
Code Chunk
   ↓
Embedding Model
   ↓
Vector
```

### 8. Vector Storage

Embeddings and documents are stored in a ChromaDB collection associated with the repository.

## Question Answering Pipeline

When the user asks a question:

```text
Question
   ↓
Embedding / Semantic Retrieval
   ↓
Relevant Code Chunks
   ↓
Prompt Construction
   ↓
Gemini
   ↓
Repository-aware Answer
```

The important RAG principle is that the LLM receives retrieved repository context rather than relying only on its pretrained knowledge.

## Chat Persistence

Chat state is stored separately from repository embeddings.

```text
User
  ↓
ChatSession
  ↓
ChatMessage
  ↓
PostgreSQL
```

This makes conversation history independent of the vector-store representation of the repository.

## Backend Service Responsibilities

### `github_service.py`

Repository URL validation, cloning, branch detection, language detection, and license detection.

### `repository_reader.py`

Repository file discovery and reading.

### `chunking_service.py`

Splits source content into chunks.

### `embedding_service.py`

Generates semantic embeddings.

### `vector_database.py`

Creates/retrieves ChromaDB collections and stores embeddings.

### `retrieval_service.py`

Finds relevant repository chunks for a user question.

### `prompt_builder.py`

Builds the context/prompt used by the answer-generation stage.

### `gemini_service.py`

Communicates with Google Gemini for answer generation.

### `orchestrator_service.py`

Coordinates retrieval, prompt construction, and AI generation.

## Architectural Strengths

- clear separation of frontend and backend;
- service-oriented backend structure;
- relational and vector storage are separated;
- embedding generation is isolated from retrieval;
- AI generation is isolated from repository processing;
- database migrations are tracked through Alembic;
- environment configuration is separated from source code.

## Current Architectural Gaps

- production persistence for local vector storage needs to be addressed;
- cloned repositories require lifecycle management;
- authenticated user identity should be propagated into chat ownership;
- automated testing and observability should be added before production deployment.
