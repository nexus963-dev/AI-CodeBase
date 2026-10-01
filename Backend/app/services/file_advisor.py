"""
Per-file advisor (Phase 3).

Two flows that share one guarded file reader:
- explanation: what does this file do and how does it fit the repo?
- improvement suggestions: concrete, prioritized, real issues only

Every file request is resolved through the repository manifest, so
a client can only ever read files that were part of the analysis
(no path traversal, no .git internals, no files outside the clone).
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.config.settings import settings
from app.services.repository_manifest import load_repository_manifest


# ==========================================================
# Budgets (same spirit as prompt_builder.py)
# ==========================================================

# Maximum characters of source code kept in the prompt
MAX_FILE_CHARS = 12000

# Manifest pruning caps for the structure context
MAX_STRUCTURE_ENTRIES = 30
MAX_SIBLING_FILES = 30
MAX_SYMBOLS_LISTED = 40


class UnknownRepositoryError(Exception):
    """The repository was never analyzed on this server."""


class UnknownFileError(Exception):
    """The file is not part of the analyzed repository."""


def _truncate(text: str, limit: int) -> str:
    """Cut off text that would blow up the token budget."""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... [truncated]"


# ==========================================================
# Guarded file resolution
# ==========================================================

def resolve_repository(repository_name: str) -> Tuple[Path, Dict]:
    """
    Resolve an analyzed repository by name.

    Returns (repo_path, manifest). Raises UnknownRepositoryError
    for anything that is not a directory inside REPOSITORIES_PATH
    (this also rejects repository_name values like "../../etc").
    """
    if not repository_name or not repository_name.strip():
        raise UnknownRepositoryError("Repository name is empty.")

    root = Path(settings.REPOSITORIES_PATH).resolve()
    repo_path = (root / repository_name).resolve()

    if not repo_path.is_relative_to(root) or not repo_path.is_dir():
        raise UnknownRepositoryError(
            f"Repository '{repository_name}' has not been analyzed yet."
        )

    return repo_path, load_repository_manifest(repo_path)


def resolve_file(repository_name: str, file_path: str) -> Tuple[Path, Dict, Dict]:
    """
    Resolve a file inside an analyzed repository.

    Returns (target, manifest, file_entry). Raises
    UnknownRepositoryError / UnknownFileError. The file must be
    listed in the manifest, which is the same set of files the
    analysis indexed.
    """
    if not file_path or not file_path.strip():
        raise UnknownFileError("File path is empty.")

    repo_path, manifest = resolve_repository(repository_name)

    normalized = file_path.replace("\\", "/").lstrip("/")

    entries = {
        entry.get("path", ""): entry
        for entry in manifest.get("files", [])
    }

    entry = entries.get(normalized)

    if entry is None:
        raise UnknownFileError(
            f"File '{file_path}' is not part of '{repository_name}'. "
            "Re-analyze the repository if it was added recently."
        )

    target = (repo_path / normalized).resolve()

    # Defense in depth: the manifest should already guarantee this.
    if not target.is_relative_to(repo_path) or not target.is_file():
        raise UnknownFileError(
            f"File '{file_path}' could not be found on disk."
        )

    return target, manifest, entry


def read_file_content(target: Path) -> str:
    """Read a source file leniently (encodings vary across repos)."""
    return target.read_text(encoding="utf-8", errors="ignore")


# ==========================================================
# Shared manifest context
# ==========================================================

def _structure_context(manifest: Dict, current_path: str) -> str:
    """
    Compact repository context for file prompts:
    - directory listing
    - sibling files in the same directory
    - declared symbols of the file itself
    """
    files = manifest.get("files", [])
    if not files:
        return "No repository manifest is available."

    current_directory = (
        current_path.rsplit("/", 1)[0]
        if "/" in current_path
        else "(root)"
    )

    lines = [
        f"Repository: {manifest.get('repository', 'unknown')}",
        f"Files: {manifest.get('file_count', len(files))}",
    ]

    # --- Directory structure -------------------------------
    directories: List[str] = []
    for file_entry in files:
        path = file_entry.get("path", "")
        directory = (
            path.rsplit("/", 1)[0] + "/"
            if "/" in path
            else "(root)/"
        )
        if directory not in directories:
            directories.append(directory)

    lines.append("")
    lines.append("Directory structure:")
    for directory in directories[:MAX_STRUCTURE_ENTRIES]:
        marker = " <-- this file is here" if directory == current_directory + "/" or (
            current_directory == "(root)" and directory == "(root)/"
        ) else ""
        lines.append(f"- {directory}{marker}")
    if len(directories) > MAX_STRUCTURE_ENTRIES:
        lines.append(
            f"- ... and {len(directories) - MAX_STRUCTURE_ENTRIES} more directories"
        )

    # --- Siblings in the same directory ---------------------
    siblings = [
        file_entry.get("path", "")
        for file_entry in files
        if file_entry.get("path", "") != current_path
        and (
            file_entry.get("path", "").rsplit("/", 1)[0] + "/"
            if "/" in file_entry.get("path", "")
            else "(root)/"
        )
        == (current_directory + "/" if current_directory != "(root)" else "(root)/")
    ]

    if siblings:
        lines.append("")
        lines.append(f"Other files in {current_directory}/:")
        for sibling in siblings[:MAX_SIBLING_FILES]:
            lines.append(f"- {sibling}")
        if len(siblings) > MAX_SIBLING_FILES:
            lines.append(
                f"- ... and {len(siblings) - MAX_SIBLING_FILES} more files"
            )

    # --- Symbols of this file ------------------------------
    current_entry = next(
        (
            file_entry
            for file_entry in files
            if file_entry.get("path", "") == current_path
        ),
        None,
    )
    symbols = (current_entry or {}).get("symbols", [])

    lines.append("")
    if symbols:
        lines.append("This file's declared symbols (kind name at line):")
        for symbol in symbols[:MAX_SYMBOLS_LISTED]:
            lines.append(
                f"- {symbol.get('kind', '?')} {symbol.get('name', '?')} "
                f"(line {symbol.get('line', '?')})"
            )
    else:
        lines.append(
            "This file's declared symbols: none detected "
            "(not a parsed source file, or no top-level definitions)."
        )

    return "\n".join(lines)


# ==========================================================
# Prompt builders
# ==========================================================

def build_explanation_prompt(
    repository_name: str,
    file_path: str,
    file_content: str,
    manifest: Dict,
) -> str:
    """Prompt that explains a single file to a developer."""

    structure = _structure_context(manifest, file_path)
    content = _truncate(file_content, MAX_FILE_CHARS)

    return f"""
You are Repix, an AI assistant that helps developers understand GitHub repositories.

Rules:
- Explain ONLY the file below, using its contents and the repository structure context.
- Refer to concrete parts as `path:line`, for example `app/auth.py:42`.
- If the file is empty or unreadable, reply exactly: "I couldn't find that information in the repository."
- Never invent code, functions, or behavior that is not in the file.
- Use Markdown: short headings, bullet lists, and fenced code blocks for code.
- Keep it clear and developer-friendly.

Repository: {repository_name}

Repository Context (from the analysis manifest):

{structure}

File Path:

{file_path}

File Contents (may be truncated):

{content}

Write the explanation with exactly these four Markdown sections:

1. **Purpose** - one or two sentences on what this file does.
2. **Key Components** - the important functions, classes, and constants, each with a `path:line` reference and a short description.
3. **How It Fits** - how this file relates to the rest of the repository, using the structure above (name likely neighboring files it works with).
4. **Dependencies & Side Effects** - what it imports or relies on, plus anything notable (file I/O, globals, configuration).
"""


def build_suggestion_prompt(
    repository_name: str,
    file_path: str,
    file_content: str,
    manifest: Dict,
) -> str:
    """Prompt that produces prioritized improvement suggestions for a file."""

    structure = _structure_context(manifest, file_path)
    content = _truncate(file_content, MAX_FILE_CHARS)

    return f"""
You are Repix, a senior engineer reviewing code in a GitHub repository.

Rules:
- Suggest improvements ONLY for issues that actually exist in the file below; never invent problems.
- Every suggestion must cite the exact location as `path:line`, for example `app/auth.py:42`.
- Order suggestions by priority: bugs and correctness first, then security, then performance, then code quality and readability, then testing gaps.
- Produce at most 6 suggestions - the most valuable ones, not a checklist of every nit.
- If the file is in good shape, say so plainly instead of manufacturing issues.
- Use Markdown and format EVERY suggestion exactly like this template:

### [priority: high|medium|low] Short title
**Issue:** what is wrong or missing, with `path:line`.
**Why it matters:** the concrete risk or cost.
**Suggested fix:** how to fix it, including a small fenced code block when a code change is needed.

Repository: {repository_name}

Repository Context (from the analysis manifest):

{structure}

File Path:

{file_path}

File Contents (may be truncated):

{content}

Review the file and return the prioritized suggestions in the format above.
"""
