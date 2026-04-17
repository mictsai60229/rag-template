"""
workflow.py — LangGraph multi-agent orchestration for Claude Code agents.

Usage:
    # Start a new workflow
    python scripts/workflow.py "Build a blog platform with auth, posts, and comments"

    # Resume an interrupted workflow (human-in-the-loop or blocker)
    python scripts/workflow.py --resume <thread-id>

    # Override default retry limit
    python scripts/workflow.py "..." --max-retries 5

Workflow phases:
  1. project-manager   → docs/prd.md          → human approval
  2. system-architecture → docs/sad.md        → human approval
  3. project-planner   → docs/plans/*.md
  4. coding loop       → for each plan:
       coding-agent (internally calls reviewer-agent)
       → read .review.md → PUSH | FIX_NEEDED
       → retry up to max_retries, then human escalation
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import uuid
from typing import Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from typing_extensions import TypedDict

from agents import invoke_claude_agent
from plan_parser import discover_plans

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.expanduser("~/.claude/workflow_state.db")

console = Console()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class WorkflowState(TypedDict, total=False):
    project_description: str
    phase: str                       # "prd" | "sad" | "planning" | "coding" | "done"
    error_message: Optional[str]
    human_feedback: Optional[str]

    # Phase 1 — PRD
    prd_session_id: str
    prd_approved: bool

    # Phase 2 — SAD
    sad_session_id: str
    sad_approved: bool

    # Phase 3 — Planning
    planner_session_id: str

    # Phase 4 — Coding loop
    plans: list[str]                 # ordered absolute paths
    current_plan_idx: int
    retry_count: int                 # incremented after each failed review
    max_retries: int                 # set at startup
    coding_session_id: Optional[str]  # reused across retries of same plan
    initial_sha: Optional[str]        # git HEAD before coding starts
    review_decision: Optional[str]    # "PUSH" | "FIX_NEEDED"
    review_feedback: Optional[str]    # findings from .review.md
    blocker_action: Optional[str]     # "retry" | "skip"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _review_path(plan_path: str) -> str:
    """Convert docs/plans/foo-plan-1.md → docs/plans/foo-plan-1.review.md"""
    return re.sub(r"\.md$", ".review.md", plan_path)


def parse_review_file(review_path: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse a reviewer-agent .review.md file.

    Returns:
        (decision, feedback_text)
        decision is "PUSH" | "FIX_NEEDED" | None (if file missing / unparseable)
        feedback_text is the Findings section text, or None
    """
    if not os.path.isfile(review_path):
        return None, None

    content = open(review_path, encoding="utf-8").read()

    # Match: "## Decision\nPUSH"  or  "Decision: FIX_NEEDED"  or  "**Decision:** PUSH"
    m = re.search(
        r"##\s*Decision\s*\n+([A-Z_]+)"
        r"|Decision[:\s*]+([A-Z_]+)",
        content,
        re.IGNORECASE,
    )
    if not m:
        return None, None

    raw = ((m.group(1) or m.group(2)) or "").strip().upper()
    if raw not in ("PUSH", "FIX_NEEDED"):
        return None, None

    # Extract the findings block for feedback on retries
    fm = re.search(
        r"##\s*Findings Requiring Coding-Agent Fix\s*\n+(.*?)(?=\n##|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    feedback = fm.group(1).strip() if fm else None
    return raw, feedback


def _git_head_sha() -> str:
    """Return current HEAD SHA, or sentinel 'ROOT' for repos with no commits."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "ROOT"


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _prd_prompt(description: str, feedback: Optional[str]) -> str:
    base = (
        f"Create a comprehensive Product Requirements Document for the following project "
        f"and write it to docs/prd.md.\n\nProject description: {description}"
    )
    if feedback:
        base += (
            f"\n\nThe previous version was rejected. "
            f"Please address all of the following feedback before writing the new version:\n{feedback}"
        )
    return base


def _sad_prompt(description: str, feedback: Optional[str]) -> str:
    base = (
        "Read docs/prd.md and produce a System Architecture Document. "
        "Write the output to docs/sad.md.\n\n"
        f"Project description (for context): {description}"
    )
    if feedback:
        base += (
            f"\n\nThe previous version was rejected. "
            f"Please address all of the following feedback:\n{feedback}"
        )
    return base


def _planner_prompt(description: str) -> str:
    return (
        "Read docs/prd.md and docs/sad.md, then plan the full project. "
        "Write all output (init-plan.md and per-system plan files) to docs/. "
        f"Project description (for context): {description}"
    )


def _coding_prompt(
    plan_path: str,
    initial_sha: str,
    feedback: Optional[str],
) -> str:
    base = (
        f"Implement the plan at {plan_path}.\n"
        f"Record this as the initial SHA for your git range: {initial_sha}"
    )
    if feedback:
        base += (
            f"\n\nThe previous attempt was rejected by the reviewer. "
            f"Address all of the following issues before proceeding:\n{feedback}"
        )
    return base


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def run_project_manager(state: WorkflowState) -> dict:
    session_id = state.get("prd_session_id") or str(uuid.uuid4())
    console.print("[yellow]Phase 1:[/yellow] Running project-manager agent…")

    prompt = _prd_prompt(
        state["project_description"],
        state.get("human_feedback"),
    )
    _, stderr, rc = invoke_claude_agent(
        agent_name="project-manager",
        prompt=prompt,
        session_id=session_id,
        cwd=REPO_ROOT,
        timeout=900,
    )
    if rc != 0:
        console.print(f"[red]project-manager failed (rc={rc})[/red]")
        return {
            "prd_session_id": session_id,
            "error_message": f"project-manager failed (rc={rc}): {stderr[:500]}",
            "phase": "prd",
        }
    console.print("[green]PRD written to docs/prd.md[/green]")
    return {
        "prd_session_id": session_id,
        "error_message": None,
        "human_feedback": None,
        "phase": "prd",
    }


def await_prd_approval(state: WorkflowState) -> dict:
    prd_path = os.path.join(REPO_ROOT, "docs", "prd.md")
    response = interrupt({
        "type": "prd_approval",
        "file": prd_path,
        "message": f"PRD written to {prd_path}. Open the file, review it, then approve or reject.",
    })
    if response.get("action") == "approve":
        return {"prd_approved": True, "human_feedback": None}
    return {"prd_approved": False, "human_feedback": response.get("feedback", "")}


def run_system_architecture(state: WorkflowState) -> dict:
    session_id = state.get("sad_session_id") or str(uuid.uuid4())
    console.print("[yellow]Phase 2:[/yellow] Running system-architecture agent…")

    prompt = _sad_prompt(
        state["project_description"],
        state.get("human_feedback"),
    )
    _, stderr, rc = invoke_claude_agent(
        agent_name="system-architecture",
        prompt=prompt,
        session_id=session_id,
        cwd=REPO_ROOT,
        timeout=900,
    )
    if rc != 0:
        console.print(f"[red]system-architecture failed (rc={rc})[/red]")
        return {
            "sad_session_id": session_id,
            "error_message": f"system-architecture failed (rc={rc}): {stderr[:500]}",
            "phase": "sad",
        }
    console.print("[green]SAD written to docs/sad.md[/green]")
    return {
        "sad_session_id": session_id,
        "error_message": None,
        "human_feedback": None,
        "phase": "sad",
    }


def await_sad_approval(state: WorkflowState) -> dict:
    sad_path = os.path.join(REPO_ROOT, "docs", "sad.md")
    response = interrupt({
        "type": "sad_approval",
        "file": sad_path,
        "message": f"SAD written to {sad_path}. Open the file, review it, then approve or reject.",
    })
    if response.get("action") == "approve":
        return {"sad_approved": True, "human_feedback": None}
    return {"sad_approved": False, "human_feedback": response.get("feedback", "")}


def run_project_planner(state: WorkflowState) -> dict:
    session_id = state.get("planner_session_id") or str(uuid.uuid4())
    console.print("[yellow]Phase 3:[/yellow] Running project-planner agent…")

    _, stderr, rc = invoke_claude_agent(
        agent_name="project-planner",
        prompt=_planner_prompt(state["project_description"]),
        session_id=session_id,
        cwd=REPO_ROOT,
        timeout=1200,
    )
    if rc != 0:
        console.print(f"[red]project-planner failed (rc={rc})[/red]")
        return {
            "planner_session_id": session_id,
            "error_message": f"project-planner failed (rc={rc}): {stderr[:500]}",
            "phase": "planning",
        }
    console.print("[green]Plans written to docs/[/green]")
    return {
        "planner_session_id": session_id,
        "error_message": None,
        "phase": "planning",
    }


def parse_plans(state: WorkflowState) -> dict:
    plans = discover_plans(REPO_ROOT)
    if plans:
        console.print(f"[green]Found {len(plans)} plan(s):[/green]")
        for p in plans:
            console.print(f"  • {os.path.relpath(p, REPO_ROOT)}")
    else:
        console.print("[yellow]No plan files found under docs/. Nothing to implement.[/yellow]")
    return {
        "plans": plans,
        "current_plan_idx": 0,
        "retry_count": 0,
        "phase": "coding",
    }


def prepare_coding(state: WorkflowState) -> dict:
    initial_sha = _git_head_sha()
    retry_count = state.get("retry_count", 0)

    # New session per plan; reuse session across retries of the same plan
    if retry_count == 0 or not state.get("coding_session_id"):
        coding_session_id = str(uuid.uuid4())
    else:
        coding_session_id = state["coding_session_id"]

    plan_path = state["plans"][state["current_plan_idx"]]
    rel = os.path.relpath(plan_path, REPO_ROOT)
    attempt = retry_count + 1
    console.print(
        f"[yellow]Phase 4:[/yellow] Plan [cyan]{rel}[/cyan] — attempt {attempt}"
    )
    return {
        "initial_sha": initial_sha,
        "coding_session_id": coding_session_id,
    }


def run_coding_agent(state: WorkflowState) -> dict:
    plan_path = state["plans"][state["current_plan_idx"]]
    feedback = state.get("human_feedback") or state.get("review_feedback")

    console.print(
        f"  [dim]→[/dim] coding-agent on [cyan]{os.path.relpath(plan_path, REPO_ROOT)}[/cyan]…"
    )
    _, stderr, rc = invoke_claude_agent(
        agent_name="coding-agent",
        prompt=_coding_prompt(plan_path, state.get("initial_sha", "ROOT"), feedback),
        session_id=state["coding_session_id"],
        cwd=REPO_ROOT,
        timeout=3600,
    )
    if rc != 0:
        return {
            "error_message": f"coding-agent failed (rc={rc}): {stderr[:500]}",
        }
    return {"error_message": None, "human_feedback": None}


def run_reviewer_agent(state: WorkflowState) -> dict:
    """
    Does NOT invoke the reviewer CLI — the coding-agent already runs it
    internally as a sub-agent and writes the .review.md file.
    This node reads that file and extracts the Decision.
    """
    plan_path = state["plans"][state["current_plan_idx"]]
    review_path = _review_path(plan_path)
    rel = os.path.relpath(review_path, REPO_ROOT)

    decision, feedback = parse_review_file(review_path)

    if decision is None:
        console.print(f"  [red]Review file missing or unparseable:[/red] {rel}")
        return {
            "review_decision": "FIX_NEEDED",
            "review_feedback": f"Review file not found or missing Decision field: {review_path}",
        }

    icon = "[green]PUSH[/green]" if decision == "PUSH" else "[red]FIX_NEEDED[/red]"
    console.print(f"  [dim]→[/dim] Review decision: {icon}")
    return {
        "review_decision": decision,
        "review_feedback": feedback,
    }


def increment_retry(state: WorkflowState) -> dict:
    return {"retry_count": state.get("retry_count", 0) + 1}


def advance_plan(state: WorkflowState) -> dict:
    new_idx = state["current_plan_idx"] + 1
    total = len(state["plans"])
    if new_idx < total:
        rel = os.path.relpath(state["plans"][new_idx], REPO_ROOT)
        console.print(f"[green]Plan complete. Next:[/green] {rel}")
    else:
        console.print("[bold green]All plans complete![/bold green]")
    return {
        "current_plan_idx": new_idx,
        "retry_count": 0,
        "coding_session_id": None,
        "review_decision": None,
        "review_feedback": None,
        "human_feedback": None,
        "initial_sha": None,
        "error_message": None,
        "blocker_action": None,
    }


def await_blocker(state: WorkflowState) -> dict:
    plan_path = state["plans"][state["current_plan_idx"]]
    review_path = _review_path(plan_path)
    response = interrupt({
        "type": "blocker",
        "plan": os.path.relpath(plan_path, REPO_ROOT),
        "review_file": os.path.relpath(review_path, REPO_ROOT),
        "retry_count": state.get("retry_count", 0),
        "max_retries": state.get("max_retries", 3),
        "message": (
            f"Max retries ({state.get('max_retries', 3)}) reached for "
            f"{os.path.relpath(plan_path, REPO_ROOT)}. "
            f"Review {os.path.relpath(review_path, REPO_ROOT)} and provide guidance."
        ),
        "error": state.get("error_message"),
        "review_feedback": state.get("review_feedback"),
    })
    if response.get("action") == "skip":
        return {
            "blocker_action": "skip",
            "human_feedback": None,
        }
    return {
        "blocker_action": "retry",
        "retry_count": 0,
        "coding_session_id": None,   # fresh session with human guidance in prompt
        "human_feedback": response.get("feedback", ""),
    }


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------


def _route_prd(state: WorkflowState) -> str:
    return "run_system_architecture" if state.get("prd_approved") else "run_project_manager"


def _route_sad(state: WorkflowState) -> str:
    return "run_project_planner" if state.get("sad_approved") else "run_system_architecture"


def _route_after_plans(state: WorkflowState) -> str:
    return "prepare_coding" if state.get("plans") else END


def _route_review(state: WorkflowState) -> str:
    decision = state.get("review_decision")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if decision == "PUSH":
        return "advance_plan"
    if retry_count > max_retries:
        return "await_blocker"
    return "prepare_coding"


def _route_after_advance(state: WorkflowState) -> str:
    idx = state.get("current_plan_idx", 0)
    plans = state.get("plans", [])
    return "prepare_coding" if idx < len(plans) else END


def _route_after_blocker(state: WorkflowState) -> str:
    return "advance_plan" if state.get("blocker_action") == "skip" else "prepare_coding"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph():
    builder = StateGraph(WorkflowState)

    builder.add_node("run_project_manager", run_project_manager)
    builder.add_node("await_prd_approval", await_prd_approval)
    builder.add_node("run_system_architecture", run_system_architecture)
    builder.add_node("await_sad_approval", await_sad_approval)
    builder.add_node("run_project_planner", run_project_planner)
    builder.add_node("parse_plans", parse_plans)
    builder.add_node("prepare_coding", prepare_coding)
    builder.add_node("run_coding_agent", run_coding_agent)
    builder.add_node("run_reviewer_agent", run_reviewer_agent)
    builder.add_node("increment_retry", increment_retry)
    builder.add_node("advance_plan", advance_plan)
    builder.add_node("await_blocker", await_blocker)

    # Linear edges
    builder.add_edge(START, "run_project_manager")
    builder.add_edge("run_project_manager", "await_prd_approval")
    builder.add_edge("run_system_architecture", "await_sad_approval")
    builder.add_edge("run_project_planner", "parse_plans")
    builder.add_edge("prepare_coding", "run_coding_agent")
    builder.add_edge("run_coding_agent", "run_reviewer_agent")
    builder.add_edge("run_reviewer_agent", "increment_retry")

    # Conditional edges
    builder.add_conditional_edges("await_prd_approval", _route_prd)
    builder.add_conditional_edges("await_sad_approval", _route_sad)
    builder.add_conditional_edges("parse_plans", _route_after_plans)
    builder.add_conditional_edges(
        "increment_retry",
        _route_review,
        {
            "advance_plan": "advance_plan",
            "prepare_coding": "prepare_coding",
            "await_blocker": "await_blocker",
        },
    )
    builder.add_conditional_edges("advance_plan", _route_after_advance)
    builder.add_conditional_edges(
        "await_blocker",
        _route_after_blocker,
        {
            "prepare_coding": "prepare_coding",
            "advance_plan": "advance_plan",
        },
    )

    checkpointer = SqliteSaver.from_conn_string(DB_PATH)
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Rich human-in-the-loop prompt handlers
# ---------------------------------------------------------------------------


def _handle_approval_interrupt(interrupt_data: dict) -> dict:
    file_path = interrupt_data.get("file", "")
    itype = interrupt_data.get("type", "")
    label = "PRD" if itype == "prd_approval" else "SAD"

    console.print(
        Panel(
            f"[bold yellow]Human Review Required — {label}[/bold yellow]\n\n"
            f"File: [cyan]{file_path}[/cyan]\n\n"
            f"{interrupt_data.get('message', '')}",
            title=f"[bold]Approval Gate: {label}[/bold]",
            border_style="yellow",
        )
    )
    approved = Confirm.ask(f"Approve the {label}?", default=False)
    if approved:
        return {"action": "approve"}
    feedback = Prompt.ask(f"Rejection feedback (sent to the {label} agent)")
    return {"action": "reject", "feedback": feedback}


def _handle_blocker_interrupt(interrupt_data: dict) -> dict:
    console.print(
        Panel(
            f"[bold red]Blocker: Max Retries Reached[/bold red]\n\n"
            f"Plan:        [cyan]{interrupt_data.get('plan', '')}[/cyan]\n"
            f"Review file: [cyan]{interrupt_data.get('review_file', '')}[/cyan]\n"
            f"Retries:     {interrupt_data.get('retry_count', 0)} / "
            f"{interrupt_data.get('max_retries', 3)}\n\n"
            f"[yellow]{interrupt_data.get('message', '')}[/yellow]\n\n"
            + (
                f"[dim]Last review feedback:[/dim]\n{interrupt_data['review_feedback']}"
                if interrupt_data.get("review_feedback")
                else ""
            ),
            title="[bold]Manual Intervention Required[/bold]",
            border_style="red",
        )
    )
    action = Prompt.ask("Action", choices=["retry", "skip"], default="retry")
    if action == "retry":
        guidance = Prompt.ask("Guidance for coding-agent (describe what needs to change)")
        return {"action": "retry", "feedback": guidance}
    return {"action": "skip"}


def dispatch_interrupt(interrupt_data: dict) -> dict:
    itype = interrupt_data.get("type")
    if itype in ("prd_approval", "sad_approval"):
        return _handle_approval_interrupt(interrupt_data)
    if itype == "blocker":
        return _handle_blocker_interrupt(interrupt_data)
    raise ValueError(f"Unknown interrupt type: {itype!r}")


# ---------------------------------------------------------------------------
# Graph driver loop
# ---------------------------------------------------------------------------


def run_graph_loop(
    graph,
    config: dict,
    initial_input,
):
    """Drive the graph to completion, handling interrupts interactively."""
    current_input = initial_input

    while True:
        for _ in graph.stream(current_input, config, stream_mode="values"):
            pass  # progress is printed inside each node

        state = graph.get_state(config)

        if not state.next:
            console.print(
                Panel(
                    "[bold green]Workflow complete! All plans implemented and pushed.[/bold green]",
                    border_style="green",
                )
            )
            break

        # Collect interrupt data from the suspended node
        tasks = state.tasks
        if not tasks or not tasks[0].interrupts:
            console.print(
                "[red]Graph stopped unexpectedly (no interrupt data). "
                "Check agent output above for errors.[/red]"
            )
            sys.exit(1)

        interrupt_data = tasks[0].interrupts[0].value
        resume_data = dispatch_interrupt(interrupt_data)
        current_input = Command(resume=resume_data)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LangGraph orchestrator for Claude Code multi-agent workflows.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python scripts/workflow.py "Build a blog platform"\n'
            "  python scripts/workflow.py --resume 3f8a1c2d-...\n"
        ),
    )
    parser.add_argument(
        "project_description",
        nargs="?",
        help="Project description (required for new runs)",
    )
    parser.add_argument(
        "--resume",
        metavar="THREAD_ID",
        help="Resume an interrupted workflow by thread ID",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        metavar="N",
        help="Max coding-agent retries per plan before human escalation (default: 3)",
    )
    args = parser.parse_args()

    graph = build_graph()

    if args.resume:
        thread_id = args.resume
        config = {"configurable": {"thread_id": thread_id}}
        console.print(
            Panel(
                f"[bold cyan]Resuming workflow[/bold cyan]\nThread: [dim]{thread_id}[/dim]",
                border_style="cyan",
            )
        )

        state = graph.get_state(config)
        if not state.next:
            console.print("[yellow]This workflow is already complete or was never started.[/yellow]")
            sys.exit(0)

        tasks = state.tasks
        if not tasks or not tasks[0].interrupts:
            console.print(
                "[red]No interrupt found in saved state. "
                "The workflow may need to be restarted from scratch.[/red]"
            )
            sys.exit(1)

        interrupt_data = tasks[0].interrupts[0].value
        resume_data = dispatch_interrupt(interrupt_data)
        run_graph_loop(graph, config, Command(resume=resume_data))

    else:
        if not args.project_description:
            parser.error(
                "project_description is required when starting a new workflow. "
                "Use --resume <thread-id> to resume an existing one."
            )

        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        console.print(
            Panel(
                f"[bold green]Starting new workflow[/bold green]\n\n"
                f"Project: [cyan]{args.project_description}[/cyan]\n"
                f"Thread:  [dim]{thread_id}[/dim]\n\n"
                f"[yellow]Save this thread ID — use it to resume if the process is interrupted:[/yellow]\n"
                f"  python scripts/workflow.py --resume {thread_id}",
                title="[bold]Coding Agent Orchestrator[/bold]",
                border_style="green",
            )
        )

        initial_state: WorkflowState = {
            "project_description": args.project_description,
            "max_retries": args.max_retries,
            "prd_approved": False,
            "sad_approved": False,
            "retry_count": 0,
            "current_plan_idx": 0,
            "plans": [],
        }

        run_graph_loop(graph, config, initial_state)


if __name__ == "__main__":
    main()
