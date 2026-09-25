from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User          # noqa: F401 (register with Base)
from app.models.chat_session import ChatSession  # noqa: F401
from app.models.chat_message import ChatMessage
from app.services.chat_history import load_conversation_history


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_messages(db, count):
    session = ChatSession(user_id=1, repository_name="demo", title="t")
    db.add(session)
    db.commit()
    db.refresh(session)

    base_time = datetime(2026, 1, 1, 12, 0, 0)
    for index in range(1, count + 1):
        db.add(
            ChatMessage(
                session_id=session.id,
                role="user" if index % 2 else "assistant",
                content=f"message-{index}",
                created_at=base_time + timedelta(seconds=index),
            )
        )
    db.commit()
    return session


def test_returns_latest_messages_not_oldest():
    """The old implementation kept the OLDEST 12 messages.
    It must now keep the LATEST 12."""
    db = make_session()
    session = seed_messages(db, count=15)

    history = load_conversation_history(db, session.id)
    numbers = [
        int(line.split("message-")[1])
        for line in history.splitlines()
    ]

    # latest 12 of 15 => exactly messages 4..15 (oldest 3 dropped)
    assert numbers == list(range(4, 16))


def test_history_is_ordered_oldest_first_latest_last():
    db = make_session()
    session = seed_messages(db, count=15)

    history = load_conversation_history(db, session.id)
    lines = history.splitlines()

    # seed uses: odd => user, even => assistant
    assert lines[0] == "assistant: message-4"
    assert lines[-1] == "user: message-15"

    # strictly increasing message numbers
    numbers = [int(line.split("message-")[1]) for line in lines]
    assert numbers == sorted(numbers)


def test_short_conversation_returns_everything():
    db = make_session()
    session = seed_messages(db, count=3)

    history = load_conversation_history(db, session.id)

    assert "message-1" in history
    assert "message-3" in history


def test_empty_session_returns_empty_string():
    db = make_session()
    session = ChatSession(user_id=1, repository_name="demo", title="t")
    db.add(session)
    db.commit()
    db.refresh(session)

    assert load_conversation_history(db, session.id) == ""
