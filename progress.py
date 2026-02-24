"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Progress is tracked via Linear issues, with local state cached in .linear_project.json.
"""

import json
import os
import subprocess
from pathlib import Path

from linear_config import LINEAR_PROJECT_MARKER


def load_linear_project_state(project_dir: Path) -> dict | None:
    """
    Load the Linear project state from the marker file.

    Args:
        project_dir: Directory containing .linear_project.json

    Returns:
        Project state dict or None if not initialized
    """
    marker_file = project_dir / LINEAR_PROJECT_MARKER

    if not marker_file.exists():
        return None

    try:
        with open(marker_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def is_linear_initialized(project_dir: Path) -> bool:
    """
    Check if Linear project has been initialized.

    Args:
        project_dir: Directory to check

    Returns:
        True if .linear_project.json exists and is valid
    """
    state = load_linear_project_state(project_dir)
    return state is not None and state.get("initialized", False)


def print_session_header(session_num: int, is_initializer: bool) -> None:
    """Print a formatted header for the session."""
    session_type = "INITIALIZER" if is_initializer else "CODING AGENT"

    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {session_type}")
    print("=" * 70)
    print()


def print_progress_summary(project_dir: Path) -> None:
    """
    Print a summary of current progress.

    Since actual progress is tracked in Linear, this reads the local
    state file for cached information. The agent updates Linear directly
    and reports progress in session comments.
    """
    state = load_linear_project_state(project_dir)

    if state is None:
        print("\nProgress: Linear project not yet initialized")
        return

    total = state.get("total_issues", 0)
    meta_issue = state.get("meta_issue_id", "unknown")

    print(f"\nLinear Project Status:")
    print(f"  Total issues created: {total}")
    print(f"  META issue ID: {meta_issue}")
    print(f"  (Check Linear for current Done/In Progress/Todo counts)")


def is_project_complete(project_dir: Path) -> bool:
    """
    Check if all non-META issues in the Linear project are Done.

    Queries the Linear API directly rather than relying on the agent
    to self-report completion. META issues are excluded from the check
    since they stay in Backlog as tracking issues.

    Falls back to checking .linear_project.json if the API call fails.

    Args:
        project_dir: Directory containing .linear_project.json

    Returns:
        True if all non-META issues are Done
    """
    state = load_linear_project_state(project_dir)
    if state is None:
        return False

    project_id = state.get("project_id")
    if not project_id:
        # No project ID — fall back to local flag
        return state.get("app_complete", False) is True

    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        return state.get("app_complete", False) is True

    # Query Linear for all issues in this project
    query = json.dumps({
        "query": (
            '{ issues(filter: { project: { id: { eq: "%s" } } }) '
            '{ nodes { title state { name } } } }' % project_id
        )
    })

    try:
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                "https://api.linear.app/graphql",
                "-H", f"Authorization: {api_key}",
                "-H", "Content-Type: application/json",
                "-d", query,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return state.get("app_complete", False) is True

        data = json.loads(result.stdout)
        issues = data.get("data", {}).get("issues", {}).get("nodes", [])

        if not issues:
            return False

        # Filter out META issues and check if all remaining are Done
        non_meta = [i for i in issues if not i["title"].startswith("[META]")]

        if not non_meta:
            return False

        all_done = all(i["state"]["name"] == "Done" for i in non_meta)

        if all_done:
            done_count = len(non_meta)
            print(f"\n  Linear check: {done_count}/{done_count} non-META issues Done")

        return all_done

    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        # API failed — fall back to local flag
        return state.get("app_complete", False) is True
