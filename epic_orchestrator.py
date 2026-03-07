"""
Epic Orchestration Loop
=======================

Multi-epic orchestration that wraps the existing session loop.
Python is responsible for gathering state and injecting it as facts —
the agent is responsible for reasoning and implementation only.
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Optional

from agent import run_agent_session, run_epic_initializer_session, AUTO_CONTINUE_DELAY_SECONDS
from client import create_client
from discovery import discover_user_ecosystem, print_discovery_summary
from linear_client import (
    get_current_issue,
    get_human_gate_issue,
    is_human_gate_resolved,
    get_all_issues_complete,
    get_snapshot_issue,
)
from progress import (
    acquire_harness_lock,
    load_epic_index,
    get_epic_by_number,
    get_next_pending_epic,
    get_human_gate_issue_id,
    get_linear_project_id,
    set_human_gate,
    clear_human_gate,
    mark_epic_complete,
    print_session_header,
)
from prompts import get_coding_prompt, build_coding_agent_session_prompt
from security import configure_allowed_commands

MAX_ISSUE_RETRIES = 3


async def _run_coding_loop(
    project_dir: Path,
    project_id: str,
    epic_number: int,
    epic_name: str,
    model: str,
    ecosystem: dict,
    max_iterations: int | None,
    base_prompt: str,
) -> tuple[int, bool]:
    """
    Run the coding agent loop for a single epic.
    Returns (issues_resolved, should_stop).
    should_stop=True means the harness should halt entirely.
    """
    iteration = 0
    epic_issues_resolved = 0
    issue_retry_counts: dict[str, int] = {}
    no_issue_retry_count = 0
    MAX_NO_ISSUE_RETRIES = 50

    while True:
        iteration += 1

        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations}) for epic {epic_number}")
            print("Re-run to continue.")
            return (0, True)

        # Fetch the current issue from Linear
        current_issue = get_current_issue(project_id)

        if current_issue is None:
            # All regular issues done — check for human gate
            gate_issue = get_human_gate_issue(project_id)
            if gate_issue and gate_issue["state"]["type"] != "completed":
                gate_id = gate_issue["id"]
                set_human_gate(project_dir, gate_id)
                _print_human_gate_pause_detail(
                    epic_number, gate_issue.get("description", ""), project_dir
                )
                return (0, True)

            # No more eligible issues — check if all complete
            if get_all_issues_complete(project_id):
                # Run snapshot session before marking epic complete
                snapshot_issue = get_snapshot_issue(project_id)
                if snapshot_issue and snapshot_issue["state"]["type"] != "completed":
                    print(f"\n  Running Snapshot session for Epic {epic_number}...")
                    snapshot_prompt = build_coding_agent_session_prompt(
                        project_dir, snapshot_issue, base_prompt
                    )
                    snapshot_client = create_client(
                        project_dir, model, mode="greenfield", ecosystem=ecosystem,
                        session_type="coding",
                    )
                    async with snapshot_client:
                        await run_agent_session(snapshot_client, snapshot_prompt, project_dir)

                epic_issues_resolved = iteration - 1  # approximate
                return (epic_issues_resolved, False)
            else:
                # Issues exist but none are eligible (all gates/snapshots?)
                no_issue_retry_count += 1
                if no_issue_retry_count > MAX_NO_ISSUE_RETRIES:
                    print(f"\n  No eligible issues found after {MAX_NO_ISSUE_RETRIES} attempts.")
                    print("  Check Linear for stuck issues or run with --verbose for details.")
                    return (0, True)
                print("  No eligible issues found but epic not complete. Retrying...")
                await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)
                continue

        issue_id = current_issue["id"]
        no_issue_retry_count = 0  # Reset when we find an eligible issue
        issue_retry_counts[issue_id] = issue_retry_counts.get(issue_id, 0) + 1

        if issue_retry_counts[issue_id] > MAX_ISSUE_RETRIES:
            print(f"\n  ❌ Issue '{current_issue['title']}' has failed {MAX_ISSUE_RETRIES} times.")
            print(f"  Fix the issue in Linear or re-run to retry from scratch.")
            print(f"  Stopping harness to prevent infinite loop.\n")
            return (0, True)

        # Build the prompt with injected context
        prompt = build_coding_agent_session_prompt(
            project_dir, current_issue, base_prompt
        )

        print_session_header(iteration, False)
        print(f"  Epic {epic_number}: {epic_name}")
        print(f"  Issue: {current_issue['title']}")
        print()

        # Create client and run session
        client = create_client(
            project_dir, model, mode="greenfield", ecosystem=ecosystem,
            session_type="coding",
        )

        async with client:
            status, response = await run_agent_session(client, prompt, project_dir)

        if status == "error":
            print("\nSession encountered an error. Will retry...")

        await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)


async def run_epic_mode(
    project_dir: Path,
    model: str,
    max_iterations: Optional[int] = None,
) -> None:
    """
    Epic mode orchestration loop.

    1. Load epic index
    2. Check for unresolved human gate
    3. Get next pending epic
    4. Run Epic Initializer session
    5. Coding agent loop per issue
    6. Repeat for next epic
    """
    print("\n" + "=" * 70)
    print("  EVERYTHINGBAGELAI CODING AGENT HARNESS — EPIC MODE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print(f"Model: {model}")
    if max_iterations:
        print(f"Max iterations per epic: {max_iterations}")
    else:
        print("Max iterations: Unlimited")
    print()

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    # Acquire harness lock — prevents two instances from running on the same project
    _lock_fd = acquire_harness_lock(project_dir)  # noqa: F841 — prevent GC releasing the lock

    # Copy skill files into project so agent can access them from project CWD
    skills_src = Path(__file__).parent / ".claude" / "skills"
    skills_dst = project_dir / ".claude" / "skills"
    if skills_src.exists() and not skills_dst.exists():
        shutil.copytree(skills_src, skills_dst)
        # Copies all skills (e2e-test, api-test, etc.) into the project
        print(f"  Copied skill files to {skills_dst}")

    # --- Dynamic Ecosystem Discovery ---
    linear_api_key = os.environ.get("LINEAR_API_KEY", "")
    ecosystem = discover_user_ecosystem(project_dir, linear_api_key)
    print_discovery_summary(ecosystem)
    configure_allowed_commands(ecosystem.merged_allowed_commands)

    # Load epic index
    try:
        epic_index = load_epic_index(project_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"\nError: {e}")
        return

    total_epics = len(epic_index)
    print(f"Epic index loaded: {total_epics} epic(s)")

    # --- Check for unresolved human gate ---
    gate_id = get_human_gate_issue_id(project_dir)
    if gate_id:
        try:
            if not is_human_gate_resolved(gate_id):
                _print_human_gate_pause(gate_id, project_dir)
                return
            else:
                print("  Previous human gate resolved. Continuing...")
                clear_human_gate(project_dir)
        except Exception as e:
            print(f"  Warning: Could not check human gate status: {e}")
            print("  Assuming gate is still pending.")
            _print_human_gate_pause(gate_id, project_dir)
            return

    # --- Epic loop ---
    total_issues_resolved = 0
    epics_completed = 0

    while True:
        epic_number = get_next_pending_epic(project_dir)
        if epic_number is None:
            _print_final_completion(epics_completed, total_issues_resolved)
            return

        epic = get_epic_by_number(project_dir, epic_number)
        if epic is None:
            print(f"\nError: Epic {epic_number} not found in index")
            return

        epic_name = epic["name"]

        # --- Check if we already have a project ID (resuming mid-epic) ---
        project_id = get_linear_project_id(project_dir)

        if not project_id:
            # Run Epic Initializer
            project_id = await run_epic_initializer_session(
                project_dir, model, epic_number, epic_name, ecosystem
            )
            if not project_id:
                print("\nEpic Initializer failed to produce a project ID. Stopping.")
                return

        # --- Coding agent loop ---
        base_prompt = get_coding_prompt()

        epic_issues_resolved, should_stop = await _run_coding_loop(
            project_dir, project_id, epic_number, epic_name,
            model, ecosystem, max_iterations, base_prompt,
        )

        if should_stop:
            return

        total_issues_resolved += epic_issues_resolved
        mark_epic_complete(project_dir, epic_number)
        epics_completed += 1

        next_epic = get_next_pending_epic(project_dir)
        if next_epic is not None:
            next_entry = get_epic_by_number(project_dir, next_epic)
            next_name = next_entry["name"] if next_entry else "unknown"
            _print_epic_completion(epic_number, epic_name, epic_issues_resolved, next_epic, next_name)


def _print_human_gate_pause(gate_id: str, project_dir: Path) -> None:
    """Print human gate pause message (minimal — gate ID only)."""
    print()
    print("\u2501" * 53)
    print("  HUMAN GATE — Setup required before continuing")
    print("\u2501" * 53)
    print()
    print(f"  Gate issue ID: {gate_id}")
    print()
    print("  Once complete:")
    print("  1. Mark the gate issue Done in Linear")
    print(f"  2. Re-run: python autonomous_agent_demo.py --project-dir {project_dir} --mode epic")
    print()
    print("\u2501" * 53)


def _print_human_gate_pause_detail(
    epic_number: int, description: str, project_dir: Path
) -> None:
    """Print human gate pause message with full description."""
    print()
    print("\u2501" * 53)
    print(f"  HUMAN GATE — Epic {epic_number} complete, setup required")
    print("\u2501" * 53)
    print()
    if description:
        print(description)
        print()
    print("  Once complete:")
    print("  1. Mark the gate issue Done in Linear")
    print(f"  2. Re-run: python autonomous_agent_demo.py --project-dir {project_dir} --mode epic")
    print()
    print("\u2501" * 53)


def _print_epic_completion(
    epic_number: int,
    epic_name: str,
    issues_resolved: int,
    next_epic: int,
    next_name: str,
) -> None:
    """Print epic completion message."""
    print()
    print("\u2501" * 53)
    print(f"  Epic {epic_number}: {epic_name} complete")
    print("\u2501" * 53)
    print(f"   Issues resolved: ~{issues_resolved}")
    print(f"   Starting Epic {next_epic}: {next_name}...")
    print()


def _print_final_completion(epics_completed: int, total_issues: int) -> None:
    """Print final completion message."""
    print()
    print("\u2501" * 53)
    print("  Build complete — all epics resolved")
    print("\u2501" * 53)
    print(f"   Epics completed: {epics_completed}")
    print(f"   Total issues resolved: ~{total_issues}")
    print("   Review build_deviations.md for architectural decisions.")
    print()
