"""
Epic Orchestration Loop
=======================

Multi-epic orchestration that wraps the existing session loop.
Python is responsible for gathering state and injecting it as facts —
the agent is responsible for reasoning and implementation only.
"""

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from agent import run_agent_session, run_agent_session_with_timeout, run_epic_initializer_session, AUTO_CONTINUE_DELAY_SECONDS
from client import create_client
from discovery import discover_user_ecosystem, print_discovery_summary
from linear_client import (
    _get_all_issues,
    filter_current_issue,
    filter_human_gate_issue,
    filter_all_issues_complete,
    filter_snapshot_issue,
    get_project_name,
    is_human_gate_resolved,
    set_issue_in_progress,
    verify_all_issues_complete,
)
from progress import (
    acquire_harness_lock,
    load_epic_index,
    get_epic_by_number,
    get_next_pending_epic,
    get_current_epic,
    get_human_gate_issue_id,
    get_linear_project_id,
    get_linear_project_epic,
    get_coding_sessions_run,
    increment_coding_sessions,
    reset_coding_sessions,
    set_current_epic,
    set_human_gate,
    clear_human_gate,
    mark_epic_complete,
    print_session_header,
)
from prompts import get_coding_prompt, build_coding_agent_session_prompt
from security import configure_allowed_commands

MAX_ISSUE_RETRIES = 3
MAX_NO_ISSUE_RETRIES = 50


async def _validate_epic_completion(
    project_dir: Path,
    project_id: str,
    epic_number: int,
    epic_name: str,
) -> tuple[bool, str]:
    """
    Validate that an epic can be marked complete.
    Returns (is_valid, reason) — reason explains why validation failed.

    Checks:
    1. Project ID is scoped to this epic (not stale from a previous one)
    2. Linear project name contains the epic number
    3. At least 1 non-meta issue exists in the project
    4. All non-meta issues are completed
    5. At least 1 coding session was run for this epic
    """
    # Check 1: Epic-scoped project ID
    stored_epic = get_linear_project_epic(project_dir)
    if stored_epic is not None and stored_epic != epic_number:
        return False, (
            f"Project ID is scoped to epic {stored_epic}, but current epic is {epic_number}. "
            "Stale project ID detected."
        )

    # Check 2: Linear project name contains epic number (word-boundary match)
    project_name = await get_project_name(project_id)
    if project_name:
        # Use word boundaries to prevent "Epic 1" matching "Epic 10"
        pattern = rf"\bepic[\s_-]0*{epic_number}(?!\d)"
        if not re.search(pattern, project_name, re.IGNORECASE):
            return False, (
                f"Linear project name '{project_name}' does not reference epic {epic_number}. "
                "This project ID may belong to a different epic."
            )

    # Check 3 & 4: Issues exist and are all complete
    all_done, done_count, total_count = await verify_all_issues_complete(project_id)
    if total_count == 0:
        return False, (
            f"Linear project has 0 non-meta issues. "
            f"Epic {epic_number} issues were never created."
        )
    if not all_done:
        return False, (
            f"Linear verification failed: {done_count}/{total_count} issues complete."
        )

    # Check 5: At least 1 coding session ran
    sessions_run = get_coding_sessions_run(project_dir)
    if sessions_run == 0:
        return False, (
            f"Zero coding sessions ran for epic {epic_number}. "
            "Cannot mark complete without doing work."
        )

    return True, "All validation checks passed"


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

    while True:
        iteration += 1

        # Ensure progress state matches current epic (prevents stale state after crashes)
        current_state_epic = get_current_epic(project_dir)
        if current_state_epic != epic_number:
            logger.info(
                "Progress state epic (%s) differs from running epic (%s) — updating state file",
                current_state_epic, epic_number,
            )
            set_current_epic(project_dir, epic_number, epic_name)

        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations}) for epic {epic_number}")
            print("Re-run to continue.")
            return (0, True)

        # Fetch all issues once per iteration (single API call)
        try:
            all_issues = await _get_all_issues(project_id)
        except Exception as e:
            logger.warning("Linear API error fetching issues: %s. Retrying next iteration.", e)
            await asyncio.sleep(5)
            continue

        # Filter locally — no additional API calls
        current_issue = filter_current_issue(all_issues)

        if current_issue is None:
            # Check if all regular issues are complete
            if filter_all_issues_complete(all_issues):
                # Run snapshot FIRST (before checking gates)
                snapshot_issue = filter_snapshot_issue(all_issues)
                if snapshot_issue and snapshot_issue["state"]["type"] != "completed":
                    print(f"\n  Running Snapshot session for Epic {epic_number}...")
                    shared_context_file = project_dir / "shared_context.md"
                    context_mtime_before = shared_context_file.stat().st_mtime if shared_context_file.exists() else 0
                    snapshot_prompt = build_coding_agent_session_prompt(
                        project_dir, snapshot_issue, base_prompt
                    )
                    snapshot_client = create_client(
                        project_dir, model, mode="greenfield", ecosystem=ecosystem,
                        session_type="coding",
                    )
                    async with snapshot_client:
                        snap_status, snap_response = await run_agent_session_with_timeout(snapshot_client, snapshot_prompt, project_dir)
                    snapshot_success = snap_status != "error"
                    if not snapshot_success:
                        warning_msg = (
                            f"SNAPSHOT FAILED for epic {epic_number}. "
                            "shared_context.md was not updated. "
                            "Subsequent epics may build on stale context. "
                            "Re-run this epic or manually update shared_context.md before continuing."
                        )
                        logger.error(warning_msg)
                        warning_file = project_dir / "SNAPSHOT_FAILURE.txt"
                        warning_file.write_text(warning_msg)
                        print(f"\n  ❌ {warning_msg}")
                        print(f"  Written to: {warning_file}")
                        return (epic_issues_resolved, True)
                    # Verify shared_context.md was actually modified
                    context_mtime_after = shared_context_file.stat().st_mtime if shared_context_file.exists() else 0
                    if context_mtime_after <= context_mtime_before:
                        logger.warning(
                            "Snapshot session completed but shared_context.md was not updated. "
                            "The agent may not have written architectural context."
                        )
                        warning_file = project_dir / "SNAPSHOT_FAILURE.txt"
                        warning_file.write_text(
                            "Snapshot session ran but shared_context.md was not modified. "
                            "Review the snapshot session output and update shared_context.md manually."
                        )
                        print("\n  ⚠ Warning: shared_context.md was not updated by snapshot session.")

                # NOW check for human gate (after snapshot has run)
                gate_issue = filter_human_gate_issue(all_issues)
                if gate_issue and gate_issue["state"]["type"] != "completed":
                    gate_id = gate_issue["id"]
                    set_human_gate(project_dir, gate_id)
                    _print_human_gate_pause_detail(
                        epic_number, gate_issue.get("description", ""), project_dir
                    )
                    return (epic_issues_resolved, True)

                # All done (including snapshot and gate)
                epic_issues_resolved = iteration - 1  # approximate
                return (epic_issues_resolved, False)
            else:
                # Issues exist but none are eligible (all gates/snapshots?)
                no_issue_retry_count += 1
                if no_issue_retry_count > MAX_NO_ISSUE_RETRIES:
                    print(f"\n  No eligible issues found after {MAX_NO_ISSUE_RETRIES} attempts.")
                    print("  Check Linear directly for stuck or blocked issues.")
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

        # Set issue to In Progress in Linear
        try:
            await set_issue_in_progress(issue_id)
        except Exception as e:
            logger.warning("Could not set issue to In Progress: %s", e)

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
            status, response = await run_agent_session_with_timeout(client, prompt, project_dir)

        # Track that a coding session ran for this epic
        if status != "error":
            increment_coding_sessions(project_dir)

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

    # Copy static harness skills (e2e-test, api-test) into project
    skills_src = Path(__file__).parent / ".claude" / "skills"
    skills_dst = project_dir / ".claude" / "skills"
    if skills_src.exists():
        skills_dst.mkdir(parents=True, exist_ok=True)
        for skill_name in ("e2e-test", "api-test"):
            src = skills_src / skill_name
            dst = skills_dst / skill_name
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
        print(f"  Copied static skill files to {skills_dst}")

    # Generate project-specific skills from detected tech stack
    from skills import detect_tech_stack, generate_library_skills, generate_project_skills

    spec_path = project_dir / "epics" / "spec_index.md"
    if not spec_path.exists():
        spec_path = project_dir / "app_spec.txt"
    _spec_text = spec_path.read_text() if spec_path.exists() else ""
    shared_ctx_path = project_dir / "shared_context.md"
    if shared_ctx_path.exists():
        _spec_text += "\n" + shared_ctx_path.read_text()

    stack = detect_tech_stack(_spec_text, project_dir, mode="greenfield")
    generated = generate_project_skills(project_dir, _spec_text, mode="greenfield", is_epic=True, stack=stack)
    if generated:
        print(f"  Generated {len(generated)} project-specific skill(s): {', '.join(generated)}")

    lib_generated = generate_library_skills(project_dir, stack)
    if lib_generated:
        print(f"  Generated {len(lib_generated)} library documentation skill(s): {', '.join(lib_generated)}")

    # --- Dynamic Ecosystem Discovery ---
    from linear_config import get_linear_api_key
    linear_api_key = get_linear_api_key()
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
            if not await is_human_gate_resolved(gate_id):
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
    MAX_VALIDATION_RETRIES = 3
    validation_failures = 0

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

        # Validate stored project ID is scoped to this epic (not stale)
        if project_id:
            stored_epic = get_linear_project_epic(project_dir)
            if stored_epic is not None and stored_epic != epic_number:
                logger.warning(
                    "Stored project ID belongs to epic %s, not current epic %s — clearing stale state",
                    stored_epic, epic_number,
                )
                project_id = None

        if not project_id:
            # Clean up stale marker file from previous epic to prevent ID reuse
            stale_marker = project_dir / ".linear_project.json"
            if stale_marker.exists():
                logger.info("Removing stale .linear_project.json before Epic %s initializer", epic_number)
                stale_marker.unlink()

            # Reset session counter for fresh epic
            reset_coding_sessions(project_dir)

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

        # --- Validate before marking complete ---
        is_valid, reason = await _validate_epic_completion(
            project_dir, project_id, epic_number, epic_name,
        )
        if not is_valid:
            validation_failures += 1
            if validation_failures >= MAX_VALIDATION_RETRIES:
                print(f"\n  Epic {epic_number} validation failed {MAX_VALIDATION_RETRIES} times. Stopping.")
                print(f"  Last reason: {reason}")
                return
            print(f"\n  Epic {epic_number} completion BLOCKED ({validation_failures}/{MAX_VALIDATION_RETRIES}): {reason}")
            print("  Re-running coding loop to resolve.")
            continue

        validation_failures = 0  # Reset on success
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
