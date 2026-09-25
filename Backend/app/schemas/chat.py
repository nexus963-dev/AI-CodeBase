from pydantic import BaseModel


class ChatRequest(BaseModel):
    repository_name: str
    question: str
    session_id: int | None = None


class ChatResponse(BaseModel):
    answer: str
    session_id: int