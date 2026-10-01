from unittest.mock import patch

import pytest
import requests
from fastapi import HTTPException
from git import Repo

from app.routes import history as history_routes
from app.services import commit_history_service, file_advisor
from app.services.commit_history_service import (
    CommitHistoryError,
    CommitHistoryNotFoundError,
    GitHubRateLimitError,
    get_commit_history,
    normalize_commits,
    split_message,
)
from app.services.file_advisor import UnknownRepositoryError


# ==========================================================
# Helpers
# ==========================================================

class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def gh_entry(
    sha,
    message,
    name="Ada Lovelace",
    date="2026-09-20T10:00:00Z",
    login=None,
):
    if login:
        author = {
            "login": login,
            "avatar_url": f"https://avatars.test/{login}.png",
        }
    else:
        author = None

    return {
        "sha": sha,
        "html_url": f"https://github.com/acme/Demo-Repo/commit/{sha}",
        "author": author,
        "commit": {
            "message": message,
            "author": {"name": name, "date": date},
        },
    }


SAMPLE_COMMITS = [
    gh_entry(
        "abcdef1234567890",
        "Add LSTM model\n\nTrained on 5 years of stock data.",
        login="octocat",
    ),
    gh_entry(
        "1234567abcdef",
        "Initial commit",
        name="Grace Hopper",
        date="2026-09-19T08:30:00Z",
    ),
]


# ==========================================================
# Fixtures
# ==========================================================

@pytest.fixture(autouse=True)
def clear_cache():
    commit_history_service._cache.clear()
    yield
    commit_history_service._cache.clear()


@pytest.fixture
def demo_repo(tmp_path):
    """An analyzed clone whose remote points at GitHub."""
    repo = tmp_path / "Demo-Repo"
    repo.mkdir()
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")

    from app.services.repository_manifest import build_repository_manifest

    build_repository_manifest(repo)

    git_repo = Repo.init(repo)
    git_repo.create_remote(
        "origin", "https://github.com/acme/Demo-Repo.git"
    )

    with patch.object(
        file_advisor.settings, "REPOSITORIES_PATH", str(tmp_path)
    ):
        with patch.object(
            commit_history_service.settings, "GITHUB_TOKEN", ""
        ):
            yield repo


# ==========================================================
# Pure helpers
# ==========================================================

def test_split_message_separates_title_and_body():
    title, body = split_message("Fix bug\n\nThe real explanation.")

    assert title == "Fix bug"
    assert body == "The real explanation."


def test_split_message_handles_empty():
    assert split_message("") == ("(no message)", "")
    assert split_message(None) == ("(no message)", "")


def test_normalize_maps_github_payload():
    commits = normalize_commits(SAMPLE_COMMITS)

    first, second = commits

    assert first["sha"] == "abcdef1"  # first 7 chars
    assert first["title"] == "Add LSTM model"
    assert first["body"] == "Trained on 5 years of stock data."
    assert first["author"] == "octocat"          # GitHub login wins
    assert first["avatar"].endswith("octocat.png")
    assert first["date"] == "2026-09-20T10:00:00Z"
    assert first["url"].endswith("abcdef1234567890")

    assert second["author"] == "Grace Hopper"    # falls back to git name
    assert second["body"] == ""


def test_normalize_survives_missing_fields():
    commits = normalize_commits([{"sha": "x" * 40}])

    assert commits[0]["title"] == "(no message)"
    assert commits[0]["author"] == "Unknown"
    assert commits[0]["date"] == ""


# ==========================================================
# get_commit_history — success paths
# ==========================================================

def test_commit_history_success(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(200, SAMPLE_COMMITS),
    ) as mock_get:
        payload = get_commit_history("Demo-Repo", limit=5)

    assert payload["owner"] == "acme"
    assert payload["repository_url"] == "https://github.com/acme/Demo-Repo"
    assert payload["commit_count"] == 2
    assert payload["cached"] is False
    assert payload["commits"][0]["title"] == "Add LSTM model"

    # Request shape
    url = mock_get.call_args[0][0]
    assert url == "https://api.github.com/repos/acme/Demo-Repo/commits"
    params = mock_get.call_args[1]["params"]
    assert params["per_page"] == 5
    assert "path" not in params
    headers = mock_get.call_args[1]["headers"]
    assert "Authorization" not in headers   # no token -> no auth


def test_commit_history_passes_path_filter(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(200, SAMPLE_COMMITS),
    ) as mock_get:
        get_commit_history("Demo-Repo", path="/README.md")

    params = mock_get.call_args[1]["params"]
    assert params["path"] == "README.md"    # leading slash stripped


def test_commit_history_sends_token_header(demo_repo):
    with patch.object(
        commit_history_service.settings, "GITHUB_TOKEN", "ghp_test_token"
    ):
        with patch(
            "app.services.commit_history_service.requests.get",
            return_value=FakeResponse(200, SAMPLE_COMMITS),
        ) as mock_get:
            get_commit_history("Demo-Repo")

    headers = mock_get.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer ghp_test_token"
    assert headers["Accept"] == "application/vnd.github+json"


def test_commit_history_clamps_limit(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(200, SAMPLE_COMMITS),
    ) as mock_get:
        get_commit_history("Demo-Repo", limit=5000)

    params = mock_get.call_args[1]["params"]
    assert params["per_page"] == commit_history_service.MAX_LIMIT


def test_commit_history_second_call_hits_cache(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(200, SAMPLE_COMMITS),
    ) as mock_get:
        first = get_commit_history("Demo-Repo", limit=10)
        second = get_commit_history("Demo-Repo", limit=10)

    assert mock_get.call_count == 1
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["commits"] == first["commits"]


# ==========================================================
# get_commit_history — failure paths
# ==========================================================

def test_unknown_repository_raises(demo_repo):
    with pytest.raises(UnknownRepositoryError):
        get_commit_history("Never-Analyzed")


def test_missing_github_remote_raises(demo_repo):
    # A clone with no remote at all.
    no_remote = demo_repo.parent / "Local-Only"
    no_remote.mkdir()
    (no_remote / "a.py").write_text("x = 1\n", encoding="utf-8")

    from app.services.repository_manifest import build_repository_manifest

    build_repository_manifest(no_remote)
    Repo.init(no_remote)

    with pytest.raises(CommitHistoryNotFoundError) as excinfo:
        get_commit_history("Local-Only")

    assert excinfo.value.status_code == 404
    assert "no GitHub remote" in str(excinfo.value)


def test_github_404_raises_not_found(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(404),
    ):
        with pytest.raises(CommitHistoryNotFoundError) as excinfo:
            get_commit_history("Demo-Repo")

    assert excinfo.value.status_code == 404
    assert "not found" in str(excinfo.value)


def test_rate_limit_429_raises(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(429),
    ):
        with pytest.raises(GitHubRateLimitError) as excinfo:
            get_commit_history("Demo-Repo")

    assert excinfo.value.status_code == 429
    assert "GITHUB_TOKEN" in str(excinfo.value)


def test_rate_limit_403_with_zero_remaining_raises(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(
            403, headers={"X-RateLimit-Remaining": "0"}
        ),
    ):
        with pytest.raises(GitHubRateLimitError):
            get_commit_history("Demo-Repo")


def test_plain_403_raises_generic_error(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(403, headers={"X-RateLimit-Remaining": "42"}),
    ):
        with pytest.raises(CommitHistoryError) as excinfo:
            get_commit_history("Demo-Repo")

    assert excinfo.value.status_code == 502
    assert "refused" in str(excinfo.value)


def test_network_failure_raises(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        side_effect=requests.ConnectionError("boom"),
    ):
        with pytest.raises(CommitHistoryError) as excinfo:
            get_commit_history("Demo-Repo")

    assert "Could not reach GitHub" in str(excinfo.value)


def test_unreadable_json_raises(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(200, payload=None),
    ):
        with pytest.raises(CommitHistoryError) as excinfo:
            get_commit_history("Demo-Repo")

    assert "unreadable" in str(excinfo.value)


# ==========================================================
# Route
# ==========================================================

def test_route_returns_payload(demo_repo):
    with patch(
        "app.services.commit_history_service.requests.get",
        return_value=FakeResponse(200, SAMPLE_COMMITS),
    ):
        payload = history_routes.list_commits(
            repository_name="Demo-Repo", limit=5
        )

    assert payload["commit_count"] == 2
    assert payload["commits"][0]["author"] == "octocat"


def test_route_maps_unknown_repository_to_404():
    with patch.object(
        history_routes,
        "get_commit_history",
        side_effect=UnknownRepositoryError("not analyzed"),
    ):
        with pytest.raises(HTTPException) as excinfo:
            history_routes.list_commits(repository_name="Nope")

    assert excinfo.value.status_code == 404


def test_route_maps_rate_limit_to_429():
    with patch.object(
        history_routes,
        "get_commit_history",
        side_effect=GitHubRateLimitError("slow down"),
    ):
        with pytest.raises(HTTPException) as excinfo:
            history_routes.list_commits(repository_name="Demo-Repo")

    assert excinfo.value.status_code == 429


def test_route_maps_upstream_failure_to_502():
    with patch.object(
        history_routes,
        "get_commit_history",
        side_effect=CommitHistoryError("GitHub exploded"),
    ):
        with pytest.raises(HTTPException) as excinfo:
            history_routes.list_commits(repository_name="Demo-Repo")

    assert excinfo.value.status_code == 502
