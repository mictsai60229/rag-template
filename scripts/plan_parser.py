"""
plan_parser.py — Discover and order plan files for the coding loop.

Execution order:
  1. docs/init-plan.md   (if it exists — project scaffolding/setup)
  2. docs/plans/*.md     (alphabetically sorted, excluding *.review.md files)
"""

from __future__ import annotations

import glob
import os


def discover_plans(repo_root: str) -> list[str]:
    """
    Return absolute paths of plan files in execution order.

    Args:
        repo_root: Absolute path to the repository root.

    Returns:
        Ordered list of plan file paths. Empty list if no plans exist yet.
    """
    plans: list[str] = []

    # 1. init-plan.md runs first (project bootstrap / scaffolding)
    init_plan = os.path.join(repo_root, "docs", "init-plan.md")
    if os.path.isfile(init_plan):
        plans.append(init_plan)

    # 2. Per-system plans, alphabetically sorted
    #    Sorting gives correct order: backend-plan-1.md < backend-plan-2.md < frontend-plan.md
    plans_dir = os.path.join(repo_root, "docs", "plans")
    all_md = sorted(glob.glob(os.path.join(plans_dir, "*.md")))
    plans.extend(p for p in all_md if not p.endswith(".review.md"))

    return plans
