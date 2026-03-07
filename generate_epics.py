#!/usr/bin/env python3
"""
Epic Generator
==============

Standalone script that reads a master app spec and uses an Architect Agent
to decompose it into epic sub-specs in the epics/ directory.

Usage:
    python generate_epics.py --project-dir ./my-project
    python generate_epics.py --project-dir ./my-project --spec path/to/custom_spec.md
    python generate_epics.py --project-dir ./my-project --model claude-opus-4-5-20251101
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

from agent import run_agent_session
from discovery import discover_user_ecosystem, print_discovery_summary
from security import bash_security_hook, configure_allowed_commands


# Configuration
DEFAULT_MODEL = "claude-opus-4-5-20251101"
PROMPTS_DIR = Path(__file__).parent / "prompts"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate epic sub-specs from a master app spec",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default spec (prompts/master_app_spec.md)
  python generate_epics.py --project-dir ./my-project

  # Use a custom spec file
  python generate_epics.py --project-dir ./my-project --spec path/to/custom_spec.md

  # Use a specific model
  python generate_epics.py --project-dir ./my-project --model claude-sonnet-4-5-20250929

Environment Variables:
  CLAUDE_CODE_OAUTH_TOKEN    Claude Code OAuth token (required)
  LINEAR_API_KEY             Linear API key (required)
        """,
    )

    parser.add_argument(
        "--spec",
        type=Path,
        default=PROMPTS_DIR / "master_app_spec.md",
        help="Path to the master app spec (default: prompts/master_app_spec.md)",
    )

    parser.add_argument(
        "--project-dir", type=Path, required=True,
        help="Target project directory for generated epics",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )

    return parser.parse_args()


def create_architect_client(
    model: str,
    system_prompt: str,
    project_dir: Path,
) -> ClaudeSDKClient:
    """
    Create a Claude Agent SDK client configured for the Architect Agent.

    Follows the same pattern as client.py's create_client but tailored
    for epic generation rather than the full coding harness.

    Args:
        model: Claude model to use
        system_prompt: The architect prompt content
        project_dir: Target project directory (used as agent CWD)

    Returns:
        Configured ClaudeSDKClient
    """
    linear_api_key = os.environ.get("LINEAR_API_KEY", "")

    # Dynamic ecosystem discovery
    ecosystem = discover_user_ecosystem(project_dir, linear_api_key)
    print_discovery_summary(ecosystem)

    # Configure security with discovered commands
    configure_allowed_commands(ecosystem.merged_allowed_commands)

    # Built-in tools always available
    allowed_tools: list[str] = [
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "Bash",
    ]

    # Add wildcard per MCP server
    for server_name in ecosystem.merged_mcp_servers:
        allowed_tools.append(f"mcp__{server_name}__*")

    # Print client configuration summary
    print("Architect Client Configuration:")
    print(f"   - Model: {model}")
    print(f"   - MCP servers: {len(ecosystem.merged_mcp_servers)}")
    print(f"   - Allowed tools: {len(allowed_tools)}")
    if ecosystem.disallowed_tools:
        print(f"   - Disallowed tools: {len(ecosystem.disallowed_tools)}")
    print(f"   - Bash allowlist: {len(ecosystem.merged_allowed_commands)} commands")
    print()

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
            disallowed_tools=ecosystem.disallowed_tools,
            mcp_servers=ecosystem.merged_mcp_servers,
            permission_mode="acceptEdits",
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
                ],
            },
            max_turns=1000,
            cwd=str(project_dir.resolve()),
        )
    )


async def generate_epics(spec_path: Path, model: str, project_dir: Path) -> None:
    """
    Run the Architect Agent to decompose a master spec into epics.

    Args:
        spec_path: Path to the master app spec
        model: Claude model to use
        project_dir: Target project directory for generated output
    """
    print("\n" + "=" * 70)
    print("  EVERYTHINGBAGELAI EPIC GENERATOR")
    print("=" * 70)
    print(f"\nSpec file: {spec_path}")
    print(f"Model: {model}")
    print(f"Project dir: {project_dir.resolve()}")
    print(f"Output: {project_dir / 'epics'}")
    print()

    # Load the architect prompt
    architect_prompt_path = PROMPTS_DIR / "architect_prompt.md"
    if not architect_prompt_path.exists():
        print(f"Error: Architect prompt not found at {architect_prompt_path}")
        sys.exit(1)

    architect_prompt = architect_prompt_path.read_text()

    # Build the task message
    task_message = (
        f"Read {spec_path} and decompose it into epic sub-specs.\n"
        "\n"
        "Produce the following files:\n"
        "- epics/spec_index.md\n"
        "- epics/spec_index.json (machine-readable index — see system prompt)\n"
        "- shared_context.md (in the PROJECT ROOT, not epics/)\n"
        "- epics/epic-01-[name].md\n"
        "- epics/epic-02-[name].md\n"
        "- (etc. for each epic)\n"
        "\n"
        "Follow the instructions in your system prompt exactly."
    )

    # Create the architect client
    client = create_architect_client(model, architect_prompt, project_dir)

    # Ensure project and epics directories exist
    project_dir.mkdir(parents=True, exist_ok=True)
    epics_dir = project_dir / "epics"
    epics_dir.mkdir(parents=True, exist_ok=True)

    print("Starting Architect Agent session...")
    print("This may take several minutes depending on spec complexity.")
    print()

    # Run the agent session
    async with client:
        status, response = await run_agent_session(client, task_message, project_dir)

    if status == "error":
        print(f"\nArchitect Agent encountered an error: {response}")
        sys.exit(1)

    # Success message
    print("\n" + "=" * 70)
    print("  EPICS GENERATED")
    print("=" * 70)
    print()
    print(f"Epics generated in {project_dir / 'epics'}")
    print()
    print("Next steps:")
    print(f"1. Review and edit each file in {project_dir / 'epics'} -- especially the human gate checklists")
    print(f"2. Run: python autonomous_agent_demo.py --project-dir {project_dir} --mode epic")
    print()


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

    # Validate spec file exists
    spec_path = args.spec
    if not spec_path.exists():
        print(f"Error: Spec file not found: {spec_path}")
        print()
        print("Either:")
        print(f"  1. Create your spec at {spec_path}")
        print("  2. Copy and edit the template:")
        print("     cp templates/master_app_spec_template.md prompts/master_app_spec.md")
        print("  3. Pass a custom path: python generate_epics.py --spec path/to/spec.md")
        return

    # Run the epic generator
    try:
        asyncio.run(generate_epics(spec_path, args.model, args.project_dir))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise


if __name__ == "__main__":
    main()
