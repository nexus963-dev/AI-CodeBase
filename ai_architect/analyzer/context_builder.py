"""Repository context assembly.

Builds a compact, structured snapshot of a repository by reading ONLY through
:mod:`analyzer.knowledge_base` (itself scoped per project). This module is the
single producer of the "Structured Repository Context" that the LLM is
allowed to see — nothing in the project bypasses it to reach parser data.

It contains no AI. The only "intelligence" is a lightweight lexical relevance
filter used to keep prompts concise: when a user question has meaningful
keywords, candidates whose names/signatures mention them are ranked ahead of
others and the results are capped. This is plain text matching — NOT
embeddings and NOT vector search.
"""

import re

from . import knowledge_base
from .models import Project

# Words that carry no retrieval meaning for relevance ranking.
_STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'do', 'does',
    'did', 'how', 'why', 'what', 'which', 'who', 'when', 'where', 'explain',
    'summarize', 'give', 'me', 'list', 'name', 'tell', 'about', 'in', 'on',
    'at', 'to', 'of', 'for', 'with', 'and', 'or', 'this', 'that', 'these',
    'repository', 'project', 'code', 'please', 'i',
}

# Default per-category caps so prompts never blow up on large repos.
_DEFAULT_LIMITS = {
    'files': 15,
    'classes': 20,
    'functions': 25,
    'methods': 20,
    'relationships': 15,
}


def _tokens_from_question(question):
    """Return the meaningful keyword tokens of a question (set, lowercased)."""
    if not question:
        return set()
    return {
        re.sub(r'\W', '', t)
        for t in re.findall(r'\w+', question.lower())
        if len(re.sub(r'\W', '', t)) > 2
        and re.sub(r'\W', '', t) not in _STOPWORDS
    }


def _rank(candidates, tokens, search_text_fn, limit):
    """Rank + cap ``candidates`` by keyword matches.

    If ``tokens`` is empty (broad question, e.g. "summarize this repo") the
    candidates are returned in stable order, capped to ``limit``.
    """
    if not tokens:
        return candidates[:limit]

    def key(cand):
        text = search_text_fn(cand).lower()
        return sum(text.count(t) for t in tokens)

    ranked = sorted(candidates, key=key, reverse=True)
    # Only keep candidates that actually matched at least one token.
    matched = [c for c in ranked if key(c) > 0]
    # If nothing matched, fall back to a representative prefix.
    return (matched or ranked)[:limit]


def build_repository_context(project_id, question=None, limits=None):
    """Assemble the structured, project-scoped context for one repository.

    Returns a dict of only the most relevant (or, for short questions, a
    representative subset of) files / classes / functions / relationships, plus
    a summary. Every field is sourced from :mod:`knowledge_base`, so it is
    strictly bounded to ``project_id`` — never global.

    ``limits`` may override the per-category caps (e.g. to send more context).
    Raises ``Project.DoesNotExist`` for an unknown project id.
    """
    # Propagate 404 for invalid projects rather than masking it.
    Project.objects.get(id=project_id)

    caps = {**_DEFAULT_LIMITS, **(limits or {})}
    tokens = _tokens_from_question(question)

    classes = knowledge_base.get_project_classes(project_id)
    functions = knowledge_base.get_project_functions(project_id)
    methods = knowledge_base.get_project_methods(project_id)
    relationships = knowledge_base.get_project_relationships(project_id)

    # Ranked classes (with their method counts) for the context.
    ranked_classes = _rank(
        classes, tokens,
        lambda c: ' '.join((c['name'], c.get('file_path', ''))),
        caps['classes'],
    )

    ranked_functions = _rank(
        functions, tokens,
        lambda f: ' '.join((f['name'], f.get('signature', ''), f.get('file_path', ''))),
        caps['functions'],
    )

    ranked_methods = _rank(
        methods, tokens,
        lambda m: ' '.join((m['name'], m.get('signature', ''), m.get('file_path', ''))),
        caps['methods'],
    )

    ranked_relationships = _rank(
        relationships, tokens,
        lambda r: ' '.join((r.get('caller_name', ''), r.get('callee_name', ''),
                            r.get('file_path', ''))),
        caps['relationships'],
    )

    # Files: use the union of files that produced ranked entities, plus any
    # files whose path mentions a token. Capped to the file limit.
    file_rank_fn = lambda f: f.get('path', '')
    ranked_files = _rank(
        knowledge_base.get_project_files(project_id), tokens,
        file_rank_fn, caps['files'],
    )

    return {
        'project_id': project_id,
        'question': question,
        'summary': knowledge_base.get_project_summary(project_id),
        'files': ranked_files,
        'classes': ranked_classes,
        'functions': ranked_functions,
        'methods': ranked_methods,
        'relationships': ranked_relationships,
        'limits': caps,
        # Track whether the prompt was relevance-filtered, for metadata.
        'filtered': bool(tokens),
    }