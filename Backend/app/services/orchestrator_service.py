from app.services.vector_database import get_repository_collection
from app.services.retrieval_service import retrieve_relevant_chunks
from app.services.prompt_builder import build_prompt
from app.services.llm_service import generate_repository_answer
from app.config.settings import settings
from app.services.repository_manifest import load_repository_manifest
from pathlib import Path

def chat_with_repository(
    repository_name: str,
    question: str,
    conversation_history: str = ""
):

    try:

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
            return "I couldn't find any relevant information in this repository."

        # Step 4
        prompt = build_prompt(
            question=question,
            retrieval_results=retrieval_results,
            manifest=load_repository_manifest(Path(settings.REPOSITORIES_PATH) / repository_name),
            conversation_history=conversation_history,
        )

        # Step 5
        return generate_repository_answer(prompt)

    except Exception as e:
        return f"Error: {str(e)}"