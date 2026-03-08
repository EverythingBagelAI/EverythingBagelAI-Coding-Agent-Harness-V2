"""
Claude SDK Client Configuration
===============================

Functions for creating and configuring the Claude Agent SDK client.
Dynamically builds configuration from the discovered ecosystem.
"""

from pathlib import Path
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

from discovery import EcosystemInfo, build_dynamic_system_prompt, discover_user_ecosystem, _filter_mcps_by_session
from security import bash_security_hook


# Built-in tools always available
BUILTIN_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
]


def create_client(
    project_dir: Path,
    model: str,
    mode: str = "greenfield",
    ecosystem: Optional[EcosystemInfo] = None,
    system_prompt_override: Optional[str] = None,
    session_type: Optional[str] = None,
    max_turns: int = 200,
) -> ClaudeSDKClient:
    """
    Create a Claude Agent SDK client with dynamic configuration.

    Uses the discovered ecosystem to configure MCP servers, allowed/disallowed
    tools, system prompt, and security hooks — all dynamically.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        mode: "greenfield" or "brownfield"
        ecosystem: Pre-discovered ecosystem (runs discovery if None)
        system_prompt_override: If provided, use this instead of the dynamic system prompt
    Returns:
        Configured ClaudeSDKClient

    Security layers (defence in depth):
    1. Sandbox — OS-level bash command isolation prevents filesystem escape
    2. Permissions — File operations restricted to project_dir via acceptEdits
    3. Security hooks — Bash commands validated against a dynamic allowlist
       (see security.py, configured from discovery.py)
    4. Disallowed tools — Conflicting frameworks blocked at SDK level
    """
    from linear_config import get_linear_api_key
    linear_api_key = get_linear_api_key()

    # Run discovery if not pre-computed
    if ecosystem is None:
        ecosystem = discover_user_ecosystem(project_dir, linear_api_key)

    # Apply session-scoped MCP filtering
    mcp_servers = _filter_mcps_by_session(ecosystem.merged_mcp_servers, session_type)

    # Build dynamic allowed tools: built-ins + wildcard per MCP server
    allowed_tools: list[str] = list(BUILTIN_TOOLS)
    for server_name in mcp_servers:
        allowed_tools.append(f"mcp__{server_name}__*")

    # Build dynamic system prompt (or use override)
    system_prompt = system_prompt_override or build_dynamic_system_prompt(ecosystem, mode)

    # Print client configuration summary
    print("Client Configuration:")
    print(f"   - Model: {model}")
    print(f"   - Mode: {mode}")
    print(f"   - MCP servers: {len(mcp_servers)}")
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
            mcp_servers=mcp_servers,
            permission_mode="acceptEdits",
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
                ],
            },
            max_turns=max_turns,
            cwd=str(project_dir.resolve()),
        )
    )
