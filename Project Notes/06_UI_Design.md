# UI Design

## Design Goal

The Repix frontend is designed around a simple flow:

```text
Landing Page
     ↓
Repository Input
     ↓
Repository Analysis
     ↓
Loading Sequence
     ↓
Chat Workspace
```

The interface aims to make repository analysis feel like a single continuous workflow rather than exposing every backend operation to the user.

## Main Components

The frontend components are located in:

```text
Frontend/src/components/
```

Important components include:

- `Navbar.jsx`
- `Hero.jsx`
- `RepositoryInput.jsx`
- `LoadingSequence.jsx`
- `ChatLayout.jsx`
- `ChatWindow.jsx`
- `Sidebar.jsx`
- `ChatMessage.jsx`
- `MessageInput.jsx`
- `Features.jsx`
- `HowItWorks.jsx`
- `Footer.jsx`
- `AuroraBackground.jsx`

## Landing Page

The landing page introduces Repix and provides the repository input flow.

Major sections include:

- navigation;
- hero section;
- repository input;
- feature overview;
- how-it-works section;
- footer.

## Repository Input

The repository input is responsible for:

1. accepting the GitHub repository URL;
2. sending the analysis request to the backend;
3. displaying analysis progress;
4. receiving repository metadata;
5. transitioning to the chat experience.

## Loading Sequence

The application provides a visual analysis sequence with stages representing:

1. repository connection;
2. file analysis;
3. code chunk creation;
4. embedding generation;
5. AI knowledge-base preparation.

The sequence is a frontend representation of the analysis workflow. It should not be interpreted as a real-time progress percentage from the backend.

## Chat Workspace

The chat workspace is composed of:

```text
ChatLayout
├── Sidebar
└── ChatWindow
    ├── ChatMessage
    └── MessageInput
```

## Sidebar

The sidebar displays repository chat sessions and allows the user to switch between conversations.

## Chat Window

The chat window:

- loads existing messages;
- sends new questions;
- displays assistant answers;
- associates messages with the selected repository/session.

## Message Input

The message input provides the interaction point for asking repository questions.

## Visual Direction

The application uses a modern AI/developer-tool visual style with:

- animated background elements;
- gradient/aurora visual effects;
- icon-based UI;
- loading states;
- conversational layout.

## State Management

The frontend currently uses React state and browser local storage for repository metadata needed across the application flow.

Examples include:

```text
repositoryName
chunkCount
repositoryLanguage
repositoryBranch
repositoryLicense
```

## Environment Configuration

The backend API address is supplied through:

```env
VITE_API_URL=http://localhost:8000
```

This avoids hard-coding the local backend URL throughout the React components.

## Future UI Improvements

- repository file explorer;
- file-level citations in answers;
- markdown/code syntax highlighting improvements;
- streaming answer animation;
- better error states;
- mobile optimization;
- repository re-indexing controls;
- user profile/authentication UI.
