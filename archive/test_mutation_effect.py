# test_mutation_effect.py
"""Verify that GEPA mutation actually changes the skill body text."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from evolution.skills.skill_module_v2 import MultiComponentSkillModule
from evolution.core.fitness import skill_fitness_metric
from evolution.skills.skill_module import find_skill, load_skill
from evolution.core.config import EvolutionConfig

def main():
    config = EvolutionConfig()
    skill_path = find_skill("companion-roundtable", config.hermes_agent_path)
    if not skill_path:
        skill_path = find_skill("companion-roundtable", Path.home() / ".hermes")
    if not skill_path:
        for base in [Path.cwd(), Path.home() / ".hermes", Path.home() / "hermes0"]:
            found = list(base.rglob("companion-roundtable/SKILL.md"))
            if found:
                skill_path = found[0]
                break

    if not skill_path:
        print("ERROR: Cannot find companion-roundtable skill")
        sys.exit(1)

    print(f"Skill path: {skill_path}")
    skill = load_skill(skill_path)
    skill_body = skill["body"]
    print(f"Original body length: {len(skill_body)} chars")

    # Build module
    module = MultiComponentSkillModule(skill_body)
    print(f"Module sections: {len(module.sections)}")

    # Show what str(module) returns
    reconstructed = str(module)
    print(f"reconstructed body length: {len(reconstructed)} chars")
    if reconstructed == skill_body:
        print("✓ str(module) reconstructs original exactly")
    else:
        print("⚠ str(module) DIFFERS from original")

    # Find first predictor
    named_preds = module.named_predictors()
    print(f"Named predictors: {len(named_preds)}")
    first_name, first_pred = named_preds[0]
    print(f"First predictor: {first_name}")
    original_text = first_pred.signature.instructions
    print(f"First predictor instructions length: {len(original_text)}")

    # Simulate mutation: change instructions
    mutated_text = original_text + "\n\n[MUTATION TEST: this text was added]"
    first_pred.signature = first_pred.signature.with_instructions(mutated_text)
    print(f"\nAfter manual mutation (added 40 chars):")

    mutated_body = str(module)
    print(f"Mutated body length: {len(mutated_body)} chars")

    if mutated_body == reconstructed:
        print("⚠  BODY DID NOT CHANGE")
        changed = False
    else:
        print("✓ Body changed")
        changed = True
        # Find diff position
        for i, (a, b) in enumerate(zip(mutated_body, reconstructed)):
            if a != b:
                print(f"  First diff at position {i}")
                break

    # Test metric discrimination  
    # The metric expects a dspy.Prediction with .output, not a raw string!
    import dspy
    
    # Configure a local LM for the metric's _invoke_skill_as_agent call
    lm = dspy.LM('ollama/qwen3:sm', api_base='http://localhost:11434')
    dspy.configure(lm=lm)
    
    example = dspy.Example(task_input="Generate roundtable response", expected_behavior="A response")
    
    pred_original = dspy.Prediction(output=reconstructed)
    score_original = skill_fitness_metric(example, pred_original)
    print(f"\nOriginal body metric score: {score_original:.4f}")

    if changed:
        pred_mutated = dspy.Prediction(output=mutated_body)
        score_mutated = skill_fitness_metric(example, pred_mutated)
        print(f"Mutated body metric score:  {score_mutated:.4f}")
        if abs(score_original - score_mutated) < 0.001:
            print("⚠  METRIC DID NOT DETECT THE CHANGE")
        else:
            print(f"✓ Metric detected change: {score_mutated - score_original:+.4f}")

if __name__ == "__main__":
    main()
