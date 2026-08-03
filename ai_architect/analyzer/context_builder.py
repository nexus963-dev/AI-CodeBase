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
from . import source_retriever
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

# ---------------------------------------------------------------------------
# Intent-aware source retrieval. PostgreSQL stays metadata-only; real code is
# read on demand from the project clone on disk (via source_retriever).
# ---------------------------------------------------------------------------
_SOURCE_BUDGET_CHARS = 14000     # max code characters read per question
_FEATURE_MAX_ENTITIES = 8        # max entities pulled for feature questions

# Caps used when a question asks to *list* a category: raise the default caps
# so the model sees a near-complete list instead of a tiny path-ordered sample.
_LIST_LIMITS = {
    'list_functions': {'functions': 250, 'methods': 100},
    'list_classes': {'classes': 150, 'methods': 120},
    'list_files': {'files': 300},
}
_ARCHITECTURE_LIMITS = {'relationships': 80, 'files': 60, 'classes': 40}


def _detect_intent(question):
    """Route a question to one of the retrieval intents (keyword based).

    Broad "list" questions need a near-complete metadata list; "explain X" /
    "where is X" questions need the real code around the matched entities.
    """
    q = (question or '').lower()
    if any(k in q for k in ('function', 'functions', 'method', 'methods')) and \
            any(k in q for k in ('list', 'defined', 'all', 'what', 'which', 'name')):
        return 'list_functions'
    if 'class' in q and any(k in q for k in ('list', 'defined', 'all', 'what', 'which')):
        return 'list_classes'
    if 'file' in q and any(k in q for k in ('list', 'defined', 'all', 'what', 'which',
                                            'structure', 'tree')):
        return 'list_files'
    if any(k in q for k in ('what does', 'purpose', 'overview', 'try to do',
                            'about this', 'summary', 'introduction', 'describe')):
        return 'repo_summary'
    if any(k in q for k in ('depend', 'import', 'architecture', 'architectural',
                            'relationship', 'call graph')):
        return 'architecture'
    # Default: the question points at some concrete feature ("login",
    # "database connection", "JWT tokens", "this API endpoint", ...).
    return 'feature'


def _match_strength(token, text):
    """Keyword match strength between a question token and a metadata string.

    A tiny prefix stem makes singular/plural and verb/gerund forms still hit
    (``database``↔``database.py``, ``connection``↔``connect``,
    ``create``↔``created``). Pure text matching — no embeddings.
    """
    token = (token or '').lower()
    text = (text or '').lower()
    if not token:
        return 0
    if token in text:
        return 5
    stem = token[:4]
    if len(stem) >= 4 and stem in text:
        return 3
    if len(text) >= 4 and text[:4] in token:
        return 3
    return 0


def _feature_entities(project_id, question, limit=_FEATURE_MAX_ENTITIES):
    """Rank ALL of a project's metadata entities by how well they match.

    Scans the full metadata index (names + signatures + file paths) — cheap,
    in-memory — and returns the best-matching entities to read from disk.
    """
    tokens = _tokens_from_question(question)
    if not tokens:
        return []
    candidates = knowledge_base.get_project_entities(project_id)
    scored = []
    for e in candidates:
        text = ' '.join((e.get('name', ''), e.get('signature', ''),
                         e.get('file_path', '')))
        score = sum(_match_strength(t, text) for t in tokens)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda x: (-x[0], x[1].get('file_path', ''), x[1].get('name', '')))
    seen = set()
    top = []
    for _, e in scored:
        key = (e.get('file_path'), e.get('name'))
        if key in seen:
            continue
        seen.add(key)
        top.append(e)
        if len(top) >= limit:
            break
    return top


def _retrieve_code(project_id, question, budget=_SOURCE_BUDGET_CHARS):
    """Read real source for a feature question; returns (blocks, chars_used).

    Each block is ``{path, start_line, end_line, snippet, truncated}``. Reading
    stops once ``budget`` characters have been consumed, so no question ever
    pulls more than a fixed amount of code regardless of repository size.
    """
    blocks = []
    used = 0
    head_files = set()

    def add(block):
        nonlocal used
        if block is None:
            return
        if used + len(block['snippet']) > budget:
            return
        blocks.append(block)
        used += len(block['snippet'])

    for entity in _feature_entities(project_id, question):
        add(source_retriever.read_entity(project_id, entity))
        file_key = entity.get('file_path')
        if file_key and file_key not in head_files:
            head_files.add(file_key)
            # The file's imports / module docstring often contain the setup the
            # question asks about (create_engine, jwt.encode, db init, ...).
            add(source_retriever.read_file_head(project_id, file_key))

    return blocks, used


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


def build_repository_context(project_id, question=None, limits=None, sources=False):
    """Assemble the structured, project-scoped context for one repository.

    Returns a dict of only the most relevant (or, for short questions, a
    representative subset of) files / classes / functions / relationships, plus
    a summary. Every field is sourced from :mod:`knowledge_base`, so it is
    strictly bounded to ``project_id`` — never global.

    ``limits`` may override the per-category caps (e.g. to send more context).
    ``sources=True`` additionally runs intent-aware retrieval: it reads real
    code from the project's clone on disk (PostgreSQL stays metadata-only) and
    attaches it to the context as ``code`` / ``readme`` / ``intent`` /
    ``truncated``. Listing questions get raised caps so the model sees a
    near-complete list instead of a tiny sample.
    Raises ``Project.DoesNotExist`` for an unknown project id.
    """
    # Propagate 404 for invalid projects rather than masking it.
    Project.objects.get(id=project_id)

    intent = None
    caps = {**_DEFAULT_LIMITS, **(limits or {})}
    if sources and question:
        intent = _detect_intent(question)
        if intent in _LIST_LIMITS:
            caps.update(_LIST_LIMITS[intent])
        elif intent == 'architecture':
            caps.update(_ARCHITECTURE_LIMITS)

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

    context = {
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

    # Intent-aware real-source retrieval. The metadata above is untouched; the
    # clone directory on disk remains the single source of truth for code.
    if sources and question:
        context['intent'] = intent
        context['code'] = []
        context['readme'] = None
        context['truncated'] = False
        context['retrieval'] = {'intent': intent, 'snippets': 0, 'chars': 0}
        if intent in ('repo_summary', 'architecture'):
            context['readme'] = source_retriever.read_readme(project_id)
        if intent == 'feature':
            blocks, used = _retrieve_code(project_id, question)
            context['code'] = blocks
            context['retrieval']['snippets'] = len(blocks)
            context['retrieval']['chars'] = used
        # Flag when a listing was cut short so the prompt can say so honestly.
        # Only the category the question asked about matters — a capped *files*
        # section should not make the model hedge a complete function list.
        if intent in _LIST_LIMITS:
            categories = {
                'list_functions': ('functions', 'methods'),
                'list_classes': ('classes', 'methods'),
                'list_files': ('files',),
            }[intent]
            for key in categories:
                if len(context[key]) < context['summary'][key]:
                    context['truncated'] = True
                    break

    return context