"""Build evaluation datasets for tool description evolution.

Tool selection is a classification problem: given a task description,
predict the correct tool.  This module builds evaluation datasets from:
  1. SessionDB — real conversation traces (preferred, highest fidelity)
  2. Synthetic — programmatically generated (task, tool) pairs per tool

Each sample is a dict with:
  task:       natural-language task description
  tool_name:  the correct tool to use
  difficulty: "easy" | "medium" | "hard" (for stratified evaluation)
  source:     "sessiondb" | "synthetic"
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.dataset_builder import EvalDataset


# ------------------------------------------------------------------
# Synthetic dataset templates per tool
# Each tool maps to a list of task-description templates
# ------------------------------------------------------------------

TOOL_TASK_TEMPLATES: Dict[str, List[str]] = {
    "read_file": [
        "Read the contents of {path}",
        "Show me what's in {path}",
        "I need to see the file at {path}",
        "Open and display {path}",
        "Cat {path}",
    ],
    "write_file": [
        "Write {content} to {path}",
        "Create a new file at {path} with the following content: {content}",
        "Save this to {path}",
        "Overwrite {path} with the provided content",
        "Write the following text to {path}: {content}",
    ],
    "terminal": [
        "Run the command {cmd}",
        "Execute {cmd} in the shell",
        "Run {cmd} and return the output",
        "Execute the shell command {cmd}",
        "Run this terminal command: {cmd}",
    ],
    "search_files": [
        "Search for the pattern {pattern} in all files under {path}",
        "Find all files containing {pattern}",
        "Grep for {pattern} in {path}",
        "Search recursively for {pattern} in {path}",
        "Find files matching {pattern}",
    ],
    "patch": [
        "Apply this patch to {path}: {patch}",
        "Replace the text {old} with {new} in {path}",
        "Edit {path} to change {old} to {new}",
        "Patch {path} with the following change",
    ],
    "delegate_task": [
        "Delegate this task to a subagent: {task}",
        "Spawn a worker agent to handle {task}",
        "Have another agent instance work on {task}",
        "Offload {task} to a subagent",
    ],
    "memory": [
        "Remember that {fact}",
        "Save this to memory: {fact}",
        "Store this persistent fact: {fact}",
        "Note that {fact}",
        "Save the following to my long-term memory: {fact}",
    ],
    "session_search": [
        "Search my conversation history for {query}",
        "Find past conversations about {query}",
        "Look up what we discussed regarding {query}",
        "Find earlier mentions of {query} in our chat history",
    ],
    "skill_manage": [
        "Create a new skill called {name}",
        "Update the skill {name} with these instructions",
        "Delete the skill {name}",
        "Patch the skill {name} with these changes",
    ],
    "skill_view": [
        "Show me the skill {name}",
        "What does the {name} skill do?",
        "Look up the {name} skill",
        "Display the contents of skill {name}",
    ],
    "skills_list": [
        "What skills are available?",
        "List all my loaded skills",
        "Show me all available skills",
        "What skills do I have access to?",
    ],
    "browser_navigate": [
        "Go to {url}",
        "Navigate to {url}",
        "Open {url} in the browser",
        "Visit {url}",
    ],
    "browser_snapshot": [
        "Take a screenshot of the current page",
        "Capture the current browser state",
        "Snapshot the browser",
        "Take a screenshot",
    ],
    "browser_vision": [
        "Describe what's on the current page",
        "What do I see in the browser?",
        "Analyze the current browser view",
        "Look at the current page and describe it",
    ],
    "browser_click": [
        "Click on the element matching {selector}",
        "Click the {selector} element",
        "Click on {selector}",
    ],
    "browser_type": [
        "Type {text} into the {selector} field",
        "Enter {text} in the {selector} input",
        "Type {text} into the {selector} element",
    ],
    "web_search": [
        "Search the web for {query}",
        "Look up {query} online",
        "Web search for {query}",
        "Search for {query}",
    ],
    "web_extract": [
        "Extract the main content from {url}",
        "Fetch and parse the article at {url}",
        "Scrape the content from {url}",
        "Extract the text from {url}",
    ],
    "cronjob": [
        "Show me my scheduled cron jobs",
        "List all cron jobs",
        "What scheduled tasks do I have?",
        "Show cron jobs",
    ],
    "clarify": [
        "Ask the user to clarify: {question}",
        "I need to ask the user: {question}",
        "Request clarification on {question}",
    ],
    "todo": [
        "Add {item} to my todo list",
        "Create a todo item: {item}",
        "Add a task: {item}",
        "Track {item} as a todo",
    ],
    "process": [
        "Check the status of background process {session_id}",
        "What is process {session_id} doing?",
        "Show output from process {session_id}",
        "Poll background task {session_id}",
    ],
    "vision_analyze": [
        "Analyze this image: {image_path}",
        "Describe what's in the image at {image_path}",
        "Look at {image_path} and tell me what you see",
    ],
    "text_to_speech": [
        "Convert this text to speech: {text}",
        "Read this aloud: {text}",
        "Generate audio from: {text}",
    ],
    "send_message": [
        "Send a message to {recipient}: {message}",
        "Message {recipient} saying {message}",
        "Send {message} to {recipient}",
    ],
    "discord": [
        "Post to Discord channel {channel}: {message}",
        "Send {message} to Discord channel {channel}",
    ],
    "discord_admin": [
        "Manage Discord: {action}",
        "Admin action in Discord: {action}",
    ],
    "ha_get_state": [
        "Get the state of HomeAssistant entity {entity_id}",
        "What is {entity_id} in HomeAssistant?",
    ],
    "ha_call_service": [
        "Call HomeAssistant service {service}",
        "Trigger {service} in HomeAssistant",
    ],
    "patch": [
        "Apply this patch to {path}",
    ],
    "execute_code": [
        "Run this Python code: {code}",
        "Execute Python code: {code}",
        "Run {code} in a Python sandbox",
    ],
    "rl_list_environments": [
        "List available RL training environments",
        "What RL environments are available?",
    ],
    "rl_start_training": [
        "Start RL training with {config}",
        "Begin a training run with config {config}",
    ],
    "rl_check_status": [
        "Check the status of RL run {run_id}",
        "How is RL training run {run_id} progressing?",
    ],
    "mixture_of_agents": [
        "Route this hard problem through multiple LLMs: {problem}",
        "Use ensemble reasoning to solve: {problem}",
    ],
}

# Harder / more ambiguous task templates that test discrimination ability
TOOL_DISCRIMINATION_TEMPLATES: Dict[str, List[str]] = {
    # Pairs of similar tools that are easy to confuse
    ("read_file", "search_files"): [
        "Find information about {topic} — first check if it's already in a file at {path}",
        "Look for {topic} in any file under {path}",
        "Search for {topic} starting from {path}",
    ],
    ("browser_navigate", "web_search"): [
        "I want to see the Stripe dashboard — navigate there or search for it",
        "Get me to the {service} login page",
    ],
    ("skill_view", "skills_list"): [
        "Show me what the {name} skill contains and also list all other skills I have",
        "What does skill {name} do, and what else is available?",
    ],
    ("session_search", "memory"): [
        "Did we discuss {topic} before? Also remember that {fact}",
        "Search for {topic} in our history and save it to memory",
    ],
    ("patch", "write_file"): [
        "Fix the typo in {path} by replacing '{old}' with '{new}'",
        "Update {path} with the corrected content: {content}",
    ],
    ("browser_vision", "browser_snapshot"): [
        "Look at the current page and tell me what you see",
        "Describe what's displayed and also take a screenshot",
    ],
}


def _build_synthetic_examples(
    tool_store, config: EvolutionConfig, num_per_tool: int = 5
) -> List[Dict[str, Any]]:
    """Generate synthetic (task, tool) examples for all tools in the store."""
    examples = []
    placeholder_values = {
        "path": ["/home/user/file.txt", "/tmp/config.yaml", "~/docs/README.md"],
        "content": ["hello world", "Hello, World!\n", "# Heading\n"],
        "cmd": ["ls -la", "find . -name '*.py'", "git status"],
        "pattern": ["TODO", "FIXME", "class.*:"],
        "old": ["old text", "v1"],
        "new": ["new text", "v2"],
        "patch": ["@@ -1,3 +1,4 @@\n+added line"],
        "task": ["debug the issue", "review this code", "analyze the results"],
        "fact": ["the user prefers short responses", "project uses pytest"],
        "query": ["debugging tips", "previous work on X"],
        "name": ["github-code-review", "systematic-debugging"],
        "url": ["https://example.com", "https://github.com/foo/bar"],
        "selector": ["button#submit", ".login-form", "//input[@id='q']"],
        "text": ["hello world", "test input"],
        "image_path": ["/tmp/screenshot.png", "~/screenshots/shot.png"],
        "recipient": ["@alice", "#general"],
        "message": ["Hello!", "Test message"],
        "channel": ["#general", "#alerts"],
        "action": ["list channels", "invite user"],
        "entity_id": ["light.living_room", "switch.desk"],
        "service": ["light.turn_on", "switch.turn_off"],
        "code": ["print('hello')", "import os\nos.listdir('.')"],
        "config": ["{\"lr\": 1e-4}", "batch_size=16"],
        "run_id": ["run_abc123", "train_xyz"],
        "problem": ["Prove that there are infinitely many primes"],
        "topic": ["logging configuration", "API keys"],
    }

    for tool_name in tool_store.tools:
        templates = TOOL_TASK_TEMPLATES.get(tool_name, [])
        if not templates:
            # Generic fallback for tools without templates
            templates = [
                f"Use the {tool_name} tool to accomplish this task",
                f"Call {tool_name} with appropriate arguments",
            ]

        for i in range(min(num_per_tool, len(templates))):
            template = templates[i % len(templates)]
            # Replace placeholders deterministically
            task = template
            for placeholder, values in placeholder_values.items():
                if f"{{{placeholder}}}" in task:
                    task = task.replace(
                        f"{{{placeholder}}}", values[i % len(values)]
                    )

            examples.append({
                "task": task,
                "tool_name": tool_name,
                "difficulty": "easy" if i < 2 else "medium",
                "source": "synthetic",
            })

    return examples


def _load_sessiondb_examples(
    config: EvolutionConfig, tool_filter: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Load real (task, tool) examples from SessionDB.

    Looks for session history files in the hermes-agent's session directory
    and extracts tool-call pairs where the task context is recoverable.
    """
    hermes_path = config.hermes_agent_path or get_hermes_agent_path()
    session_dir = hermes_path / "sessions"
    if not session_dir.exists():
        return []

    examples = []
    for session_file in sorted(session_dir.glob("*.json"))[:50]:
        try:
            data = json.loads(session_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        # Extract tool calls with preceding user message as task context
        messages = data.get("messages", [])
        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                continue

            # Use the preceding user message as task context
            task = ""
            for j in range(i - 1, -1, -1):
                if messages[j].get("role") == "user":
                    task = messages[j].get("content", "")[:200]
                    break

            if not task:
                continue

            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                if not tool_name:
                    continue
                if tool_filter and tool_name not in tool_filter:
                    continue

                examples.append({
                    "task": task,
                    "tool_name": tool_name,
                    "difficulty": "medium",
                    "source": "sessiondb",
                    "session_id": session_file.stem,
                })

    return examples


class ToolDescriptionDataset(EvalDataset):
    """Eval dataset for tool description evolution.

    Attributes:
        examples: List of dicts with task, tool_name, difficulty, source
    """

    def __init__(self, examples: List[Dict[str, Any]]):
        self.examples = examples

    def split(
        self, train_frac: float = 0.6, val_frac: float = 0.2, test_frac: float = 0.2
    ) -> tuple["ToolDescriptionDataset", "ToolDescriptionDataset", "ToolDescriptionDataset"]:
        """Split dataset into train/val/test sets."""
        assert abs(train_frac + val_frac + test_frac - 1.0) < 1e-6
        examples = list(self.examples)
        random.seed(42)
        random.shuffle(examples)

        n = len(examples)
        n_train = int(n * train_frac)
        n_val = int(n * val_frac)

        train_set = ToolDescriptionDataset(examples[:n_train])
        val_set = ToolDescriptionDataset(examples[n_train:n_train + n_val])
        test_set = ToolDescriptionDataset(examples[n_train + n_val:])
        return train_set, val_set, test_set

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, i: int) -> Dict[str, Any]:
        return self.examples[i]

    def by_difficulty(self, difficulty: str) -> "ToolDescriptionDataset":
        return ToolDescriptionDataset([
            e for e in self.examples if e.get("difficulty") == difficulty
        ])

    def by_source(self, source: str) -> "ToolDescriptionDataset":
        return ToolDescriptionDataset([
            e for e in self.examples if e.get("source") == source
        ])


def build_dataset(
    tool_store,
    config: EvolutionConfig,
    eval_source: str = "synthetic",
    sessiondb_dir: Optional[str] = None,
    num_synthetic: int = 5,
    tool_filter: Optional[List[str]] = None,
) -> ToolDescriptionDataset:
    """Build the full evaluation dataset.

    Args:
        tool_store:      ToolDescriptionStore with all tool descriptions
        config:          EvolutionConfig
        eval_source:     "synthetic", "sessiondb", or "both"
        sessiondb_dir:   Override path for session history (default: hermes/sessions)
        num_synthetic:   Synthetic examples per tool
        tool_filter:     Only include these tool names

    Returns:
        ToolDescriptionDataset with all examples
    """
    all_examples: List[Dict[str, Any]] = []

    if eval_source in ("synthetic", "both"):
        syn_examples = _build_synthetic_examples(tool_store, config, num_synthetic)
        if tool_filter:
            syn_examples = [e for e in syn_examples if e["tool_name"] in tool_filter]
        all_examples.extend(syn_examples)

    if eval_source in ("sessiondb", "both"):
        sd_examples = _load_sessiondb_examples(config, tool_filter=tool_filter)
        all_examples.extend(sd_examples)

    # Deduplicate by (task, tool_name) pair
    seen = set()
    unique = []
    for e in all_examples:
        key = (e["task"][:100], e["tool_name"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    return ToolDescriptionDataset(unique)
