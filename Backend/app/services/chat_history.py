from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage


# How many of the LATEST messages are sent to the LLM
HISTORY_LIMIT = 12


def load_conversation_history(
    db: Session,
    session_id: int,
    limit: int = HISTORY_LIMIT,
) -> str:
    """
    Returns the most recent `limit` messages of a chat session,
    oldest first (so the newest messages are closest to the question).

    The previous implementation used ASC order with LIMIT, which kept
    the OLDEST 12 messages and dropped recent context as chats grew.
    """

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(
            ChatMessage.created_at.desc(),
            ChatMessage.id.desc(),
        )
        .limit(limit)
        .all()
    )

    # Reverse so the format stays "oldest first, latest last"
    messages.reverse()

    return "\n".join(
        f"{message.role}: {message.content}"
        for message in messages
    )
