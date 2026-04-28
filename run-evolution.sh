#!/usr/bin/env bash
# =============================================================================
# run-evolution.sh — Hermes Agent skill evolution with provider selection
# =============================================================================
# Usage:
#   PROVIDER=openrouter ./run-evolution.sh --skill ceo-orchestration --iterations 10
#   PROVIDER=nous    ./run-evolution.sh --skill systematic-debugging --eval-source sessiondb
#   PROVIDER=minimax ./run-evolution.sh --skill ceo-orchestration --eval-source sessiondb --iterations 10
#
# Provider selection (set PROVIDER env var):
#   openrouter  — OpenRouter API (default). Requires OPENROUTER_API_KEY.
#   nous        — Nous Research portal. Requires ~/.hermes/auth.json with agent_key.
#   minimax     — MiniMax coding plan. Requires MINIMAX_API_KEY in ~/.hermes/.env.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load secrets ──────────────────────────────────────────────────────────────
# Priority: (1) user's ~/.hermes/.env, (2) local .env in the repo
if [[ -f "$HOME/.hermes/.env" ]]; then
    set -a
    source "$HOME/.hermes/.env"
    set +a
fi

if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# ── Provider configuration ───────────────────────────────────────────────────
PROVIDER="${PROVIDER:-openrouter}"

# Load the virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

# Determine the Python module path prefix based on provider.
# nous_auth.py handles credential resolution for both 'nous' and 'openrouter'.
# PROVIDER=openrouter falls back to OPENROUTER_API_KEY env var.
# PROVIDER=nous reads agent_key from ~/.hermes/auth.json via nous_auth.py.
OPTIMIZER_MODEL="${OPTIMIZER_MODEL:-}"
EVAL_MODEL="${EVAL_MODEL:-}"
STATS_CSV="${STATS_CSV:-}"

if [[ "$PROVIDER" == "nous" ]]; then
    # ── Nous Research Portal ──────────────────────────────────────────────────
    # Auth: OAuth login via `hermes login --provider nous` stores agent_key
    #       in ~/.hermes/auth.json under providers.nous.agent_key.
    #       This is DIFFERENT from the OAuth token (which is for CLI auth only).
    #
    # Routing: nous_auth.py sets custom_llm_provider='openai' and uses the
    #          inference-api.nousresearch.com endpoint. Model names must be
    #          BARE (e.g. "anthropic/claude-sonnet-4.6") — do NOT prefix with
    #          "openrouter/" because litellm's OpenAI provider auto-prepends it.
    #
    # Cost:   Kimi K2.6 is FREE on the Nous portal.
    #
    # Setup:  hermes login --provider nous
    #         (ensures ~/.hermes/auth.json has the agent_key)
    # ─────────────────────────────────────────────────────────────────────────
    OPTIMIZER_MODEL="${OPTIMIZER_MODEL:-anthropic/claude-sonnet-4.6}"
    EVAL_MODEL="${EVAL_MODEL:-moonshotai/kimi-k2.6}"
    JUDGE_MODEL="${JUDGE_MODEL:-moonshotai/kimi-k2.6}"

    echo "🧬 Provider: Nous Research Portal"
    echo "   Auth:     ~/.hermes/auth.json → providers.nous.agent_key"
    echo "   Endpoint: https://inference-api.nousresearch.com/v1"
    echo "   Optimizer: $OPTIMIZER_MODEL"
    echo "   Evaluator: $EVAL_MODEL (FREE on Nous portal)"

elif [[ "$PROVIDER" == "minimax" ]]; then
    # ── MiniMax Coding Plan ───────────────────────────────────────────────────
    # Auth:   MINIMAX_API_KEY env var (format: sk-cp-...). Set in ~/.hermes/.env
    # Endpoint: https://api.minimax.io/anthropic/v1  (OpenAI-compatible)
    # Routing:  litellm native MiniMax integration — use "minimax/minimax-m2.7".
    #            Do NOT use custom_llm_provider='anthropic' — MiniMax doesn't
    #            accept bare Anthropic API keys.
    # Cost:   Coding plan discounted tokens.
    #
    # Setup:  Add to ~/.hermes/.env:
    #           MINIMAX_API_KEY=sk-cp-your-key-here
    #           MINIMAX_BASE_URL=https://api.minimax.io/anthropic/v1
    # ─────────────────────────────────────────────────────────────────────────
    OPTIMIZER_MODEL="${OPTIMIZER_MODEL:-minimax/minimax-m2.7}"
    EVAL_MODEL="${EVAL_MODEL:-minimax/minimax-m2.7}"
    JUDGE_MODEL="${JUDGE_MODEL:-minimax/minimax-m2.7}"

    if [[ -z "${MINIMAX_API_KEY:-}" ]]; then
        echo "ERROR: MINIMAX_API_KEY is not set."
        echo "       Add to ~/.hermes/.env:"
        echo "         MINIMAX_API_KEY=sk-cp-your-key-here"
        echo "         MINIMAX_BASE_URL=https://api.minimax.io/anthropic/v1"
        exit 1
    fi

    echo "🧬 Provider: MiniMax (coding plan)"
    echo "   Model:    $OPTIMIZER_MODEL"
    echo "   Auth:     MINIMAX_API_KEY (sk-cp-...)"

elif [[ "$PROVIDER" == "openrouter" ]]; then
    # ── OpenRouter (default) ─────────────────────────────────────────────────
    # Auth:   OPENROUTER_API_KEY env var. Set in ~/.hermes/.env or repo .env
    # Routing: litellm standard OpenRouter routing — "provider/model" format.
    #          e.g. "anthropic/claude-sonnet-4.6" → openrouter/anthropic/claude-sonnet-4.6
    # ─────────────────────────────────────────────────────────────────────────
    OPTIMIZER_MODEL="${OPTIMIZER_MODEL:-anthropic/claude-sonnet-4.6}"
    EVAL_MODEL="${EVAL_MODEL:-google/gemini-3.1-flash-lite}"
    JUDGE_MODEL="${JUDGE_MODEL:-anthropic/claude-sonnet-4.6}"

    if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
        echo "ERROR: OPENROUTER_API_KEY is not set."
        echo "       Add to ~/.hermes/.env:"
        echo "         OPENROUTER_API_KEY=sk-or-..."
        exit 1
    fi

    echo "🧬 Provider: OpenRouter"
    echo "   Optimizer: $OPTIMIZER_MODEL"
    echo "   Evaluator: $EVAL_MODEL"

else
    echo "ERROR: Unknown PROVIDER='$PROVIDER'"
    echo "       Valid: openrouter, nous, minimax"
    exit 1
fi

# ── Build command ────────────────────────────────────────────────────────────
CMD=(python -m evolution.skills.evolve_skill
    --optimizer-model "$OPTIMIZER_MODEL"
    --eval-model "$EVAL_MODEL"
)

if [[ -n "${STATS_CSV:-}" ]]; then
    CMD+=(--stats-csv "$STATS_CSV")
fi

# Pass through all remaining arguments
CMD+=("$@")

echo ""
exec "${CMD[@]}"
