"""Django <-> parser output linkage adapter.

The parser (repo_parser.py) is stable and production-ready. It writes parsed
data globally into the 'code_understanding' PostgreSQL database
(files / code_entities / relationships / call_sites_staging) with no concept
of a Django Project, AnalysisJob, or User.

This module is the single integration point between Django and that output.
It does NOT modify or re-implement the parser. It solves exactly one problem:
associating every parser execution with the Project, AnalysisJob, and User
that produced it, so Django can retrieve only the data that belongs to a
given project.

Mechanism
---------
1. ``ensure_schema()``      idempotently adds project_id / analysis_job_id
                            columns to the parser tables
                            (ALTER TABLE ... ADD COLUMN IF NOT EXISTS).
2. ``link_project_output()``after a parser run, stamps every row under the
                            project's clone directory (media/repos/<pid>/)
                            with the project and job ids.
3. ``get_*`` helpers        scoped read access so Django never sees another
                            project's rows.

The parser creates its tables with CREATE TABLE IF NOT EXISTS and INSERTs
explicit column lists, so the extra columns here never conflict with it.
"""

import os

import psycopg2

# Same connection parameters the parser uses (overridable via env vars).
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'code_understanding'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'port': int(os.getenv('DB_PORT', 5432)),
}

# Parser tables that get project/job linkage columns.
_LINKED_TABLES = ('files', 'code_entities', 'relationships')


def _connect():
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema():
    """Idempotently add project_id / analysis_job_id to the parser tables.

    Safe to call before every linkage; the parser's CREATE TABLE IF NOT EXISTS
    will never drop or recreate these columns.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for table in _LINKED_TABLES:
                cur.execute(
                    f'ALTER TABLE {table} '
                    'ADD COLUMN IF NOT EXISTS project_id BIGINT'
                )
                cur.execute(
                    f'ALTER TABLE {table} '
                    'ADD COLUMN IF NOT EXISTS analysis_job_id BIGINT'
                )
        conn.commit()
    finally:
        conn.close()


def link_project_output(project_id, analysis_job_id, clone_dir):
    """Stamp the parser rows belonging to this project/job.

    The parser stores each file's absolute path under the project's clone
    directory (media/repos/<project_id>/), so rows are scoped by that path
    prefix. Returns the number of rows linked per table.
    """
    ensure_schema()
    prefix = str(clone_dir)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE files SET project_id=%s, analysis_job_id=%s '
                'WHERE path LIKE %s',
                (project_id, analysis_job_id, prefix + '/%'),
            )
            files_linked = cur.rowcount
            cur.execute(
                'UPDATE code_entities SET project_id=%s, analysis_job_id=%s '
                'WHERE file_id IN (SELECT id FROM files WHERE path LIKE %s)',
                (project_id, analysis_job_id, prefix + '/%'),
            )
            entities_linked = cur.rowcount
            cur.execute(
                'UPDATE relationships SET project_id=%s, analysis_job_id=%s '
                'WHERE file_id IN (SELECT id FROM files WHERE path LIKE %s)',
                (project_id, analysis_job_id, prefix + '/%'),
            )
            relationships_linked = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return {
        'files_linked': files_linked,
        'entities_linked': entities_linked,
        'relationships_linked': relationships_linked,
    }


def get_project_stats(project_id):
    """Per-project counts: files, functions, classes, methods, relationships."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            def count(sql, params):
                cur.execute(sql, params)
                return cur.fetchone()[0]

            return {
                'files': count(
                    'SELECT COUNT(*) FROM files WHERE project_id=%s',
                    (project_id,),
                ),
                'functions': count(
                    "SELECT COUNT(*) FROM code_entities "
                    "WHERE project_id=%s AND type='function'",
                    (project_id,),
                ),
                'classes': count(
                    "SELECT COUNT(*) FROM code_entities "
                    "WHERE project_id=%s AND type='class'",
                    (project_id,),
                ),
                'methods': count(
                    "SELECT COUNT(*) FROM code_entities "
                    "WHERE project_id=%s AND type='method'",
                    (project_id,),
                ),
                'relationships': count(
                    'SELECT COUNT(*) FROM relationships WHERE project_id=%s',
                    (project_id,),
                ),
            }
    finally:
        conn.close()


def get_files_for_project(project_id):
    """All files parsed for this project (scoped, never global)."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT id, path, content_hash FROM files '
                'WHERE project_id=%s ORDER BY path',
                (project_id,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def get_entities_for_project(project_id):
    """All code entities (functions/classes/methods) parsed for this project."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT ce.id, f.path AS file_path, ce.name, ce.type, '
                '       ce.start_line, ce.end_line, ce.signature '
                'FROM code_entities ce '
                'JOIN files f ON ce.file_id = f.id '
                'WHERE ce.project_id=%s '
                'ORDER BY f.path, ce.start_line',
                (project_id,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def get_relationships_for_project(project_id):
    """All relationships (caller -> callee) parsed for this project."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT r.id, f.path AS file_path, r.line_number, '
                '       caller.name AS caller_name, '
                '       callee.name AS callee_name '
                'FROM relationships r '
                'JOIN files f ON r.file_id = f.id '
                'JOIN code_entities caller ON r.caller_id = caller.id '
                'JOIN code_entities callee ON r.callee_id = callee.id '
                'WHERE r.project_id=%s '
                'ORDER BY f.path, r.line_number',
                (project_id,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
