from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.llm_service as llm_service


# ==========================================================
# Helpers
# ==========================================================

def fake_nvidia_response(text="nvidia answer", status=200, body="err"):
    response = MagicMock()
    response.status_code = status
    response.text = body
    response.json.return_value = {
        "choices": [{"message": {"content": text}}]
    }
    return response


class FakeGeminiModel:
    """Fake genai model driven by a behavior queue."""

    behaviors = []
    seen = []

    def __init__(self, model_name):
        FakeGeminiModel.seen.append(model_name)

    def generate_content(self, prompt):
        behavior = FakeGeminiModel.behaviors.pop(0)
        if isinstance(behavior, Exception):
            raise behavior
        return SimpleNamespace(text=behavior)


def fail_gemini(prompt):
    raise AssertionError("Gemini should not have been called")


# ==========================================================
# NVIDIA as primary provider
# ==========================================================

def test_nvidia_used_when_key_configured():
    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post",
            return_value=fake_nvidia_response("from nvidia"),
        ) as mock_post:
            with patch.object(
                llm_service, "_generate_gemini_answer", fail_gemini
            ):
                answer = llm_service.generate_repository_answer("prompt")

    assert answer == "from nvidia"
    assert mock_post.call_count == 1
    # OpenAI-compatible endpoint + bearer auth
    url = mock_post.call_args[0][0]
    assert url == llm_service.NVIDIA_CHAT_URL
    headers = mock_post.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer nvapi-test"


def test_nvidia_rotates_to_next_model_on_429():
    responses = [
        fake_nvidia_response(status=429, body="rate limit exceeded"),
        fake_nvidia_response("second model answered"),
    ]

    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post", side_effect=responses
        ) as mock_post:
            answer = llm_service._generate_nvidia_answer("prompt")

    assert answer == "second model answered"
    assert mock_post.call_count == 2
    tried_models = [
        call[1]["json"]["model"] for call in mock_post.call_args_list
    ]
    assert tried_models == llm_service.NVIDIA_MODEL_CANDIDATES[:2]


def test_nvidia_failure_falls_back_to_gemini():
    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post",
            return_value=fake_nvidia_response(status=503, body="unavailable"),
        ):
            with patch.object(
                llm_service, "_generate_gemini_answer",
                return_value="from gemini fallback",
            ) as mock_gemini:
                answer = llm_service.generate_repository_answer("prompt")

    assert answer == "from gemini fallback"
    mock_gemini.assert_called_once()


def test_no_nvidia_key_goes_straight_to_gemini():
    with patch.object(llm_service.settings, "NVIDIA_API_KEY", ""):
        with patch.object(
            llm_service.requests, "post"
        ) as mock_post:
            with patch.object(
                llm_service, "_generate_gemini_answer",
                return_value="gemini directly",
            ):
                answer = llm_service.generate_repository_answer("prompt")

    assert answer == "gemini directly"
    mock_post.assert_not_called()


# ==========================================================
# Gemini fallback chain
# ==========================================================

def test_gemini_chain_rotates_on_rate_limit():
    FakeGeminiModel.behaviors = [
        Exception("429 You exceeded your current quota"),
        "answer from second model",
    ]
    FakeGeminiModel.seen = []

    with patch.object(
        llm_service.genai, "GenerativeModel", FakeGeminiModel
    ):
        answer = llm_service._generate_gemini_answer("prompt")

    assert answer == "answer from second model"
    assert FakeGeminiModel.seen == llm_service.GEMINI_MODEL_CANDIDATES[:2]


def test_gemini_chain_handles_503_and_empty_responses():
    FakeGeminiModel.behaviors = [
        Exception("503 model is experiencing high demand"),
        "",
        "third model worked",
    ]
    FakeGeminiModel.seen = []

    with patch.object(
        llm_service.genai, "GenerativeModel", FakeGeminiModel
    ):
        answer = llm_service._generate_gemini_answer("prompt")

    assert answer == "third model worked"
    assert FakeGeminiModel.seen == llm_service.GEMINI_MODEL_CANDIDATES[:3]


# ==========================================================
# Total failure path
# ==========================================================

def test_raises_when_all_providers_fail():
    nvidia_error = fake_nvidia_response(status=429, body="quota")
    gemini_error = Exception("429 gemini quota")

    def gemini_fail(prompt):
        raise RuntimeError(" | ".join(
            f"{name}: {gemini_error}"
            for name in llm_service.GEMINI_MODEL_CANDIDATES
        ))

    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post", return_value=nvidia_error
        ):
            with patch.object(
                llm_service, "_generate_gemini_answer", gemini_fail
            ):
                try:
                    llm_service.generate_repository_answer("prompt")
                    raise AssertionError("should have raised RuntimeError")
                except RuntimeError as exc:
                    assert "All LLM providers failed" in str(exc)
                    assert "NVIDIA" in str(exc)
                    assert "Gemini" in str(exc)
