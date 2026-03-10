"""
Prompt Loading Utilities
========================

Functions for loading prompt templates from the prompts directory.
Includes programmatic context injection for epic mode — Python reads files
and fetches issue data, then injects everything as pre-populated context
blocks in the prompt so the agent never needs to discover state itself.
"""

import json
import logging
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import httpx


logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

REF_API_URL = "https://api.ref.tools/v1/search"

# Common library/framework names to detect in spec text
_KNOWN_LIBRARIES = [
    "Next.js", "React", "Supabase", "Clerk", "Stripe", "Tailwind",
    "shadcn", "FastAPI", "Pydantic", "Prisma", "Drizzle", "tRPC",
    "Zustand", "Zod", "Playwright", "Vitest", "GSAP", "Remotion",
    "Convex", "LangChain", "CopilotKit", "Vercel", "Render",
    "PostgreSQL", "Redis", "Resend", "Inngest", "Upstash",
    "NextAuth", "Auth.js", "Lucia", "Expo", "React Native",
    "MagicUI", "Framer Motion", "Radix", "Headless UI",
]

# Patterns that indicate a tech stack / dependency section
_TECH_SECTION_PATTERNS = re.compile(
    r"(?:tech\s*stack|libraries|frameworks|dependencies|uses|built\s*with|external\s*integrations)",
    re.IGNORECASE,
)


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
# Pre-fetch Ref documentation
# ---------------------------------------------------------------------------

def _extract_library_names(spec_text: str) -> list[str]:
    """Extract library/framework names from spec text."""
    found: list[str] = []
    spec_lower = spec_text.lower()

    for lib in _KNOWN_LIBRARIES:
        if lib.lower() in spec_lower and lib not in found:
            found.append(lib)

    # Cap at 8 queries
    return found[:8]


def _fetch_ref_doc(query: str, api_key: str) -> tuple[str, str | None]:
    """Fetch a single documentation result from Ref. Returns (query, content or None)."""
    try:
        response = httpx.get(
            REF_API_URL,
            headers={"x-ref-api-key": api_key},
            params={"q": query, "limit": 1},
            timeout=10,
        )
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                return query, results[0].get("content", "")
    except Exception:
        pass
    return query, None


def _get_ref_cache_path(project_dir: Path | None = None) -> Path | None:
    """Get the path to the Ref documentation cache file."""
    if project_dir is None:
        return None
    return project_dir / ".ref_cache.json"


def _load_ref_cache(cache_path: Path | None) -> dict[str, dict]:
    """Load cached Ref documentation results. Returns {library: {content, timestamp}}."""
    if cache_path is None or not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _save_ref_cache(cache_path: Path | None, cache: dict[str, dict]) -> None:
    """Save Ref documentation cache to disk."""
    if cache_path is None:
        return
    try:
        cache_path.write_text(json.dumps(cache, indent=2))
    except IOError as e:
        logger.warning("[Ref Cache] Could not write cache: %s", e)


REF_CACHE_TTL_SECONDS = 86400  # 24 hours


def prefetch_ref_docs(
    spec_text: str,
    ref_api_key: str | None = None,
    project_dir: Path | None = None,
) -> str:
    """
    Parse spec_text for library/framework names and fetch relevant documentation
    from the Ref API before the agent session starts.

    Uses a file-based cache at {project_dir}/.ref_cache.json with 24h TTL to avoid
    redundant fetches across sessions.

    Returns a formatted context block to inject into the agent prompt.
    If REF_API_KEY is not set or fetch fails, returns empty string (graceful degradation).
    """
    api_key = ref_api_key or os.environ.get("REF_API_KEY")
    if not api_key:
        logger.info("[Ref Prefetch] REF_API_KEY not set — skipping documentation pre-fetch")
        return ""

    libraries = _extract_library_names(spec_text)
    if not libraries:
        return ""

    logger.info("[Ref Prefetch] Fetching docs for: %s", ", ".join(libraries))

    # Load cache
    cache_path = _get_ref_cache_path(project_dir)
    cache = _load_ref_cache(cache_path)
    now = time.time()

    sections: list[str] = []
    libs_to_fetch: list[str] = []

    # Check cache first
    for lib in libraries:
        cached = cache.get(lib)
        if cached and (now - cached.get("timestamp", 0)) < REF_CACHE_TTL_SECONDS:
            content = cached.get("content")
            if content:
                sections.append(f"### {lib}\n{content}")
                logger.info("[Ref Prefetch] Cache hit: %s", lib)
        else:
            libs_to_fetch.append(lib)

    # Fetch uncached libraries
    if libs_to_fetch:
        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {
                    executor.submit(_fetch_ref_doc, lib, api_key): lib
                    for lib in libs_to_fetch
                }

                for future in as_completed(futures, timeout=15):
                    try:
                        query, content = future.result(timeout=5)
                        if content:
                            sections.append(f"### {query}\n{content}")
                            cache[query] = {"content": content, "timestamp": now}
                        else:
                            # Cache the miss too to avoid re-fetching
                            cache[query] = {"content": None, "timestamp": now}
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("[Ref Prefetch] Error during documentation fetch: %s", e)

    # Save updated cache
    _save_ref_cache(cache_path, cache)

    if not sections:
        return ""

    header = (
        "## Pre-fetched Documentation\n\n"
        "The following documentation was retrieved before this session. Use it as your "
        "primary reference before making any ref_search_documentation calls — only call "
        "Ref if you need information not covered here.\n\n"
    )

    return header + "\n\n".join(sections)


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


def _validate_spec_file_path(spec_file: str, project_dir: Path) -> Path:
    """Validate spec_file path is within project directory."""
    resolved = (project_dir / spec_file).resolve()
    try:
        resolved.relative_to(project_dir.resolve())
    except ValueError:
        raise ValueError(
            f"spec_file path '{spec_file}' resolves outside project directory. "
            "This may indicate a tampered spec_index.json."
        )
    return resolved


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
    spec_file = _validate_spec_file_path(epic["spec_file"], project_dir)
    if not spec_file.exists():
        # Fallback: glob for the spec file by epic number
        import glob

        pattern = str(project_dir / "epics" / f"epic-{epic_number:02d}-*.md")
        matches = sorted(glob.glob(pattern))
        if matches:
            spec_file = Path(matches[0])
        else:
            raise FileNotFoundError(
                f"Epic spec not found at {spec_file} or by glob pattern {pattern}"
            )
    epic_spec = _read_file_or_note(spec_file, required=True)
    sections.append(_wrap_context(epic["spec_file"], epic_spec))

    # 5. Pre-fetched Ref documentation
    ref_docs = prefetch_ref_docs(epic_spec, project_dir=project_dir)
    if ref_docs:
        sections.append(ref_docs)

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
    shared_text = shared_path.read_text() if shared_path.exists() else ""
    if shared_text:
        sections.append(_wrap_context("shared_context.md", shared_text))

    # Build deviations
    deviations_path = project_dir / "build_deviations.md"
    if deviations_path.exists():
        sections.append(_wrap_context("build_deviations.md", deviations_path.read_text()))

    # Pre-fetched Ref documentation
    issue_desc = current_issue.get("description", "") if current_issue else ""
    ref_docs = prefetch_ref_docs(issue_desc + " " + shared_text, project_dir=project_dir)
    if ref_docs:
        sections.append(ref_docs)

    # Current issue
    if current_issue is not None:
        issue_block = (
            "## CURRENT ISSUE (work on this and only this)\n\n"
            f"ID: {current_issue['id']}\n"
            f"Title: {current_issue['title']}\n"
            f"Description: {current_issue.get('description', 'No description')}\n"
            f"Priority: {current_issue.get('priority', 'unset')}\n\n"
            "Complete this issue, commit, mark it Done in Linear using the ID above, then stop.\n"
            "Do not pick up additional issues in this session."
        )
        sections.append(issue_block)
    else:
        sections.append(
            "## STATUS: All issues complete. Run the snapshot if not done, then stop."
        )

    return "\n\n---\n\n".join(sections)
