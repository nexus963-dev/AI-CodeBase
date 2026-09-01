from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
