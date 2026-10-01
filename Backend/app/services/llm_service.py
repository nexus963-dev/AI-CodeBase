"""
LLM answer generation for the RAG pipeline.

Provider order:
1. NVIDIA NIM (build.nvidia.com) - free trial tier, ~40 requests/min
2. Gemini free tier - fallback chain across several models

Each provider rotates through its own model list on failures
(429 quota / 503 load / empty response), so a single model's
rate limit never surfaces as a chat error.

Two entry points share the same chain:
- generate_repository_answer(): waits for the full answer
- stream_repository_answer(): yields tokens as they arrive
"""
import json
from typing import Iterator

import google.generativeai as genai
import requests

from app.config.settings import settings

genai.configure(api_key=settings.GEMINI_API_KEY)


# ==========================================================
# Provider 1: NVIDIA NIM
# ==========================================================

NVIDIA_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Verified against the live catalog on this key (tiny prompt timings):
#   nvidia/nemotron-3-super-120b       ~0.4s (2026-09-25; promoted to front
#                                      after gpt-oss/glm/gemma deployments
#                                      hung with no response headers)
#   openai/gpt-oss-20b                ~1.3s (healthy), hangs on bad days
#   z-ai/glm-5.3-flash                ~4.5s (healthy), hangs on bad days
#   google/gemma-4-31b-it             ~5.0s (healthy), hangs on bad days
NVIDIA_MODEL_CANDIDATES = [
    "nvidia/nemotron-3-super-120b-a12b",
    "openai/gpt-oss-20b",
    "z-ai/glm-5.3-flash",
    "google/gemma-4-31b-it",
]

NVIDIA_TIMEOUT_SECONDS = 60
NVIDIA_MAX_TOKENS = 2048

# Streaming fails over fast: a model deployment that hangs must
# not stall the visible answer stream for a full minute.
# Observed during an NVIDIA incident: gpt-oss-20b stopped sending
# response headers entirely while other models still answered.
# (connect timeout, read timeout) in seconds.
NVIDIA_STREAM_TIMEOUT = (10, 15)


def _generate_nvidia_answer(prompt: str) -> str:
    """Ask NVIDIA NIM (OpenAI-compatible endpoint) for an answer."""

    api_key = settings.NVIDIA_API_KEY

    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    failures = []

    for model_name in NVIDIA_MODEL_CANDIDATES:

        try:

            response = requests.post(
                NVIDIA_CHAT_URL,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": NVIDIA_MAX_TOKENS,
                },
                timeout=NVIDIA_TIMEOUT_SECONDS,
            )

            if response.status_code != 200:
                failures.append(
                    f"{model_name}: HTTP {response.status_code} "
                    f"{response.text[:120]}"
                )
                continue

            text = (
                response.json()
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            if text and text.strip():
                return text

            failures.append(f"{model_name}: empty response")

        except Exception as exc:
            failures.append(f"{model_name}: {exc}")
            continue

    raise RuntimeError(" | ".join(failures))


# ==========================================================
# Provider 2: Gemini (fallback)
# ==========================================================
#
# Measured on this API key (tiny prompt):
#   gemini-3-flash-preview   ~2s   (quota: 5 req/min)
#   gemini-3.7-flash         ~4s   (503 when under demand)
#   gemini-3.8-flash         ~6s   (503 when under demand)
#   gemini-3.1-flash-lite    ~1-2s (503 when under demand)
#   gemini-flash-latest      fast  (503 when under demand)
#   gemini-3.5-flash-lite    ~35s  (slow but usually works)
#   gemini-3.6-flash         ~34s  (slow but usually works)
GEMINI_MODEL_CANDIDATES = [
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
]


def _generate_gemini_answer(prompt: str) -> str:
    """Ask Gemini, rotating through the fallback model chain."""

    failures = []

    for model_name in GEMINI_MODEL_CANDIDATES:

        try:

            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = response.text

            if text and text.strip():
                return text

            failures.append(f"{model_name}: empty response")

        except Exception as exc:
            failures.append(f"{model_name}: {exc}")
            continue

    raise RuntimeError(" | ".join(failures))


# ==========================================================
# Entry point used by the orchestrator
# ==========================================================

def generate_repository_answer(prompt: str) -> str:
    """
    Returns a repository answer from the first provider that works.
    NVIDIA first (40 RPM free), Gemini chain as backup.
    """

    failures = []

    # ---- Provider 1: NVIDIA -----------------------------
    if settings.NVIDIA_API_KEY:
        try:
            return _generate_nvidia_answer(prompt)
        except Exception as exc:
            failures.append(f"NVIDIA -> {exc}")

    # ---- Provider 2: Gemini -----------------------------
    try:
        return _generate_gemini_answer(prompt)
    except Exception as exc:
        failures.append(f"Gemini -> {exc}")

    raise RuntimeError(
        "All LLM providers failed. "
        + " || ".join(failures)
    )


# ==========================================================
# Streaming variants (same provider chain, token by token)
# ==========================================================
#
# A provider may only be abandoned BEFORE the first token is
# yielded. Once tokens have been emitted we never switch
# models mid-answer, because stitching two models' output
# together would produce a garbled response.

def _stream_nvidia_answer(prompt: str) -> Iterator[str]:
    """Stream an answer from NVIDIA NIM (OpenAI-compatible SSE)."""

    api_key = settings.NVIDIA_API_KEY

    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    failures = []

    for model_name in NVIDIA_MODEL_CANDIDATES:

        yielded = False

        try:

            response = requests.post(
                NVIDIA_CHAT_URL,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": NVIDIA_MAX_TOKENS,
                    "stream": True,
                },
                stream=True,
                timeout=NVIDIA_STREAM_TIMEOUT,
            )

            if response.status_code != 200:
                failures.append(
                    f"{model_name}: HTTP {response.status_code} "
                    f"{response.text[:120]}"
                )
                continue

            for line in response.iter_lines():

                if not line:
                    continue

                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="ignore")

                if not line.startswith("data:"):
                    continue

                data = line[len("data:"):].strip()

                if data == "[DONE]":
                    break

                try:
                    payload = json.loads(data)
                except ValueError:
                    continue

                choices = payload.get("choices") or [{}]
                token = choices[0].get("delta", {}).get("content")

                if token:
                    yielded = True
                    yield token

            if yielded:
                return

            failures.append(f"{model_name}: empty stream")

        except Exception as exc:

            if yielded:
                # Tokens already reached the client - propagate.
                raise

            failures.append(f"{model_name}: {exc}")
            continue

    raise RuntimeError(" | ".join(failures))


def _stream_gemini_answer(prompt: str) -> Iterator[str]:
    """Stream an answer from Gemini, rotating through the fallback chain."""

    failures = []

    for model_name in GEMINI_MODEL_CANDIDATES:

        yielded = False

        try:

            model = genai.GenerativeModel(model_name)
            stream = model.generate_content(prompt, stream=True)

            for chunk in stream:
                token = chunk.text

                if token:
                    yielded = True
                    yield token

            if yielded:
                return

            failures.append(f"{model_name}: empty stream")

        except Exception as exc:

            if yielded:
                raise

            failures.append(f"{model_name}: {exc}")
            continue

    raise RuntimeError(" | ".join(failures))


def stream_repository_answer(prompt: str) -> Iterator[str]:
    """
    Yield an answer token by token as soon as it is generated.
    NVIDIA first (40 RPM free), Gemini chain as backup.
    """

    failures = []

    # ---- Provider 1: NVIDIA -----------------------------
    if settings.NVIDIA_API_KEY:

        yielded = False

        try:
            for token in _stream_nvidia_answer(prompt):
                yielded = True
                yield token

            if yielded:
                return

            failures.append("NVIDIA -> empty stream")

        except Exception as exc:

            if yielded:
                raise

            failures.append(f"NVIDIA -> {exc}")

    # ---- Provider 2: Gemini -----------------------------
    yielded = False

    try:
        for token in _stream_gemini_answer(prompt):
            yielded = True
            yield token

        if yielded:
            return

        failures.append("Gemini -> empty stream")

    except Exception as exc:

        if yielded:
            raise

        failures.append(f"Gemini -> {exc}")

    raise RuntimeError(
        "All LLM providers failed. "
        + " || ".join(failures)
    )
