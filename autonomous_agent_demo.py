#!/usr/bin/env python3
"""
EverythingBagelAI Coding Agent Harness
======================================

A dynamic harness for long-running autonomous coding with Claude.
Implements the two-agent pattern (initialiser + coding agent) with
dynamic ecosystem discovery for any user's Claude Code setup.

Supports greenfield, brownfield, and epic modes.

Example Usage:
    # Greenfield (default) - new project from app_spec.txt
    python autonomous_agent_demo.py --project-dir ./claude_clone_demo

    # Brownfield - work on an existing codebase
    python autonomous_agent_demo.py --mode brownfield --existing-dir /path/to/repo

    # Epic - multi-epic orchestration from generated specs
    python autonomous_agent_demo.py --project-dir ./my-project --mode epic

    # With iteration limit and cost cap
    python autonomous_agent_demo.py --project-dir ./demo --max-iterations 5 --max-budget 10.0
"""

import argparse
import asyncio
import os
from pathlib import Path

from agent import run_autonomous_agent


# Configuration
# Using Claude Opus 4.5 as default for best coding and agentic performance
# See: https://www.anthropic.com/news/claude-opus-4-5
DEFAULT_MODEL = "claude-opus-4-5-20251101"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="EverythingBagelAI Coding Agent Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start fresh greenfield project
  python autonomous_agent_demo.py --project-dir ./claude_clone

  # Use a specific model
  python autonomous_agent_demo.py --project-dir ./claude_clone --model claude-sonnet-4-5-20250929

  # Limit iterations for testing
  python autonomous_agent_demo.py --project-dir ./claude_clone --max-iterations 5

  # Brownfield - work on existing codebase
  python autonomous_agent_demo.py --mode brownfield --existing-dir /path/to/repo

  # Epic - multi-epic orchestration
  python autonomous_agent_demo.py --project-dir ./my-project --mode epic

  # With per-session cost cap
  python autonomous_agent_demo.py --project-dir ./demo --max-budget 10.0

  # Continue existing project
  python autonomous_agent_demo.py --project-dir ./claude_clone

Environment Variables:
  CLAUDE_CODE_OAUTH_TOKEN    Claude Code OAuth token (required)
  LINEAR_API_KEY             Linear API key (required)
        """,
    )

    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("./autonomous_demo_project"),
        help="Directory for the project (default: generations/autonomous_demo_project). Relative paths automatically placed in generations/ directory.",
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["greenfield", "brownfield", "epic"],
        default="greenfield",
        help="Development mode: greenfield (new project), brownfield (existing codebase), or epic (multi-epic orchestration). Default: greenfield.",
    )

    parser.add_argument(
        "--existing-dir",
        type=Path,
        default=None,
        help="Path to existing codebase (required for brownfield mode).",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of agent iterations (default: unlimited)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )

    return parser.parse_args()


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

    # Determine project directory based on mode
    mode = args.mode

    if mode == "brownfield":
        if args.existing_dir is None:
            print("Error: --existing-dir is required for brownfield mode")
            print("\nUsage: python autonomous_agent_demo.py --mode brownfield --existing-dir /path/to/repo")
            return

        project_dir = args.existing_dir.resolve()
        if not project_dir.is_dir():
            print(f"Error: --existing-dir '{project_dir}' does not exist or is not a directory")
            return

        # Validate it looks like a real project (has git or package.json or pyproject.toml)
        indicators = [".git", "package.json", "pyproject.toml", "Cargo.toml", "go.mod"]
        has_indicator = any((project_dir / f).exists() for f in indicators)
        if not has_indicator:
            print(f"Warning: '{project_dir}' doesn't look like a project directory")
            print(f"  (no {', '.join(indicators)} found)")
            print("  Continuing anyway...\n")

    elif mode == "epic":
        # Epic mode uses --project-dir as the target project directory
        project_dir = args.project_dir
        if not str(project_dir).startswith("generations/"):
            if project_dir.is_absolute():
                pass
            else:
                project_dir = Path("generations") / project_dir

    else:
        # Greenfield: existing behaviour — place in generations/
        project_dir = args.project_dir
        if not str(project_dir).startswith("generations/"):
            if project_dir.is_absolute():
                pass
            else:
                project_dir = Path("generations") / project_dir

    # Run the agent
    try:
        if mode == "epic":
            from epic_orchestrator import run_epic_mode
            asyncio.run(run_epic_mode(
                project_dir=project_dir,
                model=args.model,
                max_iterations=args.max_iterations,
            ))
        else:
            asyncio.run(
                run_autonomous_agent(
                    project_dir=project_dir,
                    model=args.model,
                    max_iterations=args.max_iterations,
                    mode=mode,
                )
            )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print("To resume, run the same command again")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise


if __name__ == "__main__":
    main()
