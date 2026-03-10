# Phase 2B: Per-Library Knowledge Skills — Implementation Plan

## Goal

For every library/framework detected in the tech stack, fetch real documentation from Ref API and code examples from Exa API, then generate a dedicated Claude Code skill package. This gives the coding agent accurate, up-to-date reference material per dependency — not generic checklists, but actual docs and patterns.

A Next.js + Clerk + Supabase + FastAPI + Stripe project would produce ~5 library skills (one per technology) **in addition to** the 5 existing workflow skills (test-runner, code-review, project-reference, deployment-check, linear-workflow).

---

## What Already Exists

### Ref API Integration (`prompts.py`)

The harness already calls the Ref API directly from Python. The proven pattern:

```python
# prompts.py — existing pattern to follow
REF_API_URL = "https://api.ref.tools/v1/search"

def _fetch_ref_doc(query: str, api_key: str) -> tuple[str, str | None]:
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
    return query, None
```

Key details:

- Auth: `x-ref-api-key` header
- Env var: `REF_API_KEY`
- Parallel fetching via `ThreadPoolExecutor(max_workers=8)`
- File-based cache at `{project_dir}/.ref_cache.json` with 24h TTL
- Graceful degradation: no API key = skip silently

### Exa API (new integration)

REST API at `https://api.exa.ai/search`:

```python
# Exa API — new integration
EXA_API_URL = "https://api.exa.ai/search"

def _fetch_exa_code(query: str, api_key: str) -> tuple[str, str | None]:
    response = httpx.post(
        EXA_API_URL,
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "type": "auto",
            "numResults": 3,
            "contents": {
                "text": True,
                "highlights": {"maxCharacters": 4000},
            },
        },
        timeout=15,
    )
    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            # Combine highlights from top results
            snippets = []
            for r in results:
                title = r.get("title", "")
                url = r.get("url", "")
                highlights = r.get("highlights", [])
                text = "\n".join(highlights) if highlights else r.get("text", "")[:2000]
                snippets.append(f"### {title}\nSource: {url}\n\n{text}")
            return query, "\n\n".join(snippets)
    return query, None
```

Key details:

- Auth: `x-api-key` header
- Env var: `EXA_API_KEY`
- POST request (not GET like Ref)
- `highlights` mode extracts the most relevant snippets (LLM-identified)
- Cap at 3 results per library to keep skills concise
- Same parallel + cache pattern as Ref

### Tech Stack Detection (`skills.py`)

Already complete. `detect_tech_stack()` returns a `TechStack` dataclass with `all_libraries: list[str]` — the superset of every detected library. This is the input list for generating per-library skills.

### Existing Skill Generation (`skills.py`)

Already complete. 5 workflow skills generated via `_SKILL_BUILDERS` registry, written to `<project>/.claude/skills/<name>/SKILL.md` with `<!-- generated-by: harness -->` marker for idempotency.

---

## Architecture

### New Function: `generate_library_skills()`

Added to `skills.py` alongside the existing `generate_project_skills()`. Called immediately after it in both lifecycle hooks.

```
detect_tech_stack()
    → stack.all_libraries = ["Next.js", "Clerk", "Supabase", "FastAPI", "Stripe", ...]
    → for each library:
        → parallel fetch: Ref docs + Exa code examples
        → assemble into <lib-slug>/SKILL.md
    → write all skills to <project>/.claude/skills/
```

### Skill Naming

Library names need to be slugified for skill directory names:

```python
_LIBRARY_SKILL_SLUGS = {
    "Next.js": "nextjs-docs",
    "React": "react-docs",
    "FastAPI": "fastapi-docs",
    "Clerk": "clerk-docs",
    "Supabase": "supabase-docs",
    "Stripe": "stripe-docs",
    "Tailwind": "tailwind-docs",
    "shadcn": "shadcn-docs",
    "Prisma": "prisma-docs",
    "Drizzle": "drizzle-docs",
    "LangChain": "langchain-docs",
    "CopilotKit": "copilotkit-docs",
    "Zustand": "zustand-docs",
    "Zod": "zod-docs",
    "Playwright": "playwright-docs",
    "Vitest": "vitest-docs",
    "GSAP": "gsap-docs",
    "Remotion": "remotion-docs",
    # ... etc — fallback: lib.lower().replace(" ", "-").replace(".", "") + "-docs"
}
```

The `-docs` suffix distinguishes these from the workflow skills (e.g. `clerk-docs` vs a hypothetical `clerk-auth` workflow skill).

### Search Query Strategy

Each library gets tailored search queries to fetch the most useful content:

```python
_LIBRARY_SEARCH_QUERIES = {
    "Next.js": {
        "ref": "Next.js 15 App Router API reference",
        "exa": "Next.js 15 App Router best practices examples server components",
    },
    "Clerk": {
        "ref": "Clerk Next.js authentication setup middleware",
        "exa": "Clerk Next.js authentication implementation examples 2024",
    },
    "Supabase": {
        "ref": "Supabase JavaScript client API reference",
        "exa": "Supabase Row Level Security policies Next.js examples",
    },
    "FastAPI": {
        "ref": "FastAPI Python async endpoints Pydantic V2",
        "exa": "FastAPI Pydantic V2 async endpoint examples best practices",
    },
    "Stripe": {
        "ref": "Stripe API checkout subscriptions webhooks",
        "exa": "Stripe Next.js integration checkout webhook examples",
    },
    "Tailwind": {
        "ref": "Tailwind CSS utility classes responsive design",
        "exa": "Tailwind CSS component patterns responsive design examples",
    },
    # ... etc
}
```

For libraries not in the map, fall back to:

- Ref: `"{library_name} API reference documentation"`
- Exa: `"{library_name} best practices examples {current_year}"`

### Generated SKILL.md Structure

Each per-library skill follows this template:

```markdown
---
name: clerk-docs
description: Clerk authentication documentation and patterns. Reference for middleware setup, user management, webhook integration, and auth hooks. Use when implementing or modifying authentication.
---

<!-- generated-by: harness -->

# Clerk — Documentation Reference

## Official Documentation

{ref_content}

## Code Examples & Patterns

{exa_content}

## Quick Reference

- Docs: https://clerk.com/docs
- Package: @clerk/nextjs
```

The Quick Reference section has a static fallback URL and package name per library, defined in a `_LIBRARY_METADATA` dict.

### Caching

Extend the existing `.ref_cache.json` pattern:

```python
# Cache structure: {project_dir}/.skill_docs_cache.json
{
    "Clerk": {
        "ref_content": "...",
        "exa_content": "...",
        "timestamp": 1710000000
    },
    "FastAPI": { ... }
}
```

- Separate cache file from the prompt prefetch cache (different concern)
- Same 24h TTL as the existing Ref cache
- Cache is per-project (different projects may need different queries)

### Content Size Management

Each skill must stay under 500 lines. Content from APIs can be verbose, so:

1. Ref content: take first result only, truncate to 8000 chars
2. Exa content: take top 3 results, use `highlights` mode (pre-summarised by Exa), truncate each to 2000 chars
3. If combined content exceeds 400 lines, truncate Exa section first (docs > examples)
4. Add a `## Further Reading` section pointing to official docs URL as fallback

---

## Implementation Steps

### Step 1: Add API Fetch Functions

**File:** `skills.py`

Add two new fetch functions following the `prompts.py` pattern:

1. `_fetch_ref_for_skill(library: str, api_key: str) -> str | None` — fetches Ref docs for a specific library using the query from `_LIBRARY_SEARCH_QUERIES`
2. `_fetch_exa_for_skill(library: str, api_key: str) -> str | None` — fetches Exa code examples using POST to `https://api.exa.ai/search`
3. `_fetch_all_library_docs(libraries: list[str], ref_key: str | None, exa_key: str | None, cache_path: Path | None) -> dict[str, dict]` — parallel fetcher for all libraries with caching

Key implementation details:

- Use `ThreadPoolExecutor(max_workers=8)` for parallel fetching (same as existing Ref pattern)
- Cache results in `{project_dir}/.skill_docs_cache.json`
- Both APIs optional — graceful degradation if either key missing
- Timeout: 10s for Ref, 15s for Exa
- Cap total libraries at 15 (avoid excessive API calls)

**Environment variables to document:**

- `REF_API_KEY` — already exists, reuse
- `EXA_API_KEY` — new, optional

### Step 2: Add Library Metadata & Query Maps

**File:** `skills.py`

Add three dicts:

1. `_LIBRARY_SKILL_SLUGS: dict[str, str]` — maps library name to skill directory slug
2. `_LIBRARY_SEARCH_QUERIES: dict[str, dict[str, str]]` — maps library name to `{"ref": "...", "exa": "..."}` queries
3. `_LIBRARY_METADATA: dict[str, dict]` — maps library name to `{"url": "...", "package": "...", "category": "..."}` for the Quick Reference section

Include entries for all libraries in `_KNOWN_LIBRARIES` (from `prompts.py`). Use a sensible fallback for any library not in the map.

### Step 3: Build Library Skill Assembler

**File:** `skills.py`

Add `_build_library_skill(library: str, ref_content: str | None, exa_content: str | None) -> str`:

1. Generate frontmatter with library-specific name and description
2. Add `## Official Documentation` section with Ref content (or "No documentation pre-fetched" note)
3. Add `## Code Examples & Patterns` section with Exa content (or skip if empty)
4. Add `## Quick Reference` section with static metadata (docs URL, package name)
5. Add `<!-- generated-by: harness -->` marker
6. Enforce 500-line limit by truncating content sections

### Step 4: Add `generate_library_skills()` Function

**File:** `skills.py`

```python
def generate_library_skills(
    project_dir: Path,
    stack: TechStack,
    ref_api_key: str | None = None,
    exa_api_key: str | None = None,
) -> list[str]:
    """
    Generate per-library documentation skills from Ref + Exa APIs.

    For each library in stack.all_libraries, fetches documentation and
    code examples, then writes a skill to <project>/.claude/skills/<slug>/SKILL.md.

    Returns list of generated skill names.
    """
```

Key logic:

1. Read API keys from env vars if not passed (same pattern as `prefetch_ref_docs`)
2. Skip if no API keys at all (graceful degradation)
3. Cap at 15 libraries
4. Call `_fetch_all_library_docs()` for parallel fetching
5. For each library with content, call `_build_library_skill()` and write to disk
6. Respect the existing harness marker / user-skill preservation logic
7. Return list of generated skill names

### Step 5: Integrate into Lifecycle

**File:** `epic_orchestrator.py` (after existing `generate_project_skills()` call, ~line 248)

```python
from skills import generate_library_skills

lib_generated = generate_library_skills(project_dir, stack)
if lib_generated:
    print(f"  Generated {len(lib_generated)} library documentation skill(s): {', '.join(lib_generated)}")
```

**File:** `agent.py` (after existing `generate_project_skills()` call, ~line 315)

Same pattern. Only on `is_first_run`.

**Note:** `generate_library_skills()` needs the `TechStack` object. Currently `generate_project_skills()` calls `detect_tech_stack()` internally. Refactor so `generate_project_skills()` returns the stack, or extract detection to the caller:

```python
# In both epic_orchestrator.py and agent.py:
from skills import detect_tech_stack, generate_project_skills, generate_library_skills

stack = detect_tech_stack(_spec_text, project_dir, mode="greenfield")
workflow_generated = generate_project_skills(project_dir, spec_text=_spec_text, mode="greenfield", is_epic=True, stack=stack)
library_generated = generate_library_skills(project_dir, stack)
```

This means `generate_project_skills()` should accept an optional `stack` parameter to avoid double-detection.

### Step 6: Update Configuration

**File:** `README.md` — add `EXA_API_KEY` to the environment variables table

| Variable      | Required | Description                                                                                                                |
| ------------- | -------- | -------------------------------------------------------------------------------------------------------------------------- |
| `EXA_API_KEY` | No       | [Exa](https://exa.ai) API key for fetching code examples into library skills. Without it, library skills use Ref docs only |

### Step 7: Tests

**File:** `test_skills.py` — add new test class

```python
class TestGenerateLibrarySkills:
    """Tests for per-library documentation skill generation."""

    def test_generates_skills_for_detected_libraries(self, tmp_project):
        """With mocked API responses, generates one skill per library."""

    def test_graceful_degradation_no_api_keys(self, tmp_project):
        """Returns empty list when no API keys are set."""

    def test_respects_harness_marker(self, tmp_project):
        """Overwrites harness-generated, preserves user-created."""

    def test_skill_under_500_lines(self, tmp_project):
        """Generated library skills stay under 500 lines."""

    def test_caching_prevents_refetch(self, tmp_project):
        """Second call uses cache instead of hitting APIs."""

    def test_library_cap_at_15(self, tmp_project):
        """No more than 15 library skills generated."""

    def test_fallback_queries_for_unknown_libraries(self, tmp_project):
        """Libraries not in _LIBRARY_SEARCH_QUERIES get sensible defaults."""
```

Mock both Ref and Exa HTTP calls using `pytest-mock` or `respx` — never hit real APIs in tests.

### Step 8: Update README

Add a section about library skills to the Skills key concept, and add `EXA_API_KEY` to the config table.

---

## File-by-File Change Summary

| File                   | Change   | Description                                                                                                                                                                                                                               |
| ---------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `skills.py`            | MODIFIED | Add `_fetch_ref_for_skill()`, `_fetch_exa_for_skill()`, `_fetch_all_library_docs()`, `_build_library_skill()`, `generate_library_skills()`, library metadata dicts. Refactor `generate_project_skills()` to accept optional `stack` param |
| `epic_orchestrator.py` | MODIFIED | Call `generate_library_skills()` after `generate_project_skills()`, pass `stack` object                                                                                                                                                   |
| `agent.py`             | MODIFIED | Same integration as epic_orchestrator                                                                                                                                                                                                     |
| `test_skills.py`       | MODIFIED | Add `TestGenerateLibrarySkills` test class with mocked HTTP calls                                                                                                                                                                         |
| `README.md`            | MODIFIED | Add `EXA_API_KEY` to config table, update Skills section                                                                                                                                                                                  |

---

## Key Reference Files

When implementing, read these files for patterns and context:

| File                                 | Why                                                                                                                                                                             |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `skills.py` (full file)              | Contains all existing skill generation code — `TechStack`, `detect_tech_stack()`, `_SKILL_BUILDERS`, `generate_project_skills()`, `_is_harness_generated()`, `GENERATED_MARKER` |
| `prompts.py` lines 83-232            | Contains the Ref API fetch pattern to follow — `_fetch_ref_doc()`, `ThreadPoolExecutor`, cache load/save, `REF_API_URL`, `REF_CACHE_TTL_SECONDS`                                |
| `prompts.py` lines 31-39             | `_KNOWN_LIBRARIES` list — the master list of detectable libraries                                                                                                               |
| `epic_orchestrator.py` lines 223-248 | Existing skill generation integration point                                                                                                                                     |
| `agent.py` lines 309-315             | Existing skill generation integration point (standard mode)                                                                                                                     |
| `test_skills.py` (full file)         | Existing test patterns to follow                                                                                                                                                |

---

## API Reference

### Ref API

- **URL:** `https://api.ref.tools/v1/search`
- **Method:** GET
- **Auth:** `x-ref-api-key: {REF_API_KEY}`
- **Params:** `q` (query string), `limit` (number of results)
- **Response:** `{ "results": [{ "content": "..." }] }`

### Exa API

- **URL:** `https://api.exa.ai/search`
- **Method:** POST
- **Auth:** `x-api-key: {EXA_API_KEY}`
- **Body:**

```json
{
  "query": "search query",
  "type": "auto",
  "numResults": 3,
  "contents": {
    "text": true,
    "highlights": { "maxCharacters": 4000 }
  }
}
```

- **Response:** `{ "results": [{ "title": "...", "url": "...", "text": "...", "highlights": [...] }] }`

---

## Example Output

For a project with `stack.all_libraries = ["Next.js", "Clerk", "Supabase", "FastAPI", "Stripe"]`, the harness generates:

```
<project>/.claude/skills/
├── e2e-test/SKILL.md              # Static (copied from harness)
├── api-test/SKILL.md              # Static (copied from harness)
├── test-runner/SKILL.md           # Workflow (generated, step-aware)
├── code-review/SKILL.md           # Workflow (generated, step-aware)
├── project-reference/SKILL.md     # Workflow (generated)
├── deployment-check/SKILL.md      # Workflow (generated, step-aware)
├── linear-workflow/SKILL.md       # Workflow (generated)
├── nextjs-docs/SKILL.md           # Library (Ref + Exa fetched)
├── clerk-docs/SKILL.md            # Library (Ref + Exa fetched)
├── supabase-docs/SKILL.md         # Library (Ref + Exa fetched)
├── fastapi-docs/SKILL.md          # Library (Ref + Exa fetched)
└── stripe-docs/SKILL.md           # Library (Ref + Exa fetched)
```

Each library skill:

- Loads only when triggered (description-based matching)
- Contains real, current documentation from Ref
- Contains real code examples from Exa
- Is cached for 24h to avoid redundant API calls
- Under 500 lines
- Has the harness marker for safe regeneration

---

## Risk Mitigation

| Risk                       | Mitigation                                                                 |
| -------------------------- | -------------------------------------------------------------------------- |
| API rate limits            | Cap at 15 libraries, parallel but with max_workers=8                       |
| Slow fetches delay startup | 10-15s timeout per request, total ~5-8s with parallelism                   |
| Stale documentation        | 24h cache TTL, regenerate on next harness run                              |
| APIs return garbage        | Truncate to 8000 chars, 500-line limit, fallback to static Quick Reference |
| No API keys                | Graceful skip — workflow skills still generated, just no library docs      |
| Content too verbose        | Highlights mode on Exa, single result from Ref, line-count enforcement     |
