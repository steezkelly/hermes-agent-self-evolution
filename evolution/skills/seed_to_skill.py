"""Generate a complete SKILL.md from a seed prompt using parallel GEPA.

Phase 2: Takes a 1-3 sentence seed -> generates title -> runs section-wise
GEPA optimizations in parallel -> coherence check -> assembles complete SKILL.md.

Two modes:
  1) Single-section worker (internal):
       python -m evolution.skills.seed_to_skill \
         --seed "..." --target-section steps --iterations 3 --optimizer-model ... --eval-model ...

  2) Full skill generation:
       python -m evolution.skills.seed_to_skill \
         --seed "..." --full-skill --iterations 3 --optimizer-model ... --eval-model ...
"""

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import click
import dspy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.nous_auth import _get_lm_kwargs

console = Console()

# 11-section project condensed to these core 5 for generation in this script.
SECTION_ORDER = ["steps", "pitfalls", "examples", "constraints", "verification"]

# Model name normalization.
# Some call-sites pass "deepseek-v4-flash" (no provider slash), but Nous/OpenAI
# routing expects "deepseek/deepseek-v4-flash".

def _normalize_model(model: str) -> str:
    m = (model or "").strip()
    if not m:
        return m
    if m.startswith("deepseek-") and "/" not in m:
        # deepseek-v4-flash -> deepseek/deepseek-v4-flash
        suffix = m[len("deepseek-"):]
        return f"deepseek/deepseek-{suffix}"
    if m == "deepseek-v4-flash":
        return "deepseek/deepseek-v4-flash"
    if m == "deepseek-v4-pro":
        return "deepseek/deepseek-v4-pro"
    return m


TITLE_PROMPT = """Generate a short, descriptive name and one-sentence description for a skill that: {seed}

The name should be lowercase, hyphenated, max 40 chars (e.g. "arxiv-paper-search").
The description should be a single sentence explaining what the skill does.

Return:
name=slug name\ndescription=one sentence description"""

COHERENCE_PROMPT = """Check the following SKILL.md sections for internal contradictions.

Seed: {seed}

Sections:
{all_sections}

Look for:
- Contradictory instructions (section A says do X, section B says don't do X)
- Missing prerequisites (step references something never introduced)
- Inconsistent terminology (same concept named differently across sections)
- Format mismatches (numbered steps vs bullet lists where inappropriate)

Return:
pass=true|false
issues=brief list of problems found, or "none"""

SECTION_TEMPLATES: dict[str, str] = {
    "steps": (
        "Write the SKILL.md 'Steps' section content for a Hermes Agent skill. "
        "Use numbered steps starting at 1. Keep steps actionable and ordered. "
        "Where relevant, include concrete Hermes CLI commands (as inline code) or tool calls "
        "the agent should make. Avoid including the heading '## Steps'."
    ),
    "pitfalls": (
        "Write the SKILL.md 'Pitfalls' section content for a Hermes Agent skill. "
        "Use bullet points. For each pitfall, include: (a) what goes wrong, (b) why it matters, "
        "and (c) a specific mitigation or check. Avoid including the heading '## Pitfalls'."
    ),
    "examples": (
        "Write the SKILL.md 'Examples' section content for a Hermes Agent skill. "
        "Provide 2-3 short example interactions or mini-scenarios. "
        "For each example, show (Input) and (Output/Result) with enough detail to be usable. "
        "Avoid including the heading '## Examples'."
    ),
    "constraints": (
        "Write the SKILL.md 'Constraints' section content for a Hermes Agent skill. "
        "Use bullet points that are precise and enforceable. Prefer 'Do ...' / 'Don't ...' phrasing. "
        "Include any required formats, limits, or safety constraints implied by the seed. "
        "Avoid including the heading '## Constraints'."
    ),
    "verification": (
        "Write the SKILL.md 'Verification' section content for a Hermes Agent skill. "
        "Describe how to test correctness. Include at least 2 checks with clear pass/fail criteria. "
        "Prefer lightweight tests the agent (or a user) can perform. "
        "Avoid including the heading '## Verification'."
    ),
}


def _generate_title(seed: str, eval_model: str) -> tuple[str, str]:
    """Generate skill name and description from seed via LLM."""
    console.print("\n[bold]Generating title & description[/bold]")
    try:
        lm_kwargs, model = _get_lm_kwargs(_normalize_model(eval_model))
        lm = dspy.LM(model, **lm_kwargs)
        result = lm(TITLE_PROMPT.format(seed=seed))
        if isinstance(result, list):
            text = result[0] if result else ""
        elif isinstance(result, dict):
            # Litellm / DSPy often nests: choices[0].message.content
            text = (
                result.get("choices", [{}])[0]
                .get("message", {})
                .get("content")
                or result.get("content")
                or result.get("text")
                or str(result)
            )
        else:
            text = str(result)
        name_match = re.search(r"name[=:]\s*([^\n]+)", text, re.IGNORECASE)
        desc_match = re.search(r"description[=:]\s*([^\n]+)", text, re.IGNORECASE)
        name = name_match.group(1).strip() if name_match else "unnamed-skill"
        description = desc_match.group(1).strip() if desc_match else seed

        # Sanitize name
        name = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-").replace("_", "-"))
        name = name[:40]
        console.print(f"  Name: {name}")
        console.print(f"  Description: {description[:80]}...")
        return name, description
    except Exception as e:
        console.print(f"[yellow]  ⚠ Title generation failed ({e}), using fallback[/yellow]")
        name = re.sub(r"[^a-z0-9-]", "", seed.lower().replace(" ", "-")[:40])
        return name, seed


def _coherence_check(seed: str, sections: dict[str, str], eval_model: str) -> tuple[bool, str]:
    """Single LLM call to check all sections for contradictions."""
    console.print("\n[bold]Running coherence check[/bold]")
    all_text = ""
    for sec_name, content in sections.items():
        all_text += f"\n### {sec_name}\n{(content or '')[:1500]}\n"

    try:
        lm_kwargs, model = _get_lm_kwargs(_normalize_model(eval_model))
        lm = dspy.LM(model, **lm_kwargs)
        result = lm(COHERENCE_PROMPT.format(seed=seed, all_sections=all_text))
        if isinstance(result, list):
            text = result[0] if result else ""
        elif isinstance(result, dict):
            text = (
                result.get("choices", [{}])[0]
                .get("message", {})
                .get("content")
                or result.get("content")
                or result.get("text")
                or str(result)
            )
        else:
            text = str(result)

        pass_match = re.search(r"pass[=:]\s*(true|false)", text, re.IGNORECASE)
        issues_match = re.search(r"issues[=:]\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        passes = bool(pass_match) and pass_match.group(1).lower() == "true"
        issues = issues_match.group(1).strip() if issues_match else text[:300]
        return passes, issues
    except Exception as e:
        return True, f"coherence check failed: {e} (proceeding anyway)"


def _assemble_skill(name: str, description: str, sections: dict[str, str], seed: str, generation_meta: dict) -> str:
    """Assemble full SKILL.md from sections.

    Metadata formatting standard (machine-first):
      - YAML-native mapping only
      - No inline raw JSON objects
    """

    body = f"# {name.replace('-', ' ').title()}\n\n{description}\n\n"

    for sec_name in SECTION_ORDER:
        content = sections.get(sec_name, "") or ""
        if content.strip():
            # Strip any template-ish boilerplate lines.
            cleaned = content
            for pattern in [r"^#\s+\w+\s+for:.*\n", r"^##\s+\w+\s*\n"]:
                cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r"^(?:Provide|Write|List|Each|Generate).*\n", "", cleaned, flags=re.MULTILINE)
            body += f"\n## {sec_name.title()}\n\n{cleaned.strip()}\n"

    coherence_issues_val = (generation_meta.get('coherence_issues') or 'none')
    coherence_issues_escaped = coherence_issues_val.replace('"', '\\"')
    ts = generation_meta.get('timestamp') or ''
    secs_meta = generation_meta.get('section_metrics') or {}

    section_metrics_lines = ''.join(
        f"        {sec}:\n"
        f"          exit_code: {secs_meta.get(sec, {}).get('exit_code')}\n"
        f"          elapsed_seconds: {secs_meta.get(sec, {}).get('elapsed_seconds')}\n"
        for sec in SECTION_ORDER
    )

    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "version: 0.1.0-seed\n"
        "metadata:\n"
        "  hermes:\n"
        "    tags: [seed-generated]\n"
        "    generation:\n"
        f"      seed: \"{seed}\"\n"
        f"      iterations_per_section: {generation_meta.get('iterations_per_section')}\n"
        f"      optimizer_model: \"{generation_meta.get('optimizer_model')}\"\n"
        f"      eval_model: \"{generation_meta.get('eval_model')}\"\n"
        f"      coherence_passed: {str(generation_meta.get('coherence_passed', False)).lower()}\n"
        f"      coherence_issues: \"{coherence_issues_escaped}\"\n"
        "      section_metrics:\n"
        + section_metrics_lines
        + f"      total_elapsed_seconds: {generation_meta.get('total_elapsed_seconds')}\n"
        f"      timestamp: \"{ts}\"\n"
        "---\n\n"
        f"{body}\n"
    )


def _make_structural_fitness(section_name: str) -> Callable:
    """Structural-only fitness for GEPA.

    Must accept exactly 5 args for GEPA compatibility.
    """

    # Regexes kept lightweight.
    numbered_re = re.compile(r"^\s*\d+[\.)]\s+", re.MULTILINE)
    bullet_re = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)
    codeblock_re = re.compile(r"```[\s\S]*?```", re.MULTILINE)
    url_re = re.compile(r"https?://\S+", re.IGNORECASE)
    inline_code_re = re.compile(r"`[^`]+`")

    section_expectations = {
        "steps": {"numbered": 1.0, "bullet": 0.2},
        "pitfalls": {"numbered": 0.0, "bullet": 1.0},
        "examples": {"numbered": 0.2, "bullet": 0.2},
        "constraints": {"numbered": 0.0, "bullet": 1.0},
        "verification": {"numbered": 0.2, "bullet": 0.5},
    }
    expected = section_expectations.get(section_name, {"numbered": 0.5, "bullet": 0.5})

    def _structural_fitness(gold, pred, trace=None, pred_name=None, pred_trace=None) -> float:
        # pred should contain output.
        if pred is None:
            return 0.0
        # DSPy Prediction objects may expose the generated text as .output,
        # or under a signature field name (e.g. section_text).
        text = getattr(pred, "output", "") or ""
        if not text:
            for v in getattr(pred, "__dict__", {}).values():
                if isinstance(v, str) and v.strip():
                    text = v
                    break
            if not text:
                # Fallback: try attribute-style fields
                for k in dir(pred):
                    if k.startswith("_"):
                        continue
                    try:
                        v = getattr(pred, k)
                    except Exception:
                        continue
                    if isinstance(v, str) and v.strip():
                        text = v
                        break
        text = text.strip()
        if not text:
            return 0.0

        # Base length reward (avoid garbage short outputs).
        length = len(text)
        score = 0.0
        score += min(1.0, length / 1800) * 0.25

        # Section-typical structure.
        numbered = len(numbered_re.findall(text))
        bullets = len(bullet_re.findall(text))
        blocks = 1 if codeblock_re.search(text) else 0
        urls = 1 if url_re.search(text) else 0
        inline_code = 1 if inline_code_re.search(text) else 0

        score += min(1.0, numbered / 6) * 0.35 * expected.get("numbered", 0.5)
        score += min(1.0, bullets / 8) * 0.35 * expected.get("bullet", 0.5)

        score += blocks * 0.05
        score += urls * 0.03
        score += inline_code * 0.02

        # Penalties for suspicious artifacts.
        if "[[]" in text or "TODO" in text:
            score -= 0.1
        if re.search(r"\b(none|n/a)\b", text, re.IGNORECASE):
            score -= 0.08

        score = max(0.0, min(1.0, score))

        # GEPA supports dict-based feedback for predictor-level calls, but float is sufficient.
        return score

    return _structural_fitness


class SeedSectionModule(dspy.Module):
    """A single-section generator.

    GEPA will mutate the Predict.signature.instructions for this predictor.
    During forward(), we call the underlying dspy.Predict so the mutated
    instructions actually drive LM generation of the section text.
    """

    def __init__(self, section_name: str, section_template: str):
        super().__init__()
        self.section_name = section_name
        self.output_field = "section_text"

        sig = dspy.Signature(
            f"task_input: str -> {self.output_field}: str",
            instructions=section_template,
        )
        self.predict = dspy.Predict(sig)

    def named_predictors(self):
        # GEPA uses these names as the candidate keys.
        return [(f"pred_{self.section_name}", self.predict)]

    def forward(self, task_input: str) -> dspy.Prediction:
        return self.predict(task_input=task_input)


def _generate_single_section(
    seed: str,
    target_section: str,
    iterations: int,
    optimizer_model: str,
    eval_model: str,
    n_examples: int,
    dry_run: bool,
) -> str:
    if target_section not in SECTION_TEMPLATES:
        raise ValueError(f"Unknown target section: {target_section}")

    section_template = SECTION_TEMPLATES[target_section]
    fitness = _make_structural_fitness(target_section)

    console.print(f"\n[bold cyan]GEPA section:[/bold cyan] {target_section} (iters={iterations})")

    if dry_run:
        console.print("[dim]DRY RUN: skipping GEPA execution for section.[/dim]")
        return "(dry-run)"

    # Configure generation LM (the Predict that actually writes the section).
    gen_kwargs, gen_model = _get_lm_kwargs(_normalize_model(eval_model))
    # Some routing branches can return empty kwargs if no creds are available.
    # If that happens, dspy will likely throw; we fail fast here.
    if not gen_kwargs:
        raise RuntimeError(f"No credentials/route found for eval_model={eval_model}")
    gen_lm = dspy.LM(gen_model, **gen_kwargs)
    dspy.configure(lm=gen_lm)

    # Configure reflection LM (used by GEPA to propose instruction mutations).
    ref_kwargs, ref_model = _get_lm_kwargs(_normalize_model(optimizer_model))
    ref_kwargs["num_retries"] = max(6, ref_kwargs.get("num_retries", 0) or 0)
    reflection_lm = dspy.LM(ref_model, **ref_kwargs)

    # Train/val examples.
    # Important: dspy.Example requires explicit .with_inputs() for the
    # signature input fields (otherwise GEPA's evaluator crashes).
    train_examples = [
        dspy.Example(task_input=f"Seed: {seed}\n\nWrite the {target_section} section.")
        .with_inputs("task_input")
        for _ in range(max(3, n_examples))
    ]
    val_examples = [
        dspy.Example(task_input=f"Seed: {seed}\n\nWrite the {target_section} section.")
        .with_inputs("task_input")
        for _ in range(max(2, n_examples // 2))
    ]

    module = SeedSectionModule(target_section, section_template)

    # Budget: metric calls; each call includes scoring a candidate.
    # Keep this bounded to avoid runaway costs.
    max_metric_calls = max(10, iterations * 12)

    optimizer = dspy.GEPA(
        metric=fitness,
        max_metric_calls=max_metric_calls,
        reflection_minibatch_size=min(12, len(train_examples)),
        reflection_lm=reflection_lm,
    )

    optimized_module = optimizer.compile(
        module,
        trainset=train_examples,
        valset=val_examples,
    )

    # Produce final section text with the evolved prompt instructions.
    final_pred = optimized_module(task_input=f"Seed: {seed}\n\nWrite the {target_section} section.")
    out = getattr(final_pred, "section_text", "") or ""
    return out.strip()


def generate_full_skill(
    seed: str,
    iterations: int = 3,
    optimizer_model: str = "deepseek/deepseek-v4-pro",
    eval_model: str = "deepseek/deepseek-v4-flash",
    n_examples: int = 5,
    max_concurrent: int = 3,
    dry_run: bool = False,
):
    """Generate a complete SKILL.md from a seed using parallel GEPA sections."""

    overall_start = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    console.print(
        Panel(
            f"[bold cyan]🌱 Seed → Full SKILL.md[/bold cyan]\n"
            f"Seed: {seed}\n"
            f"Sections: {', '.join(SECTION_ORDER)}\n"
            f"Iterations per section: {iterations}\n"
            f"Max concurrent: {max_concurrent}\n"
            f"Optimizer: {optimizer_model} | Eval/Title: {eval_model}"
        )
    )

    if dry_run:
        console.print("\n[bold green]DRY RUN — pipeline validated.[/bold green]")
        return None

    # 1) Title
    name, description = _generate_title(seed, eval_model)

    # 2) Parallel section generation
    console.print(f"\n[bold cyan]Running {len(SECTION_ORDER)} section GEPA runs ({max_concurrent} concurrent)...[/bold cyan]")

    results: dict[str, dict] = {}
    pending = list(SECTION_ORDER)
    running: list[tuple[str, subprocess.Popen]] = []

    output_root = Path(__file__).parent.parent.parent / "output" / "seed-generated"
    output_root.mkdir(parents=True, exist_ok=True)

    while pending or running:
        while pending and len(running) < max_concurrent:
            section = pending.pop(0)
            console.print(f"  Starting: {section} ({len(pending)} remaining)")
            proc = subprocess.Popen(
                [
                    str(Path(__file__).parent.parent.parent / ".venv" / "bin" / "python"),
                    "-m", "evolution.skills.seed_to_skill",
                    "--seed", seed,
                    "--target-section", section,
                    "--iterations", str(iterations),
                    "--optimizer-model", optimizer_model,
                    "--eval-model", eval_model,
                    "--n-examples", str(n_examples),
                    "--timestamp", timestamp,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(Path(__file__).parent.parent.parent),
            )
            running.append((section, proc))

        still_running: list[tuple[str, subprocess.Popen]] = []
        for section, proc in running:
            if proc.poll() is None:
                still_running.append((section, proc))
                continue

            # Completed.
            elapsed = 0.0
            try:
                stdout = proc.stdout.read() if proc.stdout else ""
            except Exception:
                stdout = ""

            # Use exact timestamped dir so we don't accidentally read stale outputs.
            out_dir = output_root / f"{section}_{timestamp}"
            out_file = out_dir / "evolved_section.md"
            content = out_file.read_text() if out_file.exists() else ""

            console.print(f"  [green]✓ {section}[/green] completed (exit={proc.returncode})")

            results[section] = {
                "content": content,
                "elapsed": elapsed,
                "exit_code": proc.returncode,
                "stdout_tail": "\n".join(stdout.split("\n")[-10:]) if stdout else "",
            }

        running = still_running
        if pending or running:
            time.sleep(2)

    sections_content = {sec: r.get("content", "") for sec, r in results.items()}

    # 3) Coherence check
    passes, issues = _coherence_check(seed, sections_content, eval_model)

    icon = "✓" if passes else "⚠"
    color = "green" if passes else "yellow"
    console.print(f"  [{color}]{icon} Coherence: {'PASS' if passes else 'ISSUES'}[/{color}]")
    if not passes:
        console.print(f"  Issues: {issues[:200]}")

    # 4) Assemble
    generation_meta = {
        "seed": seed,
        "iterations_per_section": iterations,
        "optimizer_model": optimizer_model,
        "eval_model": eval_model,
        "coherence_passed": passes,
        "coherence_issues": issues[:200] if not passes else "none",
        "section_metrics": {
            sec: {"exit_code": r.get("exit_code"), "elapsed_seconds": r.get("elapsed")}
            for sec, r in results.items()
        },
    }

    skill_md = _assemble_skill(name, description, sections_content, seed, generation_meta)

    overall_elapsed = time.time() - overall_start
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent.parent / "output" / "seed-generated" / f"full-skill_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    skill_path = output_dir / f"{name}.SKILL.md"
    skill_path.write_text(skill_md)

    meta = {
        **generation_meta,
        "total_elapsed_seconds": overall_elapsed,
        "skill_name": name,
        "skill_description": description,
        "total_chars": len(skill_md),
        "timestamp": timestamp,
    }
    (output_dir / "generation.json").write_text(json.dumps(meta, indent=2))

    console.print(f"  Saved to {skill_path}")

    # Summary table
    table = Table(title="Seed → Complete Skill")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Seed", seed[:60] + ("..." if len(seed) > 60 else ""))
    table.add_row("Skill Name", name)
    table.add_row("Sections", str(len(results)))
    table.add_row("Coherence", "PASS" if passes else "ISSUES")
    table.add_row("Total Time", f"{overall_elapsed:.0f}s")
    table.add_row("Total Chars", f"{len(skill_md):,}")

    # Preview
    console.print("\n[bold cyan]Generated SKILL.md preview:[/bold cyan]")
    preview = skill_md[:2000]
    if len(skill_md) > 2000:
        preview += f"\n... ({len(skill_md) - 2000:,} more chars)"
    console.print(preview)

    console.print()
    console.print(table)

    return {
        "skill_path": str(skill_path),
        "skill_md": skill_md,
        "meta": meta,
    }


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--seed", required=True, type=str, help="1-3 sentence description of what the skill should do")
@click.option("--full-skill", is_flag=True, default=False, help="Generate full SKILL.md from seed")
@click.option("--target-section", default=None, type=str, help="Worker mode: generate a single target section")
@click.option("--iterations", default=3, type=int, show_default=True)
@click.option("--optimizer-model", default="deepseek/deepseek-v4-pro", type=str, show_default=True)
@click.option("--eval-model", default="deepseek/deepseek-v4-flash", type=str, show_default=True)
@click.option("--n-examples", default=5, type=int, show_default=True)
@click.option("--max-concurrent", default=3, type=int, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--timestamp", default=None, type=str, help="Override timestamp for worker output dirs (used by orchestrator)")

def cli(seed: str, full_skill: bool, target_section: Optional[str], iterations: int, optimizer_model: str, eval_model: str, n_examples: int, max_concurrent: int, dry_run: bool, timestamp: Optional[str]):
    if full_skill:
        generate_full_skill(
            seed=seed,
            iterations=iterations,
            optimizer_model=optimizer_model,
            eval_model=eval_model,
            n_examples=n_examples,
            max_concurrent=max_concurrent,
            dry_run=dry_run,
        )
        return

    if not target_section:
        raise click.UsageError("Either --full-skill or --target-section is required")

    if target_section not in SECTION_ORDER:
        raise click.UsageError(f"--target-section must be one of: {', '.join(SECTION_ORDER)}")

    # Use orchestrator-provided timestamp so worker writes to the expected dir.
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = Path(__file__).parent.parent.parent / "output" / "seed-generated"
    out_dir = output_root / f"{target_section}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    section_text = _generate_single_section(
        seed=seed,
        target_section=target_section,
        iterations=iterations,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
        n_examples=n_examples,
        dry_run=dry_run,
    )

    out_path = out_dir / "evolved_section.md"
    out_path.write_text(section_text)

    meta = {
        "seed": seed,
        "target_section": target_section,
        "iterations": iterations,
        "optimizer_model": optimizer_model,
        "eval_model": eval_model,
        "n_examples": n_examples,
        "timestamp": timestamp,
        "chars": len(section_text),
        "dry_run": dry_run,
    }
    (out_dir / "generation.json").write_text(json.dumps(meta, indent=2))

    console.print(f"\nSaved section '{target_section}' to {out_path}")


if __name__ == "__main__":
    cli()
