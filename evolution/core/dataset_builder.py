"""Evaluation dataset generation for hermes-agent-self-evolution.

Sources:
A) Synthetic generation — LLM reads a skill/tool/prompt and generates test cases
B) SessionDB mining — extract real usage patterns and score with LLM-as-judge
C) Golden sets — hand-curated JSONL files
"""

import ast
import dataclasses
import hashlib
import json
import os
import random
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import dspy
import os

from evolution.core.config import EvolutionConfig
from evolution.core.nous_auth import _get_lm_kwargs


def _try_parse_json(text: str) -> list:
    """Parse JSON with multiple fallback strategies for LLM output."""
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    try:
        result = ast.literal_eval(text)
        if isinstance(result, list):
            return result
    except (ValueError, SyntaxError):
        pass
    match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        try:
            result = ast.literal_eval(match.group())
            if isinstance(result, list):
                return result
        except (ValueError, SyntaxError):
            pass
    fixed = re.sub(r',\s*([}\]])', r'\1', text)
    fixed = re.sub(r"(?<!')\'([^']+?)'(?=\s*[:,\]\}])", r'"\1"', fixed)
    try:
        result = json.loads(fixed)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    stripped = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    stripped = re.sub(r'\s*```$', '', stripped)
    try:
        result = json.loads(stripped)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    for block_match in re.finditer(r'\{[^{}]*\}', text):
        try:
            result = json.loads(block_match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            continue
    if text.strip().startswith('['):
        import re as _re
        m = _re.search(r'\}[,\]]', text)
        if m:
            truncated = text[:m.end()]
            try:
                result = json.loads(truncated)
                if isinstance(result, list) and len(result) > 0:
                    return result
            except json.JSONDecodeError:
                pass
            try:
                result = json.loads(truncated)
                if isinstance(result, dict):
                    return [result]
            except json.JSONDecodeError:
                pass
        for obj_match in _re.finditer(r'\{[^{}]*\}', text):
            try:
                result = json.loads(obj_match.group())
                if isinstance(result, dict) and 'task_input' in result and 'expected_behavior' in result:
                    return [result]
            except json.JSONDecodeError:
                continue
    return None


@dataclass
class EvalExample:
    """A single evaluation example."""
    task_input: str
    expected_behavior: str
    difficulty: str = "medium"
    category: str = "general"
    source: str = "synthetic"
    # NEW: captured-session metadata (P0.1)
    tool_sequence: list[str] = field(default_factory=list)
    complexity_score: int = 0
    session_id: str = ""
    success_pattern: str = ""

    def to_dict(self) -> dict:
        return {
            "task_input": self.task_input,
            "expected_behavior": self.expected_behavior,
            "difficulty": self.difficulty,
            "category": self.category,
            "source": self.source,
            "tool_sequence": self.tool_sequence,
            "complexity_score": self.complexity_score,
            "session_id": self.session_id,
            "success_pattern": self.success_pattern,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvalExample":
        # Backward compatibility: old JSONL files may lack new fields
        kwargs = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        for field_name, field_obj in cls.__dataclass_fields__.items():
            if field_name not in kwargs:
                if field_obj.default is not dataclasses.MISSING:
                    kwargs[field_name] = field_obj.default
                elif field_obj.default_factory is not dataclasses.MISSING:
                    kwargs[field_name] = field_obj.default_factory()
                else:
                    kwargs[field_name] = None
        return cls(**kwargs)


@dataclass
class EvalDataset:
    """Train/val/holdout split of evaluation examples."""
    train: list[EvalExample] = field(default_factory=list)
    val: list[EvalExample] = field(default_factory=list)
    holdout: list[EvalExample] = field(default_factory=list)

    @property
    def all_examples(self) -> list[EvalExample]:
        return self.train + self.val + self.holdout

    def save(self, path: Path):
        """Save dataset splits to JSONL files."""
        path.mkdir(parents=True, exist_ok=True)
        for split_name, split_data in [("train", self.train), ("val", self.val), ("holdout", self.holdout)]:
            with open(path / f"{split_name}.jsonl", "w") as f:
                for ex in split_data:
                    f.write(json.dumps(ex.to_dict()) + "\n")

    def save_atomic(self, path: Path):
        """Atomic save: write to temp file, then rename (P0.1)."""
        path.mkdir(parents=True, exist_ok=True)
        for split_name, split_data in [("train", self.train), ("val", self.val), ("holdout", self.holdout)]:
            target = path / f"{split_name}.jsonl"
            tmp = path / f".{split_name}.jsonl.tmp"
            with open(tmp, "w") as f:
                for ex in split_data:
                    f.write(json.dumps(ex.to_dict()) + "\n")
            os.replace(tmp, target)

    @classmethod
    def load(cls, path: Path) -> "EvalDataset":
        """Load dataset splits from JSONL files."""
        dataset = cls()
        for split_name in ["train", "val", "holdout"]:
            split_file = path / f"{split_name}.jsonl"
            if split_file.exists():
                examples = []
                with open(split_file) as f:
                    for line in f:
                        if line.strip():
                            examples.append(EvalExample.from_dict(json.loads(line)))
                setattr(dataset, split_name, examples)
        return dataset

    def merge(self, other: "EvalDataset") -> dict:
        """Merge another dataset into self, deduping by task_input (P0.1)."""
        seen = {ex.task_input for ex in self.all_examples}
        added = {"train": 0, "val": 0, "holdout": 0}
        for ex in other.train:
            if ex.task_input not in seen:
                self.train.append(ex)
                seen.add(ex.task_input)
                added["train"] += 1
        for ex in other.val:
            if ex.task_input not in seen:
                self.val.append(ex)
                seen.add(ex.task_input)
                added["val"] += 1
        for ex in other.holdout:
            if ex.task_input not in seen:
                self.holdout.append(ex)
                seen.add(ex.task_input)
                added["holdout"] += 1
        return added

    def to_dspy_examples(self, split: str = "train") -> list[dspy.Example]:
        """Convert a split to DSPy Example objects."""
        data = getattr(self, split)
        return [
            dspy.Example(
                task_input=ex.task_input,
                expected_behavior=ex.expected_behavior,
            ).with_inputs("task_input")
            for ex in data
        ]


class SyntheticDatasetBuilder:
    """Generate evaluation datasets using a strong LLM."""

    class GenerateTestCases(dspy.Signature):
        """Generate realistic evaluation test cases for an agent skill or tool."""
        artifact_text: str = dspy.InputField(desc="The full text of the skill/tool/prompt being tested")
        artifact_type: str = dspy.InputField(desc="Type: 'skill', 'tool_description', or 'prompt_section'")
        num_cases: int = dspy.InputField(desc="Number of test cases to generate")
        test_cases: str = dspy.OutputField(desc="JSON array of test cases, each with: task_input, expected_behavior, difficulty, category")

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.generator = dspy.ChainOfThought(self.GenerateTestCases)

    def generate(
        self,
        artifact_text: str,
        artifact_type: str = "skill",
        num_cases: Optional[int] = None,
    ) -> EvalDataset:
        """Generate a full eval dataset with train/val/holdout splits."""
        n = num_cases or self.config.eval_dataset_size
        lm_kwargs, judge_model_used = _get_lm_kwargs(self.config.judge_model)
        lm_kwargs["num_retries"] = 8
        lm = dspy.LM(judge_model_used, **lm_kwargs)
        with dspy.context(lm=lm):
            result = self.generator(
                artifact_text=artifact_text,
                artifact_type=artifact_type,
                num_cases=n,
            )
        cases_raw = _try_parse_json(result.test_cases)
        if cases_raw is None:
            print(f"[dataset_builder] Truncated output, retrying with {max(3, n//2)} cases...")
            lm_kwargs2, judge_model_used2 = _get_lm_kwargs(self.config.judge_model)
            lm_kwargs2["num_retries"] = 8
            lm2 = dspy.LM(judge_model_used2, **lm_kwargs2)
            with dspy.context(lm=lm2):
                result2 = self.generator(
                    artifact_text=artifact_text,
                    artifact_type=artifact_type,
                    num_cases=max(3, n // 2),
                )
            cases_raw = _try_parse_json(result2.test_cases)
            if cases_raw is None:
                raise ValueError(f"Could not parse test cases from LLM output (after retry): {result2.test_cases[:500]}")
        examples = [
            EvalExample(
                task_input=c.get("task_input", ""),
                expected_behavior=c.get("expected_behavior", ""),
                difficulty=c.get("difficulty", "medium"),
                category=c.get("category", "general"),
                source="synthetic",
            )
            for c in cases_raw
            if c.get("task_input") and c.get("expected_behavior")
        ]
        random.shuffle(examples)
        n_total = len(examples)
        n_train = max(1, int(n_total * self.config.train_ratio))
        n_val = max(1, int(n_total * self.config.val_ratio))
        return EvalDataset(
            train=examples[:n_train],
            val=examples[n_train:n_train + n_val],
            holdout=examples[n_train + n_val:],
        )


class GoldenDatasetLoader:
    """Load hand-curated evaluation datasets from JSONL files."""

    @staticmethod
    def load(path: Path) -> EvalDataset:
        """Load a golden dataset. If no splits exist, auto-split the single file."""
        if (path / "train.jsonl").exists():
            return EvalDataset.load(path)
        golden_file = path if path.suffix == ".jsonl" else path / "golden.jsonl"
        if not golden_file.exists():
            raise FileNotFoundError(f"No golden dataset found at {golden_file}")
        examples = []
        with open(golden_file) as f:
            for line in f:
                if line.strip():
                    examples.append(EvalExample.from_dict(json.loads(line)))
        random.shuffle(examples)
        n = len(examples)
        n_train = max(1, int(n * 0.5))
        n_val = max(1, int(n * 0.25))
        return EvalDataset(
            train=examples[:n_train],
            val=examples[n_train:n_train + n_val],
            holdout=examples[n_train + n_val:],
        )
