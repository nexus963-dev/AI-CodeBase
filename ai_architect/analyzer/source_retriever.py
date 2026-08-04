"""Read source code on demand from the cloned repository on disk.

PostgreSQL stores only an *index* of the repository — file paths, entity names,
signatures and line numbers. The actual source lives in the cloned repository at
``MEDIA_ROOT/repos/<project_id>/`` (the single source of truth for code).

This module reads exactly the byte ranges the metadata points at, on demand,
and never loads a whole repository into memory or into the LLM context. It is
used by :mod:`analyzer.context_builder` when a question needs real
implementation details rather than metadata alone.

Guarantees
----------
* **Scoped reads** — every path is resolved and verified to stay inside the
  project's clone directory before the file is opened.
* **Bounded reads** — each snippet is capped in lines and characters, and a
  caller-supplied budget prevents any single question from reading more than a
  fixed amount of code.
* **Metadata-only DB** — nothing read from disk is ever written back to
  PostgreSQL; the database index is untouched.
"""

import re
from pathlib import Path

from django.conf import settings

# Per-snippet safety caps.
DEFAULT_MAX_SNIPPET_CHARS = 6000   # characters per entity snippet
DEFAULT_MAX_SNIPPET_LINES = 150    # lines per entity snippet
IMPORT_BLOCK_LINES = 40            # lines read from the top of a matched file
README_MAX_LINES = 80              # lines read from a README

# Context lines padded around an entity so decorators and call sites that
# surround the definition are visible to the model (e.g. FastAPI route
# decorators sitting on the line before ``def``).
PADDING_BEFORE = 3
PADDING_AFTER = 2


def project_root(project_id):
    """The clone directory for a project (same derivation as the analysis flow)."""
    return (Path(settings.MEDIA_ROOT) / 'repos' / str(project_id)).resolve()


def _safe_resolve(project_id, stored_path):
    """Resolve a stored path and refuse anything outside the project clone.

    ``Path.resolve()`` follows symlinks, so a symlinked file pointing outside
    the clone directory is rejected rather than read.
    """
    root = project_root(project_id)
    candidate = Path(stored_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Path is outside the project clone: {stored_path}")
    return candidate


def _read_range(project_id, stored_path, start_line, end_line, max_chars, max_lines):
    """Stream lines ``start_line..end_line`` (1-based) of one file.

    Returns ``None`` when the file does not exist. The returned dict carries
    the exact range that was actually read, which the prompt uses to cite the
    snippet.
    """
    try:
        path = _safe_resolve(project_id, stored_path)
    except ValueError:
        return None
    if not path.is_file():
        return None

    start = max(1, start_line)
    n_lines = min(max(0, end_line - start_line + 1), max_lines)
    chars = 0
    out = []
    truncated = False
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        # Skip to the first requested line.
        for _ in range(start - 1):
            f.readline()
        for _ in range(n_lines):
            line = f.readline()
            if not line:
                break
            chars += len(line)
            if chars > max_chars:
                truncated = True
                break
            out.append(line)

    if not out:
        return None
    snippet = ''.join(out).rstrip('\n')
    if truncated:
        snippet += '\n# ... (snippet truncated)'

    return {
        'path': stored_path,
        'start_line': start,
        'end_line': start + len(out) - 1,
        'snippet': snippet,
        'truncated': truncated,
    }


def relative_path(project_id, stored_path):
    """Convert a stored absolute path to the repository-relative form.

    Parser rows store absolute clone paths (``.../media/repos/<pid>/backend/
    app/database.py``). Responses must cite the repository-relative form
    (``backend/app/database.py``) and never leak local filesystem paths. The
    absolute path is returned unchanged when it cannot be mapped (defensive;
    callers render it only when nothing better exists).
    """
    try:
        candidate = Path(stored_path).resolve()
        root = project_root(project_id)
        if candidate.is_relative_to(root):
            return candidate.relative_to(root).as_posix()
    except (ValueError, OSError):
        pass
    return stored_path


# Definition-line patterns used to recover a reliable identifier when the
# parser stored a garbled name (a body fragment instead of ``def <name>``).
_DEF_NAME_RE = re.compile(r'\b(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(')
_CLASS_NAME_RE = re.compile(r'\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:(]')


def recover_name(project_id, entity):
    """Recover a reliable identifier for an entity from its definition line.

    The parser sometimes stores a garbled ``name`` for files with heavy
    decorators (e.g. ``'no valid Clerk'`` instead of ``get_current_user``).
    The source is the source of truth: the definition line at ``start_line``
    always holds ``def <name>`` / ``class <name>``. Returns ``None`` when
    nothing plausible is found so the caller can fall back to the stored name.
    """
    block = _read_range(
        project_id,
        entity['file_path'],
        (entity.get('start_line') or 1) - 1,
        (entity.get('start_line') or 1) + 2,
        DEFAULT_MAX_SNIPPET_CHARS,
        4,
    )
    if block is None:
        return None
    pattern = (_CLASS_NAME_RE if entity.get('type') == 'class'
               else _DEF_NAME_RE)
    match = pattern.search(block['snippet'])
    return match.group(1) if match else None


def read_entity(project_id, entity, max_chars=DEFAULT_MAX_SNIPPET_CHARS, max_lines=DEFAULT_MAX_SNIPPET_LINES):
    """Read the body of one metadata entity (function/class/method).

    Adds a little padding around the entity so surrounding context (decorators,
    the enclosing ``def`` signature, nearby helper calls) is visible.
    """
    start = max(1, (entity.get('start_line') or 1) - PADDING_BEFORE)
    end = (entity.get('end_line') or start) + PADDING_AFTER
    return _read_range(project_id, entity['file_path'], start, end, max_chars, max_lines)


def read_file_head(project_id, stored_path, max_lines=IMPORT_BLOCK_LINES):
    """Read the top of a file — its imports, module docstring and early setup.

    This is where most "where is the connection / where is the token built"
    answers live (``engine = create_engine(...)``, ``jwt.encode(...)``, ...).
    """
    return _read_range(project_id, stored_path, 1, max_lines, DEFAULT_MAX_SNIPPET_CHARS, max_lines)


def read_readme(project_id):
    """Read the repository README head if one exists (returns ``None`` otherwise)."""
    root = project_root(project_id)
    for name in ('README.md', 'README.rst', 'README.txt', 'README', 'readme.md', 'Readme.md'):
        candidate = root / name
        if candidate.is_file():
            return _read_range(project_id, str(candidate), 1, README_MAX_LINES,
                               DEFAULT_MAX_SNIPPET_CHARS, README_MAX_LINES)
    return None
