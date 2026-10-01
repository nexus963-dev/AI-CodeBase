"""
GitHub commit history (Phase 4a).

Answers "how did this project come to be?" by pulling the commit
flow from the GitHub REST API.

Why the API instead of `git log`? The clones are shallow
(--depth=1), so locally only the latest commit exists — the full
history lives on GitHub. The owner/repo identity comes from the
Phase 2 function that reads the clone's remote.

Rate limits:
- no token:  60 requests / hour / IP
- GITHUB_TOKEN set in Backend/.env: 5000 / hour

Responses are cached in memory for a few minutes so reopening the
History panel does not burn quota.
"""
import time
from typing import Dict, List, Optional

import requests

from app.config.settings import settings
from app.services.file_advisor import resolve_repository
from app.services.github_service import get_repository_identity


GITHUB_API_BASE = "https://api.github.com"

# How many commits one page returns (GitHub max = 100)
DEFAULT_LIMIT = 30
MAX_LIMIT = 100

# (connect, read) seconds
REQUEST_TIMEOUT = (5, 15)

# In-memory cache TTL
CACHE_TTL_SECONDS = 300

# key -> (monotonic timestamp, payload)
_cache: Dict[str, tuple] = {}


class CommitHistoryError(Exception):
    """Upstream GitHub failure. status_code maps to the HTTP route."""

    status_code = 502


class CommitHistoryNotFoundError(CommitHistoryError):
    """No GitHub remote for this clone, or the repo is gone/private."""

    status_code = 404


class GitHubRateLimitError(CommitHistoryError):
    """GitHub hourly quota exhausted."""

    status_code = 429


# ==========================================================
# Normalization
# ==========================================================

def split_message(message: str) -> tuple:
    """Full git message -> (first-line title, remaining body)."""
    message = (message or "").strip()

    if not message:
        return "(no message)", ""

    lines = message.splitlines()

    title = lines[0].strip() or "(no message)"

    body = "\n".join(lines[1:]).strip()

    return title, body


def short_sha(sha: str) -> str:
    return (sha or "")[:7]


def author_name(entry: dict) -> str:
    """GitHub login when the author has an account, else git name."""
    github_author = entry.get("author") or {}

    if github_author.get("login"):
        return github_author["login"]

    commit = entry.get("commit") or {}
    git_author = commit.get("author") or commit.get("committer") or {}

    return (git_author.get("name") or git_author.get("email") or "Unknown").strip()


def normalize_commits(entries: List[dict]) -> List[dict]:
    """Map GitHub's commit payload to the lean shape the UI needs."""
    commits = []

    for entry in entries:

        commit = entry.get("commit") or {}

        title, body = split_message(commit.get("message", ""))

        git_author = commit.get("author") or commit.get("committer") or {}

        github_author = entry.get("author") or {}

        commits.append({
            "sha": short_sha(entry.get("sha", "")),
            "title": title,
            "body": body,
            "author": author_name(entry),
            "avatar": github_author.get("avatar_url") or "",
            "date": git_author.get("date") or "",
            "url": entry.get("html_url") or "",
        })

    return commits


# ==========================================================
# Cache
# ==========================================================

def _cache_get(key: str):
    entry = _cache.get(key)

    if entry and time.monotonic() - entry[0] < CACHE_TTL_SECONDS:
        return entry[1]

    return None


def _cache_set(key: str, payload: dict) -> None:
    _cache[key] = (time.monotonic(), payload)


# ==========================================================
# GitHub API
# ==========================================================

def _build_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Repix-GitHub-Assistant",
    }

    token = (settings.GITHUB_TOKEN or "").strip()

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def fetch_commits(
    owner: str,
    repo_name: str,
    path: Optional[str],
    limit: int,
) -> List[dict]:
    """Call GitHub. Raises CommitHistoryError subclasses on failure."""
    params: Dict[str, object] = {"per_page": limit}

    if path:
        params["path"] = path

    try:
        response = requests.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/commits",
            params=params,
            headers=_build_headers(),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise CommitHistoryError(
            "Could not reach GitHub (network error). "
            "Check your internet connection and try again."
        )

    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            raise CommitHistoryError(
                "GitHub returned an unreadable response. Try again shortly."
            )

        if not isinstance(payload, list):
            raise CommitHistoryError(
                "GitHub returned an unexpected response. Try again shortly."
            )

        return payload

    if response.status_code == 404:
        raise CommitHistoryNotFoundError(
            "Repository not found on GitHub "
            "(it may be private, renamed, or deleted)."
        )

    if response.status_code in (403, 429):
        remaining = response.headers.get("X-RateLimit-Remaining")

        if response.status_code == 429 or remaining == "0":
            raise GitHubRateLimitError(
                "GitHub rate limit reached (60 requests/hour without a token). "
                "Add GITHUB_TOKEN to Backend/.env and restart the backend."
            )

        raise CommitHistoryError(
            "GitHub refused the request (403). "
            "The repository may be private or blocked."
        )

    raise CommitHistoryError(
        f"GitHub returned status {response.status_code}. Try again shortly."
    )


# ==========================================================
# Public entry point
# ==========================================================

def get_commit_history(
    repository_name: str,
    path: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """
    Commit flow for an analyzed repository, newest first.

    Raises:
        UnknownRepositoryError  – repo was never analyzed
        CommitHistoryNotFoundError – no GitHub remote / repo gone
        GitHubRateLimitError – hourly quota exhausted
        CommitHistoryError – any other upstream failure
    """
    repo_path, _manifest = resolve_repository(repository_name)

    identity = get_repository_identity(repo_path)

    owner = identity.get("owner")
    repository_url = identity.get("repository_url")

    if not owner or not repository_url:
        raise CommitHistoryNotFoundError(
            "This repository has no GitHub remote, "
            "so commit history is unavailable."
        )

    # https://github.com/owner/repo -> repo
    repo_name = repository_url.rstrip("/").rsplit("/", 1)[-1]

    limit = max(1, min(int(limit), MAX_LIMIT))

    path = path.strip().lstrip("/") if path and path.strip() else None

    cache_key = f"{owner}/{repo_name}:{path or ''}:{limit}"

    cached_payload = _cache_get(cache_key)

    if cached_payload is not None:
        return {**cached_payload, "cached": True}

    entries = fetch_commits(owner, repo_name, path, limit)

    payload = {
        "repository_name": repository_name,
        "owner": owner,
        "repository_url": repository_url,
        "path": path,
        "commit_count": len(entries),
        "commits": normalize_commits(entries),
        "cached": False,
    }

    _cache_set(cache_key, payload)

    return payload
