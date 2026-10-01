from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from git import Repo

from app.services import github_service


def test_clone_repository_enables_windows_long_path_support(tmp_path):
    repo_url = "https://github.com/facebook/react"
    target_dir = tmp_path / "repositories"
    target_dir.mkdir()

    with patch.object(github_service, "REPOSITORIES_DIR", target_dir):
        with patch("app.services.github_service.subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(returncode=0)

            result = github_service.clone_repository(repo_url)

            assert result == target_dir / "react"
            git_cmd = mock_run.call_args[0][0]
            assert git_cmd[:3] == ["git", "-c", "core.longpaths=true"]
            assert "--depth=1" in git_cmd
            assert str(target_dir / "react") in git_cmd


# --------------------------------------------------
# get_repository_identity
# --------------------------------------------------


IDENTITY_URL_CASES = [
    # https + .git
    "https://github.com/Akshitagupta299/Repo.git",
    # https, no .git
    "https://github.com/Akshitagupta299/Repo",
    # https with trailing slash
    "https://github.com/Akshitagupta299/Repo/",
    # SSH (SCP-like syntax)
    "git@github.com:Akshitagupta299/Repo.git",
    # SSH over ssh:// scheme
    "ssh://git@github.com/Akshitagupta299/Repo.git",
]


@pytest.mark.parametrize("remote_url", IDENTITY_URL_CASES)
def test_get_repository_identity_normalizes_remote_urls(
    tmp_path, remote_url
):
    repo = Repo.init(tmp_path)
    repo.create_remote("origin", remote_url)

    identity = github_service.get_repository_identity(tmp_path)

    assert identity == {
        "owner": "Akshitagupta299",
        "repository_url": (
            "https://github.com/Akshitagupta299/Repo"
        ),
    }


def test_get_repository_identity_garbage_url_returns_none(tmp_path):
    repo = Repo.init(tmp_path)
    repo.create_remote("origin", "not-a-url")

    assert github_service.get_repository_identity(tmp_path) == {
        "owner": None,
        "repository_url": None,
    }


def test_get_repository_identity_non_github_remote_returns_none(tmp_path):
    repo = Repo.init(tmp_path)
    repo.create_remote(
        "origin", "https://gitlab.com/someone/project.git"
    )

    assert github_service.get_repository_identity(tmp_path) == {
        "owner": None,
        "repository_url": None,
    }


def test_get_repository_identity_no_remotes_returns_none(tmp_path):
    Repo.init(tmp_path)

    assert github_service.get_repository_identity(tmp_path) == {
        "owner": None,
        "repository_url": None,
    }


def test_get_repository_identity_empty_dir_returns_none(tmp_path):
    assert github_service.get_repository_identity(tmp_path) == {
        "owner": None,
        "repository_url": None,
    }
