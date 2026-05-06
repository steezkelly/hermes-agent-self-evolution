#!/usr/bin/env python3
"""Execute GEPA v2.1 validation for mnemosyne-self-evolution-tools"""
import subprocess
import sys
import os

os.chdir('/home/steve/hermes0/hermes-agent-self-evolution')

cmd = [
    sys.executable, "-m", "evolution.core.gepa_v2_dispatch",
    "--skill", "mnemosyne-self-evolution-tools",
    "--eval-source", "golden",
    "--dataset-path", "datasets/skills/mnemosyne-self-evolution-tools",
    "--optimizer-model", "minimax/minimax-m2.7",
    "--eval-model", "minimax/minimax-m2.7",
    "--iterations", "5",
]

print(f"WORKING DIR: {os.getcwd()}")
print(f"CMD: {' '.join(cmd)}")
print("=" * 60)

result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

print("STDOUT:")
print(result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout)
print("\nSTDERR:")
print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
print(f"\nEXIT CODE: {result.returncode}")
