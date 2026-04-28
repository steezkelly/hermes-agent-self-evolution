"""Read Nous Portal credentials from hermes-agent auth store.

This lets the evolution pipeline use Steve's existing Nous Portal login
(OAuth via `hermes login --provider nous`) instead of requiring a
separate API key in environment variables.

Usage:
    from evolution.core.nous_auth import get_nous_credentials
    creds = get_nous_credentials()
    # Returns {"api_key": "***", "base_url": "https://inference-api.nousresearch.com/v1"}
    # or None if not logged in.
"""

import json
import os
from pathlib import Path
from typing import Optional, Tuple


def get_nous_credentials() -> Optional[dict]:
    """Read Nous Portal agent_key and inference base URL from auth.json.

    Returns None if Steve hasn't run `hermes login --provider nous`.
    """
    auth_path = Path.home() / ".hermes" / "auth.json"
    if not auth_path.exists():
        return None

    try:
        data = json.loads(auth_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    nous = data.get("providers", {}).get("nous", {})
    agent_key = nous.get("agent_key", "")
    inference_base = nous.get(
        "inference_base_url",
        "https://inference-api.nousresearch.com/v1",
    )

    if not isinstance(agent_key, str) or not agent_key.strip():
        return None

    return {
        "api_key": agent_key.strip(),
        "base_url": inference_base.rstrip("/"),
    }


def _get_lm_kwargs(model: str) -> Tuple[dict, str]:
    """Build DSPy LM kwargs with correct provider routing.

    Returns (kwargs, model_to_use) tuple. The model name may be stripped
    of its provider prefix when using custom_llm_provider='openai' (to avoid
    the openrouter/ prefix being prepended by litellm's OpenAI client).

    Priority:
    1. OPENROUTER_BASE_URL env var (from run-evolution.sh Nous mode)
    2. Nous Portal OAuth agent_key from ~/.hermes/auth.json
    3. Empty kwargs, original model — let DSPy infer from model name

    For OpenAI-compatible endpoints (custom api_base), litellm needs
    custom_llm_provider='openai' to route correctly. However, this causes
    litellm to parse 'provider/model' and prepend 'openrouter/' to the
    model. Fix: strip the provider prefix so the bare model ID is used.
    """
    base_url = os.getenv("OPENROUTER_BASE_URL")
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not base_url:
        nous = get_nous_credentials()
        if nous:
            base_url = nous["base_url"]
            api_key = nous["api_key"]

    if not base_url or not api_key:
        # No custom endpoint — let DSPy handle it natively
        return {}, model

    # litellm's OpenAI client reads OPENAI_API_KEY from env
    os.environ["OPENAI_API_KEY"] = api_key

    # For Nous Inference API, the model ID MUST include the provider prefix
    # (e.g., 'xiaomi/mimo-v2.5', 'deepseek/deepseek-v4-pro').
    # litellm with custom_llm_provider='openai' passes the model as-is in the
    # API request body, so keep the full model ID.
    nous_model = model

    kwargs = {
        "api_base": base_url,
        "custom_llm_provider": "openai",
    }
    return kwargs, nous_model
