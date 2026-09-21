# Tasks and Roadmap

## Phase 1 — Project Foundation

- [x] Create repository
- [x] Establish Backend and Frontend structure
- [x] Set up FastAPI
- [x] Set up React/Vite
- [x] Configure PostgreSQL
- [x] Configure SQLAlchemy
- [x] Configure Alembic
- [x] Add environment-based configuration

## Phase 2 — Repository Processing

- [x] Validate GitHub repository URLs
- [x] Clone repositories
- [x] Use shallow Git clones
- [x] Detect dominant programming language
- [x] Detect repository branch
- [x] Detect repository license
- [x] Read repository files
- [x] Ignore generated/cache directories

## Phase 3 — RAG Pipeline

- [x] Implement code chunking
- [x] Generate Sentence Transformer embeddings
- [x] Integrate ChromaDB
- [x] Store chunk metadata
- [x] Implement semantic retrieval
- [x] Build repository-aware prompts
- [x] Integrate Gemini answer generation
- [x] Connect retrieval and generation through an orchestrator

## Phase 4 — Chat System

- [x] Create chat session model
- [x] Create chat message model
- [x] Add Alembic migration
- [x] Create chat endpoint
- [x] Save user questions
- [x] Save assistant answers
- [x] Retrieve previous sessions
- [x] Retrieve messages for a session
- [x] Add chat sidebar UI

## Phase 5 — Frontend

- [x] Create landing page
- [x] Add repository input
- [x] Add analysis loading sequence
- [x] Add repository metadata display
- [x] Add chat workspace
- [x] Add message input
- [x] Add chat messages
- [x] Add sidebar
- [x] Configure API URL using environment variables
- [x] Verify complete local workflow

## Phase 6 — Repository Quality

- [x] Add Python requirements
- [x] Add frontend `.gitignore`
- [x] Ignore virtual environments
- [x] Ignore local `.env` files
- [x] Ignore ChromaDB data
- [x] Remove tracked Python cache files
- [x] Add `.env.example`
- [ ] Add automated backend tests
- [ ] Add automated frontend tests
- [ ] Add CI workflow

## Phase 7 — Deployment

- [ ] Prepare production persistence strategy
- [ ] Deploy backend
- [ ] Provision production PostgreSQL
- [ ] Configure production environment variables
- [ ] Configure vector-store persistence
- [ ] Deploy frontend
- [ ] Connect frontend to deployed backend
- [ ] Verify production CORS
- [ ] Run complete production test

## Phase 8 — Product Improvements

- [ ] Replace fixed chat user ID with authenticated user identity
- [ ] Complete GitHub OAuth flow
- [ ] Add repository re-indexing
- [ ] Add repository update detection
- [ ] Add file-level citations
- [ ] Add code syntax highlighting in answers
- [ ] Add streaming AI responses
- [ ] Add better error handling
- [ ] Add rate limiting
- [ ] Add structured logging
- [ ] Add monitoring

## Definition of a Strong Production Release

Before calling the project production-ready, the following should be true:

- authentication is properly tied to user-owned data;
- repository/vector data persists safely;
- secrets are managed through the deployment platform;
- automated tests cover critical services;
- frontend and backend communicate through production URLs;
- CORS is restricted to the deployed frontend;
- failures produce useful user-facing messages;
- the deployment can be rebuilt without losing application data.
