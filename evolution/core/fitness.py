"""Fitness functions for evaluating evolved artifacts.

Uses LLM-as-judge with rubrics to score agent outputs.
Supports length penalties and multi-dimensional scoring.

v2 Fix: skill_fitness_metric now invokes an LLM with the skill body as
instructions + the task_input, producing a real agent response that gets
scored against expected_behavior. This replaces the broken V2 behavior
where the metric scored the raw 21KB skill body text (which naturally
has high keyword overlap, creating a flat signal GEPA cannot optimize).

v3 Observatory: All judge calls and metric evaluations are logged to
judge_audit_log.db via evolution.core.observatory.

v3.1 Cost: token_cost_estimate wired via token_cost.py.
"""

import dspy
import time as _time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from evolution.core.config import EvolutionConfig
from evolution.core.nous_auth import _get_lm_kwargs

# Token cost estimation (Phase 3)
try:
    from evolution.core.token_cost import estimate_judge_call_cost
    _TOKEN_COST_AVAILABLE = True
except ImportError:
    _TOKEN_COST_AVAILABLE = False
    estimate_judge_call_cost = None

# Observatory integration (Phase 1)
try:
    from evolution.core.observatory.logger import log_judge_call, JudgeAuditLogger
    from evolution.core.observatory.context import get_evaluation_context
    _OBSERVATORY_AVAILABLE = True
except ImportError:
    _OBSERVATORY_AVAILABLE = False
    log_judge_call = None
    get_evaluation_context = None


# ─────────────────────────────────────────────────────────────────────────────
# Inference wrapper — execute a skill body as agent instructions
# ─────────────────────────────────────────────────────────────────────────────

def _invoke_skill_as_agent(body_text: str, task_input: str) -> str:
    """Execute the skill body as agent instructions + task to get a generated response.

    CRITICAL FIX (2026-05-03): This is called inside GEPA's threaded Evaluate
    context, where dspy.settings.lm may be None. We MUST configure a fresh LM
    directly rather than relying on global state. Previous code caught ALL
    exceptions silently and returned '[metric-inference-failed]', making
    every score 0.0 and hiding the real error.
    """
    if not body_text.strip() or not task_input.strip():
        return body_text

    # Import here to avoid circular deps and to re-configure after fork
    try:
        from evolution.core.nous_auth import _get_lm_kwargs
    except Exception:
        _get_lm_kwargs = None

    # Try to get a working LM. Priorities:
    # 1. Use dspy.settings.lm if available (fast path, warm cache)
    # 2. Re-configure via _get_lm_kwargs if available
    # 3. Fail LOUDLY so we can see what went wrong (never silently)
    lm = dspy.settings.lm

    if lm is None and _get_lm_kwargs is not None:
        try:
            lm_kwargs_tuple = _get_lm_kwargs("minimax/minimax-m2.7")
            if lm_kwargs_tuple and isinstance(lm_kwargs_tuple, tuple):
                lm_kwargs = lm_kwargs_tuple[0].copy()
                model_name = lm_kwargs_tuple[1]
                lm_kwargs['model'] = model_name
                lm_kwargs['request_timeout'] = 120
                lm_kwargs['num_retries'] = 2
                lm = dspy.LM(**lm_kwargs)
        except Exception as exc:
            # Log but re-raise — never silently swallow
            print(f"[GEPA METRIC ERROR] Could not configure LM: {exc}")
            raise

    if lm is None:
        raise RuntimeError(
            "No LM available for metric inference. "
            "dspy.settings.lm is None and _get_lm_kwargs failed. "
            "Call dspy.configure(lm=...) before running GEPA."
        )

    sig = dspy.Signature(
        "task_input: str -> response: str",
        instructions=body_text,
    )

    # Use dspy.context to ensure the LM is active even in threads/subprocesses
    try:
        with dspy.context(lm=lm):
            result = dspy.Predict(sig)(task_input=task_input)
        return result.response or ""
    except Exception as exc:
        # Fail loudly — never silently return a magic string
        print(f"[GEPA METRIC ERROR] dspy.Predict failed: {type(exc).__name__}: {exc}")
        raise


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
# On-the-fly embedding fallback (for when globals are lost in subprocesses)
# ─────────────────────────────────────────────────────────────────────────────

def _on_the_fly_embed_score(agent_output: str, expected_behavior: str) -> Optional[float]:
    """Compute a sentence-embedding cosine similarity with ZERO pre-caching.

    Called when _embed_scorer or _global_scorer are unavailable (e.g. in a
    forked worker thread created by GEPA's multiprocessing Evaluate). Loads
    the all-MiniLM-L6-v2 model on first call (~30MB). Subsequent calls are
    ~5ms.

    Returns None if sentence_transformers is not installed or inputs are empty.
    """
    if not agent_output.strip() or not expected_behavior.strip():
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    model = _on_the_fly_embed_score.__dict__.setdefault("_model", None)
    if model is None:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        _on_the_fly_embed_score._model = model
    vecs = model.encode([agent_output, expected_behavior], show_progress_bar=False)
    a_vec, e_vec = vecs[0], vecs[1]
    sim = float(np.dot(a_vec, e_vec) /
                (np.linalg.norm(a_vec) * np.linalg.norm(e_vec)))
    return float(np.clip(sim, 0.0, 1.0))


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
        # ── Observatory: time the judge call ────────────────────────────────
        start_ms = int(_time.time() * 1000)

        # Use module-level _get_lm_kwargs imported from nous_auth.py.
        # The old @staticmethod _get_lm_kwargs had a NameError because
        # get_nous_credentials() is not imported into this module.
        kwargs, model_used = _get_lm_kwargs(self.config.eval_model)
        lm = dspy.LM(model_used, **kwargs)

        error_flag: Optional[str] = None
        raw_score_value = 0.0
        latency_ms: int = 0

        try:
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
                    length_penalty = min(0.3, (ratio - 0.9) * 3.0)

            raw_score_value = (
                0.5 * correctness
                + 0.3 * procedure_following
                + 0.2 * conciseness
            )
            raw_score_value = max(0.0, raw_score_value - length_penalty)

            fitness_score = FitnessScore(
                correctness=correctness,
                procedure_following=procedure_following,
                conciseness=conciseness,
                length_penalty=length_penalty,
                feedback=str(result.feedback),
            )

        except Exception as exc:
            error_flag = type(exc).__name__
            raw_score_value = 0.0
            fitness_score = FitnessScore(
                correctness=0.0,
                procedure_following=0.0,
                conciseness=0.0,
                length_penalty=0.0,
                feedback=f"[JUDGE ERROR] {error_flag}: {exc}",
            )

        latency_ms = int(_time.time() * 1000) - start_ms

        # ── Observatory: log every judge call ──────────────────────────────
        if _OBSERVATORY_AVAILABLE and log_judge_call is not None:
            ctx = get_evaluation_context() if get_evaluation_context else None
            generation = ctx.generation if ctx else 0
            skill_name = ctx.skill_name if ctx else "unknown"
            session_id = ctx.session_id if ctx else None

            # v3.1: estimate cost for this judge call
            token_cost: Optional[float] = None
            if _TOKEN_COST_AVAILABLE and estimate_judge_call_cost is not None:
                try:
                    token_cost = estimate_judge_call_cost(
                        task_input=task_input,
                        expected_behavior=expected_behavior,
                        agent_output=agent_output or "",
                        skill_text=skill_text,
                        model_name=model_used,
                        feedback_text=fitness_score.feedback,
                    )
                except Exception:
                    token_cost = None

            log_judge_call(
                generation=generation,
                skill_name=skill_name,
                model_used=model_used,
                task_id=ctx.task_id if ctx and ctx.task_id is not None else "",
                expected_behavior=expected_behavior,
                actual_behavior=agent_output[:500] if agent_output else "[empty]",
                rubric="multi-dimensional: correctness, procedure_following, conciseness",
                raw_score=raw_score_value,
                latency_ms=latency_ms,
                token_cost_estimate=token_cost,
                error_flag=error_flag,
                skill_body=skill_text,
                session_id=session_id,
            )

        return fitness_score


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
