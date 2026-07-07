"""
Lucid Lineage — LLM Factory.

Single source of truth for the chat model used by BOTH entry points (Streamlit UI
in app.py and the CLI terminal in main.py). Supports two interchangeable
providers — Google Gemini and OpenAI — selected via a single toggle so you can
switch backends (e.g. when one provider is rate-limiting with 503s) without
touching the rest of the codebase.

╔══════════════════════════════════════════════════════════════════════════╗
║  THE SWITCH                                                               ║
║  Set the provider in ONE of two places (the .env value wins):            ║
║    1. `.env`  ->  LLM_PROVIDER=google   or   LLM_PROVIDER=openai          ║
║    2. `DEFAULT_PROVIDER` constant just below (used when .env is unset)    ║
╚══════════════════════════════════════════════════════════════════════════╝

Both defaults are deliberately frugal, non-frontier, tool-calling-capable models.
"""

import os
import logging

from dotenv import load_dotenv

load_dotenv()  # ensure .env is loaded even if this module is imported first

log = logging.getLogger("lucid_lineage.llm")

# ── PROVIDER TOGGLE ────────────────────────────────────────────────────────
# In-code default; overridden by LLM_PROVIDER in .env when present.
DEFAULT_PROVIDER = "google"          # <-- flip to "openai" here, or set it in .env

# Frugal, non-frontier models per provider (override via .env if desired).
GOOGLE_MODEL = "gemini-3.5-flash"
OPENAI_MODEL = "gpt-4o-mini"         # cost-efficient, supports tool calling


def active_provider() -> str:
    """Resolve the active provider — .env LLM_PROVIDER overrides DEFAULT_PROVIDER."""
    return os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()


def _get_key(name: str) -> str | None:
    """Return an API key from the environment, treating blanks and unfilled
    ``<placeholder>`` values as missing so callers degrade to mock mode cleanly."""
    value = os.getenv(name, "").strip()
    if not value or value.startswith("<"):
        return None
    return value


def build_llm(provider: str | None = None,
              temperature: float = 0.0,
              max_retries: int = 3,
              timeout: float = 120.0):
    """Construct the active chat model, or return ``None`` if its API key is missing.

    Returning ``None`` (instead of raising) lets callers degrade gracefully: the
    agent pipeline falls back to mock mode and the UI shows a friendly error.
    ``max_retries`` and ``timeout`` add resilience against transient upstream
    failures (e.g. "503 UNAVAILABLE / high demand").

    The provider's SDK is imported lazily so only the chosen backend needs to be
    installed.
    """
    provider = (provider or active_provider())

    if provider == "openai":
        api_key = _get_key("OPENAI_API_KEY")
        if not api_key:
            log.warning("OPENAI_API_KEY is not set; live LLM unavailable (mock mode).")
            return None
        from langchain_openai import ChatOpenAI
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
        log.info("LLM provider=openai model=%s", model)
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout,
        )

    if provider != "google":
        log.warning("Unknown LLM_PROVIDER '%s'; falling back to 'google'.", provider)

    api_key = _get_key("GOOGLE_API_KEY")
    if not api_key:
        log.warning("GOOGLE_API_KEY is not set; live LLM unavailable (mock mode).")
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI
    model = os.getenv("GOOGLE_MODEL", GOOGLE_MODEL)
    log.info("LLM provider=google model=%s", model)
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        max_retries=max_retries,
        timeout=timeout,
    )
