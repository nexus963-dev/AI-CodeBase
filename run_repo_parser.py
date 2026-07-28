#!/usr/bin/env python3
"""
Automated runner for repo_parser.py
This script tries to use Docker for PostgreSQL, falls back to local PostgreSQL,
and provides clear instructions if neither is available.
"""

import os
import sys
import subprocess
import time
import socket
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor

# Configuration
POSTGRES_IMAGE = "postgres:15-alpine"
CONTAINER_NAME = "ai_architect_pg_test"
DB_NAME = "code_understanding"
DB_USER = "postgres"
DB_PASSWORD = "postgres"
DB_PORT = 5432
DB_HOST = "localhost"

def run_cmd(cmd, check=True, capture_output=False, text=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=capture_output,
            text=text
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {cmd}")
        print(f"Error: {e}")
        if check:
            sys.exit(1)
        return e

def check_docker():
    """Check if Docker is installed and the daemon is running."""
    # Check if docker command exists
    result = run_cmd("docker --version", capture_output=True, check=False)
    if result.returncode != 0:
        return False, "Docker is not installed or not in PATH."
    # Check if the daemon is running
    result = run_cmd("docker info", capture_output=True, check=False)
    if result.returncode != 0:
        return False, "Docker daemon is not running. Please start Docker Desktop."
    return True, "Docker is available and running."

def check_local_postgres():
    """Check if PostgreSQL is running locally on default port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((DB_HOST, DB_PORT))
        sock.close()
        if result == 0:
            # Try to connect and see if it's PostgreSQL
            import psycopg2
            try:
                conn = psycopg2.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database="postgres"
                )
                conn.close()
                return True, "Local PostgreSQL is available."
            except Exception as e:
                return False, f"Port {DB_PORT} is open but not PostgreSQL: {e}"
        else:
            return False, f"No service listening on {DB_HOST}:{DB_PORT}"
    except Exception as e:
        return False, f"Error checking local PostgreSQL: {e}"

def start_postgres_container():
    """Start a PostgreSQL container if not already running."""
    print(f"Checking for existing container '{CONTAINER_NAME}'...")
    # Check if container exists
    result = run_cmd(
        f"docker ps -a --filter name={CONTAINER_NAME} --format '{{{{.Names}}}}'",
        capture_output=True
    )
    if CONTAINER_NAME in result.stdout:
        print(f"Container '{CONTAINER_NAME}' exists.")
        # Check if it's running
        result = run_cmd(
            f"docker ps --filter name={CONTAINER_NAME} --format '{{{{.Status}}}}'",
            capture_output=True
        )
        if "Up" in result.stdout:
            print("Container is already running.")
            return
        else:
            print("Starting existing container...")
            run_cmd(f"docker start {CONTAINER_NAME}")
    else:
        print(f"Creating and starting new container '{CONTAINER_NAME}'...")
        run_cmd(
            f"docker run -d "
            f"--name {CONTAINER_NAME} "
            f"-e POSTGRES_PASSWORD={DB_PASSWORD} "
            f"-p {DB_PORT}:{DB_PORT} "
            f"{POSTGRES_IMAGE}"
        )
    # Wait for container to be ready
    print("Waiting for PostgreSQL to be ready...")
    for _ in range(30):  # Try for 30 seconds
        result = run_cmd(
            f"docker exec {CONTAINER_NAME} pg_isready -U {DB_USER}",
            capture_output=True,
            check=False
        )
        if result.returncode == 0:
            print("PostgreSQL is ready.")
            break
        time.sleep(1)
    else:
        print("Timeout waiting for PostgreSQL to start.")
        sys.exit(1)

def setup_local_postgres():
    """Verify local PostgreSQL setup and create database."""
    print("Setting up local PostgreSQL...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database="postgres"
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            # Check if database exists
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (DB_NAME,)
            )
            if not cur.fetchone():
                cur.execute(f"CREATE DATABASE {DB_NAME}")
                print(f"Database '{DB_NAME}' created.")
            else:
                print(f"Database '{DB_NAME}' already exists.")
        conn.close()
        print("Local PostgreSQL is ready.")
    except Exception as e:
        print(f"Error setting up local PostgreSQL: {e}")
        print("Please ensure PostgreSQL is running and accessible with:")
        print(f"  host={DB_HOST}, port={DB_PORT}, user={DB_USER}, password={DB_PASSWORD}")
        sys.exit(1)

def create_database():
    """Create the database if it doesn't exist (works for both Docker and local)."""
    print(f"Creating database '{DB_NAME}'...")
    # Connect to default database to create our database
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database="postgres"  # Connect to default database
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            # Check if database exists
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (DB_NAME,)
            )
            if not cur.fetchone():
                cur.execute(f"CREATE DATABASE {DB_NAME}")
                print(f"Database '{DB_NAME}' created.")
            else:
                print(f"Database '{DB_NAME}' already exists.")
    except Exception as e:
        print(f"Error creating database: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

def install_dependencies():
    """Install required Python packages."""
    print("Checking Python dependencies...")
    required = {
        "pygit2": "pygit2",
        "tree_sitter": "tree-sitter",
        "tree_sitter_python": "tree-sitter-python",
        "psycopg2": "psycopg2"
    }
    missing = []
    for package, import_name in required.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"Installing missing packages: {', '.join(missing)}")
        run_cmd(f"pip install {' '.join(missing)}")
    else:
        print("All dependencies are already installed.")

def set_environment():
    """Set environment variables for the database connection."""
    os.environ["DB_HOST"] = DB_HOST
    os.environ["DB_NAME"] = DB_NAME
    os.environ["DB_USER"] = DB_USER
    os.environ["DB_PASSWORD"] = DB_PASSWORD
    os.environ["DB_PORT"] = str(DB_PORT)
    print("Environment variables set for database connection.")

def run_repo_parser(github_url, to_path=None):
    """Run repo_parser.py with the given GitHub URL."""
    if not to_path:
        # Extract repo name from URL
        repo_name = github_url.split("/")[-1].replace(".git", "")
        to_path = f"./{repo_name}"

    print(f"Running repo_parser.py on {github_url}...")
    print(f"Cloning to: {to_path}")

    # Build command
    cmd = f"python repo_parser.py --repo-url {github_url}"
    if to_path:
        cmd += f" --to-path {to_path}"

    # Run the script
    result = run_cmd(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("repo_parser.py failed:")
        print(result.stderr)
        sys.exit(1)

    print("repo_parser.py completed successfully.")
    print("\n" + "="*60)
    print("OUTPUT FROM REPO_PARSER.PY:")
    print("="*60)
    print(result.stdout)
    return to_path

def run_verification_queries():
    """Run verification queries and print formatted results."""
    print("\n" + "="*60)
    print("VERIFICATION RESULTS")
    print("="*60)

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )

        queries = [
            ("Files processed", "SELECT COUNT(*) AS file_count FROM files;"),
            ("Entity counts by type", "SELECT type, COUNT(*) AS count FROM code_entities GROUP BY type;"),
            ("Sample functions (first 5)", """
                SELECT f.path AS file, e.name, e.start_line, e.end_line
                FROM code_entities e
                JOIN files f ON e.file_id = f.id
                WHERE e.type = 'function'
                LIMIT 5;
            """),
            ("Sample classes (first 5)", """
                SELECT f.path AS file, e.name, e.start_line, e.end_line
                FROM code_entities e
                JOIN files f ON e.file_id = f.id
                WHERE e.type = 'class'
                LIMIT 5;
            """),
            ("Sample methods (first 5)", """
                SELECT f.path AS file, e.name, e.start_line, e.end_line
                FROM code_entities e
                JOIN files f ON e.file_id = f.id
                WHERE e.type = 'method'
                LIMIT 5;
            """),
            ("Call graph sample (resolved calls, first 10)", """
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
            """),
            ("Unresolved call sites (first 10, for inspection)", """
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
        ]

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for title, query in queries:
                print(f"\n{title}:")
                print("-" * len(title))
                try:
                    cur.execute(query)
                    rows = cur.fetchall()
                    if not rows:
                        print("  No results")
                        continue

                    # Print header
                    headers = rows[0].keys()
                    header_line = "  | ".join(headers)
                    print(f"  {header_line}")
                    print("  " + "-"*len(header_line))

                    # Print rows
                    for row in rows:
                        values = [str(row[h]) for h in headers]
                        print(f"  | ".join(values))
                except Exception as e:
                    print(f"  Error executing query: {e}")

        conn.close()

    except Exception as e:
        print(f"Failed to connect to database for verification: {e}")
        print("Make sure PostgreSQL is running and accessible.")
        sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_repo_parser.py <github_url>")
        print("Example: python run_repo_parser.py https://github.com/psf/requests.git")
        sys.exit(1)

    github_url = sys.argv[1]

    print("="*60)
    print("AI Software Architect - Automated Repository Analysis")
    print("="*60)

    # Step 1: Install dependencies FIRST (moved up to ensure psycopg2 is available for PostgreSQL operations)
    install_dependencies()

    # Step 2: Check for Docker
    docker_available, docker_msg = check_docker()
    print(f"Docker check: {docker_msg}")

    # Step 3: Check for local PostgreSQL
    local_available, local_msg = check_local_postgres()
    print(f"Local PostgreSQL check: {local_msg}")

    # Decide which approach to use
    use_docker = False
    if docker_available:
        use_docker = True
        print("\n-> Using Docker for PostgreSQL")
    elif local_available:
        use_docker = False
        print("\n-> Using local PostgreSQL")
    else:
        print("\n❌ Neither Docker nor local PostgreSQL is available.")
        print("\nPlease choose one of these options:")
        print("\nOPTION 1: Install and start Docker Desktop")
        print("  1. Download from https://www.docker.com/products/docker-desktop/")
        print("  2. Install and start Docker Desktop")
        print("  3. Wait for it to show 'Docker is running'")
        print("  4. Then run this script again")
        print("\nOPTION 2: Install and run PostgreSQL locally")
        print("  1. Download PostgreSQL from https://www.postgresql.org/download/windows/")
        print("  2. Install it (use default port 5432)")
        print("  3. Make sure the PostgreSQL service is running")
        print("  4. Then run this script again")
        print("\nOPTION 3: Manual setup (advanced)")
        print("  1. Ensure PostgreSQL is running on localhost:5432")
        print("  2. Create database 'code_understanding'")
        print("  3. Set user/password to 'postgres'/'postgres' (or edit DB_CONFIG in repo_parser.py)")
        print("  4. Install dependencies: pip install pygit2 tree-sitter tree-sitter-python psycopg2-binary")
        print("  5. Set environment variables:")
        print("     set DB_HOST=localhost")
        print("     set DB_NAME=code_understanding")
        print("     set DB_USER=postgres")
        print("     set DB_PASSWORD=postgres")
        print("     set DB_PORT=5432")
        print("  6. Run: python repo_parser.py --repo-url https://github.com/psf/requests.git --to-path ./requests_repo")
        sys.exit(1)

    # Step 4: Setup PostgreSQL (Docker or local)
    if use_docker:
        start_postgres_container()
    else:
        setup_local_postgres()

    # Step 5: Create database
    create_database()

    # Step 6: Set environment variables
    set_environment()

    # Step 7: Run repo_parser.py
    run_repo_parser(github_url)

    # Step 8: Run verification queries
    run_verification_queries()

    print("\n" + "="*60)
    print("Analysis complete!")
    if use_docker:
        print(f"PostgreSQL container '{CONTAINER_NAME}' is still running.")
        print("To stop and remove it later, run:")
        print(f"  docker stop {CONTAINER_NAME} && docker rm {CONTAINER_NAME}")
    else:
        print("Using local PostgreSQL instance.")
        print("To stop local PostgreSQL, use your system's service manager.")
    print("="*60)

if __name__ == "__main__":
    main()
