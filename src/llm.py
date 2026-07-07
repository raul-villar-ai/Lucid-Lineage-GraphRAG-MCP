"""
Lucid Lineage — LLM Factory.

Single source of truth for the Google Gemini chat model used by BOTH entry
points (Streamlit UI in app.py and the CLI terminal in main.py). Centralizing
the model id and generation parameters here prevents configuration drift between
the two front-ends and keeps the model name out of the presentation layer.

The default model (`gemini-3.5-flash`) was verified as available for the
configured API key via `check_models.py`.
"""

import os
import logging

from langchain_google_genai import ChatGoogleGenerativeAI

log = logging.getLogger("lucid_lineage.llm")

# Canonical model for the compliance agent — deterministic (temperature 0) so
# audit reasoning is reproducible.
DEFAULT_MODEL = "gemini-3.5-flash"


def build_llm(api_key: str | None = None,
              model: str = DEFAULT_MODEL,
              temperature: float = 0.0,
              max_retries: int = 3,
              timeout: float = 120.0):
    """Construct the Gemini chat model, or return ``None`` if no key is configured.

    Reads ``GOOGLE_API_KEY`` from the environment when ``api_key`` is not passed.
    Returning ``None`` (instead of raising) lets callers degrade gracefully: the
    agent pipeline falls back to mock mode and the UI can surface a friendly error
    rather than crashing the process.

    ``max_retries`` and ``timeout`` add resilience against transient upstream
    failures (e.g. "Server disconnected without sending a response") that can
    otherwise abort a long tool-calling turn.
    """
    api_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        log.warning("GOOGLE_API_KEY is not set; live LLM unavailable (mock mode).")
        return None

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        max_retries=max_retries,
        timeout=timeout,
    )
