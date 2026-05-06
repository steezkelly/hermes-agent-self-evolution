#!/usr/bin/env python3
"""Execute GEPA v2.1 validation for mnemosyne-self-evolution-tools"""
import subprocess
import sys
import os
import glob
import json

os.chdir('/home/steve/hermes0/hermes-agent-self-evolution')

# Use the venv python if it exists, otherwise current python
venv_python = os.path.join(os.getcwd(), '.venv', 'bin', 'python')
if not os.path.exists(venv_python):
    venv_python = sys.executable

print(f"WORKING DIR: {os.getcwd()}")
print(f"PYTHON: {venv_python}")
print("=" * 60)

# Run the validation script
cmd = [
    venv_python, "run_v2_validate.py",
    "--skill", "mnemosyne-self-evolution-tools",
    "--eval-source", "golden",
    "--dataset-path", "datasets/skills/mnemosyne-self-evolution-tools",
    "--optimizer-model", "minimax/minimax-m2.7",
    "--eval-model", "minimax/minimax-m2.7",
    "--iterations", "5",
]

print(f"CMD: {' '.join(cmd)}")
print("=" * 60)

result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

print("STDOUT (last 5000 chars):")
stdout = result.stdout
if len(stdout) > 5000:
    print(f"[...{len(stdout)-5000} chars truncated...]")
    print(stdout[-5000:])
else:
    print(stdout)

print("\nSTDERR (last 3000 chars):")
stderr = result.stderr
if len(stderr) > 3000:
    print(f"[...{len(stderr)-3000} chars truncated...]")
    print(stderr[-3000:])
else:
    print(stderr)

print(f"\nEXIT CODE: {result.returncode}")
print("=" * 60)

# Now find and read the output files
output_dirs = sorted(glob.glob("output/mnemosyne-self-evolution-tools/v2_*"))
if output_dirs:
    latest = output_dirs[-1]
    print(f"\nLatest output dir: {latest}")
    
    metrics_path = os.path.join(latest, "metrics.json")
    report_path = os.path.join(latest, "report.json")
    
    if os.path.exists(metrics_path):
        print("\n" + "=" * 60)
        print("METRICS.JSON:")
        print("=" * 60)
        with open(metrics_path) as f:
            metrics = json.load(f)
        print(json.dumps(metrics, indent=2))
        
        # Check v2_constraints
        if 'v2_constraints' in metrics:
            vc = metrics['v2_constraints']
            print("\nV2_CONSTRAINTS CHECK:")
            print(f"  - config_drift_passed: {vc.get('config_drift_passed')}")
            print(f"  - purpose_preservation_passed: {vc.get('purpose_preservation_passed')}")
            print(f"  - scope_status: {vc.get('scope_status')}")
            print(f"  - regression_passed: {vc.get('regression_passed')}")
            print(f"  - pareto_source: {vc.get('pareto_source')}")
            print(f"  - router_action: {vc.get('router_action')}")
            all_6 = all(k in vc for k in ['config_drift_passed','purpose_preservation_passed','scope_status','regression_passed','pareto_source','router_action'])
            print(f"  - All 6 v2_constraints keys present: {all_6}")
        else:
            print("\nWARNING: 'v2_constraints' key NOT FOUND in metrics.json")
        
        # Check shrinkage floor
        baseline_size = metrics.get('baseline_size', 0)
        evolved_size = metrics.get('evolved_size', 0)
        if baseline_size > 0:
            shrinkage = (baseline_size - evolved_size) / baseline_size * 100
            print(f"\nSHRINKAGE CHECK:")
            print(f"  - baseline_size: {baseline_size}")
            print(f"  - evolved_size: {evolved_size}")
            print(f"  - shrinkage: {shrinkage:.1f}%")
            print(f"  - Within -50% floor: {shrinkage <= 50}")
        
    if os.path.exists(report_path):
        print("\n" + "=" * 60)
        print("REPORT.JSON:")
        print("=" * 60)
        with open(report_path) as f:
            report = json.load(f)
        print(json.dumps(report, indent=2))
        
        # Check recommendation
        print(f"\nRECOMMENDATION: {report.get('recommendation')}")
        print(f"IMPROVEMENT: {report.get('improvement')}")
        if 'v2_constraints' in report:
            print(f"PURPOSE_PRESERVATION_PASSED: {report['v2_constraints'].get('purpose_preservation_passed')}")
else:
    print("\nNo output directories found!")
