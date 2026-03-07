"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Progress is tracked via Linear issues, with local state cached in .linear_project.json.
Epic state is persisted in claude-progress.txt alongside existing session state.
"""

import fcntl
import json
import logging
import os
import subprocess
from pathlib import Path

from linear_config import LINEAR_PROJECT_MARKER

logger = logging.getLogger(__name__)


def acquire_harness_lock(project_dir: Path) -> object:
    """
    Acquire an exclusive lock for the harness on this project directory.
    Prevents concurrent harness runs from corrupting state.
    Returns the lock file descriptor (keep a reference to prevent GC).
    """
    lock_path = project_dir / ".harness.lock"
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fd.close()
        print(f"\n  Another harness instance is running for {project_dir}.")
        print("  Wait for it to finish or delete .harness.lock if it crashed.\n")
        raise SystemExit(1)
    return fd


# ---------------------------------------------------------------------------
# Epic state constants
# ---------------------------------------------------------------------------
EPIC_STATE_START = "=== EPIC STATE ==="
EPIC_STATE_END = "=== END EPIC STATE ==="


# ---------------------------------------------------------------------------
# Existing functions (unchanged)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Epic state: read/write from claude-progress.txt
# ---------------------------------------------------------------------------

def _progress_file(project_dir: Path) -> Path:
    return project_dir / "claude-progress.txt"


def _read_epic_state(project_dir: Path) -> dict:
    """Read the epic state section from claude-progress.txt, or return defaults."""
    defaults = {
        "current_epic": None,
        "current_epic_name": None,
        "linear_project_id": None,
        "epic_status": {},
        "human_gate_issue_id": None,
    }

    pf = _progress_file(project_dir)
    # Clean up stale temp file from a previous crash
    stale_tmp = pf.with_suffix(".tmp")
    if stale_tmp.exists():
        stale_tmp.unlink()
    if not pf.exists():
        return defaults

    content = pf.read_text()
    if EPIC_STATE_START not in content:
        return defaults

    # Extract the section between markers
    start = content.index(EPIC_STATE_START) + len(EPIC_STATE_START)
    end = content.index(EPIC_STATE_END) if EPIC_STATE_END in content else len(content)
    section = content[start:end].strip()

    state = dict(defaults)
    for line in section.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if key == "current_epic":
            state["current_epic"] = int(value) if value != "null" else None
        elif key == "current_epic_name":
            state["current_epic_name"] = value if value != "null" else None
        elif key == "linear_project_id":
            state["linear_project_id"] = value if value != "null" else None
        elif key == "epic_status":
            try:
                state["epic_status"] = json.loads(value) if value != "{}" else {}
            except json.JSONDecodeError:
                logger.warning(
                    "Corrupt epic_status in claude-progress.txt — resetting to empty. "
                    "Re-run will restart from the current epic."
                )
                state["epic_status"] = {}
        elif key == "human_gate_issue_id":
            state["human_gate_issue_id"] = value if value != "null" else None

    return state


def _write_epic_state(project_dir: Path, state: dict) -> None:
    """Write the epic state section into claude-progress.txt."""
    pf = _progress_file(project_dir)

    # Build the epic state block
    block_lines = [
        EPIC_STATE_START,
        f"current_epic: {state['current_epic'] if state['current_epic'] is not None else 'null'}",
        f"current_epic_name: {state['current_epic_name'] if state['current_epic_name'] is not None else 'null'}",
        f"linear_project_id: {state['linear_project_id'] if state['linear_project_id'] is not None else 'null'}",
        f"epic_status: {json.dumps(state['epic_status'])}",
        f"human_gate_issue_id: {state['human_gate_issue_id'] if state['human_gate_issue_id'] is not None else 'null'}",
        EPIC_STATE_END,
    ]
    block = "\n".join(block_lines)

    if pf.exists():
        content = pf.read_text()
        if EPIC_STATE_START in content:
            # Replace existing section
            start = content.index(EPIC_STATE_START)
            end_marker = EPIC_STATE_END
            if end_marker in content:
                end = content.index(end_marker) + len(end_marker)
            else:
                end = len(content)
            content = content[:start] + block + content[end:]
        else:
            # Append the section
            content = content.rstrip() + "\n\n" + block + "\n"
    else:
        content = block + "\n"

    tmp = pf.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, pf)


# ---------------------------------------------------------------------------
# Epic state: public API
# ---------------------------------------------------------------------------

def set_current_epic(project_dir: Path, epic_number: int, epic_name: str) -> None:
    """Mark an epic as in_progress and update current epic state."""
    state = _read_epic_state(project_dir)
    state["current_epic"] = epic_number
    state["current_epic_name"] = epic_name
    state["epic_status"][str(epic_number)] = "in_progress"
    _write_epic_state(project_dir, state)


def mark_epic_complete(project_dir: Path, epic_number: int) -> None:
    """Mark an epic complete and clear current_epic_number."""
    state = _read_epic_state(project_dir)
    state["epic_status"][str(epic_number)] = "complete"
    state["current_epic"] = None
    state["current_epic_name"] = None
    state["linear_project_id"] = None
    _write_epic_state(project_dir, state)


def set_human_gate(project_dir: Path, issue_id: str) -> None:
    """Record the human gate issue ID — harness will poll this."""
    state = _read_epic_state(project_dir)
    state["human_gate_issue_id"] = issue_id
    _write_epic_state(project_dir, state)


def clear_human_gate(project_dir: Path) -> None:
    """Clear the human gate once resolved."""
    state = _read_epic_state(project_dir)
    state["human_gate_issue_id"] = None
    _write_epic_state(project_dir, state)


def set_linear_project_id(project_dir: Path, project_id: str) -> None:
    """Store the Linear project ID for the current epic."""
    state = _read_epic_state(project_dir)
    state["linear_project_id"] = project_id
    _write_epic_state(project_dir, state)


def get_linear_project_id(project_dir: Path) -> str | None:
    """Retrieve the stored Linear project ID for the current epic."""
    state = _read_epic_state(project_dir)
    return state["linear_project_id"]


def get_human_gate_issue_id(project_dir: Path) -> str | None:
    """Retrieve the stored human gate issue ID."""
    state = _read_epic_state(project_dir)
    return state["human_gate_issue_id"]


def get_next_pending_epic(project_dir: Path) -> int | None:
    """Return the number of the next epic with status 'pending', or None if all complete."""
    state = _read_epic_state(project_dir)
    index = load_epic_index(project_dir)

    for epic in index:
        num = str(epic["number"])
        status = state["epic_status"].get(num, "pending")
        if status == "pending":
            return epic["number"]

    return None


def load_epic_index(project_dir: Path) -> list[dict]:
    """
    Read epics/spec_index.json and return the list of epic entries.

    Each entry: {"number": 1, "name": "foundation", "spec_file": "epics/epic-01-foundation.md", ...}
    """
    index_path = project_dir / "epics" / "spec_index.json"
    if not index_path.exists():
        raise FileNotFoundError(
            f"spec_index.json not found at {index_path}. "
            "Run generate_epics.py first to create the epic specs."
        )

    try:
        with open(index_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"spec_index.json is malformed: {e} — re-run generate_epics.py to regenerate") from e

    if not isinstance(data, list):
        raise ValueError(f"spec_index.json must be a JSON array, got {type(data)} — re-run generate_epics.py to regenerate")

    required_keys = {"number", "name", "spec_file"}
    for i, item in enumerate(data):
        missing = required_keys - set(item.keys())
        if missing:
            raise ValueError(
                f"spec_index.json entry {i} is missing required keys: {missing} — re-run generate_epics.py to regenerate"
            )
    return data


def get_epic_by_number(project_dir: Path, epic_number: int) -> dict | None:
    """Look up an epic entry by number from the index."""
    index = load_epic_index(project_dir)
    for epic in index:
        if epic["number"] == epic_number:
            return epic
    return None
