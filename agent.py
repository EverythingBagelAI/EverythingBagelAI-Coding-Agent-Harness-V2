"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

from claude_agent_sdk import ClaudeSDKClient

from client import create_client
from discovery import EcosystemInfo, discover_user_ecosystem, print_discovery_summary
from progress import print_session_header, print_progress_summary, is_linear_initialized, is_project_complete
from prompts import get_initializer_prompt, get_coding_prompt, get_brownfield_initializer_prompt, copy_spec_to_project
from security import configure_allowed_commands


# Configuration
AUTO_CONTINUE_DELAY_SECONDS = 3


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
) -> tuple[str, str]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path

    Returns:
        (status, response_text) where status is:
        - "continue" if agent should continue working
        - "error" if an error occurred
    """
    print("Sending prompt to Claude Agent SDK...\n")

    try:
        # Send the query
        await client.query(message)

        # Collect response text and show tool use
        response_text = ""
        async for msg in client.receive_response():
            msg_type = type(msg).__name__

            # Handle AssistantMessage (text and tool use)
            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "TextBlock" and hasattr(block, "text"):
                        response_text += block.text
                        print(block.text, end="", flush=True)
                    elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                        print(f"\n[Tool: {block.name}]", flush=True)
                        if hasattr(block, "input"):
                            input_str = str(block.input)
                            if len(input_str) > 200:
                                print(f"   Input: {input_str[:200]}...", flush=True)
                            else:
                                print(f"   Input: {input_str}", flush=True)

            # Handle UserMessage (tool results)
            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "ToolResultBlock":
                        result_content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)

                        # Check if command was blocked by security hook
                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            # Show errors (truncated)
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            # Tool succeeded - just show brief confirmation
                            print("   [Done]", flush=True)

            # Handle ResultMessage (session summary with cost)
            elif msg_type == "ResultMessage":
                _log_session_cost(msg)

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except Exception as e:
        print(f"Error during agent session: {e}")
        return "error", str(e)


def _log_session_cost(result_msg) -> None:
    """Log cost and usage from a ResultMessage."""
    cost = getattr(result_msg, "total_cost_usd", None)
    turns = getattr(result_msg, "num_turns", None)
    duration = getattr(result_msg, "duration_ms", None)

    parts = []
    if cost is not None:
        parts.append(f"Cost: ${cost:.4f}")
    if turns is not None:
        parts.append(f"Turns: {turns}")
    if duration is not None:
        seconds = duration / 1000
        parts.append(f"Duration: {seconds:.1f}s")

    if parts:
        print(f"\n  Session stats: {' | '.join(parts)}")


async def run_autonomous_agent(
    project_dir: Path,
    model: str,
    max_iterations: Optional[int] = None,
    mode: str = "greenfield",
) -> None:
    """
    Run the autonomous agent loop.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        max_iterations: Maximum number of iterations (None for unlimited)
        mode: "greenfield" or "brownfield"
    """
    print("\n" + "=" * 70)
    print("  EVERYTHINGBAGELAI CODING AGENT HARNESS")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print(f"Model: {model}")
    print(f"Mode: {mode}")
    if max_iterations:
        print(f"Max iterations: {max_iterations}")
    else:
        print("Max iterations: Unlimited (will run until completion)")
    print()

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    # --- Dynamic Ecosystem Discovery ---
    linear_api_key = os.environ.get("LINEAR_API_KEY", "")
    ecosystem = discover_user_ecosystem(project_dir, linear_api_key)
    print_discovery_summary(ecosystem)

    # Configure security with discovered commands
    configure_allowed_commands(ecosystem.merged_allowed_commands)

    # Check if this is a fresh start or continuation
    # We use .linear_project.json as the marker for initialization
    is_first_run = not is_linear_initialized(project_dir)

    if is_first_run:
        if mode == "greenfield":
            print("Fresh start (greenfield) - will use initialiser agent")
            print()
            print("=" * 70)
            print("  NOTE: First session takes 10-20+ minutes!")
            print("  The agent is analysing the spec and creating Linear issues")
            print("  (typically 50-300 based on complexity).")
            print("  This may appear to hang - it's working. Watch for [Tool: ...] output.")
            print("=" * 70)
            print()
            # Copy the app spec into the project directory for the agent to read
            copy_spec_to_project(project_dir)
        else:
            print("Fresh start (brownfield) - will analyse existing codebase")
            print()
            print("=" * 70)
            print("  NOTE: First session takes 10-20+ minutes!")
            print("  The agent is analysing the existing codebase and creating")
            print("  Linear issues for the work defined in app_spec.txt.")
            print("=" * 70)
            print()
            # Copy the app spec into the project directory for the agent to read
            copy_spec_to_project(project_dir)
    else:
        print("Continuing existing project (Linear initialised)")
        print_progress_summary(project_dir)

    # Main loop
    iteration = 0

    while True:
        iteration += 1

        # Check max iterations
        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations})")
            print("To continue, run the script again without --max-iterations")
            break

        # Print session header
        print_session_header(iteration, is_first_run)

        # Create client (fresh context) with discovered ecosystem
        client = create_client(
            project_dir,
            model,
            mode=mode,
            ecosystem=ecosystem,
        )

        # Choose prompt based on session type and mode
        if is_first_run:
            if mode == "brownfield":
                prompt = get_brownfield_initializer_prompt()
            else:
                prompt = get_initializer_prompt()
            is_first_run = False  # Only use initialiser once
        else:
            prompt = get_coding_prompt()

        # Run session with async context manager
        async with client:
            status, response = await run_agent_session(client, prompt, project_dir)

        # Check if project is complete after each session
        if is_project_complete(project_dir):
            print("\n" + "=" * 70)
            print("  PROJECT COMPLETE")
            print("=" * 70)
            print("\nAll non-META Linear issues are Done.")
            print_progress_summary(project_dir)
            break

        # Handle status
        if status == "continue":
            print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
            print_progress_summary(project_dir)
            await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        elif status == "error":
            print("\nSession encountered an error")
            print("Will retry with a fresh session...")
            await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        # Small delay between sessions
        if max_iterations is None or iteration < max_iterations:
            print("\nPreparing next session...\n")
            await asyncio.sleep(1)

    # Final summary
    print("\n" + "=" * 70)
    print("  SESSION COMPLETE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print_progress_summary(project_dir)

    # Print instructions for running the generated application
    print("\n" + "-" * 70)
    print("  TO RUN THE GENERATED APPLICATION:")
    print("-" * 70)
    print(f"\n  cd {project_dir.resolve()}")
    print("  ./init.sh           # Run the setup script")
    print("  # Or manually:")
    print("  npm install && npm run dev")
    print("\n  Then open http://localhost:3000 (or check init.sh for the URL)")
    print("-" * 70)

    print("\nDone!")
