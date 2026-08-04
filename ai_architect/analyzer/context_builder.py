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

import os
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
# so the model sees a complete list (grouped by file) instead of a tiny
# path-ordered sample. Metadata is cheap — names/signatures only — so these
# can be generous; the prompt says honestly when a huge repo overflows them.
_LIST_LIMITS = {
    'list_functions': {'functions': 600, 'methods': 250},
    'list_classes': {'classes': 300, 'methods': 250},
    'list_files': {'files': 500},
}
_ARCHITECTURE_LIMITS = {'relationships': 80, 'files': 60, 'classes': 40}

# Configuration / dependency files whose *content* decides "what database /
# what stack does this project use" — matched by basename against the metadata.
_CONFIG_FILENAMES = {
    'database.py', 'db.py', 'config.py', 'settings.py',
    '.env.example', '.env.sample', '.env.local',
    'docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml',
    'requirements.txt', 'requirements-dev.txt', 'pyproject.toml', 'setup.py',
    'package.json', 'Pipfile', 'go.mod', 'Gemfile', 'pom.xml', 'Cargo.toml',
}
# Keyword fallback for DB/stack files not in the exact set above.
_CONFIG_KEYWORDS = (
    'database', 'sqlalchemy', 'postgres', 'mysql', 'redis', 'mongo',
    'sqlite', 'db_config', 'connection', 'env', 'docker',
)

# Main entry points read (head only) for architecture / entry questions.
_ENTRY_POINT_NAMES = {
    'main.py', 'app.py', 'manage.py', 'run.py', 'server.py',
    'wsgi.py', 'asgi.py', 'index.py', '__main__.py',
}

# Phrases that mean "what database / what stack", distinct from "where is the
# database connection created" (which is a feature question about a symbol).
_TECH_KEYWORDS = (
    'what database', 'which database', 'which db', 'what db',
    'database does this', 'database is used', 'database used',
    'database technology', 'database engine', 'database system',
    'what tech', 'what stack', 'which stack', 'tech stack',
    'technology stack', 'what framework', 'which framework',
    'what dependencies', 'what language',
)

# Structure tree caps (metadata only; bounded so huge repos stay readable).
_STRUCTURE_MAX_ENTRIES = 200
_STRUCTURE_MAX_DEPTH = 3


def _detect_intent(question):
    """Route a question to one of the retrieval intents (keyword based).

    Broad "list" questions need a near-complete metadata list; "explain X" /
    "where is X" questions need the real code around the matched entities;
    "what database / what stack" questions need the actual configuration files.
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
    if any(k in q for k in _TECH_KEYWORDS) or \
            any(k in q for k in ('dependencies', 'requirements', 'technology')):
        return 'technology'
    if any(k in q for k in ('what does', 'purpose', 'overview', 'try to do',
                            'about this', 'summary', 'summarize', 'introduction',
                            'describe')):
        return 'repo_summary'
    if any(k in q for k in ('depend', 'import', 'architecture', 'architectural',
                            'relationship', 'call graph', 'how is this project',
                            'how does this project', 'project structure',
                            'high-level', 'high level', 'explain the project')):
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


def _retrieve_entity_blocks(project_id, entities, budget=_SOURCE_BUDGET_CHARS):
    """Read real source for the matched entities; returns (blocks, chars_used).

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

    for entity in entities:
        add(source_retriever.read_entity(project_id, entity))
        file_key = entity.get('file_path')
        if file_key and file_key not in head_files:
            head_files.add(file_key)
            # The file's imports / module docstring often contain the setup the
            # question asks about (create_engine, jwt.encode, db init, ...).
            add(source_retriever.read_file_head(project_id, file_key))

    return blocks, used


def _feature_retrieval(project_id, question, budget=_SOURCE_BUDGET_CHARS):
    """Full retrieval for a feature question: matched code + related code.

    Returns ``(code_blocks, related_blocks, call_edges, chars_used)``.
    ``code_blocks`` is the best-matching entities' own code plus the head of
    any module the question clearly targets; ``related_blocks`` are the bodies
    of their callers/callees (relationship-aware); ``call_edges`` are the raw
    caller->callee edges touching them, for the prompt.
    """
    matched = _feature_entities(project_id, question)
    code, used = _retrieve_entity_blocks(project_id, matched, budget)
    module, m_used = _module_file_heads(project_id, question, budget - used)
    seen_paths = {b['path'] for b in code}
    for block in module:
        if block['path'] in seen_paths:
            continue
        code.append(block)
        used += len(block['snippet'])
    related, used2 = _related_snippets(project_id, matched, budget - used)
    used += used2
    edges = _edges_touching(project_id, matched)
    return code, related, edges, used


# Question tokens that map onto a whole module file (not a single entity).
# When entity names are unreliable (e.g. parser artifacts), reading the module
# head still lets the model answer auth/database/API questions accurately.
_PATH_TERMS = {
    'auth': ('auth', 'login', 'token', 'session', 'authenticate', 'password'),
    'database': ('database', 'db', 'sql', 'connection', 'sqlalchemy',
                 'postgres', 'mysql', 'engine'),
    'api': ('api', 'endpoint', 'route', 'router'),
    'main': ('main', 'entry', 'start', 'app'),
}


def _module_file_heads(project_id, question, budget=_SOURCE_BUDGET_CHARS,
                       max_files=3):
    """Read the head of module files the question clearly targets.

    ``path_terms`` are derived from the question (e.g. any auth word pulls the
    ``auth`` module). Reading is bounded: at most ``max_files`` file heads,
    under ``budget`` characters. Empty when the question targets no module.
    """
    q = (question or '').lower()
    terms = {primary for primary, aliases in _PATH_TERMS.items()
             if any(a in q for a in aliases)}
    if not terms:
        return [], 0
    blocks, used, seen = [], 0, 0
    for f in knowledge_base.get_project_files(project_id):
        if seen >= max_files:
            break
        rel = source_retriever.relative_path(project_id, f['path']).lower()
        if not any(t in rel for t in terms):
            continue
        seen += 1
        block = source_retriever.read_file_head(project_id, f['path'], max_lines=40)
        if block is None:
            continue
        if used + len(block['snippet']) > budget:
            break
        blocks.append(block)
        used += len(block['snippet'])
    return blocks, used


def _related_snippets(project_id, matched_entities, budget=_SOURCE_BUDGET_CHARS):
    """Read the bodies of caller/callee functions of the matched entities.

    Uses the parser's own call-site metadata (see
    :meth:`knowledge_base.get_project_call_edges`) so that explaining one
    function also surfaces who calls it and whom it calls. Returns
    ``(blocks, chars_used)``.
    """
    edges = knowledge_base.get_project_call_edges(project_id)
    if not edges:
        return [], 0
    by_id = {}
    for e in knowledge_base.get_project_entities(project_id):
        by_id[e['id']] = e
    matched_ids = {e.get('id') for e in matched_entities}
    related_ids = []
    seen = set(matched_ids)
    for entity in matched_entities:
        eid = entity.get('id')
        if eid is None:
            continue
        for edge in edges:
            other = None
            if edge.get('caller_id') == eid:
                other = edge.get('callee_id')
            elif edge.get('callee_id') == eid:
                other = edge.get('caller_id')
            if other is not None and other not in seen:
                seen.add(other)
                related_ids.append(other)
            if len(related_ids) >= 6:
                break
        if len(related_ids) >= 6:
            break

    blocks = []
    used = 0
    for rid in related_ids:
        ent = by_id.get(rid)
        if ent is None:
            continue
        block = source_retriever.read_entity(project_id, ent)
        if block is None:
            continue
        if used + len(block['snippet']) > budget:
            break
        blocks.append(block)
        used += len(block['snippet'])
    return blocks, used


def _edges_touching(project_id, matched_entities, limit=20):
    """Bounded caller->callee edges touching the matched entities (for display).

    Used to show the call graph around an entity without reading every body.
    """
    matched_ids = {e.get('id') for e in matched_entities}
    if not matched_ids:
        return []
    edges = knowledge_base.get_project_call_edges(project_id)
    if not edges:
        return []
    out = []
    seen = set()
    for edge in edges:
        if edge.get('caller_id') in matched_ids or edge.get('callee_id') in matched_ids:
            key = (edge.get('caller_name'), edge.get('callee_name'))
            if key in seen:
                continue
            seen.add(key)
            out.append(edge)
            if len(out) >= limit:
                break
    return out


def _build_structure(project_id,
                     max_entries=_STRUCTURE_MAX_ENTRIES,
                     max_depth=_STRUCTURE_MAX_DEPTH):
    """Render a bounded repository tree from metadata (relative paths).

    Pure metadata — no disk reads. Directories first, then files, at most
    ``max_entries`` lines. Used for file-listing and architecture questions so
    responses can show the folder hierarchy instead of a flat absolute-path dump.
    """
    root = {}
    for f in knowledge_base.get_project_files(project_id):
        rel = source_retriever.relative_path(project_id, f['path'])
        parts = rel.split('/')
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault('__files__', set()).add(parts[-1])

    lines = []
    count = [0]

    def render(node, prefix, depth):
        if count[0] >= max_entries:
            return
        names = [(n, True) for n in sorted(k for k in node if k != '__files__')]
        names += [(n, False) for n in sorted(node.get('__files__', set()))]
        for i, (name, is_dir) in enumerate(names):
            if count[0] >= max_entries:
                return
            last = (i == len(names) - 1)
            connector = '└── ' if last else '├── '
            lines.append(prefix + connector + name + ('/' if is_dir else ''))
            count[0] += 1
            if is_dir and depth < max_depth:
                render(node[name], prefix + ('    ' if last else '│   '), depth + 1)

    render(root, '', 1)
    if count[0] >= max_entries:
        lines.append('... (tree truncated)')
    return '\n'.join(lines)


def _config_snippets(project_id, budget=_SOURCE_BUDGET_CHARS):
    """Read the head of a repository's configuration / dependency files.

    Answers like "what database does this project use" are decided from the
    implementation (``create_engine(...)``, ``settings.DATABASE_URL``,
    ``requirements.txt``), not from metadata names. Selection is
    exact-basename first, then a DB/stack keyword fallback; reading stops once
    ``budget`` characters are consumed.
    """
    files = knowledge_base.get_project_files(project_id)
    exact, keyword = [], []
    for f in files:
        base = os.path.basename(f['path'])
        if base in _CONFIG_FILENAMES:
            exact.append(f['path'])
        elif any(k in base.lower() for k in _CONFIG_KEYWORDS):
            keyword.append(f['path'])
    priority = {name: i for i, name in enumerate(sorted(_CONFIG_FILENAMES))}
    exact.sort(key=lambda p: priority.get(os.path.basename(p), 999))
    keyword.sort()

    blocks = []
    used = 0
    for path in exact + keyword:
        block = source_retriever.read_file_head(project_id, path, max_lines=80)
        if block is None:
            continue
        if used + len(block['snippet']) > budget:
            break
        blocks.append(block)
        used += len(block['snippet'])
    return blocks, used


def _entry_point_snippets(project_id, budget=_SOURCE_BUDGET_CHARS):
    """Read the head of a repository's main entry points (bounded)."""
    matches = []
    for f in knowledge_base.get_project_files(project_id):
        base = os.path.basename(f['path'])
        if base in _ENTRY_POINT_NAMES:
            rel = source_retriever.relative_path(project_id, f['path'])
            # Prefer the shallowest entry points (root ``main.py`` over nested).
            matches.append((rel.count('/'), rel, f['path']))
    matches.sort()

    blocks = []
    used = 0
    for _, _, path in matches[:4]:
        block = source_retriever.read_file_head(project_id, path, max_lines=60)
        if block is None:
            continue
        if used + len(block['snippet']) > budget:
            break
        blocks.append(block)
        used += len(block['snippet'])
    return blocks, used


def _question_wants_entry_point(q):
    """True when a question explicitly asks where / how the app is started."""
    q = (q or '').lower()
    return any(k in q for k in (
        'entry point', 'entry-point', 'entrypoint', 'api entry', 'api root',
        'root endpoint', 'main', 'startup', 'where is the app',
        'how is the app started', 'where does the app start',
    ))


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
        context['related'] = []
        context['call_edges'] = []
        context['config'] = []
        context['entry_points'] = []
        context['structure'] = None
        context['readme'] = None
        context['truncated'] = False
        context['retrieval'] = {
            'intent': intent, 'snippets': 0, 'related': 0, 'config': 0,
            'chars': 0,
        }

        if intent == 'feature':
            code, related, edges, used = _feature_retrieval(project_id, question)
            context['code'] = code
            context['related'] = related
            context['call_edges'] = edges
            context['retrieval']['snippets'] = len(code)
            context['retrieval']['related'] = len(related)
            context['retrieval']['chars'] = used
            if _question_wants_entry_point(question):
                ep, ep_used = _entry_point_snippets(
                    project_id, _SOURCE_BUDGET_CHARS - used)
                context['entry_points'] = ep
                context['retrieval']['chars'] += ep_used
        elif intent == 'technology':
            cfg, used = _config_snippets(project_id)
            context['config'] = cfg
            context['readme'] = source_retriever.read_readme(project_id)
            context['retrieval']['config'] = len(cfg)
            context['retrieval']['chars'] = used
        elif intent == 'architecture':
            context['readme'] = source_retriever.read_readme(project_id)
            context['structure'] = _build_structure(project_id)
            ep, ep_used = _entry_point_snippets(project_id)
            cfg, cfg_used = _config_snippets(project_id, _SOURCE_BUDGET_CHARS - ep_used)
            context['entry_points'] = ep
            context['config'] = cfg
            context['retrieval']['chars'] = ep_used + cfg_used
        elif intent == 'repo_summary':
            context['readme'] = source_retriever.read_readme(project_id)
            context['structure'] = _build_structure(project_id)
        elif intent == 'list_files':
            context['structure'] = _build_structure(project_id)
        # list_functions / list_classes need no disk reads — the metadata lists
        # above (raised caps) are the whole answer, grouped by file in the prompt.

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