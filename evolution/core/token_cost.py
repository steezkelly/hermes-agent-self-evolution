"""Token cost estimation for GEPA Observatory.

Provides token counting (tiktoken-backed) and per-model pricing lookup
for USD cost estimates. Used by fitness.py to populate
judge_audit_log.token_cost_estimate.
"""

from typing import Optional, Tuple


# ── Model pricing: ($/1M input tokens, $/1M output tokens)
#    Keys are lowercased model name substrings — first match wins.
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULT_PRICING: dict[str, Tuple[float, float]] = {
    # MiniMax through Nous Portal (approximate — MiniMax M2.7 is very cheap)
    "minimax-m2.7":          (0.14, 0.14),
    "minimax-m2":            (0.14, 0.14),
    "minimax":               (0.50, 0.50),

    # Qwen models
    "qwen3-max":             (1.60, 6.40),
    "qwen3-8b":              (0.40, 1.20),
    "qwen3":                 (0.80, 2.40),

    # DeepSeek
    "deepseek-v4":           (1.20, 4.80),
    "deepseek-v3":           (0.50, 2.00),
    "deepseek":              (0.50, 2.00),

    # Anthropic
    "claude-sonnet-4":       (3.00, 15.00),
    "claude-sonnet":         (3.00, 15.00),
    "claude":                (3.00, 15.00),

    # OpenAI / reasoning
    "gpt-5":                 (5.00, 20.00),
    "gpt-4o":                (2.50, 10.00),
    "gpt-4":                 (3.00, 15.00),

    # Xiaomi
    "mimo-v2.5":             (0.80, 3.20),
    "mimo":                  (0.80, 3.20),

    # xAI
    "grok-4":                (2.00, 10.00),
    "grok":                  (2.00, 10.00),

    # Generic / unknown through Nous Portal (conservative default)
    "default":               (1.00, 4.00),
}


def _get_pricing(model_name: str) -> Tuple[float, float]:
    """Look up (input $/1M, output $/1M) for a model string."""
    lowered = model_name.lower()
    for key in _DEFAULT_PRICING:
        if key == "default":
            continue
        if key in lowered:
            return _DEFAULT_PRICING[key]
    return _DEFAULT_PRICING["default"]


def _count_tokens_tiktoken(text: str) -> int:
    """Count tokens using tiktoken cl100k_base (approximates most models)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return 0


def _count_tokens_approx(text: str) -> int:
    """Fallback token estimator: ~0.75 tokens per word + 0.25 per char for punctuation."""
    words = len(text.split())
    chars = len(text)
    return int(words * 0.75 + chars * 0.25)


def count_tokens(text: str) -> int:
    """Best-effort token count for a string."""
    n = _count_tokens_tiktoken(text)
    if n > 0:
        return n
    return _count_tokens_approx(text)


def estimate_cost(
    prompt_text: str,
    completion_text: str,
    model_name: str,
) -> Optional[float]:
    """Estimate USD cost of an LLM call given prompt + completion text.

    Returns a float in dollars (e.g. 0.003 = 0.3¢) or None if the model
    is unknown and no pricing default is configured.
    """
    if not model_name or not prompt_text:
        return 0.0

    input_rate, output_rate = _get_pricing(model_name)

    input_tokens = count_tokens(prompt_text)
    output_tokens = count_tokens(completion_text)

    # rates are per 1M tokens
    input_cost = input_tokens * (input_rate / 1_000_000)
    output_cost = output_tokens * (output_rate / 1_000_000)

    return input_cost + output_cost


def estimate_judge_call_cost(
    task_input: str,
    expected_behavior: str,
    agent_output: str,
    skill_text: str,
    model_name: str,
    feedback_text: Optional[str] = None,
) -> Optional[float]:
    """Estimate cost for a single LLMJudge.score() call.

    Builds the approximate prompt that DSPy/ChainOfThought sends, then
    estimates the completion based on the scores + feedback returned.
    """
    # Approximate judge prompt — mirrors LLMJudge.JudgeSignature fields
    prompt_parts = [
        "Evaluate an agent's response against an expected behavior rubric.",
        "Score the response on three dimensions (0.0 to 1.0 each):",
        "1. correctness: Did the response correctly address the task?",
        "2. procedure_following: Did it follow the expected approach/procedure?",
        "3. conciseness: Was it appropriately concise without omitting important info?",
        "Also provide specific, actionable feedback on what could be improved.",
        "\n---\n",
        f"Task input: {task_input}",
        f"Expected behavior: {expected_behavior}",
        f"Agent output: {agent_output}",
        f"Skill text: {skill_text}",
    ]
    prompt_text = "\n".join(prompt_parts)

    # Approximate completion — scores + feedback
    fb = feedback_text or ""
    completion_text = (
        f"correctness: ~0.5\n"
        f"procedure_following: ~0.5\n"
        f"conciseness: ~0.5\n"
        f"feedback: {fb[:200]}"
    )

    return estimate_cost(prompt_text, completion_text, model_name)
