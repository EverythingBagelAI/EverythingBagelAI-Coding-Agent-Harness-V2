"""
Dynamic Ecosystem Discovery
============================

Analyses any user's Claude Code setup at runtime and builds a dynamic
configuration for the harness. Works for ANY user's setup — not hardcoded.

Key capabilities:
  - Discovers MCP servers from ~/.claude.json (global + project-specific)
  - Detects conflicting task management frameworks (GSD, etc.)
  - Extracts user-approved bash commands from settings.local.json
  - Merges everything into an EcosystemInfo for client.py to consume
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_JSON = Path.home() / ".claude.json"

# Session-scoped MCP loading — maps session types to the MCPs they need.
# None = load all (preserves V1 behaviour). List = case-insensitive substring match.
SESSION_MCP_SCOPES: dict[str, list[str] | None] = {
    "architect": ["ref", "exa"],
    "epic_initializer": ["linear"],
    "coding": ["linear", "ref"],
    "initializer": None,
    "standard": None,
}

# Default bash commands always allowed for development
DEFAULT_ALLOWED_COMMANDS: set[str] = {
    "ls", "cat", "head", "tail", "wc", "grep",
    "cp", "mkdir", "chmod",
    "pwd",
    "npm", "node", "npx",
    "git",
    "ps", "lsof", "sleep", "pkill",
    "init.sh",
}

# Known safe plugins/skills/frameworks — never flagged as conflicts
KNOWN_SAFE_NAMES: set[str] = {
    # Official Anthropic
    "document-skills", "example-skills",
    # Utility plugins
    "superpowers", "episodic-memory", "recall", "obsidian",
    "double-shot-latte", "elements-of-style",
    # Visualisation skills
    "excalidraw-diagram", "mermaid-visualizer", "obsidian-canvas-creator",
    # UI/UX
    "ui-ux-pro-max",
    # Config tools
    "configure-ecc", "strategic-compact",
}

# Known conflicting framework names — always flagged
KNOWN_CONFLICTING_NAMES: set[str] = {
    "gsd", "get-shit-done", "get_shit_done",
    "ralph-wiggum", "ralph_wiggum",
}

# Strong keywords — a single match is enough to flag
STRONG_CONFLICT_KEYWORDS: set[str] = {
    "agent loop", "autonomous loop", "session driver",
    "continuous loop", "phase execution",
}

# Generic keywords — require 2+ matches to flag
GENERIC_CONFLICT_KEYWORDS: set[str] = {
    "task management", "task tracking", "project management",
    "issue tracker", "sprint planning", "kanban",
    "todo management", "work management",
}


# ---------------------------------------------------------------------------
# Pydantic V2 Models
# ---------------------------------------------------------------------------

class McpServerEntry(BaseModel):
    """A single MCP server configuration."""
    name: str
    config: dict[str, Any]
    source: str  # "global", "project", "harness"


class ConflictingFramework(BaseModel):
    """A detected conflicting task management framework."""
    name: str
    source: str  # "plugin", "skill", "command", "directory"
    reason: str
    disallowed_tools: list[str] = Field(default_factory=list)


class PluginInfo(BaseModel):
    """Metadata about an installed plugin."""
    name: str
    marketplace: str
    install_path: str = ""
    version: str = ""
    is_enabled: bool = False


class SkillInfo(BaseModel):
    """Metadata about a user skill."""
    name: str
    directory: str


class BashCommandEntry(BaseModel):
    """A bash command extracted from user permissions."""
    command: str
    source: str  # "default", "user_settings"


class EcosystemInfo(BaseModel):
    """Complete picture of a user's Claude Code ecosystem."""

    # MCP servers
    global_mcp_servers: list[McpServerEntry] = Field(default_factory=list)
    project_mcp_servers: list[McpServerEntry] = Field(default_factory=list)
    harness_mcp_servers: list[McpServerEntry] = Field(default_factory=list)
    merged_mcp_servers: dict[str, Any] = Field(default_factory=dict)

    # Plugins and skills
    plugins: list[PluginInfo] = Field(default_factory=list)
    skills: list[SkillInfo] = Field(default_factory=list)

    # Conflict detection
    conflicting_frameworks: list[ConflictingFramework] = Field(default_factory=list)
    disallowed_tools: list[str] = Field(default_factory=list)

    # Bash security
    user_approved_commands: list[BashCommandEntry] = Field(default_factory=list)
    merged_allowed_commands: set[str] = Field(default_factory=set)

    # Diagnostics
    config_files_found: list[str] = Field(default_factory=list)
    config_files_missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def aggregate_disallowed_tools(self) -> "EcosystemInfo":
        """Aggregate disallowed_tools from all conflicting frameworks."""
        all_disallowed: list[str] = []
        for conflict in self.conflicting_frameworks:
            all_disallowed.extend(conflict.disallowed_tools)
        self.disallowed_tools = sorted(set(all_disallowed))
        return self


# ---------------------------------------------------------------------------
# Discovery Functions
# ---------------------------------------------------------------------------

def _read_json_safe(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning None on any error."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError, PermissionError) as e:
        logger.warning("Could not read %s: %s", path, e)
        return None


def load_user_mcp_servers(
    project_dir: Path | None = None,
) -> tuple[list[McpServerEntry], list[McpServerEntry], list[str], list[str]]:
    """
    Load MCP servers from the user's Claude Code config.

    Reads:
      - ~/.claude.json -> mcpServers (global)
      - ~/.claude.json -> projects.{project_dir}.mcpServers (project-specific)

    Returns:
        (global_servers, project_servers, files_found, files_missing)
    """
    global_servers: list[McpServerEntry] = []
    project_servers: list[McpServerEntry] = []
    files_found: list[str] = []
    files_missing: list[str] = []

    data = _read_json_safe(CLAUDE_JSON)
    if data is None:
        files_missing.append(str(CLAUDE_JSON))
        return global_servers, project_servers, files_found, files_missing

    files_found.append(str(CLAUDE_JSON))

    # Global MCP servers
    global_mcps = data.get("mcpServers", {})
    for name, config in global_mcps.items():
        global_servers.append(McpServerEntry(
            name=name,
            config=config,
            source="global",
        ))

    # Project-specific MCP servers
    if project_dir is not None:
        resolved = str(project_dir.resolve())
        projects = data.get("projects", {})

        # Try exact match first, then parent directories
        for project_path, project_config in projects.items():
            if resolved.startswith(project_path) or project_path == resolved:
                project_mcps = project_config.get("mcpServers", {})
                for name, config in project_mcps.items():
                    project_servers.append(McpServerEntry(
                        name=name,
                        config=config,
                        source="project",
                    ))
                break

    return global_servers, project_servers, files_found, files_missing


def load_installed_plugins() -> list[PluginInfo]:
    """
    Load installed plugins from ~/.claude/plugins/installed_plugins.json.

    Returns:
        List of PluginInfo for all installed plugins
    """
    plugins_file = CLAUDE_HOME / "plugins" / "installed_plugins.json"
    data = _read_json_safe(plugins_file)
    if data is None:
        return []

    plugins: list[PluginInfo] = []
    plugin_entries = data.get("plugins", {})

    # Read enabled plugins from settings.json
    settings = _read_json_safe(CLAUDE_HOME / "settings.json")
    enabled_plugins: dict[str, bool] = {}
    if settings:
        enabled_plugins = settings.get("enabledPlugins", {})

    for plugin_id, installs in plugin_entries.items():
        # plugin_id format: "name@marketplace"
        parts = plugin_id.split("@", 1)
        name = parts[0]
        marketplace = parts[1] if len(parts) > 1 else "unknown"

        install = installs[0] if installs else {}

        plugins.append(PluginInfo(
            name=name,
            marketplace=marketplace,
            install_path=install.get("installPath", ""),
            version=install.get("version", ""),
            is_enabled=enabled_plugins.get(plugin_id, False),
        ))

    return plugins


def load_user_skills() -> list[SkillInfo]:
    """
    Load user skills from ~/.claude/skills/.

    Returns:
        List of SkillInfo for all discovered skills
    """
    skills_dir = CLAUDE_HOME / "skills"
    if not skills_dir.is_dir():
        return []

    skills: list[SkillInfo] = []
    for entry in skills_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            skills.append(SkillInfo(
                name=entry.name,
                directory=str(entry),
            ))

    return skills


def _check_name_conflict(name: str) -> bool:
    """Check if a name matches known conflicting frameworks."""
    normalised = name.lower().replace("_", "-").replace(" ", "-")
    for conflicting in KNOWN_CONFLICTING_NAMES:
        if conflicting in normalised:
            return True
    return False


def _check_safe_name(name: str) -> bool:
    """Check if a name is in the known safe list."""
    normalised = name.lower().replace("_", "-").replace(" ", "-")
    for safe in KNOWN_SAFE_NAMES:
        if safe in normalised:
            return True
    return False


def _scan_text_for_conflict_keywords(text: str) -> tuple[bool, str]:
    """
    Scan text for conflict keywords.

    Returns:
        (is_conflict, reason)
    """
    text_lower = text.lower()

    # Check strong keywords first — single match is enough
    for keyword in STRONG_CONFLICT_KEYWORDS:
        if keyword in text_lower:
            return True, f"Strong conflict keyword found: '{keyword}'"

    # Check generic keywords — need 2+ matches
    matches = []
    for keyword in GENERIC_CONFLICT_KEYWORDS:
        if keyword in text_lower:
            matches.append(keyword)

    if len(matches) >= 2:
        return True, f"Multiple conflict keywords found: {matches}"

    return False, ""


def detect_conflicting_frameworks(
    plugins: list[PluginInfo],
    skills: list[SkillInfo],
) -> list[ConflictingFramework]:
    """
    Detect conflicting task management frameworks by scanning 4 sources:
      1. Installed plugins (name + install path for description files)
      2. User skills (name + SKILL.md content)
      3. Slash commands (~/.claude/commands/)
      4. Framework directories (~/.claude/get-shit-done/, etc.)

    Returns:
        List of detected ConflictingFramework entries
    """
    conflicts: list[ConflictingFramework] = []
    seen_names: set[str] = set()

    # --- Source 1: Installed plugins ---
    for plugin in plugins:
        if _check_safe_name(plugin.name):
            continue

        if _check_name_conflict(plugin.name):
            conflict_name = plugin.name
            if conflict_name not in seen_names:
                seen_names.add(conflict_name)

                # Build disallowed tools based on the plugin name
                disallowed = _build_disallowed_tools(conflict_name)

                conflicts.append(ConflictingFramework(
                    name=conflict_name,
                    source="plugin",
                    reason=f"Plugin '{plugin.name}' matches known conflicting framework",
                    disallowed_tools=disallowed,
                ))
                continue

        # Scan plugin description files for keywords
        if plugin.install_path:
            plugin_path = Path(plugin.install_path)
            for desc_file in ["PLUGIN.md", "README.md", "SKILL.md", "plugin.json"]:
                desc_path = plugin_path / desc_file
                if desc_path.is_file():
                    try:
                        content = desc_path.read_text(errors="replace")
                        is_conflict, reason = _scan_text_for_conflict_keywords(content)
                        if is_conflict and plugin.name not in seen_names:
                            seen_names.add(plugin.name)
                            conflicts.append(ConflictingFramework(
                                name=plugin.name,
                                source="plugin",
                                reason=f"Plugin '{plugin.name}': {reason}",
                                disallowed_tools=_build_disallowed_tools(plugin.name),
                            ))
                    except (IOError, PermissionError):
                        pass

    # --- Source 2: User skills ---
    for skill in skills:
        if _check_safe_name(skill.name):
            continue

        if _check_name_conflict(skill.name):
            if skill.name not in seen_names:
                seen_names.add(skill.name)
                conflicts.append(ConflictingFramework(
                    name=skill.name,
                    source="skill",
                    reason=f"Skill '{skill.name}' matches known conflicting framework",
                    disallowed_tools=_build_disallowed_tools(skill.name),
                ))
                continue

        # Read SKILL.md for keyword scanning
        skill_md = Path(skill.directory) / "SKILL.md"
        if skill_md.is_file():
            try:
                content = skill_md.read_text(errors="replace")
                is_conflict, reason = _scan_text_for_conflict_keywords(content)
                if is_conflict and skill.name not in seen_names:
                    seen_names.add(skill.name)
                    conflicts.append(ConflictingFramework(
                        name=skill.name,
                        source="skill",
                        reason=f"Skill '{skill.name}': {reason}",
                        disallowed_tools=_build_disallowed_tools(skill.name),
                    ))
            except (IOError, PermissionError):
                pass

    # --- Source 3: Slash commands ---
    commands_dir = CLAUDE_HOME / "commands"
    if commands_dir.is_dir():
        for entry in commands_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                cmd_name = entry.name
                if _check_safe_name(cmd_name):
                    continue
                if _check_name_conflict(cmd_name) and cmd_name not in seen_names:
                    seen_names.add(cmd_name)
                    conflicts.append(ConflictingFramework(
                        name=cmd_name,
                        source="command",
                        reason=f"Command group '{cmd_name}' matches known conflicting framework",
                        disallowed_tools=_build_disallowed_tools(cmd_name),
                    ))

    # --- Source 4: Framework directories ---
    framework_dirs = [
        "get-shit-done", "get_shit_done", "gsd",
        "ralph-wiggum", "ralph_wiggum",
    ]
    for dir_name in framework_dirs:
        framework_path = CLAUDE_HOME / dir_name
        if framework_path.is_dir() and dir_name not in seen_names:
            seen_names.add(dir_name)
            conflicts.append(ConflictingFramework(
                name=dir_name,
                source="directory",
                reason=f"Framework directory '{dir_name}' found in ~/.claude/",
                disallowed_tools=_build_disallowed_tools(dir_name),
            ))

    return conflicts


def _build_disallowed_tools(framework_name: str) -> list[str]:
    """
    Build a list of tools to disallow for a given conflicting framework.

    Maps framework names to the Skill() patterns and command groups they own.
    """
    normalised = framework_name.lower().replace("_", "-").replace(" ", "-")

    # GSD / get-shit-done
    if "gsd" in normalised or "get-shit-done" in normalised:
        # List all known GSD skill commands
        gsd_commands = [
            "gsd:health", "gsd:quick", "gsd:cleanup", "gsd:discuss-phase",
            "gsd:reapply-patches", "gsd:verify-work", "gsd:update",
            "gsd:execute-phase", "gsd:new-project", "gsd:new-milestone",
            "gsd:insert-phase", "gsd:map-codebase", "gsd:join-discord",
            "gsd:add-phase", "gsd:help", "gsd:audit-milestone",
            "gsd:progress", "gsd:resume-work", "gsd:plan-milestone-gaps",
            "gsd:add-todo", "gsd:pause-work", "gsd:check-todos",
            "gsd:plan-phase", "gsd:research-phase", "gsd:complete-milestone",
            "gsd:remove-phase", "gsd:settings", "gsd:set-profile",
            "gsd:debug", "gsd:list-phase-assumptions",
        ]
        return [f"Skill({cmd})" for cmd in gsd_commands]

    # claude-session-driver
    if "session-driver" in normalised or "claude-session-driver" in normalised:
        return [f"Skill({normalised}:*)"]

    # ralph-wiggum
    if "ralph" in normalised:
        return [f"Skill({normalised}:*)"]

    # Generic fallback — block the whole namespace
    return [f"Skill({normalised}:*)"]


def load_user_allowed_commands() -> tuple[list[BashCommandEntry], set[str]]:
    """
    Extract bash commands from the user's settings.local.json permissions.

    Parses patterns like:
      - "Bash(npm install:*)" -> "npm"
      - "Bash(git commit:*)" -> "git"
      - "Bash(python3:*)" -> "python3"

    Returns:
        (user_entries, merged_set) where merged_set includes defaults
    """
    user_entries: list[BashCommandEntry] = []
    user_commands: set[str] = set()

    settings_path = CLAUDE_HOME / "settings.local.json"
    data = _read_json_safe(settings_path)

    if data is not None:
        permissions = data.get("permissions", {})
        allow_list = permissions.get("allow", [])

        # Regex to extract command name from Bash(...) patterns
        bash_pattern = re.compile(r"^Bash\(([a-zA-Z0-9_./-]+)")

        for entry in allow_list:
            if not isinstance(entry, str) or not entry.startswith("Bash("):
                continue

            match = bash_pattern.match(entry)
            if match:
                cmd = match.group(1)
                # Extract just the base command (first word before spaces/special chars)
                base_cmd = cmd.split()[0] if " " in cmd else cmd
                # Remove any path prefix
                base_cmd = os.path.basename(base_cmd)

                if base_cmd and base_cmd not in user_commands:
                    user_commands.add(base_cmd)
                    user_entries.append(BashCommandEntry(
                        command=base_cmd,
                        source="user_settings",
                    ))

    # Merge with defaults
    merged = DEFAULT_ALLOWED_COMMANDS | user_commands

    return user_entries, merged


def _merge_mcp_servers(
    global_servers: list[McpServerEntry],
    project_servers: list[McpServerEntry],
    harness_servers: list[McpServerEntry],
    warnings: list[str],
) -> dict[str, Any]:
    """
    Merge MCP servers from all sources.

    Priority: harness > project > global
    (harness-required servers like Linear always win)
    """
    merged: dict[str, Any] = {}

    # Add global servers first (lowest priority)
    for server in global_servers:
        merged[server.name] = server.config

    # Override with project-specific (medium priority)
    for server in project_servers:
        if server.name in merged:
            warnings.append(
                f"Project MCP '{server.name}' overrides global config"
            )
        merged[server.name] = server.config

    # Override with harness-required (highest priority)
    for server in harness_servers:
        if server.name in merged:
            warnings.append(
                f"Harness MCP '{server.name}' overrides user config "
                f"(required for harness functionality)"
            )
        merged[server.name] = server.config

    return merged


def _filter_mcps_by_session(
    merged: dict[str, Any],
    session_type: str | None,
) -> dict[str, Any]:
    """
    Filter merged MCP servers based on session type scope.

    If session_type is None, unknown, or maps to None in SESSION_MCP_SCOPES,
    returns the full dict unchanged (V1 behaviour).
    """
    if session_type is None:
        return merged

    scope = SESSION_MCP_SCOPES.get(session_type)
    if scope is None:
        return merged

    total = len(merged)
    filtered: dict[str, Any] = {}
    matched_scopes: list[str] = []

    for name, config in merged.items():
        name_lower = name.lower()
        for s in scope:
            if s.lower() in name_lower:
                filtered[name] = config
                if s.lower() not in matched_scopes:
                    matched_scopes.append(s.lower())
                break

    logger.info(
        "[Discovery] Session type: %s — loading %d of %d configured MCPs (%s)",
        session_type,
        len(filtered),
        total,
        ", ".join(matched_scopes) if matched_scopes else "none",
    )

    return filtered


def discover_user_ecosystem(
    project_dir: Path | None = None,
    linear_api_key: str | None = None,
    session_type: str | None = None,
) -> EcosystemInfo:
    """
    Orchestrator — discovers the complete user ecosystem at runtime.

    Args:
        project_dir: The project directory (for project-specific MCPs)
        linear_api_key: Linear API key (for harness-required MCP)
        session_type: Optional session type for MCP scoping (e.g. "epic_initializer", "coding").
                      When provided, filters merged MCPs to only those needed for the session type.

    Returns:
        Complete EcosystemInfo with all discovery results
    """
    warnings: list[str] = []

    # 1. Load MCP servers
    global_servers, project_servers, found, missing = load_user_mcp_servers(project_dir)

    # Build harness-required servers
    harness_servers: list[McpServerEntry] = [
        McpServerEntry(
            name="puppeteer",
            config={"command": "npx", "args": ["puppeteer-mcp-server"]},
            source="harness",
        ),
    ]

    if linear_api_key:
        harness_servers.append(McpServerEntry(
            name="linear",
            config={
                "type": "http",
                "url": "https://mcp.linear.app/mcp",
                "headers": {"Authorization": f"Bearer {linear_api_key}"},
            },
            source="harness",
        ))

    # Merge all MCP servers
    merged_mcps = _merge_mcp_servers(
        global_servers, project_servers, harness_servers, warnings
    )

    # Apply session-scoped MCP filtering
    merged_mcps = _filter_mcps_by_session(merged_mcps, session_type)

    # 2. Load plugins and skills
    plugins = load_installed_plugins()
    skills = load_user_skills()

    # 3. Detect conflicts
    conflicts = detect_conflicting_frameworks(plugins, skills)

    # 4. Load bash commands
    user_bash_entries, merged_commands = load_user_allowed_commands()

    # 5. Build and return ecosystem info
    ecosystem = EcosystemInfo(
        global_mcp_servers=global_servers,
        project_mcp_servers=project_servers,
        harness_mcp_servers=harness_servers,
        merged_mcp_servers=merged_mcps,
        plugins=plugins,
        skills=skills,
        conflicting_frameworks=conflicts,
        user_approved_commands=user_bash_entries,
        merged_allowed_commands=merged_commands,
        config_files_found=found,
        config_files_missing=missing,
        warnings=warnings,
    )

    return ecosystem


def build_dynamic_system_prompt(ecosystem: EcosystemInfo, mode: str = "greenfield") -> str:
    """
    Generate a context-aware system prompt based on the discovered ecosystem.

    Args:
        ecosystem: The discovered ecosystem info
        mode: "greenfield" or "brownfield"

    Returns:
        System prompt string
    """
    sections: list[str] = []

    sections.append(
        "You are an expert full-stack developer building a production-quality "
        "web application. You use Linear for project management and tracking "
        "all your work."
    )

    # Mode-specific context
    if mode == "brownfield":
        sections.append(
            "\n## Working Mode: Brownfield Development\n"
            "You are working on an EXISTING codebase. Before making changes:\n"
            "- Read CLAUDE.md, README, and any project documentation first\n"
            "- Match existing code patterns, naming conventions, and file structure\n"
            "- Don't introduce new libraries when existing alternatives are in use\n"
            "- Follow the existing test framework and patterns\n"
            "- Respect the existing git history and commit conventions"
        )

    # Available MCP servers
    if ecosystem.merged_mcp_servers:
        mcp_lines = ["\n## Available MCP Servers"]

        harness_names = {s.name for s in ecosystem.harness_mcp_servers}
        user_names = {
            s.name for s in ecosystem.global_mcp_servers + ecosystem.project_mcp_servers
        }

        for name in sorted(ecosystem.merged_mcp_servers.keys()):
            if name in harness_names:
                mcp_lines.append(f"- **{name}** (harness-required)")
            elif name in user_names:
                mcp_lines.append(f"- **{name}** (user-configured)")

        sections.append("\n".join(mcp_lines))

    # Excluded frameworks
    if ecosystem.conflicting_frameworks:
        conflict_lines = ["\n## Excluded Frameworks"]
        conflict_lines.append(
            "The following frameworks conflict with this harness's task "
            "management system (Linear) and have been excluded:"
        )
        for conflict in ecosystem.conflicting_frameworks:
            conflict_lines.append(
                f"- **{conflict.name}** ({conflict.source}): {conflict.reason}"
            )
        conflict_lines.append(
            "\nDo NOT use any tools or commands from these frameworks."
        )
        sections.append("\n".join(conflict_lines))

    # Warnings
    if ecosystem.warnings:
        warn_lines = ["\n## Configuration Notes"]
        for warning in ecosystem.warnings:
            warn_lines.append(f"- {warning}")
        sections.append("\n".join(warn_lines))

    return "\n".join(sections)


def print_discovery_summary(ecosystem: EcosystemInfo) -> None:
    """Print a human-readable summary of the discovery results."""
    print("\n" + "=" * 70)
    print("  ECOSYSTEM DISCOVERY")
    print("=" * 70)

    # MCP servers
    print(f"\n  MCP Servers ({len(ecosystem.merged_mcp_servers)} total):")
    for name in sorted(ecosystem.merged_mcp_servers.keys()):
        source = "harness"
        for s in ecosystem.harness_mcp_servers:
            if s.name == name:
                source = "harness (required)"
                break
        else:
            for s in ecosystem.project_mcp_servers:
                if s.name == name:
                    source = "project"
                    break
            else:
                for s in ecosystem.global_mcp_servers:
                    if s.name == name:
                        source = "global"
                        break
        print(f"    - {name} [{source}]")

    # Plugins
    if ecosystem.plugins:
        print(f"\n  Plugins ({len(ecosystem.plugins)}):")
        for plugin in ecosystem.plugins:
            status = "enabled" if plugin.is_enabled else "disabled"
            print(f"    - {plugin.name} ({plugin.marketplace}) [{status}]")

    # Skills
    if ecosystem.skills:
        print(f"\n  Skills ({len(ecosystem.skills)}):")
        for skill in ecosystem.skills:
            print(f"    - {skill.name}")

    # Conflicts
    if ecosystem.conflicting_frameworks:
        print(f"\n  Conflicting Frameworks ({len(ecosystem.conflicting_frameworks)}):")
        for conflict in ecosystem.conflicting_frameworks:
            print(f"    - {conflict.name} ({conflict.source}): {conflict.reason}")
            print(f"      Excluded {len(conflict.disallowed_tools)} tool(s)")
    else:
        print("\n  Conflicting Frameworks: None detected")

    # Bash commands
    extra = ecosystem.merged_allowed_commands - DEFAULT_ALLOWED_COMMANDS
    if extra:
        print(f"\n  Additional Bash Commands (from user settings): {len(extra)}")
        for cmd in sorted(extra):
            print(f"    - {cmd}")
    else:
        print(f"\n  Bash Commands: {len(ecosystem.merged_allowed_commands)} (defaults only)")

    # Warnings
    if ecosystem.warnings:
        print(f"\n  Warnings ({len(ecosystem.warnings)}):")
        for warning in ecosystem.warnings:
            print(f"    - {warning}")

    # Config files
    if ecosystem.config_files_found:
        print(f"\n  Config Files Found: {', '.join(ecosystem.config_files_found)}")
    if ecosystem.config_files_missing:
        print(f"  Config Files Missing: {', '.join(ecosystem.config_files_missing)}")

    print("\n" + "=" * 70 + "\n")


# Alias for backward compatibility and verification scripts
discover_mcps = discover_user_ecosystem
