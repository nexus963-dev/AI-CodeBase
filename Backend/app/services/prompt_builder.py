from pathlib import Path
from typing import Dict, List, Optional


# ==========================================================
# Token budget guards
# ==========================================================

# Maximum characters kept from a single retrieved chunk
MAX_CHUNK_CHARS = 1500

# Maximum characters for the whole "Repository Context" section
MAX_CONTEXT_CHARS = 12000

# Manifest pruning caps
MAX_MANIFEST_SYMBOL_FILES = 20        # normal questions: symbols for relevant files only
MAX_MANIFEST_SYMBOL_FILES_FULL = 150  # "all functions" questions: much wider symbol dump
MAX_MANIFEST_LISTED_FILES = 40        # other files listed as plain paths
MAX_MANIFEST_STRUCTURE_ENTRIES = 25   # unique directories in the structure summary

# Questions that need the widest manifest view
FUNCTION_LIST_TERMS = (
    "all functions",
    "every function",
    "each function",
    "list all",
    "all files",
    "every file",
    "methodology",
    "structure",
    "architecture",
    "overview",
)

# Question tokens ignored when matching the manifest (too generic)
QUESTION_STOPWORDS = {
    "what", "when", "where", "which", "how", "does", "this", "that",
    "with", "from", "file", "files", "code", "repo", "repository",
    "explain", "about", "give", "show", "tell", "please", "the",
    "and", "for", "are", "its", "it's", "can", "you",
}


def _truncate(text: str, limit: int) -> str:
    """Cut off text that would blow up the token budget."""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... [truncated]"


# ==========================================================
# Relevance ranking for retrieved chunks
# ==========================================================

def _relevance_band(distance: Optional[float], best: Optional[float]) -> str:
    """
    Label a chunk as high / medium / low relevance.

    ChromaDB returns L2 distances: smaller is better.
    Bands are relative to the best (smallest) distance so the
    thresholds work for any embedding space scale.
    """
    if distance is None or best is None:
        return "unknown"
    if distance <= best * 1.2:
        return "high"
    if distance <= best * 1.5:
        return "medium"
    return "low"


def _collect_context(retrieval_results: Dict) -> str:
    """
    Build the "Repository Context" section:
    - drops clearly irrelevant chunks (distance > 2x best)
    - labels each chunk with relevance + distance + source path
    - truncates oversized chunks
    - stops before exceeding the total context budget
    """
    documents = retrieval_results.get("documents", [[]])[0] or []
    metadatas = retrieval_results.get("metadatas", [[]])[0] or []
    distances = retrieval_results.get("distances", [[]])[0] or []

    entries = []
    for index, document in enumerate(documents):
        if not document:
            continue
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None
        entries.append(
            {
                "document": document,
                "path": metadata.get("file_path", "unknown file"),
                "distance": distance,
            }
        )

    present_distances = [
        entry["distance"] for entry in entries if entry["distance"] is not None
    ]
    best = min(present_distances) if present_distances else None

    # Filter out weak matches, but always keep at least one chunk
    if best is not None:
        threshold = max(best * 2.0, best + 1e-9)
        kept = [
            entry
            for entry in entries
            if entry["distance"] is None or entry["distance"] <= threshold
        ]
        if kept:
            entries = kept

    blocks = []
    used_chars = 0

    for position, entry in enumerate(entries, start=1):
        band = _relevance_band(entry["distance"], best)
        header = f"[{position}] relevance: {band}"
        if entry["distance"] is not None:
            header += f" | distance: {entry['distance']:.3f}"
        header += f" | source: {entry['path']}"

        document = _truncate(entry["document"], MAX_CHUNK_CHARS)
        block = f"{header}\n{document}"

        # Never exceed the total context budget (keep at least one block)
        if blocks and used_chars + len(block) > MAX_CONTEXT_CHARS:
            break

        blocks.append(block)
        used_chars += len(block)

    return "\n\n------------------------\n\n".join(blocks)


# ==========================================================
# Manifest pruning
# ==========================================================

def _question_tokens(question: str) -> List[str]:
    raw = "".join(
        character.lower() if character.isalnum() else " "
        for character in question
    ).split()
    return [
        token for token in raw
        if len(token) >= 4 and token not in QUESTION_STOPWORDS
    ]


def _path_is_relevant(manifest_path: str, retrieved_paths: List[str], tokens: List[str]) -> bool:
    """A manifest file is relevant if a retrieved chunk came from it
    or if one of the question keywords appears in its path."""
    normalized = manifest_path.replace("\\", "/").lower()

    for retrieved in retrieved_paths:
        if not retrieved:
            continue
        retrieved_normalized = retrieved.replace("\\", "/")
        if retrieved_normalized.endswith(normalized):
            return True

    return any(token in normalized for token in tokens)


def _format_manifest(
    manifest: Dict,
    retrieved_paths: Optional[List[str]] = None,
    question: str = "",
) -> str:
    """
    Pruned manifest:
    - compact directory structure summary
    - symbol details only for files related to the question
      (or all files when the question asks for full structure)
    - a capped plain list of remaining files
    """
    if not manifest:
        return "No repository manifest is available."

    files = manifest.get("files", [])
    if not files:
        return "No repository manifest is available."

    retrieved_paths = retrieved_paths or []
    tokens = _question_tokens(question)
    wants_full_symbols = any(
        term in question.lower() for term in FUNCTION_LIST_TERMS
    )
    symbol_cap = (
        MAX_MANIFEST_SYMBOL_FILES_FULL
        if wants_full_symbols
        else MAX_MANIFEST_SYMBOL_FILES
    )

    lines = [
        f"Repository: {manifest.get('repository', 'unknown')}",
        f"Files: {manifest.get('file_count', len(files))}",
    ]

    # --- Directory structure summary -----------------------
    directories = []
    for file_entry in files:
        path = file_entry.get("path", "")
        directory = (
            path.rsplit("/", 1)[0] + "/"
            if "/" in path
            else "(root)"
        )
        if directory not in directories:
            directories.append(directory)

    lines.append("")
    lines.append("Directory structure:")
    for directory in directories[:MAX_MANIFEST_STRUCTURE_ENTRIES]:
        lines.append(f"- {directory}")
    if len(directories) > MAX_MANIFEST_STRUCTURE_ENTRIES:
        lines.append(
            f"- ... and {len(directories) - MAX_MANIFEST_STRUCTURE_ENTRIES} more directories"
        )

    # --- Symbol details for relevant files -----------------
    key_files = []
    other_paths = []

    for file_entry in files:
        path = file_entry.get("path", "")
        symbols = file_entry.get("symbols", [])
        relevant = wants_full_symbols or _path_is_relevant(
            path, retrieved_paths, tokens
        )

        if symbols and relevant and len(key_files) < symbol_cap:
            symbol_text = ", ".join(
                f"{symbol['kind']} {symbol['name']} (line {symbol['line']})"
                for symbol in symbols
            )
            key_files.append(f"- {path}: {symbol_text}")
        else:
            other_paths.append(path)

    if key_files:
        lines.append("")
        lines.append("Key files (symbols):")
        lines.extend(key_files)

    # --- Remaining files as a capped plain list -------------
    if other_paths:
        listed = other_paths[:MAX_MANIFEST_LISTED_FILES]
        lines.append("")
        lines.append("Other files:")
        for start in range(0, len(listed), 8):
            lines.append("- " + ", ".join(listed[start:start + 8]))
        remaining = len(other_paths) - len(listed)
        if remaining > 0:
            lines.append(f"- ... and {remaining} more files")

    return "\n".join(lines)


# ==========================================================
# Prompt assembly
# ==========================================================

def build_prompt(
    question: str,
    retrieval_results: Dict,
    manifest: Dict | None = None,
    conversation_history: str = "",
) -> str:
    """
    Builds the final prompt for Gemini using:
    - relevance-ranked, budgeted repository chunks
    - a pruned repository manifest
    - the latest conversation history
    """

    metadatas = retrieval_results.get("metadatas", [[]])[0] or []
    retrieved_paths = [
        metadata.get("file_path", "")
        for metadata in metadatas
        if metadata
    ]

    context = _collect_context(retrieval_results)
    manifest_context = _format_manifest(
        manifest,
        retrieved_paths=retrieved_paths,
        question=question,
    )
    history = conversation_history.strip() or "No previous conversation."

    prompt = f"""
You are Repix, an AI assistant that helps developers understand GitHub repositories.

Rules:
- Answer only using the Repository Context and Repository Manifest below.
- If the answer is not present, reply exactly: "I couldn't find that information in the repository."
- Cite evidence as a relative source path and line number, for example `app/auth.py:42`.
- Context chunks are ranked: trust `high relevance` chunks over `low relevance` ones.
- For questions that ask for all functions, files, or the overall structure, rely on the Repository Manifest instead of guessing from retrieved excerpts.
- For greetings or casual messages (for example "hi" or "thanks"), reply briefly and naturally, and mention what repository you are ready to help with. Never refuse a greeting.
- Use Markdown: bullet points for lists and fenced code blocks for code.
- Keep the answer clear and concise.

Conversation History (oldest first, latest last):

{history}

Repository Manifest:

{manifest_context}

User Question:

{question}

Repository Context (retrieved by semantic similarity, best match first):

{context or "No relevant code chunks were retrieved."}
"""

    return prompt
