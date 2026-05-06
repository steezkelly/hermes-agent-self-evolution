#!/usr/bin/env python3
"""Execute GEPA v2.1 validation for mnemosyne-self-evolution-tools"""
import subprocess
import sys
import os

os.chdir('/home/steve/hermes0/hermes-agent-self-evolution')

# Use the venv python
venv_python = os.path.join(os.getcwd(), '.venv', 'bin', 'python')
if not os.path.exists(venv_python):
    venv_python = sys.executable

cmd = [
    venv_python, "run_v2_validate.py",
    "--skill", "mnemosyne-self-evolution-tools",
    "--eval-source", "golden",
    "--dataset-path", "datasets/skills/mnemosyne-self-evolution-tools",
    "--optimizer-model", "minimax/minimax-m2.7",
    "--eval-model", "minimax/minimax-m2.7",
    "--iterations", "5",
]

print(f"WORKING DIR: {os.getcwd()}")
print(f"PYTHON: {venv_python}")
print(f"CMD: {' '.join(cmd)}")
print("=" * 60)

result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

print("STDOUT (last 6000 chars):")
stdout = result.stdout
if len(stdout) > 6000:
    print(f"[...{len(stdout)-6000} chars truncated...]")
    print(stdout[-6000:])
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
