#!/usr/bin/env python3
"""
Epic Generator (Two-Stage)
==========================

Stage 1 — Decomposition: Single Architect session produces spec_index.json
(enriched with briefs), spec_index.md, and shared_context.md.

Stage 2 — Epic Spec Writing: One fresh session per epic, sequential. Each
writer receives the master spec, shared context, its brief from the index,
and all previously completed epic specs.

Usage:
    python generate_epics.py --project-dir ./my-project
    python generate_epics.py --project-dir ./my-project --spec path/to/custom_spec.md
    python generate_epics.py --project-dir ./my-project --model claude-opus-4-6
    python generate_epics.py --project-dir ./my-project --retry-failed
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from agent import run_agent_session_with_timeout
from client import create_client
from discovery import discover_user_ecosystem, print_discovery_summary
from config import DEFAULT_MODEL, EPIC_WRITER_TIMEOUT
from security import configure_allowed_commands

PROMPTS_DIR = Path(__file__).parent / "prompts"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate epic sub-specs from a master app spec (two-stage)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run (Stage 1 + Stage 2)
  python generate_epics.py --project-dir ./my-project

  # Use a custom spec file
  python generate_epics.py --project-dir ./my-project --spec path/to/custom_spec.md

  # Retry only failed epic writers (skips Stage 1)
  python generate_epics.py --project-dir ./my-project --retry-failed

Environment Variables:
  CLAUDE_CODE_OAUTH_TOKEN       Claude Code OAuth token (required)
  LINEAR_API_KEY                Linear API key (required)
  HARNESS_ARCHITECT_TIMEOUT     Stage 1 timeout in seconds (default: 3600)
  HARNESS_EPIC_WRITER_TIMEOUT   Per-epic writer timeout in seconds (default: 900)
        """,
    )

    parser.add_argument(
        "--spec", type=Path,
        default=PROMPTS_DIR / "master_app_spec.md",
        help="Path to the master app spec (default: prompts/master_app_spec.md)",
    )
    parser.add_argument(
        "--project-dir", type=Path, required=True,
        help="Target project directory for generated epics",
    )
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="Skip Stage 1, only re-run epic writers for missing spec files",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Stage 1: Decomposition
# ---------------------------------------------------------------------------

def _create_architect_client(model, system_prompt, project_dir, ecosystem):
    """Create a Claude Agent SDK client configured for the Architect Agent."""
    configure_allowed_commands(ecosystem.merged_allowed_commands)

    return create_client(
        project_dir=project_dir,
        model=model,
        mode="greenfield",
        ecosystem=ecosystem,
        system_prompt_override=system_prompt,
        session_type="architect",
        max_turns=500,
    )


async def run_decomposition(
    spec_path: Path, model: str, project_dir: Path, ecosystem
) -> list[dict]:
    """
    Stage 1: Run the Architect Agent to decompose the master spec.

    Produces spec_index.json (enriched with briefs), spec_index.md,
    and shared_context.md. Does NOT produce individual epic spec files.

    Returns the parsed spec_index.json as a list of dicts.
    """
    print("\n" + "=" * 70)
    print("  STAGE 1: DECOMPOSITION")
    print("=" * 70)
    print(f"\nSpec file: {spec_path}")
    print(f"Model: {model}")
    print()

    # Load the architect prompt
    architect_prompt_path = PROMPTS_DIR / "architect_prompt.md"
    if not architect_prompt_path.exists():
        print(f"Error: Architect prompt not found at {architect_prompt_path}")
        sys.exit(1)

    architect_prompt = architect_prompt_path.read_text()

    # Build the task message — note: NO individual epic spec files
    task_message = (
        f"Read {spec_path} and decompose it into epic sub-specs.\n"
        "\n"
        "Produce the following files:\n"
        "- epics/spec_index.md (human-readable index)\n"
        "- epics/spec_index.json (machine-readable index with enriched briefs — see system prompt)\n"
        "- shared_context.md (in the PROJECT ROOT, not epics/)\n"
        "\n"
        "IMPORTANT: Do NOT write individual epic spec files (epic-NN-name.md).\n"
        "Those will be written by separate spec writer agents using your briefs.\n"
        "\n"
        "Follow the instructions in your system prompt exactly."
    )

    # Create the architect client
    client = _create_architect_client(model, architect_prompt, project_dir, ecosystem)

    # Ensure directories exist
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "epics").mkdir(parents=True, exist_ok=True)

    print("Starting Architect Agent session...")
    print("This may take several minutes depending on spec complexity.\n")

    async with client:
        status, response = await run_agent_session_with_timeout(
            client=client,
            message=task_message,
            project_dir=project_dir,
            timeout=int(os.environ.get("HARNESS_ARCHITECT_TIMEOUT", 3600)),
        )

    if status == "error":
        print(f"\nArchitect Agent encountered an error: {response}")
        sys.exit(1)

    # Validate Stage 1 outputs
    return _validate_stage1_outputs(project_dir)


def _validate_stage1_outputs(project_dir: Path) -> list[dict]:
    """
    Validate Stage 1 outputs and return parsed spec_index.json.

    Checks:
    - spec_index.json exists, is valid JSON, is a non-empty array
    - Each entry has required keys: number, name, spec_file, brief
    - spec_index.md exists
    - shared_context.md exists
    """
    EXPECTED_FILES = [
        "epics/spec_index.json",
        "epics/spec_index.md",
        "shared_context.md",
    ]

    missing = [f for f in EXPECTED_FILES if not (project_dir / f).exists()]

    spec_index_path = project_dir / "epics" / "spec_index.json"
    index_data = None
    errors: list[str] = []

    if spec_index_path.exists():
        try:
            index_data = json.loads(spec_index_path.read_text())
            if not isinstance(index_data, list) or len(index_data) == 0:
                errors.append("spec_index.json is empty or not a JSON array")
            else:
                for entry in index_data:
                    epic_num = entry.get("number", "?")
                    if not entry.get("spec_file"):
                        errors.append(f"Epic {epic_num} missing 'spec_file' key")
                    if not entry.get("name"):
                        errors.append(f"Epic {epic_num} missing 'name' key")
                    if not entry.get("brief"):
                        errors.append(
                            f"Epic {epic_num} missing 'brief' key — "
                            "Stage 2 writers need this to generate specs"
                        )
        except json.JSONDecodeError as exc:
            errors.append(f"spec_index.json is not valid JSON: {exc}")

    if missing or errors:
        print("\n" + "=" * 70)
        print("  STAGE 1 VALIDATION FAILED")
        print("=" * 70)
        if missing:
            print("\n  Missing files:")
            for f in missing:
                print(f"     - {f}")
        if errors:
            print("\n  Errors:")
            for err in errors:
                print(f"     - {err}")
        print()
        print("  Re-run generate_epics.py to retry Stage 1.")
        sys.exit(1)

    print("\n  Stage 1 complete — spec index and shared context generated.")
    return index_data


# ---------------------------------------------------------------------------
# Stage 2: Epic Spec Writing
# ---------------------------------------------------------------------------

def _build_epic_writer_message(
    epic_entry: dict,
    master_spec_text: str,
    shared_context_text: str,
    spec_index_text: str,
    completed_specs: dict[int, str],
    ref_docs: str,
) -> str:
    """
    Build the user message for a single epic writer session.

    Assembles all context the writer needs to produce its epic spec.
    """
    epic_number = epic_entry["number"]
    epic_name = epic_entry["name"]
    spec_file = epic_entry["spec_file"]
    brief = epic_entry.get("brief", {})

    sections = []

    # 1. Task instruction
    sections.append(
        f"Write the epic spec file: {spec_file}\n\n"
        f"This is Epic {epic_number}: {epic_name}.\n"
        f"Write this file and ONLY this file, then stop."
    )

    # 2. Master spec
    sections.append(
        "## [CONTEXT: master_app_spec]\n\n"
        f"{master_spec_text}\n\n"
        "## [END CONTEXT: master_app_spec]"
    )

    # 3. Shared context
    sections.append(
        "## [CONTEXT: shared_context.md]\n\n"
        f"{shared_context_text}\n\n"
        "## [END CONTEXT: shared_context.md]"
    )

    # 4. Full spec index (so writer sees all epics and their briefs)
    sections.append(
        "## [CONTEXT: spec_index.json]\n\n"
        f"{spec_index_text}\n\n"
        "## [END CONTEXT: spec_index.json]"
    )

    # 5. This epic's brief (highlighted for easy reference)
    sections.append(
        f"## [CONTEXT: Your Epic Brief — Epic {epic_number}: {epic_name}]\n\n"
        f"{json.dumps(brief, indent=2)}\n\n"
        f"## [END CONTEXT: Your Epic Brief]"
    )

    # 6. Previously completed epic specs (for consistency)
    if completed_specs:
        for prev_num in sorted(completed_specs.keys()):
            sections.append(
                f"## [CONTEXT: Completed Epic {prev_num} Spec]\n\n"
                f"{completed_specs[prev_num]}\n\n"
                f"## [END CONTEXT: Completed Epic {prev_num} Spec]"
            )

    # 7. Pre-fetched Ref documentation
    if ref_docs:
        sections.append(ref_docs)

    return "\n\n---\n\n".join(sections)


async def run_epic_writers(
    spec_path: Path,
    model: str,
    project_dir: Path,
    epic_index: list[dict],
    ecosystem,
    retry_failed_only: bool = False,
) -> None:
    """
    Stage 2: Write individual epic specs, one fresh session per epic.

    Each writer receives:
    1. The full master spec text
    2. shared_context.md content
    3. The full spec_index.json (so it sees all epics and their briefs)
    4. Its specific epic's brief from the index
    5. All previously completed epic spec files (for consistency)
    6. Pre-fetched Ref documentation (batch, deduplicated)

    Runs sequentially so each writer can see previous epic specs.
    """
    print("\n" + "=" * 70)
    print("  STAGE 2: EPIC SPEC WRITING")
    print("=" * 70)
    print(f"\n  Epics to write: {len(epic_index)}")
    print(f"  Mode: sequential (each writer sees previous specs)")
    print()

    # Read inputs that are shared across all writers
    master_spec_text = spec_path.read_text()
    shared_context_text = (project_dir / "shared_context.md").read_text()
    spec_index_text = (project_dir / "epics" / "spec_index.json").read_text()

    # Load the epic writer system prompt
    writer_prompt_path = PROMPTS_DIR / "epic_writer_prompt.md"
    if not writer_prompt_path.exists():
        print(f"Error: Epic writer prompt not found at {writer_prompt_path}")
        sys.exit(1)
    writer_system_prompt = writer_prompt_path.read_text()

    # Batch pre-fetch Ref docs for all unique libraries across all epics
    all_integration_text = " ".join(
        " ".join(entry.get("brief", {}).get("integrations", []))
        for entry in epic_index
    )
    from prompts import prefetch_ref_docs
    ref_docs = prefetch_ref_docs(
        master_spec_text + " " + all_integration_text,
        project_dir=project_dir,
    )

    # Track results
    succeeded: list[int] = []
    failed: list[tuple[int, str]] = []
    skipped: list[int] = []

    # Accumulate completed epic specs for forward injection
    completed_specs: dict[int, str] = {}

    for entry in epic_index:
        epic_number = entry["number"]
        epic_name = entry["name"]
        spec_file = entry["spec_file"]
        spec_path_full = project_dir / spec_file

        # Skip if already exists and retrying
        if spec_path_full.exists() and retry_failed_only:
            print(f"  Epic {epic_number} ({epic_name}): already exists, skipping")
            # Still load it for forward injection
            completed_specs[epic_number] = spec_path_full.read_text()
            skipped.append(epic_number)
            continue

        print(f"\n  Writing Epic {epic_number}: {epic_name}...")

        # Build the user message with all context
        user_message = _build_epic_writer_message(
            epic_entry=entry,
            master_spec_text=master_spec_text,
            shared_context_text=shared_context_text,
            spec_index_text=spec_index_text,
            completed_specs=completed_specs,
            ref_docs=ref_docs,
        )

        # Create a fresh client for this epic
        client = create_client(
            project_dir=project_dir,
            model=model,
            mode="greenfield",
            ecosystem=ecosystem,
            system_prompt_override=writer_system_prompt,
            session_type="epic_writer",
            max_turns=200,
        )

        try:
            async with client:
                status, response = await run_agent_session_with_timeout(
                    client=client,
                    message=user_message,
                    project_dir=project_dir,
                    timeout=EPIC_WRITER_TIMEOUT,
                )

            if status == "error":
                print(f"  Epic {epic_number} writer failed: {response}")
                failed.append((epic_number, response))
                continue

            # Verify the spec file was written
            if spec_path_full.exists():
                completed_specs[epic_number] = spec_path_full.read_text()
                succeeded.append(epic_number)
                print(f"  Epic {epic_number}: spec written successfully")
            else:
                msg = f"Writer completed but {spec_file} was not created"
                print(f"  Epic {epic_number}: {msg}")
                failed.append((epic_number, msg))

        except Exception as e:
            print(f"  Epic {epic_number} writer error: {e}")
            failed.append((epic_number, str(e)))

    # Print summary
    _print_stage2_summary(succeeded, failed, skipped, project_dir)

    if failed:
        print("\n  To retry failed epics only:")
        print(f"  python generate_epics.py --project-dir {project_dir} --retry-failed")
        sys.exit(1)


def _print_stage2_summary(succeeded, failed, skipped, project_dir):
    """Print Stage 2 results summary."""
    print("\n" + "=" * 70)
    if not failed:
        print("  EPICS GENERATED SUCCESSFULLY")
    else:
        print("  EPIC GENERATION PARTIALLY FAILED")
    print("=" * 70)

    if succeeded:
        print(f"\n  Succeeded: {len(succeeded)} — epics {succeeded}")
    if skipped:
        print(f"  Skipped (already exist): {len(skipped)} — epics {skipped}")
    if failed:
        print(f"  Failed: {len(failed)}")
        for num, reason in failed:
            print(f"    - Epic {num}: {reason}")

    if not failed:
        print(f"\n  Epics generated in {project_dir / 'epics'}")
        print()
        print("  Next steps:")
        print(f"  1. Review each file in {project_dir / 'epics'} — especially human gate checklists")
        print(f"  2. Run: python autonomous_agent_demo.py --project-dir {project_dir} --mode epic")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def generate_epics(
    spec_path: Path, model: str, project_dir: Path, retry_failed: bool = False
) -> None:
    """
    Main orchestrator — runs Stage 1 (decomposition) then Stage 2 (per-epic writing).
    """
    print("\n" + "=" * 70)
    print("  EVERYTHINGBAGELAI EPIC GENERATOR (TWO-STAGE)")
    print("=" * 70)
    print(f"\nSpec file: {spec_path}")
    print(f"Model: {model}")
    print(f"Project dir: {project_dir.resolve()}")
    print(f"Output: {project_dir / 'epics'}")
    print()

    # Ecosystem discovery (shared across both stages)
    from linear_config import get_linear_api_key
    linear_api_key = get_linear_api_key()
    ecosystem = discover_user_ecosystem(project_dir, linear_api_key)
    print_discovery_summary(ecosystem)
    configure_allowed_commands(ecosystem.merged_allowed_commands)

    if retry_failed:
        # Skip Stage 1 — load existing spec_index.json
        print("  --retry-failed: Skipping Stage 1, loading existing spec_index.json")
        epic_index = _validate_stage1_outputs(project_dir)
    else:
        # Stage 1: Decomposition
        epic_index = await run_decomposition(spec_path, model, project_dir, ecosystem)

    # Stage 2: Per-epic spec writing
    await run_epic_writers(
        spec_path=spec_path,
        model=model,
        project_dir=project_dir,
        epic_index=epic_index,
        ecosystem=ecosystem,
        retry_failed_only=retry_failed,
    )


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Check for Claude Code OAuth token
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("Error: CLAUDE_CODE_OAUTH_TOKEN environment variable not set")
        print("\nRun 'claude setup-token' after installing the Claude Code CLI.")
        print("\nThen set it:")
        print("  export CLAUDE_CODE_OAUTH_TOKEN='your-token-here'")
        return

    # Check for Linear API key
    if not os.environ.get("LINEAR_API_KEY"):
        print("Error: LINEAR_API_KEY environment variable not set")
        print("\nGet your API key from: https://linear.app/YOUR-TEAM/settings/api")
        print("\nThen set it:")
        print("  export LINEAR_API_KEY='lin_api_xxxxxxxxxxxxx'")
        return

    # Validate spec file exists (not needed for retry-failed)
    spec_path = args.spec
    if not args.retry_failed and not spec_path.exists():
        print(f"Error: Spec file not found: {spec_path}")
        print()
        print("Either:")
        print(f"  1. Create your spec at {spec_path}")
        print("  2. Copy and edit the template:")
        print("     cp templates/master_app_spec_template.md prompts/master_app_spec.md")
        print("  3. Pass a custom path: python generate_epics.py --spec path/to/spec.md")
        return

    try:
        asyncio.run(generate_epics(spec_path, args.model, args.project_dir, args.retry_failed))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise


if __name__ == "__main__":
    main()
