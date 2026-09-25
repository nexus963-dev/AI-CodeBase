# Database Design

Repix uses PostgreSQL for relational application data and ChromaDB for semantic repository data.

## PostgreSQL

PostgreSQL stores application-level information that benefits from structured relational storage.

### Users

Table:

```text
users
```

Current fields include:

| Field | Purpose |
|---|---|
| `id` | Primary key |
| `username` | User name |
| `email` | Unique user email |
| `github_id` | Optional GitHub identifier |
| `hashed_password` | Stored password hash |
| `created_at` | Account creation time |

A user can have multiple chat sessions.

## Chat Sessions

Table:

```text
chat_sessions
```

Current fields include:

| Field | Purpose |
|---|---|
| `id` | Primary key |
| `user_id` | Foreign key to users |
| `repository_name` | Repository associated with the chat |
| `title` | Session title |
| `created_at` | Session creation time |
| `updated_at` | Last update time |

A session belongs to a user and can contain multiple messages.

## Chat Messages

Table:

```text
chat_messages
```

Messages belong to a chat session.

The model stores:

- session ID;
- role;
- content;
- creation timestamp.

## Relationships

```text
User
 │
 └── 1:N ── ChatSession
               │
               └── 1:N ── ChatMessage
```

SQLAlchemy relationships use cascading deletion for dependent chat records.

## Alembic

Database schema changes are managed through Alembic migrations.

The repository includes a migration for the chat-session and chat-message functionality.

Typical migration commands:

```bash
cd Backend

alembic upgrade head
```

## ChromaDB

ChromaDB stores semantic repository information.

A repository is converted into chunks, and each chunk is represented by:

```text
ID
Document
Embedding
Metadata
```

Metadata includes:

- file path;
- file name;
- chunk type;
- chunk number.

## Why Two Storage Systems?

PostgreSQL and ChromaDB serve different purposes.

### PostgreSQL

Best suited for:

- users;
- sessions;
- messages;
- structured relationships;
- transactional application data.

### ChromaDB

Best suited for:

- embeddings;
- semantic similarity search;
- repository chunk retrieval.

This separation allows each storage system to solve the problem it is designed for.

## Deployment Consideration

The current ChromaDB implementation uses persistent local storage. A future production deployment must provide an appropriate persistent storage strategy for vector data and cloned repositories.
