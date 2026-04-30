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


_OLLAMA_FIX_INSTALLED = False


def _install_ollama_response_fix():
    """Monkey-patch DSPy\'s LLM forward to handle Ollama Cloud\'s thinking wrapper.

    Ollama Cloud wraps all model responses with a thinking layer.
    The actual response text ends up in \'reasoning_content\' while \'content\' is left empty.
    DSPy reads choices[0].message.content, so it sees nothing.
    This installs a wrapper that promotes reasoning_content to content when content is empty.
    """
    global _OLLAMA_FIX_INSTALLED
    if _OLLAMA_FIX_INSTALLED:
        return

    import dspy.clients.lm as lm_module

    _original_forward = lm_module.LM.forward

    def _patched_forward(self, *args, **kwargs):
        results = _original_forward(self, *args, **kwargs)
        try:
            if hasattr(results, "choices"):
                needs_fix = False
                for choice in results.choices:
                    msg = getattr(choice, "message", None)
                    if msg:
                        content = getattr(msg, "content", None) or ""
                        reasoning = getattr(msg, "reasoning_content", None) or ""
                        if not content.strip() and reasoning.strip():
                            msg.content = reasoning
                            needs_fix = True
                        elif not content.strip():
                            psf = getattr(msg, "provider_specific_fields", None) or {}
                            reasoning = psf.get("reasoning_content", "") or ""
                            if reasoning.strip():
                                msg.content = reasoning
                                needs_fix = True
                if needs_fix:
                    import logging
                    logging.getLogger("ollama_fix").debug(
                        "Ollama Cloud response fix applied"
                    )
        except Exception:
            pass
        return results

    lm_module.LM.forward = _patched_forward
    _OLLAMA_FIX_INSTALLED = True


def get_nous_credentials() -> Optional[dict]:
    """Read Nous Portal agent_key and inference base URL from auth.json."""
    auth_path = Path.home() / ".hermes" / "auth.json"
    if not auth_path.exists():
        return None

    try:
        data = json.loads(auth_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    nous = data.get("providers", {}).get("nous", {})
    agent_key = nous.get("agent_key", "")
    if isinstance(agent_key, str) and agent_key.strip():
        inference_base = nous.get(
            "inference_base_url",
            "https://inference-api.nousresearch.com/v1",
        )
        return {
            "api_key": agent_key.strip(),
            "base_url": inference_base.rstrip("/"),
        }

    for pool_key in ("minimax", "custom:minimax"):
        pool = data.get("credential_pool", {}).get(pool_key, [])
        for entry in pool:
            key = entry.get("access_token", "")
            if isinstance(key, str) and key.strip() and key != "***":
                base = entry.get(
                    "base_url", "https://api.minimax.io/anthropic"
                ).rstrip("/")
                return {"api_key": key.strip(), "base_url": base}
        for entry in pool:
            if entry.get("access_token") == "***":
                base = entry.get(
                    "base_url", "https://api.minimax.io/anthropic"
                ).rstrip("/")
                return {"api_key": "***", "base_url": base}

    return None


def _get_lm_kwargs(model: str) -> Tuple[dict, str]:
    """Build DSPy LM kwargs with correct provider routing based on model name.

    Routes models to their correct provider instead of using a single global
    priority. This allows mixing providers -- e.g. deepseek-v4-pro through
    Ollama Cloud as optimizer while minimax/m2.7 through MiniMax as eval.

    Provider detection:
    1. \'minimax/\' prefix -> MiniMax API
    2. \'deepseek-\' prefix -> Ollama Cloud (with thinking fix)
    3. \'openai/\' or \'openrouter/\' prefix -> OpenRouter
    4. Fallback: backward-compatible env-based priority chain
    """
    model_lower = model.lower()
    base_url = None
    api_key = None

    # 1. MiniMax models → MiniMax API directly
    if model_lower.startswith("minimax/"):
        api_key = os.getenv("MINIMAX_API_KEY")
        if api_key and api_key != "***" and api_key.strip():
            base_url = os.getenv(
                "MINIMAX_BASE_URL", "https://api.minimax.io/anthropic/v1"
            )
            # Ensure /v1 suffix for the API endpoint
            if not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

    # 2. DeepSeek models -> Ollama Cloud (with thinking fix)
    elif model_lower.startswith("deepseek-"):
        api_key = os.getenv("OLLAMA_API_KEY")
        if api_key and api_key != "***" and api_key.strip():
            base_url = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")
            _install_ollama_response_fix()

    # 3. OpenAI/OpenRouter models
    elif model_lower.startswith("openai/") or model_lower.startswith("openrouter/"):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if api_key and api_key != "***" and api_key.strip():
            base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # 4. Fallback: backward-compatible priority chain
    if not base_url or not api_key:
        chain_base = os.getenv("OPENROUTER_BASE_URL")
        chain_key = os.getenv("OPENROUTER_API_KEY")

        if not chain_base:
            ollama_key = os.getenv("OLLAMA_API_KEY")
            if ollama_key and ollama_key != "***" and ollama_key.strip():
                chain_base = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")
                chain_key = ollama_key
                _install_ollama_response_fix()
            elif not chain_base:
                minimax_key = os.getenv("MINIMAX_API_KEY")
                if minimax_key and minimax_key != "***":
                    chain_base = os.getenv(
                        "MINIMAX_BASE_URL", "https://api.minimax.io/anthropic/v1"
                    )
                    chain_key = minimax_key
                else:
                    nous = get_nous_credentials()
                    if nous:
                        chain_base = nous["base_url"]
                        chain_key = nous["api_key"]

        base_url = chain_base
        api_key = chain_key

    if not base_url or not api_key or api_key == "***":
        return {}, model

    os.environ["OPENAI_API_KEY"] = api_key

    # Stripping provider prefix for litellm routing
    bare_model = model
    if "/" in model and not model.startswith("minimax/"):
        bare_model = model.split("/", 1)[-1]

    kwargs = {
        "api_base": base_url,
        "api_key": api_key,  # Pass explicitly so dspy.LM doesn't rely on env var
        "custom_llm_provider": "openai",
    }
    return kwargs, bare_model
