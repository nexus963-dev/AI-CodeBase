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
"""

import os

from decouple import config

from . import context_builder
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


def _render_entities_by_file(title, items, line_fn):
    """Render entities grouped by their file, so lists read like a real
    repository browser instead of a flat dump."""
    if not items:
        return ''
    by_file = {}
    for it in items:
        by_file.setdefault(it.get('file_path', '?'), []).append(it)
    chunks = [f"## {title}"]
    for path, group in by_file.items():
        chunks.append(f"### {path}")
        chunks.extend(f"- {line_fn(it)}" for it in group)
    return "\n".join(chunks) + "\n"


def build_prompt(context, question):
    """Turn a structured repository context + question into a prompt string."""
    s = context['summary']

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

    parts.append(_render_section(
        'Files', context['files'],
        lambda f: f['path'],
    ))
    parts.append(_render_entities_by_file(
        'Classes', context['classes'],
        lambda c: f"{c['name']} ({c.get('start_line', '?')}-{c.get('end_line', '?')})",
    ))
    parts.append(_render_entities_by_file(
        'Functions', context['functions'],
        lambda f: f"{f['name']}{f.get('signature', '')}",
    ))
    parts.append(_render_entities_by_file(
        'Methods', context['methods'],
        lambda m: f"{m['name']}{m.get('signature', '')}",
    ))
    parts.append(_render_section(
        'Relationships', context['relationships'],
        lambda r: f"{r.get('caller_name','?')} -> {r.get('callee_name','?')} at {r.get('file_path','?')}:{r.get('line_number','?')}",
    ))

    # Real source code read on demand from the cloned repository.
    if context.get('readme'):
        parts.append(
            f"## Repository README (first {len(context['readme']['snippet'].splitlines())} lines)\n"
            + context['readme']['snippet']
        )

    if context.get('code'):
        parts.append("## Relevant Source Code (read from the repository)")
        for block in context['code']:
            parts.append(
                f"### {block['path']} (lines {block['start_line']}-{block['end_line']})\n"
                f"```\n{block['snippet']}\n```"
            )

    # Honest truncation note so the model never mistakes a sample for the whole.
    if context.get('truncated'):
        parts.append(
            "Note: the metadata sections above are truncated; the summary lists "
            "the true totals. Reply in terms of what is shown."
        )

    parts.append(
        "Use ONLY the information above. If the answer is not in this "
        "context, say so rather than guessing. Do not invent code or files "
        "not listed here. When source code is included, quote it accurately "
        "and cite the file path.\n"
    )
    parts.append("User question:")
    parts.append(context['question'])

    return "\n".join(p for p in parts if p)


def _sources_from_context(context):
    """Collect the file paths referenced by the context (de-duplicated)."""
    sources = set()
    for f in context['files']:
        sources.add(f.get('path'))
    for group in ('classes', 'functions', 'methods'):
        for e in context[group]:
            sources.add(e.get('file_path'))
    for r in context['relationships']:
        sources.add(r.get('file_path'))
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
        "context given, cite file names, and never invent details."
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