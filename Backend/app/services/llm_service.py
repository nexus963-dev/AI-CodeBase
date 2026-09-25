"""
LLM answer generation for the RAG pipeline.

Provider order:
1. NVIDIA NIM (build.nvidia.com) - free trial tier, ~40 requests/min
2. Gemini free tier - fallback chain across several models

Each provider rotates through its own model list on failures
(429 quota / 503 load / empty response), so a single model's
rate limit never surfaces as a chat error.
"""
import google.generativeai as genai
import requests

from app.config.settings import settings

genai.configure(api_key=settings.GEMINI_API_KEY)


# ==========================================================
# Provider 1: NVIDIA NIM
# ==========================================================

NVIDIA_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Verified against the live catalog on this key (tiny prompt timings):
#   openai/gpt-oss-20b                ~1.3s
#   nvidia/nemotron-3-super-120b       ~3.3s (503 occasionally -> next model)
#   z-ai/glm-5.3-flash                ~4.5s
#   google/gemma-4-31b-it             ~5.0s
NVIDIA_MODEL_CANDIDATES = [
    "openai/gpt-oss-20b",
    "nvidia/nemotron-3-super-120b-a12b",
    "z-ai/glm-5.3-flash",
    "google/gemma-4-31b-it",
]

NVIDIA_TIMEOUT_SECONDS = 60
NVIDIA_MAX_TOKENS = 2048


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
