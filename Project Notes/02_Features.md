# Features

## 1. Repository Input

The application accepts a GitHub repository URL and validates the URL before cloning.

## 2. Repository Cloning

GitPython is used to clone the repository. The implementation uses a shallow clone to reduce unnecessary Git history.

## 3. Repository Metadata

The application extracts:

- dominant programming language;
- active branch;
- license information.

Language detection is based on source-file extensions and excludes common non-source directories.

## 4. Repository Reading

Repository files are read through the backend repository-reading services.

Directories such as `.git`, `node_modules`, virtual environments, build directories, and Python cache directories are excluded from processing.

## 5. Code Chunking

Source code is divided into smaller chunks so that relevant sections can be retrieved efficiently instead of sending an entire repository to the language model.

## 6. Embeddings

The application uses Sentence Transformers with:

```text
all-MiniLM-L6-v2
```

Each code chunk is converted into a numerical embedding.

## 7. Vector Storage

ChromaDB is used as the vector database.

Stored information includes:

- chunk ID;
- source document;
- embedding;
- file path;
- file name;
- chunk type;
- chunk number.

## 8. Semantic Retrieval

When a user asks a question, the application retrieves repository chunks that are semantically relevant to the question.

## 9. AI Answer Generation

The retrieved context is passed into the repository-answer generation pipeline, which uses Google Gemini.

## 10. Chat Sessions

A repository conversation can be represented by a chat session.

A session stores:

- repository name;
- title;
- creation time;
- update time;
- associated user.

## 11. Chat Messages

Each session can contain multiple messages.

Messages store:

- role;
- content;
- creation timestamp.

## 12. React Interface

The frontend provides:

- repository input;
- loading/analyzing state;
- repository information;
- chat interface;
- chat history/sidebar;
- message input;
- response display.

## 13. Configuration

The frontend backend URL is configurable through a Vite environment variable, allowing local and future deployed environments to use different API addresses.
