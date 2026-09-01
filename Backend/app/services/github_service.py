from git import Repo
from pathlib import Path
import re
import subprocess

from app.config.settings import settings


REPOSITORIES_DIR = Path(settings.REPOSITORIES_PATH)


def validate_github_url(repo_url: str):

    if not repo_url.startswith("https://github.com/"):
        raise ValueError("Invalid GitHub repository URL.")

    parts = repo_url.rstrip("/").split("/")

    if len(parts) < 5:
        raise ValueError("Repository owner or repository name is missing.")


def clone_repository(repo_url: str):

    validate_github_url(repo_url)

    REPOSITORIES_DIR.mkdir(exist_ok=True)

    repo_name = repo_url.rstrip("/").split("/")[-1]

    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    repo_path = REPOSITORIES_DIR / repo_name

    # Repository already exists
    if repo_path.exists():

        print(
            f"Repository '{repo_name}' already exists. "
            "Using existing copy."
        )

        return repo_path

    try:

        print(
            f"Cloning repository '{repo_name}'..."
        )

        git_cmd = [
            "git",
            "-c",
            "core.longpaths=true",
            "clone",
            "--depth=1",
            repo_url,
            str(repo_path),
        ]

        subprocess.run(
            git_cmd,
            check=True,
            capture_output=True,
            text=True,
        )

        print(
            "Repository cloned successfully."
        )

    except Exception as e:

        if repo_path.exists():

            import shutil

            shutil.rmtree(
                repo_path,
                ignore_errors=True
            )

        raise ValueError(
            f"Failed to clone repository: {str(e)}"
        )

    return repo_path


def get_repository_metadata(repo_path: Path):

    """
    Extract basic metadata from the cloned repository.

    Returns:
        {
            "language": "...",
            "branch": "...",
            "license": "..."
        }
    """

    # --------------------------------------------------
    # Branch
    # --------------------------------------------------

    try:

        repo = Repo(repo_path)

        branch = repo.active_branch.name

    except Exception:

        branch = "main"


    # --------------------------------------------------
    # Language
    # --------------------------------------------------

    language_extensions = {

        ".py": "Python",

        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",

        ".java": "Java",

        ".cpp": "C++",
        ".cc": "C++",
        ".cxx": "C++",
        ".h": "C++",
        ".hpp": "C++",

        ".c": "C",

        ".cs": "C#",

        ".go": "Go",

        ".rs": "Rust",

        ".php": "PHP",

        ".rb": "Ruby",

        ".kt": "Kotlin",

        ".swift": "Swift",

        ".dart": "Dart",

        ".html": "HTML",
        ".css": "CSS",

    }

    language_counts = {}

    ignored_directories = {
        ".git",
        "node_modules",
        "__pycache__",
        "venv",
        ".venv",
        "env",
        ".env",
        "dist",
        "build",
    }

    for file_path in repo_path.rglob("*"):

        if not file_path.is_file():
            continue

        # Ignore files inside unwanted directories
        if any(
            part in ignored_directories
            for part in file_path.parts
        ):
            continue

        extension = file_path.suffix.lower()

        language = language_extensions.get(
            extension
        )

        if language:

            language_counts[language] = (
                language_counts.get(language, 0) + 1
            )

    if language_counts:

        language = max(
            language_counts,
            key=language_counts.get
        )

    else:

        language = "Unknown"


    # --------------------------------------------------
    # License
    # --------------------------------------------------

    license_name = "No License"

    license_files = [
        "LICENSE",
        "LICENSE.txt",
        "LICENSE.md",
        "LICENCE",
        "LICENCE.txt",
        "LICENCE.md",
    ]

    license_file = None

    for filename in license_files:

        possible_file = repo_path / filename

        if possible_file.exists():

            license_file = possible_file
            break

    if license_file:

        try:

            license_text = (
                license_file
                .read_text(
                    encoding="utf-8",
                    errors="ignore"
                )
                .upper()
            )

            if "MIT LICENSE" in license_text:

                license_name = "MIT License"

            elif "APACHE LICENSE" in license_text:

                license_name = "Apache License"

            elif "GNU GENERAL PUBLIC LICENSE" in license_text:

                if "VERSION 3" in license_text:

                    license_name = "GPL-3.0"

                elif "VERSION 2" in license_text:

                    license_name = "GPL-2.0"

                else:

                    license_name = "GPL"

            elif "BSD 3-CLAUSE" in license_text:

                license_name = "BSD 3-Clause"

            elif "BSD 2-CLAUSE" in license_text:

                license_name = "BSD 2-Clause"

            elif "MOZILLA PUBLIC LICENSE" in license_text:

                license_name = "MPL"

            else:

                license_name = "Custom License"

        except Exception:

            license_name = "Unknown"


    return {

        "language": language,

        "branch": branch,

        "license": license_name,

    }