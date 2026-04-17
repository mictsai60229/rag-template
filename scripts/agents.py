"""
agents.py — Claude CLI subprocess wrapper.

Invokes named Claude Code agents via the `claude` CLI in non-interactive (-p) mode.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional

CLAUDE_BIN: Optional[str] = shutil.which("claude")
if CLAUDE_BIN is None:
    raise RuntimeError(
        "claude CLI not found in PATH. "
        "Install Claude Code: https://claude.ai/code"
    )


def invoke_claude_agent(
    agent_name: str,
    prompt: str,
    session_id: str,
    cwd: str,
    timeout: int = 1800,
) -> tuple[str, str, int]:
    """
    Invoke a Claude Code agent via the CLI.

    Args:
        agent_name:  Name matching a .claude/agents/<name>.md definition.
        prompt:      User-turn message passed to the agent.
        session_id:  UUID string for session continuity across retries.
        cwd:         Working directory (should be the repo root).
        timeout:     Subprocess timeout in seconds (default 30 min).

    Returns:
        (stdout, stderr, returncode)

    Raises:
        TimeoutError: If the subprocess exceeds `timeout`.
    """
    cmd = [
        CLAUDE_BIN,
        "--agent", agent_name,
        "--session-id", session_id,
        "--permission-mode", "bypassPermissions",
        "-p", prompt,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        raise TimeoutError(
            f"Agent '{agent_name}' timed out after {timeout}s. "
            "Consider increasing the timeout or breaking the plan into smaller pieces."
        )
