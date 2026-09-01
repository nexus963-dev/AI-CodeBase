from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.orchestrator_service import chat_with_repository


router = APIRouter()


# ==========================================================
# POST /chat
# Create a new chat or continue an existing chat
# ==========================================================

@router.post("/chat", response_model=ChatResponse)
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
    # 4. Generate AI answer
    # --------------------------------------------------

    try:

        previous_messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc())
            .limit(12)
            .all()
        )
        conversation_history = "\n".join(
            f"{message.role}: {message.content}"
            for message in previous_messages
        )

        answer = chat_with_repository(
            repository_name=request.repository_name,
            question=request.question,
            conversation_history=conversation_history,
        )

    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate answer: {str(e)}"
        )

    # --------------------------------------------------
    # 5. Save assistant answer
    # --------------------------------------------------

    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer
    )

    db.add(assistant_message)

    # Update session timestamp
    db.commit()
    db.refresh(session)

    # --------------------------------------------------
    # 6. Return answer + session ID
    # --------------------------------------------------

    return ChatResponse(
        answer=answer,
        session_id=session.id
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