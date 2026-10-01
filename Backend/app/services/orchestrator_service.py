from app.services.vector_database import get_repository_collection
from app.services.retrieval_service import retrieve_relevant_chunks
from app.services.prompt_builder import build_prompt
from app.services.llm_service import (
    generate_repository_answer,
    stream_repository_answer,
)
from app.config.settings import settings
from app.services.repository_manifest import load_repository_manifest
from pathlib import Path
from typing import Iterator, Optional


def _prepare_answer_prompt(
    repository_name: str,
    question: str,
    conversation_history: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """
    Shared steps 1-3: retrieval + prompt building.

    Returns (prompt, fallback_message):
    - (prompt, None)        -> answer the prompt with the LLM
    - (None, fallback_text) -> nothing relevant was retrieved
    """

    # Step 1
    collection = get_repository_collection(repository_name)

    # Step 2
    retrieval_results = retrieve_relevant_chunks(
        collection=collection,
        question=question,
        top_k=min(collection.count(), 30) if any(
            term in question.lower()
            for term in ("architecture", "all functions", "every function", "methodology", "structure")
        ) else 5,
    )

    # Step 3
    if not retrieval_results["documents"][0]:
        return None, "I couldn't find any relevant information in this repository."

    # Step 4
    prompt = build_prompt(
        question=question,
        retrieval_results=retrieval_results,
        manifest=load_repository_manifest(Path(settings.REPOSITORIES_PATH) / repository_name),
        conversation_history=conversation_history,
    )

    return prompt, None


def chat_with_repository(
    repository_name: str,
    question: str,
    conversation_history: str = ""
):

    try:

        prompt, fallback_message = _prepare_answer_prompt(
            repository_name=repository_name,
            question=question,
            conversation_history=conversation_history,
        )

        if prompt is None:
            return fallback_message

        # Step 5
        return generate_repository_answer(prompt)

    except Exception as e:
        return f"Error: {str(e)}"


def chat_with_repository_stream(
    repository_name: str,
    question: str,
    conversation_history: str = ""
) -> Iterator[str]:
    """
    Same pipeline as chat_with_repository, but yields answer
    tokens as soon as the LLM produces them.

    Prompt-preparation errors are converted to the same
    "Error: ..." text as before; LLM errors propagate so the
    route can report them on the stream.
    """

    try:
        prompt, fallback_message = _prepare_answer_prompt(
            repository_name=repository_name,
            question=question,
            conversation_history=conversation_history,
        )
    except Exception as e:
        yield f"Error: {str(e)}"
        return

    if prompt is None:
        yield fallback_message
        return

    yield from stream_repository_answer(prompt)
