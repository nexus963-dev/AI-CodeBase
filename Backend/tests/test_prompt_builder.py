from app.services.prompt_builder import (
    build_prompt,
    MAX_CHUNK_CHARS,
    MAX_CONTEXT_CHARS,
    MAX_MANIFEST_LISTED_FILES,
)


# ==========================================================
# Helpers
# ==========================================================

def make_results(documents, paths, distances):
    """Mimics the dict ChromaDB returns from collection.query()."""
    return {
        "documents": [documents],
        "metadatas": [[{"file_path": path} for path in paths]],
        "distances": [distances],
    }


def make_manifest(count=100):
    files = [
        {
            "path": f"src/file_{index}.py",
            "type": ".py",
            "symbols": [
                {
                    "name": f"func_{index}",
                    "kind": "function",
                    "line": index + 1,
                }
            ],
        }
        for index in range(count)
    ]
    files.append(
        {
            "path": "app/auth.py",
            "type": ".py",
            "symbols": [
                {"name": "create_access_token", "kind": "function", "line": 19},
                {"name": "get_current_user", "kind": "function", "line": 35},
            ],
        }
    )
    return {
        "repository": "demo-repo",
        "file_count": len(files),
        "files": files,
    }


# ==========================================================
# Template rules
# ==========================================================

def test_prompt_contains_rules_and_citation_format():
    results = make_results(
        ["def login(): pass"],
        ["app/auth.py"],
        [0.5],
    )

    prompt = build_prompt(
        question="How does login work?",
        retrieval_results=results,
        manifest=make_manifest(),
        conversation_history="user: hi",
    )

    assert "Rules:" in prompt
    assert "`app/auth.py:42`" in prompt          # citation example
    assert "I couldn't find that information" in prompt
    assert "Markdown" in prompt
    assert "How does login work?" in prompt


def test_history_is_included_and_fallback_works():
    results = make_results(["code"], ["a.py"], [0.5])
    manifest = make_manifest()

    prompt = build_prompt(
        question="q",
        retrieval_results=results,
        manifest=manifest,
        conversation_history="user: first question\nassistant: first answer",
    )
    assert "user: first question" in prompt
    assert "assistant: first answer" in prompt

    prompt_without_history = build_prompt(
        question="q",
        retrieval_results=results,
        manifest=manifest,
        conversation_history="",
    )
    assert "No previous conversation." in prompt_without_history


# ==========================================================
# Relevance ranking + filtering
# ==========================================================

def test_irrelevant_chunks_are_filtered_out():
    results = make_results(
        ["good match code", "also good code", "totally unrelated noise"],
        ["app/good.py", "app/also.py", "src/noise.py"],
        [0.5, 0.6, 5.0],
    )

    prompt = build_prompt(
        question="how does auth work?",
        retrieval_results=results,
        manifest=make_manifest(),
    )

    # distance 5.0 is > 2x the best (0.5) => dropped
    assert "totally unrelated noise" not in prompt
    assert "good match code" in prompt
    assert "also good code" in prompt


def test_relevance_labels_and_distances_are_shown():
    results = make_results(
        ["best chunk", "weak chunk"],
        ["app/best.py", "app/weak.py"],
        [0.5, 0.9],
    )

    prompt = build_prompt(
        question="q",
        retrieval_results=results,
        manifest=make_manifest(),
    )

    assert "relevance: high" in prompt
    assert "relevance: low" in prompt
    assert "distance: 0.500" in prompt
    assert "source: app/best.py" in prompt


def test_prompt_respects_total_context_budget():
    documents = [f"chunk {index} " + "x" * 2000 for index in range(30)]
    paths = [f"src/f{index}.py" for index in range(30)]
    distances = [0.1 + index * 0.01 for index in range(30)]

    results = make_results(documents, paths, distances)
    prompt = build_prompt(
        question="q",
        retrieval_results=results,
        manifest=make_manifest(),
    )

    marker = "Repository Context (retrieved by semantic similarity, best match first):"
    context_body = prompt.split(marker, 1)[1].strip("\n")

    assert len(context_body) <= MAX_CONTEXT_CHARS
    # budget must have stopped the loop before all 30 chunks got in
    assert prompt.count("relevance:") < 30


def test_oversized_chunks_are_truncated():
    big_document = "z" * (MAX_CHUNK_CHARS * 4)
    results = make_results([big_document], ["app/big.py"], [0.4])

    prompt = build_prompt(
        question="q",
        retrieval_results=results,
        manifest=make_manifest(),
    )

    marker = "Repository Context (retrieved by semantic similarity, best match first):"
    context_body = prompt.split(marker, 1)[1]

    assert "[truncated]" in context_body
    assert context_body.count("z") == MAX_CHUNK_CHARS


def test_missing_distances_do_not_break_prompt():
    results = {
        "documents": [["some code"]],
        "metadatas": [[{"file_path": "a.py"}]],
        "distances": [[]],
    }

    prompt = build_prompt(question="q", retrieval_results=results)
    assert "some code" in prompt
    assert "relevance: unknown" in prompt


# ==========================================================
# Manifest pruning
# ==========================================================

def test_manifest_is_pruned_for_normal_questions():
    manifest = make_manifest(count=100)
    results = make_results(["code"], ["src/file_3.py"], [0.5])

    prompt = build_prompt(
        question="How does the login route work?",
        retrieval_results=results,
        manifest=manifest,
    )

    assert "Directory structure:" in prompt
    assert "Files: 101" in prompt
    # beyond the cap of listed files => must NOT be dumped
    assert "src/file_99.py" not in prompt
    # retrieved chunk's file keeps its symbol details
    assert "func_3 (line 4)" in prompt


def test_full_structure_questions_get_wider_symbols():
    manifest = make_manifest(count=100)
    results = make_results(["code"], ["src/file_3.py"], [0.5])

    prompt = build_prompt(
        question="List all functions in this repository structure",
        retrieval_results=results,
        manifest=manifest,
    )

    # raised cap => far more symbol files included
    assert "src/file_99.py" in prompt


def test_question_keywords_pick_relevant_files():
    manifest = make_manifest(count=10)
    manifest["files"].append(
        {
            "path": "app/database.py",
            "type": ".py",
            "symbols": [{"name": "get_db", "kind": "function", "line": 16}],
        }
    )
    manifest["file_count"] = len(manifest["files"])

    results = make_results(["code"], ["src/file_1.py"], [0.5])

    prompt = build_prompt(
        question="Where is the database connection configured?",
        retrieval_results=results,
        manifest=manifest,
    )

    assert "app/database.py: function get_db (line 16)" in prompt


def test_empty_manifest_is_handled():
    results = make_results(["code"], ["a.py"], [0.5])

    prompt = build_prompt(
        question="q",
        retrieval_results=results,
        manifest=None,
    )

    assert "No repository manifest is available." in prompt
