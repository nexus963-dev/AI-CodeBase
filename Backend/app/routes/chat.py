import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage

from app.schemas.chat import ChatRequest
from app.services.orchestrator_service import chat_with_repository_stream
from app.services.chat_history import load_conversation_history


router = APIRouter()


def _event(payload: dict) -> str:
    """One NDJSON line for the streaming response."""
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _save_assistant_message(session_id: int, content: str) -> None:
    """
    Save the assistant answer with its own DB session.

    Runs inside the streaming generator, after the request-scoped
    session may already have been closed.
    """
    db = SessionLocal()
    try:
        db.add(ChatMessage(
            session_id=session_id,
            role="assistant",
            content=content,
        ))
        db.commit()
    finally:
        db.close()


# ==========================================================
# POST /chat
# Create a new chat or continue an existing chat.
#
# Streams NDJSON events:
#   {"type": "meta",  "session_id": 12}   first, before tokens
#   {"type": "token", "text": "..."}      repeated, one per chunk
#   {"type": "done"}                      answer finished + saved
#   {"type": "error", "detail": "..."}    generation failed
# ==========================================================

@router.post("/chat")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db)
):

    # --------------------------------------------------
    # 1. Find requested session if session_id is provided
    # --------------------------------------------------

    session = None

    if request.session_id:

        session = (
            db.query(ChatSession)
            .filter(
                ChatSession.id == request.session_id,
                ChatSession.user_id == 4,
                ChatSession.repository_name
                == request.repository_name
            )
            .first()
        )

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Chat session not found."
            )

    # --------------------------------------------------
    # 2. Create new session if no session exists
    # --------------------------------------------------

    if not session:

        # Use the first question as the chat title
        chat_title = request.question.strip()

        if len(chat_title) > 45:
            chat_title = chat_title[:45].rstrip() + "..."

        session = ChatSession(
            user_id=4,
            repository_name=request.repository_name,
            title=chat_title
        )

        db.add(session)
        db.commit()
        db.refresh(session)

    # --------------------------------------------------
    # 3. Save user's question
    # --------------------------------------------------

    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.question
    )

    db.add(user_message)
    db.commit()

    # --------------------------------------------------
    # 4. Generate AI answer (streamed token by token)
    # --------------------------------------------------

    try:

        # Latest 12 messages, oldest first
        conversation_history = load_conversation_history(
            db,
            session.id,
        )

    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to load chat history: {str(e)}"
        )

    session_id = session.id

    def event_stream():

        accumulated = []

        try:

            # Tell the client which session this stream belongs to
            # before the first token arrives.
            yield _event({
                "type": "meta",
                "session_id": session_id,
            })

            for token in chat_with_repository_stream(
                repository_name=request.repository_name,
                question=request.question,
                conversation_history=conversation_history,
            ):

                accumulated.append(token)

                yield _event({
                    "type": "token",
                    "text": token,
                })

            # --------------------------------------------------
            # 5. Save assistant answer (partial answers too)
            # --------------------------------------------------

            if accumulated:
                _save_assistant_message(
                    session_id,
                    "".join(accumulated),
                )

            yield _event({"type": "done"})

        except Exception as e:

            # Keep whatever tokens already reached the client.
            if accumulated:
                _save_assistant_message(
                    session_id,
                    "".join(accumulated),
                )

            yield _event({
                "type": "error",
                "detail": str(e),
            })

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
    )


# ==========================================================
# GET ALL CHAT SESSIONS
# ==========================================================

@router.get("/chat/sessions")
def get_chat_sessions(
    repository_name: str,
    db: Session = Depends(get_db)
):

    sessions = (
        db.query(ChatSession)
        .filter(
            ChatSession.user_id == 4,
            ChatSession.repository_name == repository_name
        )
        .order_by(
            ChatSession.updated_at.desc()
        )
        .all()
    )

    return [
        {
            "id": session.id,
            "title": session.title,
            "repository_name": session.repository_name,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
        for session in sessions
    ]


# ==========================================================
# GET MESSAGES OF ONE SESSION
# ==========================================================

@router.get("/chat/sessions/{session_id}")
def get_chat_messages(
    session_id: int,
    db: Session = Depends(get_db)
):

    # Verify that the session belongs to the current user
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.user_id == 4
        )
        .first()
    )

    if not session:

        raise HTTPException(
            status_code=404,
            detail="Chat session not found."
        )

    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id
        )
        .order_by(
            ChatMessage.created_at.asc()
        )
        .all()
    )

    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at,
        }
        for message in messages
    ]