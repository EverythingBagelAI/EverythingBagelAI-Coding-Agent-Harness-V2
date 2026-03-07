"""
Prompt Loading Utilities
========================

Functions for loading prompt templates from the prompts directory.
Includes programmatic context injection for epic mode — Python reads files
and fetches issue data, then injects everything as pre-populated context
blocks in the prompt so the agent never needs to discover state itself.
"""

import shutil
from pathlib import Path
from typing import Optional


PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    return prompt_path.read_text()


def get_initializer_prompt() -> str:
    """Load the initializer prompt."""
    return load_prompt("initializer_prompt")


def get_coding_prompt() -> str:
    """Load the coding agent prompt."""
    return load_prompt("coding_prompt")


def get_brownfield_initializer_prompt() -> str:
    """Load the brownfield initializer prompt."""
    return load_prompt("brownfield_initializer_prompt")


def get_epic_initializer_prompt() -> str:
    """Load the epic initializer prompt."""
    return load_prompt("epic_initializer_prompt")


def copy_spec_to_project(project_dir: Path) -> None:
    """Copy the app spec file into the project directory for the agent to read."""
    spec_source = PROMPTS_DIR / "app_spec.txt"
    spec_dest = project_dir / "app_spec.txt"
    if not spec_dest.exists():
        shutil.copy(spec_source, spec_dest)
        print("Copied app_spec.txt to project directory")


# ---------------------------------------------------------------------------
# Programmatic context injection for epic mode
# ---------------------------------------------------------------------------

def _read_file_or_note(path: Path, required: bool = False) -> str:
    """Read a file's content, or return a note if missing."""
    if path.exists():
        return path.read_text()
    if required:
        raise FileNotFoundError(
            f"Required context file not found: {path}. "
            "Run generate_epics.py first."
        )
    return f"[File not found: {path.name} — this is expected if no previous epic has run]"


def _wrap_context(filename: str, content: str) -> str:
    """Wrap content in clearly delimited context markers."""
    return (
        f"## [CONTEXT: {filename}]\n\n"
        f"{content}\n\n"
        f"## [END CONTEXT: {filename}]\n"
    )


def build_epic_initializer_context(epic_number: int, project_dir: Path) -> str:
    """
    Build the full context string injected into the Epic Initializer's user message.

    Reads and concatenates (in order):
    1. shared_context.md (required)
    2. build_deviations.md (optional)
    3. epics/spec_index.md (required)
    4. epics/epic-NN-name.md (required — the specific epic spec)

    Returns a formatted string with clearly delimited sections.
    """
    from progress import get_epic_by_number

    epic = get_epic_by_number(project_dir, epic_number)
    if epic is None:
        raise ValueError(f"Epic {epic_number} not found in spec_index.json")

    sections: list[str] = []

    # 1. shared_context.md (at project root)
    shared_ctx = _read_file_or_note(project_dir / "shared_context.md", required=True)
    sections.append(_wrap_context("shared_context.md", shared_ctx))

    # 2. build_deviations.md (optional)
    deviations = _read_file_or_note(project_dir / "build_deviations.md", required=False)
    sections.append(_wrap_context("build_deviations.md", deviations))

    # 3. epics/spec_index.md
    spec_index = _read_file_or_note(project_dir / "epics" / "spec_index.md", required=True)
    sections.append(_wrap_context("epics/spec_index.md", spec_index))

    # 4. The specific epic spec
    spec_file = project_dir / epic["spec_file"]
    epic_spec = _read_file_or_note(spec_file, required=True)
    sections.append(_wrap_context(epic["spec_file"], epic_spec))

    header = (
        f"# Epic Initializer Context — Epic {epic_number}: {epic['name']}\n\n"
        "The following context has been programmatically injected by the harness. "
        "You do not need to read these files yourself — their full contents are below.\n\n"
    )

    return header + "\n".join(sections)


def build_coding_agent_session_prompt(
    project_dir: Path,
    current_issue: Optional[dict],
    base_prompt: str,
) -> str:
    """
    Build the complete prompt for a single Coding Agent session.

    Injects programmatically gathered context directly into the prompt so the
    agent never needs to discover or read these things itself:

    1. Base coding prompt (from prompts/coding_prompt.md)
    2. Shared context block (content of shared_context.md, if exists)
    3. Build deviations block (content of build_deviations.md, if exists)
    4. Current issue block — the specific issue to work on this session

    Returns the complete prompt string.
    """
    sections: list[str] = [base_prompt]

    # Shared context
    shared_path = project_dir / "shared_context.md"
    if shared_path.exists():
        sections.append(_wrap_context("shared_context.md", shared_path.read_text()))

    # Build deviations
    deviations_path = project_dir / "build_deviations.md"
    if deviations_path.exists():
        sections.append(_wrap_context("build_deviations.md", deviations_path.read_text()))

    # Current issue
    if current_issue is not None:
        issue_block = (
            "## CURRENT ISSUE (work on this and only this)\n\n"
            f"Title: {current_issue['title']}\n"
            f"Description: {current_issue.get('description', 'No description')}\n"
            f"Priority: {current_issue.get('priority', 'unset')}\n\n"
            "Complete this issue, commit, mark it Done in Linear, then stop.\n"
            "Do not pick up additional issues in this session."
        )
        sections.append(issue_block)
    else:
        sections.append(
            "## STATUS: All issues complete. Run the snapshot if not done, then stop."
        )

    return "\n\n---\n\n".join(sections)
