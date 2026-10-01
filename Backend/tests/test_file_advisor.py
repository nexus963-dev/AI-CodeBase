from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services import file_advisor
from app.services.file_advisor import (
    UnknownFileError,
    UnknownRepositoryError,
    build_explanation_prompt,
    build_suggestion_prompt,
    read_file_content,
    resolve_file,
    resolve_repository,
)
from app.schemas.repository import FileRequest
from app.routes import files as files_routes


# ==========================================================
# Fixtures
# ==========================================================

@pytest.fixture
def repo_root(tmp_path):
    """A tiny analyzed repository with a manifest on disk."""
    repo = tmp_path / "Stock-Test"
    (repo / "app").mkdir(parents=True)
    (repo / "main.py").write_text(
        "def start():\n    return 1\n", encoding="utf-8"
    )
    (repo / "app" / "utils.py").write_text(
        "def helper(x):\n    return x * 2\n", encoding="utf-8"
    )
    (repo / "README.md").write_text("# hi\n", encoding="utf-8")

    from app.services.repository_manifest import build_repository_manifest

    build_repository_manifest(repo)

    # Written AFTER the analysis: must NOT be readable through the API.
    (repo / "secret-notes.txt").write_text("password: hunter2\n", encoding="utf-8")

    with patch.object(
        file_advisor.settings, "REPOSITORIES_PATH", str(tmp_path)
    ):
        yield tmp_path


# ==========================================================
# resolve_repository
# ==========================================================

def test_resolve_repository_returns_manifest(repo_root):
    repo_path, manifest = resolve_repository("Stock-Test")

    assert repo_path == repo_root / "Stock-Test"
    assert manifest["file_count"] == len(manifest["files"])
    assert manifest["file_count"] >= 3


def test_resolve_repository_rejects_unknown_name(repo_root):
    with pytest.raises(UnknownRepositoryError):
        resolve_repository("Never-Analyzed")


def test_resolve_repository_rejects_empty_name(repo_root):
    with pytest.raises(UnknownRepositoryError):
        resolve_repository("   ")


def test_resolve_repository_rejects_traversal(repo_root):
    # A file that really exists next to the repositories folder.
    outside = repo_root.parent / "outside.txt"
    outside.write_text("top secret", encoding="utf-8")

    for attack in ("..\\..\\outside", "../..", "..\\..\\..\\Windows"):
        with pytest.raises(UnknownRepositoryError):
            resolve_repository(attack)


# ==========================================================
# resolve_file
# ==========================================================

def test_resolve_file_returns_target_and_symbols(repo_root):
    target, manifest, entry = resolve_file("Stock-Test", "app/utils.py")

    assert target == repo_root / "Stock-Test" / "app" / "utils.py"
    assert target.is_file()
    assert entry["path"] == "app/utils.py"
    assert any(
        symbol["name"] == "helper" for symbol in entry.get("symbols", [])
    )
    assert manifest["repository"] == "Stock-Test"


def test_resolve_file_accepts_windows_separators(repo_root):
    target, _, entry = resolve_file("Stock-Test", "app\\utils.py")

    assert entry["path"] == "app/utils.py"
    assert target.is_file()


def test_resolve_file_rejects_file_not_in_manifest(repo_root):
    # Exists on disk, but was never part of the analysis.
    with pytest.raises(UnknownFileError):
        resolve_file("Stock-Test", "secret-notes.txt")


def test_resolve_file_rejects_traversal(repo_root):
    for attack in (
        "../main.py",
        "..\\..\\outside.txt",
        "app/../../secret-notes.txt",
        "/etc/passwd",
    ):
        with pytest.raises(UnknownFileError):
            resolve_file("Stock-Test", attack)


def test_resolve_file_rejects_empty_path(repo_root):
    with pytest.raises(UnknownFileError):
        resolve_file("Stock-Test", "")


def test_resolve_file_unknown_repository(repo_root):
    with pytest.raises(UnknownRepositoryError):
        resolve_file("Nope", "main.py")


# ==========================================================
# read_file_content
# ==========================================================

def test_read_file_content_tolerates_bad_bytes(tmp_path):
    target = tmp_path / "weird.py"
    target.write_bytes(b"caf\xe9 = 'latin1'\n")

    content = read_file_content(target)

    assert " = 'latin1'" in content


# ==========================================================
# Explanation prompt
# ==========================================================

def test_explanation_prompt_has_sections_rules_and_content(repo_root):
    target, manifest, entry = resolve_file("Stock-Test", "app/utils.py")

    prompt = build_explanation_prompt(
        repository_name="Stock-Test",
        file_path=entry["path"],
        file_content=read_file_content(target),
        manifest=manifest,
    )

    # Required output sections
    for section in (
        "**Purpose**",
        "**Key Components**",
        "**How It Fits**",
        "**Dependencies & Side Effects**",
    ):
        assert section in prompt

    # Grounding rules
    assert "Never invent" in prompt
    assert "app/auth.py:42" in prompt  # citation format example
    assert "I couldn't find that information" in prompt

    # File facts
    assert "app/utils.py" in prompt
    assert "def helper(x):" in prompt
    assert "Stock-Test" in prompt

    # Manifest context: symbols + structure marker
    assert "helper" in prompt
    assert "this file is here" in prompt


def test_explanation_prompt_truncates_large_content(repo_root):
    target, manifest, entry = resolve_file("Stock-Test", "main.py")

    huge = "x = 1\n" * 5000  # 30k chars

    prompt = build_explanation_prompt(
        repository_name="Stock-Test",
        file_path=entry["path"],
        file_content=huge,
        manifest=manifest,
    )

    assert "[truncated]" in prompt
    assert len(prompt) < file_advisor.MAX_FILE_CHARS + 4000


# ==========================================================
# Suggestion prompt
# ==========================================================

def test_suggestion_prompt_has_template_and_rules(repo_root):
    target, manifest, entry = resolve_file("Stock-Test", "app/utils.py")

    prompt = build_suggestion_prompt(
        repository_name="Stock-Test",
        file_path=entry["path"],
        file_content=read_file_content(target),
        manifest=manifest,
    )

    # Required per-suggestion template
    for part in (
        "### [priority: high|medium|low]",
        "**Issue:**",
        "**Why it matters:**",
        "**Suggested fix:**",
    ):
        assert part in prompt

    # Review rules
    assert "never invent problems" in prompt
    assert "at most 6 suggestions" in prompt
    assert "app/auth.py:42" in prompt

    # File facts
    assert "app/utils.py" in prompt
    assert "def helper(x):" in prompt


def test_suggestion_prompt_truncates_large_content(repo_root):
    target, manifest, entry = resolve_file("Stock-Test", "main.py")

    prompt = build_suggestion_prompt(
        repository_name="Stock-Test",
        file_path=entry["path"],
        file_content="print('line')\n" * 3000,
        manifest=manifest,
    )

    assert "[truncated]" in prompt
    assert len(prompt) < file_advisor.MAX_FILE_CHARS + 4000


# ==========================================================
# Routes
# ==========================================================

def test_list_files_returns_manifest_entries(repo_root):
    payload = files_routes.list_files("Stock-Test")

    paths = [entry["path"] for entry in payload["files"]]
    assert payload["repository_name"] == "Stock-Test"
    assert payload["file_count"] == len(paths)
    assert "app/utils.py" in paths
    assert "main.py" in paths
    assert ".repix-manifest.json" not in paths


def test_list_files_unknown_repository_404(repo_root):
    with pytest.raises(HTTPException) as excinfo:
        files_routes.list_files("Never-Analyzed")

    assert excinfo.value.status_code == 404


def test_explain_route_returns_explanation(repo_root):
    with patch.object(
        files_routes, "generate_repository_answer",
        return_value="## Purpose\n- it helps",
    ) as mock_llm:
        payload = files_routes.explain_file(
            FileRequest(repository_name="Stock-Test", file_path="app/utils.py")
        )

    assert payload == {
        "file_path": "app/utils.py",
        "explanation": "## Purpose\n- it helps",
    }
    prompt = mock_llm.call_args[0][0]
    assert "app/utils.py" in prompt
    assert "def helper(x):" in prompt


def test_explain_route_unknown_file_404(repo_root):
    with pytest.raises(HTTPException) as excinfo:
        files_routes.explain_file(
            FileRequest(repository_name="Stock-Test", file_path="nope.py")
        )

    assert excinfo.value.status_code == 404


def test_explain_route_llm_failure_500(repo_root):
    with patch.object(
        files_routes, "generate_repository_answer",
        side_effect=RuntimeError("All LLM providers failed"),
    ):
        with pytest.raises(HTTPException) as excinfo:
            files_routes.explain_file(
                FileRequest(repository_name="Stock-Test", file_path="main.py")
            )

    assert excinfo.value.status_code == 500
    assert "Failed to generate explanation" in excinfo.value.detail


def test_suggest_route_returns_suggestions(repo_root):
    with patch.object(
        files_routes, "generate_repository_answer",
        return_value="### [priority: low] Nit",
    ) as mock_llm:
        payload = files_routes.suggest_file_improvements(
            FileRequest(repository_name="Stock-Test", file_path="main.py")
        )

    assert payload["file_path"] == "main.py"
    assert payload["suggestions"].startswith("### [priority: low]")
    prompt = mock_llm.call_args[0][0]
    assert "**Suggested fix:**" in prompt


def test_suggest_route_unknown_repository_404(repo_root):
    with pytest.raises(HTTPException) as excinfo:
        files_routes.suggest_file_improvements(
            FileRequest(repository_name="Missing", file_path="main.py")
        )

    assert excinfo.value.status_code == 404
