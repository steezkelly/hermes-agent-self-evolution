"""Fitness functions for evaluating evolved artifacts.

Uses LLM-as-judge with rubrics to score agent outputs.
Supports length penalties and multi-dimensional scoring.

v2 Fix: skill_fitness_metric now invokes an LLM with the skill body as
instructions + the task_input, producing a real agent response that gets
scored against expected_behavior. This replaces the broken V2 behavior
where the metric scored the raw 21KB skill body text (which naturally
has high keyword overlap, creating a flat signal GEPA cannot optimize).
"""

import dspy
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from evolution.core.config import EvolutionConfig
from evolution.core.nous_auth import _get_lm_kwargs


# ─────────────────────────────────────────────────────────────────────────────
# Inference wrapper — execute a skill body as agent instructions
# ─────────────────────────────────────────────────────────────────────────────

def _invoke_skill_as_agent(body_text: str, task_input: str) -> str:
    """Execute the skill body as agent instructions + task to get a generated response.

    Uses the globally configured LM. Timeout/retry is handled at the LM level
    (not via signal alarms, which break in threaded DSPy Evaluate contexts).
    """
    if not body_text.strip() or not task_input.strip():
        return body_text

    sig = dspy.Signature(
        "task_input: str -> response: str",
        instructions=body_text,
    )
    try:
        result = dspy.Predict(sig)(task_input=task_input)
        return result.response or ""
    except Exception:
        return "[metric-inference-failed]"


# ─────────────────────────────────────────────────────────────────────────────
# TF-IDF Semantic Similarity Scorer
# ─────────────────────────────────────────────────────────────────────────────

class TFIDFSimilarityScorer:
    """Fast TF-IDF cosine similarity for evaluation scoring.

    Computes semantic similarity between agent outputs and expected behaviors
    using TF-IDF vectors. Unlike keyword overlap, this captures:
    - Synonymy (debug vs diagnose)
    - Subphrase matching (partial credit for partial coverage)
    - Term frequency weighting (rare terms matter more)

    Caches the vectorizer and vocabulary after first fit to avoid
    recomputing on every scoring call.
    """

    def __init__(self):
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._expected_vectors: Optional[np.ndarray] = None
        self._expected_texts: list[str] = []
        self._fitted: bool = False

    def fit(self, expected_behaviors: list[str]) -> "TFIDFSimilarityScorer":
        """Fit the TF-IDF vectorizer on a corpus of expected behaviors.

        Call once per skill/dataset (not per evaluation).
        """
        # Filter out empty strings
        texts = [t for t in expected_behaviors if t.strip()]
        if not texts:
            self._fitted = False
            return self

        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),   # unigrams + bigrams for better semantics
            max_features=5000,
            sublinear_tf=True,    # use 1 + log(tf) to reduce length bias
        )
        self._expected_vectors = self._vectorizer.fit_transform(texts)
        self._expected_texts = texts
        self._fitted = True
        return self

    def score(self, agent_output: str, expected_behavior: str) -> float:
        """Score a single agent output against an expected behavior.

        Returns a float 0-1 where 1.0 = perfect TF-IDF cosine similarity.
        """
        if not self._fitted or not agent_output.strip():
            return 0.5  # Default to neutral

        output_vec = self._vectorizer.transform([agent_output])
        expected_vec = self._vectorizer.transform([expected_behavior])

        sim = cosine_similarity(output_vec, expected_vec)[0, 0]
        return float(np.clip(sim, 0.0, 1.0))

    def score_batch(
        self,
        agent_outputs: list[str],
        expected_behaviors: list[str],
    ) -> list[float]:
        """Score multiple agent outputs against expected behaviors.

        More efficient than calling score() in a loop when vectorizer
        is already fitted.
        """
        if not self._fitted:
            return [0.5] * len(agent_outputs)

        outputs = [o if o.strip() else " " for o in agent_outputs]
        output_vectors = self._vectorizer.transform(outputs)
        sims = cosine_similarity(output_vectors, self._expected_vectors)
        return [float(np.clip(s, 0.0, 1.0)) for s in sims.diagonal()]


# ─────────────────────────────────────────────────────────────────────────────
# Sentence Embedding Semantic Similarity Scorer
# ─────────────────────────────────────────────────────────────────────────────

class SentenceEmbeddingScorer:
    """Semantic similarity via sentence transformer embeddings.

    Pre-computes embeddings for all expected_behaviors using a local
    sentence transformer model (all-MiniLM-L6-v2). At scoring time,
    the agent output is embedded on-the-fly (~5ms) and compared via
    cosine similarity against the pre-computed expected behavior vector.

    Unlike TF-IDF, this captures semantic equivalence even when the
    LLM uses entirely different vocabulary than the expected behavior:
      "You can only have one provider active"  vs
      "MemoryManager rejects registration of a second external provider"
      → TF-IDF: 0.000     SentenceEmbedding: 0.648
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = None
        self._model_name = model_name
        self._expected_embeddings: dict[str, np.ndarray] = {}  # text → vector
        self._fitted: bool = False

    def fit(self, examples: list[dspy.Example]) -> "SentenceEmbeddingScorer":
        """Pre-compute embeddings for all expected_behavior texts.

        Call once per skill/dataset (not per evaluation).
        Lazy-loads the sentence transformer model on first call.
        """
        from sentence_transformers import SentenceTransformer

        texts = [
            getattr(ex, "expected_behavior", "") or ""
            for ex in examples
            if (getattr(ex, "expected_behavior", "") or "").strip()
        ]
        if not texts:
            self._fitted = False
            return self

        self._model = SentenceTransformer(self._model_name)
        vectors = self._model.encode(texts, show_progress_bar=False)
        self._expected_embeddings = dict(zip(texts, vectors))
        self._fitted = True
        return self

    def score(self, agent_output: str, expected_behavior: str) -> float:
        """Score an agent output against its expected behavior.

        Returns cosine similarity (0-1) between the two sentence embeddings.
        1.0 = semantically identical. 0.0 = completely unrelated topics.
        """
        if not self._fitted or not agent_output.strip():
            return 0.5  # Neutral default

        if expected_behavior not in self._expected_embeddings:
            return 0.5

        expected_vec = self._expected_embeddings[expected_behavior]
        # Encode on-the-fly — ~5ms per call via sentence_transformers
        output_vec = self._model.encode(agent_output, show_progress_bar=False)

        sim = float(np.dot(output_vec, expected_vec) /
                    (np.linalg.norm(output_vec) * np.linalg.norm(expected_vec)))
        return float(np.clip(sim, 0.0, 1.0))

    def score_batch(
        self,
        agent_outputs: list[str],
        expected_behaviors: list[str],
    ) -> list[float]:
        """Score multiple outputs in a batch.

        More efficient than calling score() in a loop when the model
        can batch-encode the agent outputs.
        """
        if not self._fitted:
            return [0.5] * len(agent_outputs)

        # Filter to only those with known expected behaviors
        valid_idxs = [
            i for i, eb in enumerate(expected_behaviors)
            if eb in self._expected_embeddings
        ]
        if not valid_idxs:
            return [0.5] * len(agent_outputs)

        valid_outputs = [agent_outputs[i] for i in valid_idxs]
        output_vectors = self._model.encode(valid_outputs, show_progress_bar=False)

        scores = [0.5] * len(agent_outputs)
        for idx, vec in zip(valid_idxs, output_vectors):
            expected_vec = self._expected_embeddings[expected_behaviors[idx]]
            sim = float(np.dot(vec, expected_vec) /
                        (np.linalg.norm(vec) * np.linalg.norm(expected_vec)))
            scores[idx] = float(np.clip(sim, 0.0, 1.0))
        return scores


# ─────────────────────────────────────────────────────────────────────────────
# Fitness Score Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FitnessScore:
    """Multi-dimensional fitness score."""
    correctness: float = 0.0  # Did the agent produce correct output? (0-1)
    procedure_following: float = 0.0  # Did it follow the skill's procedure? (0-1)
    conciseness: float = 0.0  # Was it appropriately concise? (0-1)
    length_penalty: float = 0.0  # Penalty for being too verbose (0-1, 0 = no penalty)
    feedback: str = ""  # Textual feedback for GEPA's reflective analysis

    @property
    def composite(self) -> float:
        """Weighted composite score."""
        raw = (
            0.5 * self.correctness
            + 0.3 * self.procedure_following
            + 0.2 * self.conciseness
        )
        return max(0.0, raw - self.length_penalty)


class LLMJudge:
    """LLM-as-judge scorer with rubric-based evaluation.

    Scores agent outputs on multiple dimensions and provides
    textual feedback that GEPA can use for reflective mutation.
    """

    class JudgeSignature(dspy.Signature):
        """Evaluate an agent's response against an expected behavior rubric.

        Score the response on three dimensions (0.0 to 1.0 each):
        1. correctness: Did the response correctly address the task?
        2. procedure_following: Did it follow the expected approach/procedure?
        3. conciseness: Was it appropriately concise without omitting important info?

        Also provide specific, actionable feedback on what could be improved.
        """
        task_input: str = dspy.InputField(desc="The task the agent was given")
        expected_behavior: str = dspy.InputField(desc="Rubric describing what a good response looks like")
        agent_output: str = dspy.InputField(desc="The agent's actual response")
        skill_text: str = dspy.InputField(desc="The skill/instructions the agent was following")
        correctness: float = dspy.OutputField(desc="Score 0.0-1.0: Did the response correctly address the task?")
        procedure_following: float = dspy.OutputField(desc="Score 0.0-1.0: Did it follow the expected procedure?")
        conciseness: float = dspy.OutputField(desc="Score 0.0-1.0: Appropriately concise?")
        feedback: str = dspy.OutputField(desc="Specific, actionable feedback on what could be improved")

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.judge = dspy.ChainOfThought(self.JudgeSignature)

    def score(
        self,
        task_input: str,
        expected_behavior: str,
        agent_output: str,
        skill_text: str,
        artifact_size: Optional[int] = None,
        max_size: Optional[int] = None,
    ) -> FitnessScore:
        """Score an agent output using LLM-as-judge."""
        # Build kwargs for the judge model
        kwargs, model_used = self._get_lm_kwargs(self.config.eval_model)
        lm = dspy.LM(model_used, **kwargs)

        with dspy.context(lm=lm):
            result = self.judge(
                task_input=task_input,
                expected_behavior=expected_behavior,
                agent_output=agent_output,
                skill_text=skill_text,
            )

        # Parse scores (clamp to 0-1)
        correctness = _parse_score(result.correctness)
        procedure_following = _parse_score(result.procedure_following)
        conciseness = _parse_score(result.conciseness)

        # Length penalty
        length_penalty = 0.0
        if artifact_size is not None and max_size is not None:
            ratio = artifact_size / max_size
            if ratio > 0.9:
                # Penalty ramps from 0 at 90% to 0.3 at 100%+
                length_penalty = min(0.3, (ratio - 0.9) * 3.0)

        return FitnessScore(
            correctness=correctness,
            procedure_following=procedure_following,
            conciseness=conciseness,
            length_penalty=length_penalty,
            feedback=str(result.feedback),
        )

    @staticmethod
    def _get_lm_kwargs(model: str) -> tuple:
        """Build DSPy LM kwargs with correct provider routing.

        Reimplements the provider detection logic from nous_auth.py
        since that file's function was corrupted.
        """
        import os
        model_lower = model.lower()
        base_url = None
        api_key = None

        # 1. MiniMax models → MiniMax API directly
        if model_lower.startswith("minimax/") or model_lower.startswith("minimax-"):
            api_key = os.getenv("MINIMAX_API_KEY")
            if api_key and api_key != "***" and api_key.strip():
                base_url = os.getenv(
                    "MINIMAX_BASE_URL", "https://api.minimax.io/anthropic/v1"
                )

        # 2. DeepSeek models → Ollama Cloud
        elif model_lower.startswith("deepseek-"):
            api_key = os.getenv("OLLAMA_API_KEY")
            if api_key and api_key != "***" and api_key.strip():
                base_url = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")

        # 3. OpenAI/OpenRouter models
        elif model_lower.startswith("openai/") or model_lower.startswith("openrouter/"):
            api_key = os.getenv("OPENROUTER_API_KEY")
            if api_key and api_key != "***" and api_key.strip():
                base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

        # 4. Fallback: backward-compatible priority chain
        if not base_url or not api_key:
            base_url = None
            api_key = None
            chain_base = os.getenv("OPENROUTER_BASE_URL")
            chain_key = os.getenv("OPENROUTER_API_KEY")

            if not chain_base:
                ollama_key = os.getenv("OLLAMA_API_KEY")
                if ollama_key and ollama_key != "***" and ollama_key.strip():
                    chain_base = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")
                    chain_key = ollama_key
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

        # Strip provider prefix for litellm routing — INCLUDING minimax
        bare_model = model
        if "/" in bare_model:
            bare_model = bare_model.split("/", 1)[-1]

        kwargs = {
            "api_base": base_url,
            "custom_llm_provider": "openai",
        }
        return kwargs, bare_model


def _generate_feedback(
    agent_output: str,
    expected: str,
    task: str,
    pred_name: str,
    raw_output: str,
) -> str:
    """Generate diagnostic feedback text for GEPA reflective mutation.

    Compares the agent's actual output against the expected behavior to
    produce actionable feedback about what went wrong and why.
    """
    if not agent_output.strip():
        return (
            f"The predictor '{pred_name}' produced an empty output for "
            f"task: '{task[:120]}'. Expected: '{expected[:200]}'. "
            "The skill instructions may need to guide the model to produce "
            "a substantive response even for short queries."
        )

    expected_lower = expected.lower()
    output_lower = agent_output.lower()
    expected_words = set(expected_lower.split())
    output_words = set(output_lower.split())

    # Check for missing key terms
    missing = expected_words - output_words
    present = expected_words & output_words

    parts = []
    if len(agent_output) < 50:
        parts.append("The response was very short and likely incomplete.")

    if len(missing) > 3 and len(present) / max(len(expected_words), 1) < 0.3:
        parts.append(
            "The response missed most of the expected content — it discussed "
            "different topics than what was asked."
        )
    elif len(missing) > len(present):
        parts.append(
            "The response covered some of the expected ground but omitted "
            f"key terms like: {', '.join(sorted(missing)[:8])}."
        )
    elif missing:
        parts.append(
            f"Good direction, but missed specific details like: "
            f"{', '.join(sorted(missing)[:6])}."
        )
    else:
        parts.append("Response matches the expected content well.")

    # Check output length relative to the skill body
    if len(raw_output) > 500 and raw_output.count("## ") >= 2:
        # This was a skill body that got invoked — the agent_output is the
        # LLM's response after reading the skill text as instructions
        if not any(w in output_lower for w in ["hermes", "command", "run", "config", "skill"]):
            parts.append(
                "The response lacked concrete Hermes CLI commands or references, "
                "suggesting the skill instructions didn't guide the model to produce "
                "specific, actionable outputs."
            )

    return " | ".join(parts) if parts else (
        f"Score reflects semantic similarity. Task: '{task[:100]}'."
    )


def skill_fitness_metric(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace=None,
    pred_name=None,
    pred_trace=None,
) -> dspy.Prediction | dict:
    """DSPy-compatible metric for skill optimization.

    Accepts the 5-argument GEPA form. For ordinary evaluation it returns a
    dspy.Prediction(score=..., feedback=...) so GEPA can consume reflective
    feedback. When GEPA asks for predictor-level feedback via pred_name, return
    the dict shape expected by DSPy.
    """
    raw_output = getattr(prediction, "output", "") or ""
    expected = getattr(example, "expected_behavior", "") or ""
    task = getattr(example, "task_input", "") or ""
    skill_text = (
        getattr(example, "skill_text", "")
        or getattr(example, "skill_instructions", "")
        or ""
    )

    if not raw_output.strip():
        result = _metric_prediction(0.0, "Agent output was empty, so no task requirements were satisfied.")
        return {"score": result.score, "feedback": result.feedback} if pred_name is not None else result

    is_skill_body = len(raw_output) > 1500 and raw_output.count("## ") >= 2
    if is_skill_body and task.strip():
        agent_output = _invoke_skill_as_agent(raw_output, task)
    else:
        agent_output = raw_output

    if not agent_output.strip():
        result = _metric_prediction(0.0, "Agent output was empty, so no task requirements were satisfied.")
        return {"score": result.score, "feedback": result.feedback} if pred_name is not None else result

    try:
        fitness = _score_with_llm_judge(
            task_input=task,
            expected_behavior=expected,
            agent_output=agent_output,
            skill_text=skill_text,
        )
        feedback = fitness.feedback or _default_feedback(fitness)
        result = _metric_prediction(fitness.composite, feedback)
    except Exception as e:
        score, fallback_feedback = _fallback_similarity_score(expected, agent_output)
        result = _metric_prediction(
            score,
            f"LLM judge unavailable ({type(e).__name__}: {e}); "
            f"used keyword-overlap fallback/local fallback. {fallback_feedback}",
        )

    if pred_name is not None:
        feedback = result.feedback or _generate_feedback(
            agent_output=agent_output,
            expected=expected,
            task=task,
            pred_name=pred_name,
            raw_output=raw_output,
        )
        return {"score": result.score, "feedback": feedback}

    return result


def _score_with_llm_judge(
    *,
    task_input: str,
    expected_behavior: str,
    agent_output: str,
    skill_text: str,
) -> FitnessScore:
    """Score a metric example with the currently configured DSPy LM."""
    judge = dspy.ChainOfThought(LLMJudge.JudgeSignature)
    result = judge(
        task_input=task_input,
        expected_behavior=expected_behavior,
        agent_output=agent_output,
        skill_text=skill_text,
    )
    return FitnessScore(
        correctness=_parse_score(result.correctness),
        procedure_following=_parse_score(result.procedure_following),
        conciseness=_parse_score(result.conciseness),
        feedback=str(result.feedback),
    )


def _fallback_similarity_score(expected: str, agent_output: str) -> tuple[float, str]:
    """Local fallback using embedding/TF-IDF scorers when fitted, else keyword overlap."""
    if _embed_scorer is not None and _embed_scorer._fitted:
        score = _embed_scorer.score(agent_output, expected)
        return min(1.0, max(0.0, score)), "Sentence-embedding fallback score."
    if _global_scorer is not None and _global_scorer._fitted:
        score = _global_scorer.score(agent_output, expected)
        return min(1.0, max(0.0, score)), "TF-IDF fallback score."

    expected_words = set(expected.lower().split())
    output_words = set(agent_output.lower().split())
    if not expected_words:
        return 0.5, "No expected-behavior rubric was provided; assigned neutral score."
    overlap_count = len(expected_words & output_words)
    overlap = overlap_count / len(expected_words)
    score = 0.3 + (0.7 * overlap)
    return min(1.0, max(0.0, score)), (
        f"Matched {overlap_count}/{len(expected_words)} expected-behavior keywords. "
        "Improve semantic correctness and procedure following, not just word overlap."
    )


def _metric_prediction(score: float, feedback: str) -> dspy.Prediction:
    """Create a feedback metric result while preserving float coercion."""
    return dspy.Prediction(score=min(1.0, max(0.0, float(score))), feedback=feedback)


def _default_feedback(fitness: FitnessScore) -> str:
    return (
        f"correctness={fitness.correctness:.2f}, "
        f"procedure_following={fitness.procedure_following:.2f}, "
        f"conciseness={fitness.conciseness:.2f}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Global TF-IDF scorer — fitted once per skill/dataset before optimization
# ─────────────────────────────────────────────────────────────────────────────

_global_scorer: Optional[TFIDFSimilarityScorer] = None


def fit_global_scorer(examples: list[dspy.Example]) -> TFIDFSimilarityScorer:
    """Fit the global TF-IDF scorer on a list of evaluation examples.

    Extracts expected_behavior from each example and fits the vectorizer.
    Call this ONCE before starting GEPA optimization.

    After fitting, skill_fitness_metric will use TF-IDF cosine similarity
    instead of raw keyword overlap for more stable scoring.
    """
    global _global_scorer
    behaviors = [getattr(ex, "expected_behavior", "") or "" for ex in examples]
    _global_scorer = TFIDFSimilarityScorer()
    _global_scorer.fit(behaviors)
    return _global_scorer


def clear_global_scorer() -> None:
    """Reset both global scorers. Call between different skills."""
    global _global_scorer, _embed_scorer
    _global_scorer = None
    _embed_scorer = None


# ─────────────────────────────────────────────────────────────────────────────
# Global Sentence Embedding scorer — fitted once per skill/dataset
# ─────────────────────────────────────────────────────────────────────────────

_embed_scorer: Optional[SentenceEmbeddingScorer] = None


def fit_embedding_scorer(examples: list[dspy.Example]) -> SentenceEmbeddingScorer:
    """Fit the global sentence embedding scorer on evaluation examples.

    Pre-computes embeddings for all expected_behavior texts using a local
    sentence transformer model. Call this ONCE before starting GEPA optimization.

    After fitting, skill_fitness_metric will use sentence embedding cosine
    similarity as the primary scoring method (semantic-aware).
    """
    global _embed_scorer
    _embed_scorer = SentenceEmbeddingScorer()
    _embed_scorer.fit(examples)
    return _embed_scorer


def _parse_score(value) -> float:
    """Parse a score value, handling various LLM output formats."""
    if isinstance(value, (int, float)):
        return min(1.0, max(0.0, float(value)))
    try:
        return min(1.0, max(0.0, float(str(value).strip())))
    except (ValueError, TypeError):
        return 0.5  # Default to neutral on parse failure
