from typing import Dict


def _format_manifest(manifest: Dict) -> str:
    lines = [
        f"Repository: {manifest.get('repository', 'unknown')}",
        f"Files: {manifest.get('file_count', 0)}",
    ]
    for file_entry in manifest.get("files", []):
        symbols = file_entry.get("symbols", [])
        symbol_text = ", ".join(
            f"{symbol['kind']} {symbol['name']} (line {symbol['line']})"
            for symbol in symbols
        )
        lines.append(f"- {file_entry['path']}" + (f": {symbol_text}" if symbol_text else ""))
    return "\n".join(lines)


def build_prompt(
    question: str,
    retrieval_results: Dict,
    manifest: Dict | None = None,
    conversation_history: str = "",
) -> str:
    """
    Builds the final prompt for Gemini
    using retrieved repository chunks.
    """

    documents = retrieval_results["documents"][0]
    metadatas = retrieval_results.get("metadatas", [[]])[0]

    context_parts = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        source = metadata.get("file_path", "unknown file")
        context_parts.append(f"Source: {source}\n{document}")
    context = "\n\n------------------------\n\n".join(context_parts)
    manifest_context = _format_manifest(manifest) if manifest else "No repository manifest is available."

    prompt = f"""
    You are an AI assistant that helps developers understand GitHub repositories.

    Rules:
    - Answer only using the provided repository context.
    - If the answer is not present, say:
    "I couldn't find that information in the repository."
    - For file and line questions, cite the relative source path and line number from the context or manifest.
    - For function-list questions, use the complete repository manifest instead of guessing from retrieved excerpts.
    - Keep your answers clear and concise.

    Conversation History:

    {conversation_history or "No previous conversation."}

    Repository Manifest:

    {manifest_context}

    User Question:

    {question}

    Repository Context:

    {context}
    """

    return prompt