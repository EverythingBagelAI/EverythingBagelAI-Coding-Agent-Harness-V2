# Epic Completion Validation & Issue Ordering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent epics from being marked complete without work being done, and enforce strict sequential issue ordering within epics.

**Architecture:** Three layers of defence: (1) stale state cleanup before each epic initializer, (2) epic-scoped project ID validation that ties project IDs to specific epic numbers, (3) a coding session counter that refuses to mark an epic complete if zero sessions ran. Issue ordering is fixed by parsing the `[NN]` prefix from titles as primary sort key.

**Tech Stack:** Python 3.11+, Linear GraphQL API, existing progress.py/linear_client.py/epic_orchestrator.py

---

### Task 1: Add `get_project_name()` to Linear client

**Files:**

- Modify: `linear_client.py:264-279` (after `verify_all_issues_complete`)

**Step 1: Write the function**

Add this function after `verify_all_issues_complete()` in `linear_client.py`:

```python
async def get_project_name(project_id: str) -> str | None:
    """Fetch the project name from Linear by ID."""
    query = """
    query GetProject($id: String!) {
        project(id: $id) { name }
    }
    """
    try:
        data = await _query(query, {"id": project_id})
        return data.get("project", {}).get("name")
    except Exception as e:
        logger.warning("Could not fetch project name for %s: %s", project_id, e)
        return None
```

**Step 2: Commit**

```bash
git add linear_client.py
git commit -m "feat: add get_project_name() for epic validation"
```

---

### Task 2: Add epic-scoped project ID tracking to progress state

**Files:**

- Modify: `progress.py:137-258`

This task adds `linear_project_epic` and `coding_sessions_run` fields to the epic state, so the harness can verify a project ID belongs to the correct epic and that work was actually done.

**Step 1: Update `_read_epic_state` defaults and parsing**

In `_read_epic_state()`, add two new fields to `defaults` dict (line 139-145):

```python
defaults = {
    "current_epic": None,
    "current_epic_name": None,
    "linear_project_id": None,
    "linear_project_epic": None,
    "epic_status": {},
    "human_gate_issue_id": None,
    "coding_sessions_run": 0,
}
```

Add parsing for the two new fields inside the `for line in section.splitlines()` loop, after the `human_gate_issue_id` elif (after line 193):

```python
elif key == "linear_project_epic":
    state["linear_project_epic"] = int(value) if value != "null" else None
elif key == "coding_sessions_run":
    try:
        state["coding_sessions_run"] = int(value)
    except (ValueError, TypeError):
        state["coding_sessions_run"] = 0
```

**Step 2: Update `_write_epic_state` to include new fields**

In `_write_epic_state()`, add the two new lines to `block_lines` (after line 208, before the `EPIC_STATE_END` line):

```python
block_lines = [
    EPIC_STATE_START,
    f"current_epic: {state['current_epic'] if state['current_epic'] is not None else 'null'}",
    f"current_epic_name: {state['current_epic_name'] if state['current_epic_name'] is not None else 'null'}",
    f"linear_project_id: {state['linear_project_id'] if state['linear_project_id'] is not None else 'null'}",
    f"linear_project_epic: {state['linear_project_epic'] if state['linear_project_epic'] is not None else 'null'}",
    f"epic_status: {json.dumps(state['epic_status'])}",
    f"human_gate_issue_id: {state['human_gate_issue_id'] if state['human_gate_issue_id'] is not None else 'null'}",
    f"coding_sessions_run: {state['coding_sessions_run']}",
    EPIC_STATE_END,
]
```

**Step 3: Update `set_linear_project_id` to accept and store epic number**

Replace the existing `set_linear_project_id` function (line 277-282):

```python
def set_linear_project_id(project_dir: Path, project_id: str, epic_number: int | None = None) -> None:
    """Store the Linear project ID and its associated epic number."""
    logger.info("Linear project ID set: %s (epic %s)", project_id, epic_number)
    state = _read_epic_state(project_dir)
    state["linear_project_id"] = project_id
    if epic_number is not None:
        state["linear_project_epic"] = epic_number
    _write_epic_state(project_dir, state)
```

**Step 4: Add `get_linear_project_epic`, `increment_coding_sessions`, `get_coding_sessions_run`, `reset_coding_sessions` functions**

Add after `get_human_gate_issue_id` (after line 300):

```python
def get_linear_project_epic(project_dir: Path) -> int | None:
    """Retrieve the epic number associated with the stored project ID."""
    state = _read_epic_state(project_dir)
    return state.get("linear_project_epic")


def increment_coding_sessions(project_dir: Path) -> int:
    """Increment and return the coding session counter for the current epic."""
    state = _read_epic_state(project_dir)
    state["coding_sessions_run"] = state.get("coding_sessions_run", 0) + 1
    _write_epic_state(project_dir, state)
    return state["coding_sessions_run"]


def get_coding_sessions_run(project_dir: Path) -> int:
    """Retrieve the coding session counter for the current epic."""
    state = _read_epic_state(project_dir)
    return state.get("coding_sessions_run", 0)


def reset_coding_sessions(project_dir: Path) -> None:
    """Reset the coding session counter (called when starting a new epic)."""
    state = _read_epic_state(project_dir)
    state["coding_sessions_run"] = 0
    _write_epic_state(project_dir, state)
```

**Step 5: Update `mark_epic_complete` to also clear new fields**

Replace `mark_epic_complete` (line 250-258):

```python
def mark_epic_complete(project_dir: Path, epic_number: int) -> None:
    """Mark an epic complete and clear all per-epic state."""
    logger.info("Marking epic %s complete", epic_number)
    state = _read_epic_state(project_dir)
    state["epic_status"][str(epic_number)] = "complete"
    state["current_epic"] = None
    state["current_epic_name"] = None
    state["linear_project_id"] = None
    state["linear_project_epic"] = None
    state["coding_sessions_run"] = 0
    _write_epic_state(project_dir, state)
```

**Step 6: Commit**

```bash
git add progress.py
git commit -m "feat: add epic-scoped project ID tracking and session counter to progress state"
```

---

### Task 3: Fix issue ordering — parse `[NN]` prefix as primary sort key

**Files:**

- Modify: `linear_client.py:123-142`

**Step 1: Add `_parse_issue_sequence` helper**

Add this helper above `filter_current_issue` (before line 123):

```python
import re

def _parse_issue_sequence(title: str) -> int:
    """Extract the [NN] sequence number from an issue title. Returns 999 if not found."""
    match = re.match(r"\[(\d+)\]", title)
    return int(match.group(1)) if match else 999
```

Note: the `re` import should go at the top of the file with other imports.

**Step 2: Update `filter_current_issue` to sort by sequence number**

Replace the sort line (line 141):

```python
eligible.sort(key=lambda i: (_parse_issue_sequence(i["title"]), i.get("priority", 0) or 999))
```

This sorts by `[NN]` prefix first (so `[01]` before `[02]`), then by priority as tiebreaker.

**Step 3: Commit**

```bash
git add linear_client.py
git commit -m "feat: sort issues by [NN] sequence prefix for deterministic ordering"
```

---

### Task 4: Delete stale `.linear_project.json` before each epic initializer

**Files:**

- Modify: `epic_orchestrator.py:327-337`

**Step 1: Add stale file cleanup before initializer**

In the epic loop, after `if not project_id:` (line 330), add cleanup before calling the initializer:

```python
if not project_id:
    # Clean up stale marker file from previous epic to prevent ID reuse
    stale_marker = project_dir / ".linear_project.json"
    if stale_marker.exists():
        logger.info("Removing stale .linear_project.json before Epic %s initializer", epic_number)
        stale_marker.unlink()

    # Run Epic Initializer
    project_id = await run_epic_initializer_session(
        project_dir, model, epic_number, epic_name, ecosystem
    )
    if not project_id:
        print("\nEpic Initializer failed to produce a project ID. Stopping.")
        return
```

**Step 2: Commit**

```bash
git add epic_orchestrator.py
git commit -m "fix: delete stale .linear_project.json before each epic initializer"
```

---

### Task 5: Add epic-scoped validation to the epic loop

**Files:**

- Modify: `epic_orchestrator.py:310-365`
- Modify: `agent.py:222-232` (update `set_linear_project_id` call)

This is the core task — add the validation chain that prevents marking an epic complete without work.

**Step 1: Update imports in `epic_orchestrator.py`**

Add new imports at the top of the file. Update the `progress` import block (line 31-44):

```python
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
```

Add `get_project_name` to the `linear_client` import block (line 21-30):

```python
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
```

**Step 2: Add `_validate_epic_completion` function**

Add this function before `_run_coding_loop` (before line 52):

```python
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

    # Check 2: Linear project name contains epic number
    project_name = await get_project_name(project_id)
    if project_name:
        epic_markers = [
            f"epic {epic_number}",
            f"epic-{epic_number}",
            f"epic_{epic_number}",
            f"epic {epic_number:02d}",
            f"epic-{epic_number:02d}",
        ]
        name_lower = project_name.lower()
        if not any(marker in name_lower for marker in epic_markers):
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
```

**Step 3: Update the epic loop to use validation**

Replace the epic loop section (lines 310-365) with:

```python
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
            print(f"\n  Epic {epic_number} completion BLOCKED: {reason}")
            print("  Re-running coding loop to resolve.")
            continue

        total_issues_resolved += epic_issues_resolved
        mark_epic_complete(project_dir, epic_number)
        epics_completed += 1

        next_epic = get_next_pending_epic(project_dir)
        if next_epic is not None:
            next_entry = get_epic_by_number(project_dir, next_epic)
            next_name = next_entry["name"] if next_entry else "unknown"
            _print_epic_completion(epic_number, epic_name, epic_issues_resolved, next_epic, next_name)
```

**Step 4: Update `agent.py` to pass `epic_number` to `set_linear_project_id`**

In `run_epic_initializer_session` (agent.py:228-230), update the call:

```python
if project_id:
    set_linear_project_id(project_dir, project_id, epic_number)
    set_current_epic(project_dir, epic_number, epic_name)
```

**Step 5: Commit**

```bash
git add epic_orchestrator.py agent.py
git commit -m "feat: add multi-layer epic completion validation chain"
```

---

### Task 6: Increment coding session counter in the coding loop

**Files:**

- Modify: `epic_orchestrator.py:180-208` (inside `_run_coding_loop`, where sessions run)

**Step 1: Add session counter increment**

In `_run_coding_loop`, after the session runs successfully (after line 203, before the status check on line 205), add:

```python
        async with client:
            status, response = await run_agent_session_with_timeout(client, prompt, project_dir)

        # Track that a coding session ran for this epic
        if status != "error":
            increment_coding_sessions(project_dir)

        if status == "error":
            print("\nSession encountered an error. Will retry...")
```

**Step 2: Commit**

```bash
git add epic_orchestrator.py
git commit -m "feat: increment coding session counter after each successful session"
```

---

### Task 7: Add strict previous-epic validation to `get_next_pending_epic`

**Files:**

- Modify: `progress.py:303-314`

This ensures epic N cannot start until epic N-1 is marked complete. Prevents out-of-order execution.

**Step 1: Update `get_next_pending_epic` to enforce sequential order**

Replace the existing function (lines 303-314):

```python
def get_next_pending_epic(project_dir: Path) -> int | None:
    """
    Return the number of the next epic with status 'pending', or None if all complete.

    Enforces strict sequential order: epic N cannot be pending unless all epics
    before it (in index order) are marked complete. This prevents skipping epics.
    """
    state = _read_epic_state(project_dir)
    index = load_epic_index(project_dir)

    for epic in index:
        num = str(epic["number"])
        status = state["epic_status"].get(num, "pending")
        if status == "pending":
            return epic["number"]
        if status != "complete":
            # This epic is in_progress or some other non-complete state.
            # Do not skip it — return it so the loop re-enters for this epic.
            logger.info(
                "Epic %s has status '%s' (not complete) — cannot advance past it",
                num, status,
            )
            return epic["number"]

    return None
```

**Step 2: Commit**

```bash
git add progress.py
git commit -m "feat: enforce strict sequential epic ordering in get_next_pending_epic"
```

---

## Summary of Defence Layers

| Layer                                            | What it prevents                        | Where                            |
| ------------------------------------------------ | --------------------------------------- | -------------------------------- |
| Delete `.linear_project.json` before initializer | Stale project ID from previous epic     | `epic_orchestrator.py` epic loop |
| `linear_project_epic` field                      | Using a project ID scoped to wrong epic | `progress.py` state              |
| Stale ID check at loop start                     | Resuming with wrong project ID          | `epic_orchestrator.py` epic loop |
| `_validate_epic_completion` check 1              | Stale project ID bypass                 | `epic_orchestrator.py`           |
| `_validate_epic_completion` check 2              | Project name mismatch                   | `epic_orchestrator.py`           |
| `_validate_epic_completion` check 3              | Zero issues created                     | `epic_orchestrator.py`           |
| `_validate_epic_completion` check 4              | Incomplete issues                       | `epic_orchestrator.py`           |
| `_validate_epic_completion` check 5              | Zero coding sessions                    | `epic_orchestrator.py`           |
| `[NN]` prefix sorting                            | Out-of-order issue execution            | `linear_client.py`               |
| Sequential epic enforcement                      | Skipping epics                          | `progress.py`                    |
