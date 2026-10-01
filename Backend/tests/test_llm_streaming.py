from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.services.llm_service as llm_service


# ==========================================================
# Helpers
# ==========================================================

def sse_lines(*tokens):
    """Build OpenAI-style SSE byte lines for the given tokens."""
    lines = [
        (
            '{"choices":[{"delta":{"content":'
            + __import__("json").dumps(token)
            + "}}]}"
        ).encode("utf-8")
        for token in tokens
    ]
    lines = [b"data: " + line for line in lines]
    lines.append(b"data: [DONE]")
    return lines


def fake_stream_response(lines, status=200, body="err"):
    response = MagicMock()
    response.status_code = status
    response.text = body
    response.iter_lines.return_value = lines
    return response


class FakeGeminiStreamModel:
    """Fake streaming genai model driven by a behavior queue.

    Each behavior is either an Exception (raise it) or a list of
    chunk objects the stream will yield.
    """

    behaviors = []
    seen = []

    def __init__(self, model_name):
        FakeGeminiStreamModel.seen.append(model_name)

    def generate_content(self, prompt, stream=False):
        behavior = FakeGeminiStreamModel.behaviors.pop(0)
        if isinstance(behavior, Exception):
            raise behavior
        return iter(behavior)


def chunk(text):
    return SimpleNamespace(text=text)


def fail_gemini_stream(prompt, stream=False):
    raise AssertionError("Gemini should not have been called")


# ==========================================================
# NVIDIA streaming
# ==========================================================

def test_stream_nvidia_yields_sse_tokens():
    response = fake_stream_response(sse_lines("Hello", " world"))

    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post", return_value=response
        ) as mock_post:
            with patch.object(
                llm_service, "_stream_gemini_answer", fail_gemini_stream
            ):
                tokens = list(llm_service.stream_repository_answer("prompt"))

    assert tokens == ["Hello", " world"]

    kwargs = mock_post.call_args[1]
    assert kwargs["json"]["stream"] is True
    assert kwargs["stream"] is True
    assert kwargs["json"]["model"] == llm_service.NVIDIA_MODEL_CANDIDATES[0]
    assert kwargs["headers"]["Authorization"] == "Bearer nvapi-test"
    assert kwargs["timeout"] == llm_service.NVIDIA_STREAM_TIMEOUT


def test_stream_nvidia_rotates_to_next_model_on_429():
    responses = [
        fake_stream_response([], status=429, body="rate limit exceeded"),
        fake_stream_response(sse_lines("second model answered")),
    ]

    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post", side_effect=responses
        ) as mock_post:
            tokens = list(llm_service._stream_nvidia_answer("prompt"))

    assert tokens == ["second model answered"]
    assert mock_post.call_count == 2
    tried_models = [
        call[1]["json"]["model"] for call in mock_post.call_args_list
    ]
    assert tried_models == llm_service.NVIDIA_MODEL_CANDIDATES[:2]


def test_stream_midstream_failure_does_not_switch_models():
    def broken_stream():
        yield b'data: {"choices":[{"delta":{"content":"partial"}}]}'
        raise ConnectionError("connection reset")

    response = fake_stream_response(broken_stream())

    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post", return_value=response
        ) as mock_post:
            stream = llm_service.stream_repository_answer("prompt")
            assert next(stream) == "partial"
            with pytest.raises(ConnectionError):
                next(stream)

    # Never stitch a second model onto a half-emitted answer.
    assert mock_post.call_count == 1


# ==========================================================
# Streaming fallback chain
# ==========================================================

def test_stream_falls_back_to_gemini_when_nvidia_fails():
    FakeGeminiStreamModel.behaviors = [
        [chunk("from "), chunk("gemini fallback")],
    ]
    FakeGeminiStreamModel.seen = []

    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post",
            return_value=fake_stream_response([], status=503, body="unavailable"),
        ):
            with patch.object(
                llm_service.genai, "GenerativeModel", FakeGeminiStreamModel
            ):
                tokens = list(llm_service.stream_repository_answer("prompt"))

    assert tokens == ["from ", "gemini fallback"]
    assert FakeGeminiStreamModel.seen == [
        llm_service.GEMINI_MODEL_CANDIDATES[0]
    ]


def test_stream_no_nvidia_key_goes_straight_to_gemini():
    FakeGeminiStreamModel.behaviors = [
        [chunk("gemini directly")],
    ]
    FakeGeminiStreamModel.seen = []

    with patch.object(llm_service.settings, "NVIDIA_API_KEY", ""):
        with patch.object(
            llm_service.requests, "post"
        ) as mock_post:
            with patch.object(
                llm_service.genai, "GenerativeModel", FakeGeminiStreamModel
            ):
                tokens = list(llm_service.stream_repository_answer("prompt"))

    assert tokens == ["gemini directly"]
    mock_post.assert_not_called()


def test_stream_gemini_chain_rotates_on_error():
    FakeGeminiStreamModel.behaviors = [
        Exception("429 You exceeded your current quota"),
        [chunk("answer from second model")],
    ]
    FakeGeminiStreamModel.seen = []

    with patch.object(
        llm_service.genai, "GenerativeModel", FakeGeminiStreamModel
    ):
        tokens = list(llm_service._stream_gemini_answer("prompt"))

    assert tokens == ["answer from second model"]
    assert FakeGeminiStreamModel.seen == llm_service.GEMINI_MODEL_CANDIDATES[:2]


# ==========================================================
# Total failure path
# ==========================================================

def test_stream_raises_when_all_providers_fail():
    FakeGeminiStreamModel.behaviors = [
        Exception("gemini down")
        for _ in llm_service.GEMINI_MODEL_CANDIDATES
    ]
    FakeGeminiStreamModel.seen = []

    with patch.object(llm_service.settings, "NVIDIA_API_KEY", "nvapi-test"):
        with patch.object(
            llm_service.requests, "post",
            return_value=fake_stream_response([], status=429, body="quota"),
        ):
            with patch.object(
                llm_service.genai, "GenerativeModel", FakeGeminiStreamModel
            ):
                with pytest.raises(RuntimeError) as excinfo:
                    list(llm_service.stream_repository_answer("prompt"))

    assert "All LLM providers failed" in str(excinfo.value)
    assert "NVIDIA" in str(excinfo.value)
    assert "Gemini" in str(excinfo.value)
