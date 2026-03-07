"""
Security Hooks for EverythingBagelAI Coding Agent Harness
==========================================

Pre-tool-use hooks that validate bash commands for security.
Uses an allowlist approach - only explicitly permitted commands can run.

The allowlist is configurable at runtime via configure_allowed_commands(),
called from agent.py after ecosystem discovery.
"""

import os
import shlex


# Default allowed commands (used if configure_allowed_commands is never called)
_DEFAULT_ALLOWED_COMMANDS: set[str] = {
    # File inspection
    "ls", "cat", "head", "tail", "wc", "grep",
    # File operations
    "cp", "mkdir", "chmod",
    "find", "echo", "touch", "mv", "rm", "sed", "awk",
    # Directory
    "pwd",
    # Node.js development
    "npm", "node", "npx",
    # Python development
    "python3", "python", "pytest", "pip", "pip3", "export",
    # Version control
    "git",
    # Process management
    "ps", "lsof", "sleep", "pkill",
    # Archive
    "unzip", "tar",
    # Script execution
    "init.sh",
}

# Active allowlist — starts as defaults, updated by configure_allowed_commands()
_allowed_commands: set[str] = set(_DEFAULT_ALLOWED_COMMANDS)

# Commands that need additional validation even when in the allowlist
COMMANDS_NEEDING_EXTRA_VALIDATION = {"pkill", "chmod", "init.sh", "rm", "git", "mv", "cp", "sed", "awk", "export"}


def configure_allowed_commands(commands: set[str]) -> None:
    """
    Configure the active bash command allowlist.

    Called from agent.py after ecosystem discovery merges the default
    set with commands extracted from the user's settings.local.json.

    Args:
        commands: The complete set of allowed command names
    """
    global _allowed_commands
    _allowed_commands = commands
    print(f"Security: Bash allowlist configured with {len(_allowed_commands)} commands")


def get_allowed_commands() -> set[str]:
    """Return the current active allowlist (for testing/inspection)."""
    return set(_allowed_commands)


def split_command_segments(command_string: str) -> list[str]:
    """
    Split a compound command into individual command segments.

    Handles command chaining (&&, ||, ;) but not pipes (those are single commands).

    Args:
        command_string: The full shell command

    Returns:
        List of individual command segments
    """
    import re

    # Split on && and || while preserving the ability to handle each segment
    # This regex splits on && or || that aren't inside quotes
    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    # Further split on semicolons
    result = []
    for segment in segments:
        sub_segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            if sub:
                result.append(sub)

    return result


def extract_commands(command_string: str) -> list[str]:
    """
    Extract command names from a shell command string.

    Handles pipes, command chaining (&&, ||, ;), and subshells.
    Returns the base command names (without paths).

    Args:
        command_string: The full shell command

    Returns:
        List of command names found in the string
    """
    commands = []

    # shlex doesn't treat ; as a separator, so we need to pre-process
    import re

    # Split on semicolons that aren't inside quotes (simple heuristic)
    # This handles common cases like "echo hello; ls"
    segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', command_string)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Malformed command (unclosed quotes, etc.)
            # Return empty to trigger block (fail-safe)
            return []

        if not tokens:
            continue

        # Track when we expect a command vs arguments
        expect_command = True

        for token in tokens:
            # Shell operators indicate a new command follows
            if token in ("|", "||", "&&", "&"):
                expect_command = True
                continue

            # Skip shell keywords that precede commands
            if token in (
                "if",
                "then",
                "else",
                "elif",
                "fi",
                "for",
                "while",
                "until",
                "do",
                "done",
                "case",
                "esac",
                "in",
                "!",
                "{",
                "}",
            ):
                continue

            # Skip flags/options
            if token.startswith("-"):
                continue

            # Skip variable assignments (VAR=value)
            if "=" in token and not token.startswith("="):
                continue

            if expect_command:
                # Extract the base command name (handle paths like /usr/bin/python)
                cmd = os.path.basename(token)
                commands.append(cmd)
                expect_command = False

    return commands


def validate_pkill_command(command_string: str) -> tuple[bool, str]:
    """
    Validate pkill commands - only allow killing dev-related processes.

    Uses shlex to parse the command, avoiding regex bypass vulnerabilities.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    # Allowed process names for pkill
    allowed_process_names = {
        "node",
        "npm",
        "npx",
        "vite",
        "next",
    }

    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse pkill command"

    if not tokens:
        return False, "Empty pkill command"

    # Separate flags from arguments
    args = []
    for token in tokens[1:]:
        if not token.startswith("-"):
            args.append(token)

    if not args:
        return False, "pkill requires a process name"

    # The target is typically the last non-flag argument
    target = args[-1]

    # For -f flag (full command line match), extract the first word as process name
    # e.g., "pkill -f 'node server.js'" -> target is "node server.js", process is "node"
    if " " in target:
        target = target.split()[0]

    if target in allowed_process_names:
        return True, ""
    return False, f"pkill only allowed for dev processes: {allowed_process_names}"


def validate_chmod_command(command_string: str) -> tuple[bool, str]:
    """
    Validate chmod commands - only allow making files executable with +x.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse chmod command"

    if not tokens or tokens[0] != "chmod":
        return False, "Not a chmod command"

    # Look for the mode argument
    # Valid modes: +x, u+x, a+x, etc. (anything ending with +x for execute permission)
    mode = None
    files = []

    for token in tokens[1:]:
        if token.startswith("-"):
            # Skip flags like -R (we don't allow recursive chmod anyway)
            return False, "chmod flags are not allowed"
        elif mode is None:
            mode = token
        else:
            files.append(token)

    if mode is None:
        return False, "chmod requires a mode"

    if not files:
        return False, "chmod requires at least one file"

    # Only allow +x variants (making files executable)
    # This matches: +x, u+x, g+x, o+x, a+x, ug+x, etc.
    import re

    if not re.match(r"^[ugoa]*\+x$", mode):
        return False, f"chmod only allowed with +x mode, got: {mode}"

    return True, ""


def validate_rm_command(command_string: str) -> tuple[bool, str]:
    """Validate rm — block path traversal outside project dir."""
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse rm command"

    if not tokens:
        return False, "Empty rm command"

    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        # Block absolute paths
        if token.startswith("/"):
            return False, "rm with absolute paths is not permitted"
        # Block path traversal
        if ".." in token:
            return False, "rm with path traversal (..) is not permitted"
        # Block home directory references
        if token.startswith("~"):
            return False, "rm with ~ paths is not permitted"

    # Block dangerously short targets with recursive flag
    import re
    has_recursive = any(
        "r" in t.lstrip("-") for t in tokens[1:] if t.startswith("-")
    )
    for token in tokens[1:]:
        if not token.startswith("-"):
            if has_recursive and token in (".", "*", "./"):
                return False, f"rm -r on '{token}' is not permitted"

    return True, ""


def validate_git_command(command_string: str) -> tuple[bool, str]:
    """Validate git commands — block destructive remote operations."""
    BLOCKED_SUBCOMMANDS = {
        "push",       # Never push without human review
        "remote",     # Don't let agent add/change remotes
        "reset",      # Too destructive
        "rebase",     # Too destructive
    }
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse git command"

    if len(tokens) < 2:
        return True, ""  # bare `git` is fine

    # Scan all tokens for blocked subcommands — not just index 1
    # This prevents bypass via `git -c key=val push`
    for token in tokens[1:]:
        if token.startswith("-"):
            continue  # skip flags
        if token in BLOCKED_SUBCOMMANDS:
            return False, f"git {token} is not permitted — human review required"

    # Block --force anywhere in the command but NOT inside quoted commit messages
    # Check only actual flag tokens (starting with -)
    flag_tokens = [t for t in tokens[1:] if t.startswith("-")]
    if "--force" in flag_tokens:
        return False, "git --force is not permitted"

    # Block -f only as a standalone flag (not inside -m "message with -f")
    # Find flags that are value-taking and exclude the next token from flag checks
    force_check_tokens = []
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in ("-m", "--message", "--author", "--date"):
            skip_next = True  # next token is a value, not a flag
            continue
        force_check_tokens.append(token)

    if "-f" in force_check_tokens:
        return False, "git -f is not permitted"

    return True, ""


def validate_file_command_paths(command_string: str) -> tuple[bool, str]:
    """
    Validate file operation commands — block absolute paths and traversal.
    Used for mv, cp, sed, awk and similar commands.
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse command"

    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        if token.startswith("/"):
            return False, f"Absolute paths are not permitted: {token}"
        if ".." in token:
            return False, f"Path traversal (..) is not permitted: {token}"
        if token.startswith("~"):
            return False, f"Home directory paths are not permitted: {token}"

    return True, ""


def validate_export_command(command_string: str) -> tuple[bool, str]:
    """Validate export — block overriding sensitive environment variables."""
    PROTECTED_VARS = {
        "LINEAR_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
        "REF_API_KEY", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID",
        "DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    }
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse export command"

    for token in tokens[1:]:
        var_name = token.split("=")[0].upper()
        if var_name in PROTECTED_VARS:
            return False, f"export of protected variable '{var_name}' is not permitted"

    return True, ""


def validate_init_script(command_string: str) -> tuple[bool, str]:
    """
    Validate init.sh script execution - only allow ./init.sh.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse init script command"

    if not tokens:
        return False, "Empty command"

    # The command should be exactly ./init.sh (possibly with arguments)
    script = tokens[0]

    # Allow ./init.sh or paths ending in /init.sh
    if script == "./init.sh" or script.endswith("/init.sh"):
        return True, ""

    return False, f"Only ./init.sh is allowed, got: {script}"


def get_command_for_validation(cmd: str, segments: list[str]) -> str:
    """
    Find the specific command segment that contains the given command.

    Args:
        cmd: The command name to find
        segments: List of command segments

    Returns:
        The segment containing the command, or empty string if not found
    """
    for segment in segments:
        segment_commands = extract_commands(segment)
        if cmd in segment_commands:
            return segment
    return ""


async def bash_security_hook(input_data, tool_use_id=None, context=None):
    """
    Pre-tool-use hook that validates bash commands using an allowlist.

    Only commands in _allowed_commands are permitted.

    Args:
        input_data: Dict containing tool_name and tool_input
        tool_use_id: Optional tool use ID
        context: Optional context

    Returns:
        Empty dict to allow, or {"decision": "block", "reason": "..."} to block
    """
    if input_data.get("tool_name") != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return {}

    # Block subshell syntax that could bypass the allowlist
    SUBSHELL_PATTERNS = ["`", "$(", "<("]
    for pattern in SUBSHELL_PATTERNS:
        if pattern in command:
            return {
                "decision": "block",
                "reason": f"Subshell syntax '{pattern}' is not allowed",
            }

    # Extract all commands from the command string
    commands = extract_commands(command)

    if not commands:
        # Could not parse - fail safe by blocking
        return {
            "decision": "block",
            "reason": f"Could not parse command for security validation: {command}",
        }

    # Split into segments for per-command validation
    segments = split_command_segments(command)

    # Check each command against the allowlist
    for cmd in commands:
        if cmd not in _allowed_commands:
            return {
                "decision": "block",
                "reason": f"Command '{cmd}' is not in the allowed commands list",
            }

    # Additional validation for sensitive commands — check ALL pipe segments.
    # This covers pipe-bypass attacks like `cat foo | pkill bash` where the
    # dangerous command is not the first segment (S13 fix).
    pipe_segments = [s.strip() for s in command.split("|")]
    for segment in pipe_segments:
        segment_cmds = extract_commands(segment)
        for cmd in segment_cmds:
            if cmd in COMMANDS_NEEDING_EXTRA_VALIDATION:
                if cmd == "pkill":
                    allowed, reason = validate_pkill_command(segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}
                elif cmd == "chmod":
                    allowed, reason = validate_chmod_command(segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}
                elif cmd == "init.sh":
                    allowed, reason = validate_init_script(segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}
                elif cmd == "rm":
                    allowed, reason = validate_rm_command(segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}
                elif cmd == "git":
                    allowed, reason = validate_git_command(segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}
                elif cmd in ("mv", "cp", "sed", "awk"):
                    allowed, reason = validate_file_command_paths(segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}
                elif cmd == "export":
                    allowed, reason = validate_export_command(segment)
                    if not allowed:
                        return {"decision": "block", "reason": reason}

    return {}
