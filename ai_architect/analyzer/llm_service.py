"""The ONLY Django <-> LLM interface.

Nothing else in the project should call an LLM directly. This module:

* receives a ``project_id`` + ``question``,
* builds a concise, project-scoped context via :mod:`analyzer.context_builder`
  (which reads ONLY through :mod:`analyzer.knowledge_base`),
* turns it into a prompt,
* calls the configured LLM provider,
* returns a uniform ``{answer, sources, metadata}`` dict — or a meaningful
  error in that same shape.

Design notes for adding another provider (OpenAI / Anthropic / Ollama) later:

  * Each provider is a function in :func:`_PROVIDERS` with the signature
    ``(api_key, model, system_prompt, user_prompt) -> str``.
  * The active provider is chosen by the ``LLM_PROVIDER`` env var (default
    ``"gemini"``). Drop a new key in and it is usable with no other change.

The API key is read from the environment (``GEMINI_API_KEY``) — never
hardcoded. There is no embeddings, no vector search, and no chat UI here.

Formatting rule used everywhere below: responses cite repository-relative
paths (``backend/app/database.py``), never the local filesystem path that the
parser stores (``.../media/repos/<id>/backend/app/database.py``).
"""

import os

from decouple import config

from . import context_builder
from . import source_retriever
from .models import Project

# Provider selection + model naming, all overridable via environment.
DEFAULT_PROVIDER = 'gemini'
DEFAULT_MODEL = 'gemini-flash-lite-latest'

# Sentinel returned when the project does not exist.
class InvalidProjectError(Exception):
    """Raised when ``project_id`` does not map to a saved Project."""


def _is_project_empty(context):
    """True when a repository produced no parseable knowledge."""
    summary = context['summary']
    return summary['files'] == 0


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
def _render_section(title, items, line_fn):
    """Render a titled, indented block of context items (skips empty lists)."""
    if not items:
        return ''
    lines = [line_fn(it) for it in items]
    return f"## {title}\n" + "\n".join(f"- {l}" for l in lines) + "\n"


def _rel(context, path):
    """Repository-relative path (absolute parser paths never reach the prompt)."""
    return source_retriever.relative_path(context['project_id'], path)


def _entity_line(context, entity):
    """A clean display line for one entity.

    The parser occasionally stores a garbled name/signature (a body fragment).
    ``source_retriever.recover_name`` re-derives the identifier from the actual
    definition line; when it differs from the stored name, the clean name is
    shown instead (the stored signature is unreliable for those, so it is
    dropped rather than echoing garbage).
    """
    stored = entity.get('name', '?')
    recovered = source_retriever.recover_name(context['project_id'], entity)
    if recovered and recovered != stored:
        # Methods are stored as ClassName.method — keep the class prefix, but
        # only when the stored value is genuinely that shape (a garbled body
        # fragment like ``rrent_user.id)`` is not).
        cls, dot, method = stored.partition('.')
        if dot and cls.isidentifier() and method.isidentifier():
            recovered = cls + '.' + recovered
        return recovered
    if entity.get('type') == 'class':
        return f"{stored} ({entity.get('start_line', '?')}-{entity.get('end_line', '?')})"
    return f"{stored}{entity.get('signature', '')}"


def _render_entities_by_file(title, items, line_fn, context):
    """Render entities grouped by their repository-relative file path, so lists
    read like a real repository browser instead of a flat dump."""
    if not items:
        return ''
    by_file = {}
    for it in items:
        by_file.setdefault(_rel(context, it.get('file_path', '?')), []).append(it)
    chunks = [f"## {title}"]
    for path, group in by_file.items():
        chunks.append(f"### {path}")
        chunks.extend(f"- {line_fn(it)}" for it in group)
    return "\n".join(chunks) + "\n"


def _render_code_blocks(title, blocks, context):
    """Render on-disk source snippets under repository-relative headers."""
    if not blocks:
        return ''
    chunks = [title]
    for block in blocks:
        chunks.append(
            f"### {_rel(context, block['path'])} "
            f"(lines {block['start_line']}-{block['end_line']})\n"
            f"```\n{block['snippet']}\n```"
        )
    return "\n".join(chunks) + "\n"


def build_prompt(context, question):
    """Turn a structured repository context + question into a prompt string.

    Sections are intent-aware: a repository summary gets prose material
    (README, structure, entry points, config) instead of a flat file dump; a
    listing question gets the full per-file list; a "what database" question
    gets the actual configuration files; a feature question gets the matched
    source plus its callers/callees.
    """
    s = context['summary']
    intent = context.get('intent')

    parts = []
    parts.append(
        f"You are a software architect assistant answering questions "
        f"exclusively about the repository '{s['project_name'] or s['project_id']}'."
    )
    parts.append(
        f"Repository summary: {s['files']} files, {s['classes']} classes, "
        f"{s['functions']} functions, {s['methods']} methods, "
        f"{s['relationships']} relationships."
    )

    # ---- Intent-specific body ----------------------------------------------
    if intent in ('repo_summary', 'architecture'):
        if context.get('readme'):
            parts.append(
                f"## Repository README (first "
                f"{len(context['readme']['snippet'].splitlines())} lines)\n"
                + context['readme']['snippet']
            )
        if context.get('structure'):
            parts.append("## Project Structure (repository-relative)\n"
                         + context['structure'])
        if context.get('entry_points'):
            parts.append(_render_code_blocks(
                "## Main Entry Points", context['entry_points'], context))
        if context.get('config') and intent == 'architecture':
            parts.append(_render_code_blocks(
                "## Configuration / Dependencies", context['config'], context))

    elif intent == 'technology':
        # The actual config files decide the stack — never metadata guesses.
        if context.get('config'):
            parts.append(_render_code_blocks(
                "## Configuration Files (the source of truth for the stack)",
                context['config'], context))
        if context.get('readme'):
            parts.append(
                f"## Repository README (first "
                f"{len(context['readme']['snippet'].splitlines())} lines)\n"
                + context['readme']['snippet']
            )

    elif intent == 'list_functions':
        parts.append(_render_entities_by_file(
            'Functions (complete list, grouped by file)', context['functions'],
            lambda f: _entity_line(context, f), context))
        if context.get('methods'):
            parts.append(_render_entities_by_file(
                'Methods', context['methods'],
                lambda m: _entity_line(context, m), context))

    elif intent == 'list_classes':
        parts.append(_render_entities_by_file(
            'Classes (complete list, grouped by file)', context['classes'],
            lambda c: _entity_line(context, c), context))
        if context.get('methods'):
            parts.append(_render_entities_by_file(
                'Methods', context['methods'],
                lambda m: _entity_line(context, m), context))

    elif intent == 'list_files':
        if context.get('structure'):
            parts.append("## Repository Tree (repository-relative paths)\n"
                         + context['structure'])
        parts.append(_render_entities_by_file(
            'All files', context['files'],
            lambda f: _rel(context, f['path']), context))

    else:  # feature / general — matched source plus the call graph around it.
        if context.get('code'):
            parts.append(_render_code_blocks(
                "## Relevant Source Code (read from the repository)",
                context['code'], context))
        if context.get('call_edges'):
            chunks = ["## Call Graph Around The Matched Code"]
            for edge in context['call_edges']:
                chunks.append(
                    f"- {edge.get('caller_name', '?')} -> "
                    f"{edge.get('callee_name', '?')} "
                    f"({_rel(context, edge['file_path'])}:{edge.get('line_number', '?')})")
            parts.append("\n".join(chunks))
        if context.get('related'):
            parts.append(_render_code_blocks(
                "## Related Functions (callers/callees read from the repository)",
                context['related'], context))

    # Honest truncation note so the model never mistakes a sample for the whole.
    if context.get('truncated'):
        parts.append(
            "Note: the metadata sections above are truncated; the summary lists "
            "the true totals. Reply in terms of what is shown."
        )

    parts.append(
        "Use ONLY the information above. If the answer is not in this "
        "context, say so rather than guessing. Do not invent code or files "
        "not listed here. Always cite repository-relative paths "
        "(e.g. backend/app/database.py), never absolute filesystem paths. "
        "When source code is included, quote it accurately.\n"
    )
    parts.append("User question:")
    parts.append(context['question'])

    return "\n".join(p for p in parts if p)


def _sources_from_context(context):
    """Collect the repository-relative file paths referenced by the context."""
    sources = set()
    for f in context['files']:
        sources.add(_rel(context, f.get('path')))
    for group in ('classes', 'functions', 'methods'):
        for e in context[group]:
            sources.add(_rel(context, e.get('file_path')))
    for r in context['relationships']:
        sources.add(_rel(context, r.get('file_path')))
    return sorted(x for x in sources if x)


# ---------------------------------------------------------------------------
# Provider layer (Gemini now; add OpenAI/Anthropic/Ollama by adding a callable)
# ---------------------------------------------------------------------------
def _call_gemini(api_key, model, system_prompt, user_prompt):
    """Call Google Gemini and return the answer text.

    Imports the SDK lazily so the module still loads and degrades cleanly when
    the package is absent. Parses 429 (rate limit) and timeout errors to
    meaningful messages.
    """
    import google.genai as genai  # may raise ImportError if not installed
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
        ),
    )
    try:
        return response.text
    except (AttributeError, ValueError):
        return "The model returned no text."


def _call_provider(provider, api_key, model, system_prompt, user_prompt):
    """Route to the active provider, raising a clear error on failure."""
    if provider == 'gemini':
        return _call_gemini(api_key, model, system_prompt, user_prompt)
    raise ValueError(
        f"Unknown LLM provider '{provider}'. Supported: gemini."
    )


# Public registry kept so a future provider can be added in one place.
_PROVIDERS = {'gemini': _call_gemini}


def _classify_error(exc):
    """Map an LLM call exception to a readable, specific message."""
    name = type(exc).__name__
    text = str(exc).lower()
    if '429' in text or 'rate' in text or 'quota' in text:
        return "The provider rate-limited the request. Try again shortly."
    if 'timeout' in name.lower() or 'timeout' in text or 'timed out' in text:
        return "The AI request timed out. Try a shorter question or a larger model cap."
    if 'unauthorized' in text or 'invalid' in text and 'key' in text:
        return "The API key is invalid or unauthorized."
    return f"The AI provider returned an error ({name}): {exc}"


def _error_result(message, error_type, **extra):
    """Return a uniform error dict that matches the success shape."""
    meta = {
        'error': True,
        'error_type': error_type,
        'message': message,
        **extra,
    }
    return {'answer': message, 'sources': [], 'metadata': meta}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def answer_repository_question(project_id, question, provider=None, model=None):
    """Answer a question about a specific repository.

    Returns ``{"answer": str, "sources": [file paths], "metadata": {...}``.
    On failure the dict is the same shape but ``metadata['error']`` is True
    with a readable ``message``.
    """
    if not question or not question.strip():
        return _error_result("A question is required.", 'empty_question')

    provider = provider or os.getenv('LLM_PROVIDER', DEFAULT_PROVIDER)
    model = model or os.getenv('LLM_MODEL', DEFAULT_MODEL)

    try:
        context = context_builder.build_repository_context(
            project_id, question, sources=True,
        )
    except Project.DoesNotExist:
        return _error_result(
            f"No project found with id {project_id}.", 'invalid_project',
        )
    except Exception as e:  # e.g. parser database unreachable
        return _error_result(
            f"Could not load repository data for project {project_id}: {e}",
            'repository_not_available',
        )

    # Empty repository / missing parser data.
    if _is_project_empty(context):
        return _error_result(
            f"No parsed data for project {project_id} — analyze the repository first.",
            'empty_repository',
        )

    # Read from .env (via decouple, matching how settings.py reads secrets)
    # with a fallback to a real environment variable for production.
    api_key = config('GEMINI_API_KEY', default='') or os.getenv('GEMINI_API_KEY', '')
    if provider == 'gemini' and not api_key:
        return _error_result(
            "Gemini API key is missing. Set the GEMINI_API_KEY environment "
            "variable.",
            'missing_api_key',
        )

    prompt = build_prompt(context, question)
    system_prompt = (
        "You are a software architect assistant. Answer from the repository "
        "context given and never invent details.\n"
        "Formatting rules:\n"
        "- Use repository-relative paths only (e.g. backend/app/database.py). "
        "Never show absolute filesystem paths like /home/... or media/repos/...\n"
        "- When listing functions, classes or methods, group them by file and "
        "list every one shown in the context; if the context is truncated, say "
        "so and give the totals from the summary.\n"
        "- For 'summarize' or 'architecture' questions, write a prose technical "
        "overview of how the system is organized and how the pieces connect. "
        "Do not answer with a bare list of file names.\n"
        "- When a question asks what database or framework a project uses, "
        "decide from the configuration/source shown (create_engine, "
        "settings.DATABASE_URL, requirements.txt, ...), never from assumptions."
    )

    try:
        answer = _call_provider(provider, api_key, model, system_prompt, prompt)
    except ImportError:
        return _error_result(
            f"The '{provider}' LLM SDK is not installed. Run "
            "`pip install google-genai` for Gemini.",
            'provider_sdk_missing',
        )
    except Exception as e:
        message = _classify_error(e)
        return _error_result(message, 'provider_error', provider=provider, model=model)

    return {
        'answer': answer,
        'sources': _sources_from_context(context),
        'metadata': {
            'project_id': project_id,
            'provider': provider,
            'model': model,
            'context': {
                'files': len(context['files']),
                'classes': len(context['classes']),
                'functions': len(context['functions']),
                'methods': len(context['methods']),
                'relationships': len(context['relationships']),
                'filtered': context['filtered'],
            },
            'prompt_chars': len(prompt),
        },
    }