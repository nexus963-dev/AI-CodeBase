#!/usr/bin/env python3
"""
AI Software Architect Backend - Structural Database and Call Graph Extractor
Language-agnostic design (Python implemented first, easy to extend to JS/TS, Java, Go, etc.)

Given a GitHub repository, clones it, walks through supported files, extracts
structural entities (functions, classes, methods) and builds a resolved call graph
(same-file calls) using Tree-sitter parsers. Stores results in PostgreSQL.

Designed for easy extension: add new language support by:
1. Installing the tree-sitter language package (e.g., pip install tree-sitter-javascript)
2. Adding a language config to the LANGUAGES dict
3. Implementing get_entities() and get_calls() functions for that language

Usage:
    python repo_parser.py --repo-url <github_url> --to-path <local_dir>
    or
    python repo_parser.py --repo-path <existing_local_dir>

Environment Variables (optional, overrides hardcoded DB_CONFIG):
    DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT

Output:
    Populates PostgreSQL database with:
        - files table
        - code_entities table (language-agnostic types)
        - relationships table (call graph)

Includes verification queries to manually verify extraction accuracy.
"""

import os
import sys
import hashlib
import argparse
from pathlib import Path
import logging

import pygit2
from tree_sitter import Language, Parser
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database connection parameters - can be overridden by environment variables
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'code_understanding'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'port': int(os.getenv('DB_PORT', 5432))
}

# ============================================================================
# LANGUAGE SUPPORT CONFIGURATION
# ============================================================================
# To add a new language:
# 1. Install tree-sitter language package: pip install tree-sitter-<language>
# 2. Import the language module
# 3. Add entry to LANGUAGES dict with:
#    - extension: file extension (e.g., '.js')
#    - language: Tree-sitter Language object
#    - get_entities: function(tree_root, source_code) -> list of entity dicts
#    - get_calls: function(tree_root, source_code) -> list of call site dicts with byte positions
# Each entity dict should have: name, type, start_line, end_line, signature, start_byte, end_byte
# Each call site dict should have: line_number, called_name, start_byte, end_byte

try:
    import tree_sitter_python as tspython
    PYTHON_LANGUAGE = Language(tspython.language())
except ImportError:
    logger.warning("tree-sitter-python not installed. Python support disabled.")
    PYTHON_LANGUAGE = None

# TODO: Add other languages as needed
# import tree_sitter_javascript as tsjavascript
# JAVASCRIPT_LANGUAGE = Language(tsjavascript.language())

LANGUAGES = {}

if PYTHON_LANGUAGE:
    # Python language configuration
    def get_python_entities(root_node, source_code):
        """Extract functions, classes, methods from Python AST."""
        entities = []

        def get_line_col(point):
            return point.row, point.column

        def get_text(node):
            return source_code[node.start_byte:node.end_byte].strip()

        def get_lines(node):
            start_line = get_line_col(node.start_point)[0] + 1
            end_line = get_line_col(node.end_point)[0] + 1
            return start_line, end_line

        def collect_definitions(node, current_class=None):
            if node.type == 'function_definition':
                name_node = node.child_by_field_name('name')
                if name_node is None:
                    return
                name = get_text(name_node)
                start_line, end_line = get_lines(node)
                params_node = node.child_by_field_name('parameters')
                signature = get_text(params_node) if params_node else ""

                if current_class is not None:
                    full_name = f"{current_class}.{name}"
                    entity_type = 'method'
                else:
                    full_name = name
                    entity_type = 'function'

                entities.append({
                    'name': full_name,
                    'type': entity_type,
                    'start_line': start_line,
                    'end_line': end_line,
                    'signature': signature,
                    'start_byte': node.start_byte,
                    'end_byte': node.end_byte
                })
                # Process function body for nested definitions (rare in Python)
                body_node = node.child_by_field_name('body')
                if body_node:
                    for child in body_node.children:
                        collect_definitions(child, current_class)

            elif node.type == 'class_definition':
                name_node = node.child_by_field_name('name')
                if name_node is None:
                    return
                name = get_text(name_node)
                start_line, end_line = get_lines(node)
                # Class signature could include inheritance, but we keep it simple
                signature = ""

                entities.append({
                    'name': name,
                    'type': 'class',
                    'start_line': start_line,
                    'end_line': end_line,
                    'signature': signature,
                    'start_byte': node.start_byte,
                    'end_byte': node.end_byte
                })
                # Recurse into class body to find methods
                body_node = node.child_by_field_name('body')
                if body_node:
                    for child in body_node.children:
                        collect_definitions(child, current_class=name)
            else:
                for child in node.children:
                    collect_definitions(child, current_class)

        collect_definitions(root_node)
        return entities

    def get_python_calls(root_node, source_code):
        """Extract function call sites from Python AST."""
        calls = []

        def get_text(node):
            return source_code[node.start_byte:node.end_byte].strip()

        def get_line_col(point):
            return point.row, point.column

        def find_calls(node, current_function=None):
            if node.type == 'call':
                func_node = node.child_by_field_name('function')
                if func_node is None:
                    return

                called_name = None
                if func_node.type == 'identifier':
                    called_name = get_text(func_node)
                elif func_node.type == 'attribute':
                    attr_node = func_node.child_by_field_name('attribute')
                    if attr_node:
                        called_name = get_text(attr_node)
                    else:
                        # Fallback for complex attribute access
                        full_text = get_text(func_node)
                        called_name = full_text.split('.')[-1] if '.' in full_text else full_text
                # Ignore other call types (like calls via indexing) for simplicity

                if called_name is None:
                    return

                calls.append({
                    'line_number': get_line_col(node.start_point)[0] + 1,
                    'called_name': called_name,
                    'start_byte': node.start_byte,
                    'end_byte': node.end_byte
                })

            for child in node.children:
                find_calls(child, current_function)

        find_calls(root_node)
        return calls

    LANGUAGES['.py'] = {
        'language': PYTHON_LANGUAGE,
        'get_entities': get_python_entities,
        'get_calls': get_python_calls
    }
    logger.info("Python language support enabled")

# Add other languages here as they're implemented
# Example template:
# try:
#     import tree_sitter_javascript as tsjavascript
#     JAVASCRIPT_LANGUAGE = Language(tsjavascript.language())
#
#     def get_js_entities(...): ...
#     def get_js_calls(...): ...
#
#     LANGUAGES['.js'] = {
#         'language': JAVASCRIPT_LANGUAGE,
#         'get_entities': get_js_entities,
#         'get_calls': get_js_calls
#     }
# except ImportError:
#     logger.warning("tree-sitter-javascript not installed. JavaScript support disabled.")

# ============================================================================
# DATABASE SETUP
# ============================================================================

def get_db_connection():
    """Create and return a PostgreSQL database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Could not connect to database: {e}")
        logger.info("Make sure PostgreSQL is running and the database exists.")
        logger.info(f"Connection params: {DB_CONFIG}")
        sys.exit(1)

def init_db(conn):
    """Initialize database tables if they don't exist."""
    with conn.cursor() as cur:
        # Files table for caching
        cur.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id SERIAL PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                content_hash TEXT NOT NULL
            )
        """)

        # Code entities: functions, classes, methods (language-agnostic types)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS code_entities (
                id SERIAL PRIMARY KEY,
                file_id INTEGER REFERENCES files(id),
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                signature TEXT
            )
        """)

        # Relationships: call graph
        cur.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id SERIAL PRIMARY KEY,
                caller_id INTEGER REFERENCES code_entities(id),
                callee_id INTEGER REFERENCES code_entities(id),
                file_id INTEGER REFERENCES files(id),
                line_number INTEGER NOT NULL
            )
        """)

        # Staging table for call sites during first pass
        # Stores resolved caller_id (from first pass) and called_name to resolve
        cur.execute("""
            CREATE TABLE IF NOT EXISTS call_sites_staging (
                id SERIAL PRIMARY KEY,
                file_id INTEGER REFERENCES files(id),
                line_number INTEGER NOT NULL,
                caller_id INTEGER REFERENCES code_entities(id),
                called_name TEXT NOT NULL
            )
        """)

        # Indexes for performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_file ON code_entities(file_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON code_entities(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_relationships_caller ON relationships(caller_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_relationships_callee ON relationships(callee_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_staging_file ON call_sites_staging(file_id)")

    conn.commit()
    logger.info("Database initialized")

# ============================================================================
# CORE PROCESSING LOGIC
# ============================================================================

def get_file_hash(filepath):
    """Compute SHA256 hash of file content."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_language_for_file(file_path):
    """Determine language config based on file extension."""
    ext = file_path.suffix.lower()
    return LANGUAGES.get(ext)

def find_containing_entity(byte_position, entities):
    """
    Find which entity contains a given byte position.
    Returns the entity dict if exactly one contains the position, None otherwise.
    """
    containing = [
        e for e in entities
        if e['start_byte'] <= byte_position < e['end_byte']
    ]
    return containing[0] if len(containing) == 1 else None

def process_file(file_path, conn):
    """
    Process a single file: hash check, parse, extract entities and calls,
    store in database.
    Returns True if file was processed (not skipped), False if skipped.
    """
    # Calculate file hash
    file_hash = get_file_hash(file_path)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Check if we've processed this file before with same hash
        cur.execute("SELECT id, content_hash FROM files WHERE path = %s", (str(file_path),))
        result = cur.fetchone()

        if result and result['content_hash'] == file_hash:
            logger.debug(f"Skipping unchanged file: {file_path}")
            file_id = result['id']
            return False  # Skipped

    # Determine language
    lang_config = get_language_for_file(file_path)
    if lang_config is None:
        logger.debug(f"Skipping unsupported file: {file_path}")
        return False  # Unsupported language

    # Parse file with Tree-sitter
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()

        try:
            parser = Parser()
            parser.set_language(lang_config["language"])
        except AttributeError:
            # Fallback for newer versions of tree-sitter
            parser = Parser(lang_config["language"])
        tree = parser.parse(bytes(source, "utf8"))
        root_node = tree.root_node
    except Exception as e:
        logger.warning(f"Failed to read or parse {file_path}: {e}")
        return False

    # Extract entities and calls
    entities = lang_config['get_entities'](root_node, source)
    call_sites = lang_config['get_calls'](root_node, source)

    logger.info(f"Processed {file_path}: {len(entities)} entities, {len(call_sites)} call sites")

    # Store in database
    with conn.cursor() as cur:
        # Insert or update file record
        if result:
            # Update existing file record
            cur.execute(
                "UPDATE files SET content_hash = %s WHERE id = %s",
                (file_hash, result['id'])
            )
            file_id = result['id']
        else:
            # Insert new file record
            cur.execute(
                "INSERT INTO files (path, content_hash) VALUES (%s, %s) RETURNING id",
                (str(file_path), file_hash)
            )
            file_id = cur.fetchone()[0]

        # Insert entities and get their IDs
        entity_id_map = {}  # Map entity start_byte to DB id
        for entity in entities:
            cur.execute(
                """
                INSERT INTO code_entities
                (file_id, name, type, start_line, end_line, signature)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    file_id,
                    entity['name'],
                    entity['type'],
                    entity['start_line'],
                    entity['end_line'],
                    entity['signature']
                )
            )
            entity_id = cur.fetchone()[0]
            entity_id_map[entity["start_byte"]] = entity_id  # Map the entity's start_byte to its DB ID

        # Process call sites: resolve caller entity by byte position
        for call_site in call_sites:
            # Find which entity contains this call site
            caller_entity = find_containing_entity(call_site['start_byte'], entities)
            if caller_entity is None:
                logger.debug(f"Call site at line {call_site['line_number']} not inside any function/method in {file_path}")
                continue  # Skip module-level calls for now

            caller_id = entity_id_map[caller_entity['start_byte']]

            # Stage the call site with resolved caller_id
            cur.execute(
                """
                INSERT INTO call_sites_staging
                (file_id, line_number, caller_id, called_name)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    file_id,
                    call_site['line_number'],
                    caller_id,
                    call_site['called_name']
                )
            )

    conn.commit()
    return True  # Processed

def resolve_call_sites(conn):
    """
    Second pass: resolve staged call sites against entity table to build call graph.
    Only resolves same-file calls for simplicity in this version.
    """
    logger.info("Resolving call sites...")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get all staged call sites
        cur.execute("""
            SELECT id, file_id, line_number, caller_id, called_name
            FROM call_sites_staging
        """)
        call_sites = cur.fetchall()

        resolved_count = 0
        unresolved_count = 0

        for site in call_sites:
            file_id = site['file_id']
            line_number = site['line_number']
            caller_id = site['caller_id']
            called_name = site['called_name']

            # Find potential callees: entities in same file with matching name
            cur.execute(
                """
                SELECT id FROM code_entities
                WHERE file_id = %s AND name = %s
                """,
                (file_id, called_name)
            )
            matches = cur.fetchall()

            if len(matches) == 1:
                callee_id = matches[0]['id']

                # Insert relationship (avoid self-calls if desired)
                if caller_id != callee_id:
                    cur.execute(
                        """
                        INSERT INTO relationships
                        (caller_id, callee_id, file_id, line_number)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (caller_id, callee_id, file_id, line_number)
                    )
                resolved_count += 1
            else:
                # Zero or multiple matches - unresolved
                unresolved_count += 1
                # Optional: log unresolved for debugging
                if unresolved_count <= 5:  # Only log first few to avoid spam
                    logger.debug(
                        f"Unresolved call: '{called_name}' at line {line_number} "
                        f"in file_id {file_id} (found {len(matches)} matches)"
                    )

        logger.info(f"Call site resolution: {resolved_count} resolved, {unresolved_count} unresolved")

def process_repository(repo_path):
    """Walk through repository and process all supported files."""
    conn = get_db_connection()
    try:
        init_db(conn)

        processed_count = 0
        skipped_count = 0
        unsupported_count = 0

        logger.info(f"Scanning repository: {repo_path}")

        for root, dirs, files in os.walk(repo_path):
            # Skip common directories that aren't source code
            dirs[:] = [d for d in dirs if not d.startswith('.') and
                      d not in {'__pycache__', 'node_modules', 'venv', 'env', '.git', 'build', 'dist'}]

            for file in files:
                file_path = Path(root) / file
                lang_config = get_language_for_file(file_path)

                if lang_config is None:
                    unsupported_count += 1
                    continue

                if process_file(file_path, conn):
                    processed_count += 1
                else:
                    skipped_count += 1  # Either skipped (unchanged) or failed to parse

        logger.info(f"Scan complete: {processed_count} processed, {skipped_count} skipped/failed, {unsupported_count} unsupported")

        # Resolve call sites after all files processed
        resolve_call_sites(conn)

    finally:
        conn.close()

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Extract structural data and call graph from GitHub repository')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--repo-url', help='GitHub repository URL to clone')
    group.add_argument('--repo-path', help='Path to existing local repository')
    parser.add_argument('--to-path', help='Local path to clone repository to (used with --repo-url)')

    args = parser.parse_args()

    # Determine repository path
    if args.repo_url:
        if not args.to_path:
            # Extract repo name from URL
            repo_name = args.repo_url.split('/')[-1].replace('.git', '')
            args.to_path = os.path.join(os.getcwd(), repo_name)

        repo_path = clone_repo(args.repo_url, args.to_path)
    else:
        repo_path = args.repo_path
        if not os.path.exists(repo_path):
            logger.error(f"Path does not exist: {repo_path}")
            sys.exit(1)

    # Process the repository
    process_repository(repo_path)

    # Print verification queries
    print_verification_queries()

def clone_repo(repo_url, to_path):
    """Clone a GitHub repository using pygit2."""
    if os.path.exists(to_path):
        logger.info(f"Repository already exists at {to_path}")
        return to_path

    logger.info(f"Cloning {repo_url} to {to_path}")
    try:
        pygit2.clone_repository(repo_url, to_path)
        logger.info("Clone successful")
        return to_path
    except Exception as e:
        logger.error(f"Failed to clone repository: {e}")
        sys.exit(1)

def print_verification_queries():
    """Print SQL queries to manually verify the extraction."""
    print("\n" + "="*60)
    print("VERIFICATION QUERIES - Run these in your PostgreSQL database")
    print("="*60)
    print("\n-- 1. Check files processed")
    print("SELECT COUNT(*) as file_count FROM files;")
    print("\n-- 2. Check entities by type")
    print("SELECT type, COUNT(*) as count FROM code_entities GROUP BY type;")
    print("\n-- 3. Sample functions (first 5)")
    print("SELECT f.path AS file, e.name, e.start_line, e.end_line FROM code_entities e JOIN files f ON e.file_id = f.id WHERE e.type = 'function' LIMIT 5;")
    print("\n-- 4. Sample classes (first 5)")
    print("SELECT f.path AS file, e.name, e.start_line, e.end_line FROM code_entities e JOIN files f ON e.file_id = f.id WHERE e.type = 'class' LIMIT 5;")
    print("\n-- 5. Sample methods (first 5)")
    print("SELECT f.path AS file, e.name, e.start_line, e.end_line FROM code_entities e JOIN files f ON e.file_id = f.id WHERE e.type = 'method' LIMIT 5;")
    print("\n-- 6. Call graph sample (resolved calls)")
    print("""
    SELECT
        caller.name AS caller_name,
        callee.name AS callee_name,
        f.path AS file_path,
        r.line_number
    FROM relationships r
    JOIN code_entities caller ON r.caller_id = caller.id
    JOIN code_entities callee ON r.callee_id = callee.id
    JOIN files f ON r.file_id = f.id
    LIMIT 10;
    """)
    print("\n-- 7. Unresolved call sites (for inspection)")
    print("""
    SELECT
        css.called_name,
        f.path AS file_path,
        css.line_number
    FROM call_sites_staging css
    JOIN files f ON css.file_id = f.id
    WHERE NOT EXISTS (
        SELECT 1 FROM code_entities ce
        WHERE css.file_id = ce.file_id
          AND ce.name = css.called_name
          AND ce.type IN ('function', 'class', 'method')
    )
    LIMIT 10;
    """)
    print("\n-- 8. Total call graph edges")
    print("SELECT COUNT(*) AS edge_count FROM relationships;")
    print("\n-- 9. Check processing status (files vs entities)")
    print("""
    SELECT
        f.path,
        COUNT(e.id) as entity_count
    FROM files f
    LEFT JOIN code_entities e ON f.id = e.file_id
    GROUP BY f.id, f.path
    ORDER BY entity_count DESC
    LIMIT 10;
    """)
    print("\n" + "="*60)

if __name__ == '__main__':
    main()