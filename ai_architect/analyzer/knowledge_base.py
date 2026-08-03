"""Project-scoped repository knowledge layer.

This is the ONLY interface between Django (and any future AI assistant) and
the parser's PostgreSQL output. It is a pure retrieval layer — it contains no
AI, no embeddings, no LLM calls, and no vector search.

Rules enforced by this module:

* Every function takes exactly one ``project_id`` and returns ONLY data
  stamped with that project. No global queries exist here.
* Raw SQL never leaves this module (and in practice lives one layer down, in
  :mod:`analyzer.parser_adapter`, which ``knowledge_base`` reuses rather than
  duplicating).
* Django views and future AI code import this module and never import
  ``parser_adapter`` or touch the parser tables directly.

The parser's data model (as exposed here):

* files       -> one row per parsed ``.py`` file (path, content hash)
* entities    -> functions / classes / methods, each tied to a file, with
                 name, line range, and signature
* relationships -> caller -> callee edges with file + line number (the parser
                 resolves calls only within the same file)

The write path used during analysis (``link_project_output``) is also
re-exported here so that even the worker talks to parser data exclusively
through this module.
"""

import os

from . import parser_adapter
from .models import Project


# ---------------------------------------------------------------------------
# Write path (used by the analysis worker). Delegates to parser_adapter so
# that this module remains the single entry point for parser data.
# ---------------------------------------------------------------------------
def link_project_output(project_id, analysis_job_id, clone_dir):
    """Associate a finished parser run with its Project + AnalysisJob.

    Delegates to ``parser_adapter`` (the data-access layer); exposed here so
    views never import the adapter directly. Returns per-table link counts.
    """
    return parser_adapter.link_project_output(
        project_id, analysis_job_id, clone_dir,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _get_project(project_id):
    """Return the Project for ``project_id`` or None (for summary metadata)."""
    try:
        return Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return None


def _entities_for_project(project_id):
    """All parsed entities for a project (shared by the typed helpers)."""
    return parser_adapter.get_entities_for_project(project_id)


# ---------------------------------------------------------------------------
# Project-level retrieval
# ---------------------------------------------------------------------------
def get_project_files(project_id):
    """Every parsed file for a project, enriched with a short ``name``."""
    files = parser_adapter.get_files_for_project(project_id)
    for f in files:
        f['name'] = os.path.basename(f['path'])
    return files


def get_project_classes(project_id):
    """Every class parsed for a project."""
    return [
        e for e in _entities_for_project(project_id)
        if e['type'] == 'class'
    ]


def get_project_functions(project_id):
    """Every top-level function parsed for a project (methods excluded)."""
    return [
        e for e in _entities_for_project(project_id)
        if e['type'] == 'function'
    ]


def get_project_methods(project_id):
    """Every method parsed for a project (methods are stored as
    ``<ClassName>.<method_name>`` by the parser)."""
    return [
        e for e in _entities_for_project(project_id)
        if e['type'] == 'method'
    ]


def get_project_entities(project_id):
    """Every entity (functions, classes, methods) parsed for a project."""
    return _entities_for_project(project_id)


def get_project_relationships(project_id):
    """Every caller -> callee relationship parsed for a project."""
    return parser_adapter.get_relationships_for_project(project_id)


def get_project_summary(project_id):
    """Compact summary of a project's parsed knowledge.

    Counts come from the parser DB; name/status come from the Django Project
    record. Useful as the first thing a future AI reads about a repo.
    """
    stats = parser_adapter.get_project_stats(project_id)
    project = _get_project(project_id)
    return {
        'project_id': project_id,
        'project_name': project.name if project else None,
        'analysis_status': project.analysis_status if project else None,
        'files': stats['files'],
        'classes': stats['classes'],
        'functions': stats['functions'],
        'methods': stats['methods'],
        'relationships': stats['relationships'],
    }


# ---------------------------------------------------------------------------
# Item-level retrieval
# ---------------------------------------------------------------------------
def get_file_details(project_id, file_path):
    """All parsed entities for one file in a project.

    ``file_path`` may be the full stored path or any trailing suffix (a
    basename like ``utils.py`` or a relative path). Matching is scoped to the
    project's own files. Returns None if the file was never parsed.
    """
    match = None
    for f in parser_adapter.get_files_for_project(project_id):
        if f['path'] == file_path or f['path'].endswith(file_path):
            match = f
            break
    if match is None:
        return None
    entities = [
        e for e in _entities_for_project(project_id)
        if e['file_path'] == match['path']
    ]
    return {
        'id': match['id'],
        'path': match['path'],
        'name': os.path.basename(match['path']),
        'content_hash': match['content_hash'],
        'entities': entities,
    }


def get_class_details(project_id, class_name):
    """One class plus its methods.

    The parser stores methods as ``<ClassName>.<method>``, so a class's
    methods are identified by that prefix within the class's own file.
    Returns None if the class was never parsed.
    """
    entities = _entities_for_project(project_id)
    cls = next(
        (e for e in entities if e['type'] == 'class' and e['name'] == class_name),
        None,
    )
    if cls is None:
        return None
    prefix = class_name + '.'
    methods = [
        e for e in entities
        if e['type'] == 'method'
        and e['name'].startswith(prefix)
        and e['file_path'] == cls['file_path']
    ]
    return {
        'name': cls['name'],
        'file_path': cls['file_path'],
        'start_line': cls['start_line'],
        'end_line': cls['end_line'],
        'signature': cls['signature'],
        'methods': methods,
    }


def get_function_details(project_id, function_name):
    """One function (or method) plus the edges touching it.

    ``calls`` = relationships where this entity is the caller; ``called_by`` =
    relationships where it is the callee. Because the parser resolves calls
    within the same file only, these lists reflect that scope.
    """
    entities = _entities_for_project(project_id)
    func = next(
        (
            e for e in entities
            if e['type'] in ('function', 'method') and e['name'] == function_name
        ),
        None,
    )
    if func is None:
        return None
    rels = parser_adapter.get_relationships_for_project(project_id)
    return {
        'name': func['name'],
        'type': func['type'],
        'file_path': func['file_path'],
        'start_line': func['start_line'],
        'end_line': func['end_line'],
        'signature': func['signature'],
        'calls': [r for r in rels if r.get('caller_id') == func['id']],
        'called_by': [r for r in rels if r.get('callee_id') == func['id']],
    }
