"""
Skill Generation System
=======================

Analyses the tech stack from an app spec and/or existing codebase, then
generates project-specific Claude Code skills in <project>/.claude/skills/.

Skills are on-demand knowledge packages — only descriptions load at startup,
full content loads when the agent invokes the skill.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from prompts import _KNOWN_LIBRARIES

logger = logging.getLogger(__name__)

GENERATED_MARKER = "<!-- generated-by: harness -->"


# ---------------------------------------------------------------------------
# Tech Stack Detection
# ---------------------------------------------------------------------------

@dataclass
class TechStack:
    """Detected technology stack for a project."""

    # Frontend
    frontend_framework: str | None = None  # "nextjs", "react-vite", "vue", "svelte"
    frontend_language: str = "typescript"
    styling: list[str] = field(default_factory=list)
    ui_libraries: list[str] = field(default_factory=list)
    state_management: str | None = None
    auth_provider: str | None = None

    # Backend
    backend_framework: str | None = None  # "fastapi", "express", "nextjs-api"
    backend_language: str = "python"
    orm_or_db_client: str | None = None
    database: str | None = None

    # Testing
    frontend_test_runner: str = "vitest"
    e2e_test_runner: str = "playwright"
    backend_test_runner: str = "pytest"

    # Deployment
    frontend_deploy: str | None = None
    backend_deploy: str | None = None

    # AI/Integrations
    ai_libraries: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)

    # All detected libraries (superset)
    all_libraries: list[str] = field(default_factory=list)


# Mapping from detected library name (lowercase) to TechStack field updates
_FRAMEWORK_DETECTION: dict[str, dict] = {
    "next.js": {"frontend_framework": "nextjs", "frontend_language": "typescript"},
    "react": {"frontend_framework": "react-vite"},
    "vue": {"frontend_framework": "vue"},
    "svelte": {"frontend_framework": "svelte"},
    "fastapi": {"backend_framework": "fastapi", "backend_language": "python"},
    "express": {"backend_framework": "express", "backend_language": "typescript"},
    "clerk": {"auth_provider": "clerk"},
    "nextauth": {"auth_provider": "nextauth"},
    "auth.js": {"auth_provider": "nextauth"},
    "lucia": {"auth_provider": "lucia"},
    "supabase": {"database": "supabase", "orm_or_db_client": "supabase-py"},
    "convex": {"database": "convex", "state_management": "convex"},
    "postgresql": {"database": "postgresql"},
    "prisma": {"orm_or_db_client": "prisma"},
    "drizzle": {"orm_or_db_client": "drizzle"},
    "tailwind": {"styling": ["tailwind"]},
    "shadcn": {"ui_libraries": ["shadcn"]},
    "magicui": {"ui_libraries": ["magicui"]},
    "framer motion": {"ui_libraries": ["framer-motion"]},
    "radix": {"ui_libraries": ["radix"]},
    "headless ui": {"ui_libraries": ["headless-ui"]},
    "zustand": {"state_management": "zustand"},
    "zod": {},
    "stripe": {"integrations": ["stripe"]},
    "resend": {"integrations": ["resend"]},
    "inngest": {"integrations": ["inngest"]},
    "upstash": {"integrations": ["upstash"]},
    "redis": {"integrations": ["redis"]},
    "langchain": {"ai_libraries": ["langchain"]},
    "copilotkit": {"ai_libraries": ["copilotkit"]},
    "vercel": {"frontend_deploy": "vercel"},
    "render": {"backend_deploy": "render"},
    "netlify": {"frontend_deploy": "netlify"},
    "railway": {"backend_deploy": "railway"},
    "vitest": {"frontend_test_runner": "vitest"},
    "playwright": {"e2e_test_runner": "playwright"},
    "expo": {"frontend_framework": "expo"},
    "react native": {"frontend_framework": "react-native"},
    "gsap": {"ui_libraries": ["gsap"]},
    "remotion": {"ui_libraries": ["remotion"]},
    "trpc": {},
}

# package.json dependency names → library names for detection
_NPM_PACKAGE_MAP: dict[str, str] = {
    "next": "next.js",
    "react": "react",
    "@clerk/nextjs": "clerk",
    "@clerk/clerk-react": "clerk",
    "@supabase/supabase-js": "supabase",
    "tailwindcss": "tailwind",
    "@radix-ui/react-slot": "radix",
    "framer-motion": "framer motion",
    "motion": "framer motion",
    "zustand": "zustand",
    "zod": "zod",
    "stripe": "stripe",
    "@stripe/stripe-js": "stripe",
    "resend": "resend",
    "inngest": "inngest",
    "@upstash/redis": "upstash",
    "prisma": "prisma",
    "@prisma/client": "prisma",
    "drizzle-orm": "drizzle",
    "vitest": "vitest",
    "@playwright/test": "playwright",
    "next-auth": "nextauth",
    "@trpc/server": "trpc",
    "gsap": "gsap",
    "remotion": "remotion",
    "expo": "expo",
    "react-native": "react native",
    "convex": "convex",
    "@langchain/core": "langchain",
}

# Python package names → library names for detection
_PYTHON_PACKAGE_MAP: dict[str, str] = {
    "fastapi": "fastapi",
    "supabase": "supabase",
    "prisma": "prisma",
    "langchain": "langchain",
    "langchain-core": "langchain",
    "copilotkit": "copilotkit",
    "stripe": "stripe",
    "resend": "resend",
    "pydantic": "fastapi",  # strong signal
    "httpx": "fastapi",
    "uvicorn": "fastapi",
}

# Config file presence → library names
_CONFIG_FILE_MAP: dict[str, str] = {
    "next.config.ts": "next.js",
    "next.config.js": "next.js",
    "next.config.mjs": "next.js",
    "tailwind.config.ts": "tailwind",
    "tailwind.config.js": "tailwind",
    "drizzle.config.ts": "drizzle",
    "vite.config.ts": "react",
    "svelte.config.js": "svelte",
    "vue.config.js": "vue",
    "playwright.config.ts": "playwright",
    "vitest.config.ts": "vitest",
    "vitest.config.js": "vitest",
    "vercel.json": "vercel",
    "render.yaml": "render",
    "netlify.toml": "netlify",
}


def _extract_libs_from_spec(spec_text: str) -> list[str]:
    """Extract library/framework names from spec text using _KNOWN_LIBRARIES."""
    found: list[str] = []
    spec_lower = spec_text.lower()
    for lib in _KNOWN_LIBRARIES:
        if lib.lower() in spec_lower and lib not in found:
            found.append(lib)
    return found


def _extract_libs_from_package_json(project_dir: Path) -> list[str]:
    """Extract library names from package.json dependencies."""
    pkg_path = project_dir / "package.json"
    if not pkg_path.exists():
        return []

    try:
        pkg = json.loads(pkg_path.read_text())
    except (json.JSONDecodeError, IOError):
        return []

    found: list[str] = []
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for dep_name, lib_name in _NPM_PACKAGE_MAP.items():
        if dep_name in all_deps and lib_name not in found:
            found.append(lib_name)
    return found


def _extract_libs_from_python_deps(project_dir: Path) -> list[str]:
    """Extract library names from requirements.txt or pyproject.toml."""
    found: list[str] = []

    # Check requirements.txt
    req_path = project_dir / "requirements.txt"
    if req_path.exists():
        try:
            text = req_path.read_text().lower()
            for pkg_name, lib_name in _PYTHON_PACKAGE_MAP.items():
                if pkg_name in text and lib_name not in found:
                    found.append(lib_name)
        except IOError:
            pass

    # Check pyproject.toml (simple regex, no toml parser needed)
    pyproject_path = project_dir / "pyproject.toml"
    if pyproject_path.exists():
        try:
            text = pyproject_path.read_text().lower()
            for pkg_name, lib_name in _PYTHON_PACKAGE_MAP.items():
                if pkg_name in text and lib_name not in found:
                    found.append(lib_name)
        except IOError:
            pass

    return found


def _extract_libs_from_config_files(project_dir: Path) -> list[str]:
    """Detect libraries from config file presence."""
    found: list[str] = []
    for filename, lib_name in _CONFIG_FILE_MAP.items():
        if (project_dir / filename).exists() and lib_name not in found:
            found.append(lib_name)
    return found


def _apply_detection(stack: TechStack, lib_name: str) -> None:
    """Apply a detected library to the TechStack fields."""
    mapping = _FRAMEWORK_DETECTION.get(lib_name.lower(), {})
    for field_name, value in mapping.items():
        if isinstance(value, list):
            # List fields: extend without duplicates
            current = getattr(stack, field_name)
            for item in value:
                if item not in current:
                    current.append(item)
        else:
            # Scalar fields: only set if not already set (first detection wins)
            # Exception: codebase detection runs first, so it takes priority
            if getattr(stack, field_name) is None or getattr(stack, field_name) == field_name:
                setattr(stack, field_name, value)

    if lib_name not in stack.all_libraries:
        stack.all_libraries.append(lib_name)


def detect_tech_stack(
    spec_text: str,
    project_dir: Path,
    mode: str = "greenfield",
) -> TechStack:
    """
    Detect the technology stack from the app spec and/or existing codebase.

    Detection priority: codebase files > spec text > defaults.
    Codebase scanning only runs for brownfield mode or when files exist.
    """
    stack = TechStack()

    # 1. Codebase files (highest priority — applied first so they "win")
    codebase_libs: list[str] = []
    if mode == "brownfield" or (project_dir / "package.json").exists():
        codebase_libs.extend(_extract_libs_from_package_json(project_dir))
        codebase_libs.extend(_extract_libs_from_python_deps(project_dir))
        codebase_libs.extend(_extract_libs_from_config_files(project_dir))

    for lib in codebase_libs:
        _apply_detection(stack, lib)

    # 2. Spec text (fills in gaps not covered by codebase)
    spec_libs = _extract_libs_from_spec(spec_text)
    for lib in spec_libs:
        _apply_detection(stack, lib)

    # If next.js detected, don't also set react-vite
    if stack.frontend_framework == "nextjs":
        pass  # Already correct
    elif stack.frontend_framework == "react-vite" and "next.js" in [
        l.lower() for l in stack.all_libraries
    ]:
        stack.frontend_framework = "nextjs"

    logger.info(
        "[Skills] Detected stack: frontend=%s, backend=%s, db=%s, libs=%s",
        stack.frontend_framework,
        stack.backend_framework,
        stack.database,
        stack.all_libraries,
    )

    return stack


# ---------------------------------------------------------------------------
# Skill Builder Functions
# ---------------------------------------------------------------------------

def _frontmatter(name: str, description: str) -> str:
    """Build YAML frontmatter for a SKILL.md file."""
    return f"---\nname: {name}\ndescription: {description}\n---\n{GENERATED_MARKER}\n"


def _build_test_runner_skill(stack: TechStack, ctx: dict) -> str:
    """Assemble the test-runner SKILL.md from sections."""
    # Build test frameworks summary for description
    frameworks: list[str] = []
    if stack.frontend_framework:
        frameworks.append(f"{stack.frontend_test_runner} with React Testing Library (frontend)")
    if stack.backend_framework:
        frameworks.append(f"{stack.backend_test_runner} with httpx (backend)")
    if stack.e2e_test_runner:
        frameworks.append(f"{stack.e2e_test_runner} (E2E)")
    test_summary = ", ".join(frameworks) if frameworks else "project tests"

    sections: list[str] = [
        _frontmatter(
            "test-runner",
            f"Run and manage tests for this project. Covers {test_summary}. "
            "Use when running tests, debugging test failures, or setting up the test environment.",
        ),
        "# Test Runner\n",
    ]

    # Quick commands table
    commands: list[tuple[str, str]] = []
    if stack.frontend_framework:
        commands.extend([
            ("All frontend tests", "npx vitest run"),
            ("Frontend watch mode", "npx vitest"),
            ("Single frontend test", "npx vitest run path/to/test.test.ts"),
        ])
    if stack.backend_framework == "fastapi":
        commands.extend([
            ("All backend tests", "pytest api_tests/ -v"),
            ("Single backend test", "pytest api_tests/test_example.py -v"),
        ])
    if stack.e2e_test_runner == "playwright":
        commands.extend([
            ("All E2E tests", "npx playwright test"),
            ("Single E2E test", "npx playwright test e2e/example.spec.ts"),
        ])

    if commands:
        table = "## Quick Commands\n\n| What | Command |\n|------|---------|"
        for label, cmd in commands:
            table += f"\n| {label} | `{cmd}` |"
        sections.append(table)

    # Frontend test section
    if stack.frontend_framework:
        fe_section = "## Frontend Tests (Vitest + React Testing Library)\n\n"
        fe_section += "Test files live in `__tests__/` directories or alongside components as `*.test.ts(x)`.\n\n"
        fe_section += "### Setup\n\n"
        fe_section += "```bash\nnpm install -D vitest @testing-library/react @testing-library/jest-dom jsdom\n```\n\n"
        fe_section += "### Key Patterns\n\n"
        fe_section += "- Use `render()` from `@testing-library/react` — never `ReactDOM.render()`\n"
        fe_section += '- Query by role: `screen.getByRole("button", { name: "Submit" })`\n'
        fe_section += "- Use `userEvent` over `fireEvent` for realistic interactions\n"

        if stack.auth_provider == "clerk":
            fe_section += "- Mock Clerk auth with `@clerk/testing` or mock `useUser()` directly\n"
        if stack.database == "supabase":
            fe_section += "- Mock Supabase client — never hit real Supabase in unit tests\n"

        fe_section += "\n### Example\n\n"
        fe_section += '```typescript\nimport { render, screen } from "@testing-library/react";\n'
        fe_section += 'import userEvent from "@testing-library/user-event";\n\n'
        fe_section += 'test("renders component correctly", async () => {\n'
        fe_section += "  render(<MyComponent />);\n"
        fe_section += '  expect(screen.getByText(/expected text/)).toBeInTheDocument();\n'
        fe_section += "});\n```"
        sections.append(fe_section)

    # Backend test section
    if stack.backend_framework == "fastapi":
        be_section = "## Backend Tests (pytest + httpx)\n\n"
        be_section += "Test files live in `api_tests/` at the project root.\n\n"
        be_section += "### Setup\n\n"
        be_section += "```bash\npip install pytest httpx pytest-asyncio\n```\n\n"
        be_section += "### Key Patterns\n\n"
        be_section += '- Use `httpx.AsyncClient` with `base_url="http://localhost:8000"`\n'
        be_section += "- Assert status codes explicitly: `assert response.status_code == 201`\n"
        be_section += "- Use Pydantic V2 models to validate response shapes\n"
        be_section += "- Test auth guards: call endpoints without token, expect 401\n"

        if stack.database == "supabase":
            be_section += "- For Supabase operations: mock the Supabase client in fixtures\n"

        be_section += "\nSee `.claude/skills/api-test/SKILL.md` for detailed patterns and examples."
        sections.append(be_section)

    # E2E section
    if stack.e2e_test_runner == "playwright":
        e2e_section = "## E2E Tests (Playwright)\n\n"
        e2e_section += "Test files live in `e2e/` at the project root.\n\n"
        e2e_section += "See `.claude/skills/e2e-test/SKILL.md` for detailed patterns and examples."
        sections.append(e2e_section)

    # When to use which
    if stack.frontend_framework and stack.backend_framework:
        guide = "## When to Use Which\n\n"
        guide += "| Issue type | Test type |\n|-----------|----------|\n"
        guide += f"| Frontend-only (component, page, styling) | {stack.frontend_test_runner} + {stack.e2e_test_runner} |\n"
        guide += f"| Backend-only (API route, auth guard, DB) | {stack.backend_test_runner} + httpx |\n"
        guide += f"| Full-stack (form → API → UI update) | {stack.backend_test_runner} + httpx AND {stack.e2e_test_runner} |\n"
        guide += "| Config, refactoring, migrations | Run full existing suite |"
        sections.append(guide)

    return "\n\n".join(sections)


def _build_code_review_skill(stack: TechStack, ctx: dict) -> str:
    """Assemble the code-review SKILL.md from sections."""
    sections: list[str] = [
        _frontmatter(
            "code-review",
            "Review code changes for this project. Provides stack-specific checklists "
            "and common mistake detection. Use when reviewing code, before committing, "
            "or when asked to review a pull request or diff.",
        ),
        "# Code Review Checklist\n",
    ]

    # General checks
    general = "## General\n\n"
    general += "- [ ] No unused imports or variables\n"
    general += "- [ ] No hardcoded secrets, API keys, or tokens\n"
    general += "- [ ] No `console.log` / `print()` statements left in production code\n"
    general += "- [ ] Error handling is present for external calls (APIs, DB, file I/O)\n"
    general += "- [ ] Types are explicit — no `any` in TypeScript, no untyped dicts in Python\n"
    sections.append(general)

    # Frontend checks
    if stack.frontend_framework == "nextjs":
        fe = "## Next.js (App Router)\n\n"
        fe += "- [ ] Server Components used by default — `'use client'` only where needed\n"
        fe += "- [ ] `next/image` for all images, `next/link` for internal navigation\n"
        fe += "- [ ] `next/font` for font loading — no external stylesheet font imports\n"
        fe += "- [ ] Metadata API used (`generateMetadata` or static `metadata`) — no `<head>` tags\n"
        fe += "- [ ] No `getServerSideProps` / `getStaticProps` (Pages Router patterns)\n"
        fe += "- [ ] No `useEffect` for data fetching — use Server Components or server actions\n"
        fe += "- [ ] `loading.tsx` and `error.tsx` present for new route segments\n"
        fe += "- [ ] Environment variables: `NEXT_PUBLIC_` prefix only for client-side vars\n"
        sections.append(fe)
    elif stack.frontend_framework:
        fe = "## Frontend\n\n"
        fe += "- [ ] Components are properly typed\n"
        fe += "- [ ] No inline styles where utility classes exist\n"
        fe += "- [ ] Accessibility: semantic HTML, alt text, ARIA labels\n"
        sections.append(fe)

    if "tailwind" in stack.styling:
        tw = "## Tailwind CSS\n\n"
        tw += "- [ ] No inline styles when Tailwind classes exist for the same purpose\n"
        tw += "- [ ] Responsive classes used where appropriate (`sm:`, `md:`, `lg:`)\n"
        tw += "- [ ] Dark mode classes if the project supports dark mode\n"
        sections.append(tw)

    # Auth checks
    if stack.auth_provider == "clerk":
        auth = "## Clerk Auth\n\n"
        auth += "- [ ] `clerkMiddleware()` used in `middleware.ts` — no custom auth middleware\n"
        auth += "- [ ] `useUser()` / `useAuth()` hooks for client-side user data\n"
        auth += "- [ ] No custom JWT validation unless integrating external services\n"
        auth += "- [ ] User data synced via Clerk webhooks if stored in DB\n"
        sections.append(auth)

    # Backend checks
    if stack.backend_framework == "fastapi":
        be = "## FastAPI\n\n"
        be += "- [ ] `async def` for endpoints by default\n"
        be += "- [ ] Pydantic V2 models for all request/response schemas — no raw dicts\n"
        be += "- [ ] `@field_validator` / `model_config = ConfigDict(...)` — not V1 syntax\n"
        be += "- [ ] `lifespan` context manager — not `@app.on_event(\"startup\")`\n"
        be += "- [ ] Proper HTTP status codes (201 creation, 204 deletion, 422 validation)\n"
        be += "- [ ] CORS configured explicitly — no `allow_origins=[\"*\"]` in production\n"
        be += "- [ ] Dependency injection for DB sessions, auth, shared services\n"
        be += "- [ ] Structured logging — no `print()` statements\n"
        sections.append(be)

    # Database checks
    if stack.database == "supabase":
        db = "## Supabase\n\n"
        db += "- [ ] Row Level Security (RLS) enabled on every table\n"
        db += "- [ ] No service key in client-side code\n"
        db += "- [ ] Realtime subscriptions used instead of polling where appropriate\n"
        db += "- [ ] Migrations in migration files — no manual schema changes\n"
        sections.append(db)
    elif stack.orm_or_db_client == "prisma":
        db = "## Prisma\n\n"
        db += "- [ ] Schema changes have a migration file\n"
        db += "- [ ] `prisma generate` run after schema changes\n"
        db += "- [ ] No raw SQL unless absolutely necessary\n"
        sections.append(db)
    elif stack.orm_or_db_client == "drizzle":
        db = "## Drizzle\n\n"
        db += "- [ ] Schema changes have a migration file\n"
        db += "- [ ] Type-safe queries — no raw SQL strings\n"
        sections.append(db)

    # Integration checks
    if "stripe" in stack.integrations:
        stripe_section = "## Stripe\n\n"
        stripe_section += "- [ ] Webhook endpoint validates signatures\n"
        stripe_section += "- [ ] Secret key never in client-side code\n"
        stripe_section += "- [ ] Prices and products referenced by ID, not hardcoded amounts\n"
        sections.append(stripe_section)

    # AI checks
    if "langchain" in stack.ai_libraries:
        ai = "## LangChain\n\n"
        ai += "- [ ] LCEL pipe syntax — no legacy `LLMChain` / `SequentialChain`\n"
        ai += "- [ ] `ChatPromptTemplate` — no raw string prompts\n"
        ai += "- [ ] `with_structured_output()` with Pydantic models for structured output\n"
        ai += "- [ ] `OutputParserException` handled\n"
        ai += "- [ ] All LLM calls wrapped in try/except\n"
        sections.append(ai)

    return "\n\n".join(sections)


def _build_project_reference_skill(stack: TechStack, ctx: dict) -> str:
    """Assemble the project-reference SKILL.md."""
    mode = ctx.get("mode", "greenfield")
    is_epic = ctx.get("is_epic", False)

    sections: list[str] = [
        _frontmatter(
            "project-reference",
            "Recall the original app specification, architectural decisions, and project "
            "requirements. Use when unsure about a feature's intended behaviour or to "
            "check the original design intent.",
        ),
        "# Project Reference\n",
        "## Key Files\n",
    ]

    # Spec files
    if is_epic:
        files = "| File | Purpose |\n|------|---------|"
        files += "\n| `epics/spec_index.md` | Master specification with all epics |"
        files += "\n| `epics/epic-NN-name.md` | Individual epic specifications |"
    else:
        files = "| File | Purpose |\n|------|---------|"
        files += "\n| `app_spec.txt` | Full application specification |"

    files += "\n| `shared_context.md` | Architectural decisions and shared context |"
    files += "\n| `build_deviations.md` | Documented deviations from the original spec |"

    if mode == "brownfield":
        files += "\n| `README.md` | Existing project documentation |"

    sections.append(files)

    # How to use
    usage = "## When to Reference\n\n"
    usage += "- Before implementing a feature: check the spec for intended behaviour\n"
    usage += "- When making architectural decisions: check `shared_context.md`\n"
    usage += "- When deviating from spec: document in `build_deviations.md`\n"
    usage += "- When unsure about design (colours, typography, layout): check the spec's design section\n"
    sections.append(usage)

    # Deviation tracking
    dev = "## Recording Deviations\n\n"
    dev += "When the implementation must differ from the spec, append to `build_deviations.md`:\n\n"
    dev += "```markdown\n## [Feature Name] — Deviation\n\n"
    dev += "**Spec said:** [original requirement]\n"
    dev += "**We did:** [what was actually built]\n"
    dev += "**Reason:** [why the deviation was necessary]\n```"
    sections.append(dev)

    return "\n\n".join(sections)


def _build_deployment_check_skill(stack: TechStack, ctx: dict) -> str:
    """Assemble the deployment-check SKILL.md."""
    sections: list[str] = [
        _frontmatter(
            "deployment-check",
            "Validate the project is production-ready before deployment. Checks environment "
            "variables, build commands, and stack-specific production requirements. Use before "
            "deployment or when running final checks.",
        ),
        "# Pre-Deployment Checklist\n",
    ]

    # Build commands
    build_cmds: list[tuple[str, str]] = []
    if stack.frontend_framework == "nextjs":
        build_cmds.append(("Frontend build", "npm run build"))
        build_cmds.append(("TypeScript check", "npx tsc --noEmit"))
        build_cmds.append(("Lint", "npm run lint"))
    elif stack.frontend_framework:
        build_cmds.append(("Frontend build", "npm run build"))

    if stack.backend_framework == "fastapi":
        build_cmds.append(("Backend lint", "ruff check ."))
        build_cmds.append(("Backend type check", "mypy ."))

    if build_cmds:
        table = "## Build Verification\n\nRun these commands and verify they pass:\n\n"
        table += "| Check | Command |\n|-------|---------|"
        for label, cmd in build_cmds:
            table += f"\n| {label} | `{cmd}` |"
        sections.append(table)

    # Environment variables
    env_vars: list[tuple[str, str]] = []

    if stack.frontend_framework == "nextjs":
        env_vars.append(("NEXT_PUBLIC_*", "Public client-side variables"))

    if stack.auth_provider == "clerk":
        env_vars.extend([
            ("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "Clerk frontend key"),
            ("CLERK_SECRET_KEY", "Clerk backend key"),
        ])

    if stack.database == "supabase":
        env_vars.extend([
            ("NEXT_PUBLIC_SUPABASE_URL", "Supabase project URL"),
            ("NEXT_PUBLIC_SUPABASE_ANON_KEY", "Supabase anonymous key"),
            ("SUPABASE_SERVICE_ROLE_KEY", "Supabase service key (backend only)"),
        ])

    if "stripe" in stack.integrations:
        env_vars.extend([
            ("STRIPE_SECRET_KEY", "Stripe API secret key"),
            ("STRIPE_WEBHOOK_SECRET", "Stripe webhook signing secret"),
            ("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", "Stripe publishable key"),
        ])

    if "resend" in stack.integrations:
        env_vars.append(("RESEND_API_KEY", "Resend email API key"))

    if stack.backend_framework == "fastapi":
        env_vars.append(("DATABASE_URL", "Database connection string"))

    if stack.frontend_deploy == "vercel":
        env_vars.append(("VERCEL_URL", "Auto-set by Vercel"))

    if env_vars:
        env_section = "## Environment Variables\n\nVerify these are set in production:\n\n"
        env_section += "| Variable | Purpose |\n|----------|---------|"
        for var, purpose in env_vars:
            env_section += f"\n| `{var}` | {purpose} |"
        sections.append(env_section)

    # Stack-specific checks
    checks: list[str] = []

    if stack.frontend_framework == "nextjs":
        checks.extend([
            "- [ ] `next build` completes without errors",
            "- [ ] No TypeScript errors (`tsc --noEmit`)",
            "- [ ] All images use `next/image` with proper `width`/`height` or `fill`",
            "- [ ] Metadata configured for all public pages (SEO)",
            "- [ ] `middleware.ts` protects authenticated routes",
        ])

    if stack.backend_framework == "fastapi":
        checks.extend([
            "- [ ] Uvicorn configured with appropriate workers",
            "- [ ] CORS origins set to production domains only",
            "- [ ] Health check endpoint at `/health` responds 200",
            "- [ ] All endpoints have response models",
            "- [ ] Rate limiting configured on public endpoints",
        ])

    if stack.database == "supabase":
        checks.extend([
            "- [ ] RLS enabled on ALL tables",
            "- [ ] Service role key NOT in any client-side code",
            "- [ ] Database migrations are up to date",
        ])

    if stack.auth_provider == "clerk":
        checks.extend([
            "- [ ] Clerk middleware configured in `middleware.ts`",
            "- [ ] Sign-in/sign-up URLs configured",
            "- [ ] Webhook endpoint registered for user sync (if needed)",
        ])

    if "stripe" in stack.integrations:
        checks.extend([
            "- [ ] Stripe webhook endpoint registered and verified",
            "- [ ] No hardcoded prices — use Stripe Price IDs",
            "- [ ] Webhook signature validation enabled",
        ])

    if checks:
        checks_section = "## Production Checks\n\n" + "\n".join(checks)
        sections.append(checks_section)

    # Final steps
    final = "## Final Steps\n\n"
    final += "1. Run the full test suite and verify all tests pass\n"
    final += "2. Check that `.env.example` documents all required variables\n"
    final += "3. Verify `.gitignore` excludes `.env*`, `node_modules/`, `__pycache__/`\n"
    final += "4. Review `build_deviations.md` for any unresolved deviations\n"
    sections.append(final)

    return "\n\n".join(sections)


def _build_linear_workflow_skill(stack: TechStack, ctx: dict) -> str:
    """Assemble the linear-workflow SKILL.md."""
    sections: list[str] = [
        _frontmatter(
            "linear-workflow",
            "Manage Linear issues for this project. Covers searching issues, updating "
            "status, adding comments, and handling special issue types. Use when working "
            "with Linear issues or needing to understand the project's issue structure.",
        ),
        "# Linear Workflow\n",
    ]

    # Project context (dynamic injection)
    project_ctx = "## Project Context\n\n"
    project_ctx += "Linear project state: !`cat .linear_project.json`\n"
    sections.append(project_ctx)

    # Issue lifecycle
    lifecycle = "## Issue Lifecycle\n\n"
    lifecycle += "```\nTodo → In Progress → Done\n```\n\n"
    lifecycle += "1. **Pick up an issue**: Move from Todo → In Progress\n"
    lifecycle += "2. **Work on the issue**: Implement the requirement\n"
    lifecycle += "3. **Commit and test**: Ensure all tests pass\n"
    lifecycle += "4. **Mark Done**: Update the issue status in Linear\n"
    lifecycle += "5. **Move to next issue**: Do NOT pick up multiple issues at once\n"
    sections.append(lifecycle)

    # Searching issues
    search = "## Searching Issues\n\n"
    search += "Use the Linear MCP tools to search for issues in this project. "
    search += "Filter by status (Todo, In Progress, Done) to find work.\n"
    sections.append(search)

    # Special issue types
    special = "## Special Issue Types\n\n"
    special += "### [SNAPSHOT] Issues\n\n"
    special += "These require taking a visual snapshot of the current state. "
    special += "Run the application, capture screenshots, and attach them to the issue.\n\n"
    special += "### [HUMAN GATE] Issues\n\n"
    special += "These require human review before proceeding. When encountered:\n\n"
    special += "1. Complete all work up to the gate\n"
    special += "2. Add a comment explaining what's ready for review\n"
    special += "3. **STOP** — do not continue past the gate\n"
    special += "4. The harness will pause until a human resolves the gate issue\n"
    sections.append(special)

    # Comments
    comments = "## Adding Comments\n\n"
    comments += "Add comments to issues when:\n\n"
    comments += "- You encounter a blocker or need clarification\n"
    comments += "- You deviate from the issue's original description\n"
    comments += "- You complete the issue (brief summary of what was done)\n"
    comments += "- You discover related work that needs a new issue\n"
    sections.append(comments)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Skill Writer
# ---------------------------------------------------------------------------

# Registry of skill builders: name → builder function
_SKILL_BUILDERS: dict[str, callable] = {
    "test-runner": _build_test_runner_skill,
    "code-review": _build_code_review_skill,
    "project-reference": _build_project_reference_skill,
    "deployment-check": _build_deployment_check_skill,
    "linear-workflow": _build_linear_workflow_skill,
}


def _is_harness_generated(skill_path: Path) -> bool:
    """Check if a SKILL.md was generated by the harness (has the marker)."""
    if not skill_path.exists():
        return False
    try:
        content = skill_path.read_text()
        return GENERATED_MARKER in content
    except IOError:
        return False


def generate_project_skills(
    project_dir: Path,
    spec_text: str,
    mode: str = "greenfield",
    is_epic: bool = False,
    stack: TechStack | None = None,
) -> list[str]:
    """
    Generate project-specific skills based on the detected tech stack.

    Detects the tech stack from the spec and/or codebase, renders skill
    templates, and writes them to <project>/.claude/skills/<name>/SKILL.md.

    If ``stack`` is provided, uses it directly instead of re-detecting.

    Returns list of generated skill names.
    """
    if stack is None:
        stack = detect_tech_stack(spec_text, project_dir, mode=mode)

    ctx = {
        "mode": mode,
        "is_epic": is_epic,
        "project_dir": str(project_dir),
    }

    skills_dir = project_dir / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    generated: list[str] = []

    for skill_name, builder in _SKILL_BUILDERS.items():
        skill_dir = skills_dir / skill_name
        skill_path = skill_dir / "SKILL.md"

        # Preserve user-created skills
        if skill_path.exists() and not _is_harness_generated(skill_path):
            logger.info(
                "[Skills] Skipping %s — exists and not harness-generated",
                skill_name,
            )
            continue

        # Build skill content
        try:
            content = builder(stack, ctx)
        except Exception as e:
            logger.warning("[Skills] Failed to build %s: %s", skill_name, e)
            continue

        # Write skill file
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(content)

        # Create references directory for project-reference skill
        if skill_name == "project-reference":
            refs_dir = skill_dir / "references"
            refs_dir.mkdir(exist_ok=True)

        generated.append(skill_name)
        logger.info("[Skills] Generated %s", skill_name)

    return generated


# ---------------------------------------------------------------------------
# Library Documentation Skills — Metadata & Fetch (Steps 1+2)
# ---------------------------------------------------------------------------

REF_API_URL = "https://api.ref.tools/v1/search"
EXA_API_URL = "https://api.exa.ai/search"
SKILL_DOCS_CACHE_TTL = 86400  # 24 hours
MAX_LIBRARY_SKILLS = 15

# Maps library name → skill directory slug
_LIBRARY_SKILL_SLUGS: dict[str, str] = {
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
    "Pydantic": "pydantic-docs",
    "tRPC": "trpc-docs",
    "Convex": "convex-docs",
    "Expo": "expo-docs",
    "React Native": "react-native-docs",
    "NextAuth": "nextauth-docs",
    "Auth.js": "authjs-docs",
    "Lucia": "lucia-docs",
    "Framer Motion": "framer-motion-docs",
    "Radix": "radix-docs",
    "Headless UI": "headless-ui-docs",
    "MagicUI": "magicui-docs",
    "Redis": "redis-docs",
    "Resend": "resend-docs",
    "Inngest": "inngest-docs",
    "Upstash": "upstash-docs",
    "PostgreSQL": "postgresql-docs",
    "Vercel": "vercel-docs",
    "Render": "render-docs",
}

# Maps library name → {"ref": query, "exa": query} for targeted searches
_LIBRARY_SEARCH_QUERIES: dict[str, dict[str, str]] = {
    "Next.js": {
        "ref": "Next.js 15 App Router API reference",
        "exa": "Next.js 15 App Router best practices examples server components",
    },
    "React": {
        "ref": "React hooks API reference",
        "exa": "React hooks patterns best practices examples",
    },
    "FastAPI": {
        "ref": "FastAPI Python async endpoints Pydantic V2",
        "exa": "FastAPI Pydantic V2 async endpoint examples best practices",
    },
    "Clerk": {
        "ref": "Clerk Next.js authentication setup middleware",
        "exa": "Clerk Next.js authentication implementation examples 2024",
    },
    "Supabase": {
        "ref": "Supabase JavaScript client API reference",
        "exa": "Supabase Row Level Security policies Next.js examples",
    },
    "Stripe": {
        "ref": "Stripe API checkout subscriptions webhooks",
        "exa": "Stripe Next.js integration checkout webhook examples",
    },
    "Tailwind": {
        "ref": "Tailwind CSS utility classes responsive design",
        "exa": "Tailwind CSS component patterns responsive design examples",
    },
    "shadcn": {
        "ref": "shadcn/ui component library installation usage",
        "exa": "shadcn ui Next.js component examples customisation",
    },
    "Prisma": {
        "ref": "Prisma ORM schema migrations queries",
        "exa": "Prisma ORM Next.js TypeScript examples best practices",
    },
    "Drizzle": {
        "ref": "Drizzle ORM schema queries migrations",
        "exa": "Drizzle ORM TypeScript examples best practices",
    },
    "LangChain": {
        "ref": "LangChain Python LCEL chains tools agents",
        "exa": "LangChain Python LCEL structured output examples 2024",
    },
    "CopilotKit": {
        "ref": "CopilotKit React AI copilot integration",
        "exa": "CopilotKit React integration AG-UI examples",
    },
    "Zustand": {
        "ref": "Zustand React state management API",
        "exa": "Zustand React state management patterns examples",
    },
    "Zod": {
        "ref": "Zod TypeScript schema validation API",
        "exa": "Zod TypeScript validation patterns examples",
    },
    "Playwright": {
        "ref": "Playwright end-to-end testing API reference",
        "exa": "Playwright E2E testing Next.js examples best practices",
    },
    "Vitest": {
        "ref": "Vitest unit testing framework API reference",
        "exa": "Vitest React Testing Library examples best practices",
    },
    "GSAP": {
        "ref": "GSAP animation library ScrollTrigger API",
        "exa": "GSAP React animation ScrollTrigger examples",
    },
    "Remotion": {
        "ref": "Remotion React video creation API",
        "exa": "Remotion React programmatic video examples",
    },
    "Pydantic": {
        "ref": "Pydantic V2 model validation configuration",
        "exa": "Pydantic V2 model validator field_validator examples",
    },
    "tRPC": {
        "ref": "tRPC type-safe API Next.js",
        "exa": "tRPC Next.js App Router examples best practices",
    },
    "Convex": {
        "ref": "Convex reactive backend database API",
        "exa": "Convex React real-time backend examples",
    },
    "Expo": {
        "ref": "Expo React Native SDK API reference",
        "exa": "Expo React Native app development examples",
    },
    "React Native": {
        "ref": "React Native components API reference",
        "exa": "React Native best practices examples 2024",
    },
    "NextAuth": {
        "ref": "NextAuth.js authentication providers configuration",
        "exa": "NextAuth Next.js authentication examples",
    },
    "Auth.js": {
        "ref": "Auth.js v5 authentication setup",
        "exa": "Auth.js v5 Next.js authentication examples",
    },
    "Lucia": {
        "ref": "Lucia authentication library API",
        "exa": "Lucia auth Next.js implementation examples",
    },
    "Framer Motion": {
        "ref": "Framer Motion React animation API",
        "exa": "Framer Motion React animation examples patterns",
    },
    "Radix": {
        "ref": "Radix UI accessible component primitives",
        "exa": "Radix UI React accessible component examples",
    },
    "Headless UI": {
        "ref": "Headless UI Tailwind component library",
        "exa": "Headless UI Tailwind React component examples",
    },
    "MagicUI": {
        "ref": "Magic UI animated component library",
        "exa": "Magic UI React animated component examples",
    },
    "Redis": {
        "ref": "Redis commands data structures API",
        "exa": "Redis Node.js Python caching examples best practices",
    },
    "Resend": {
        "ref": "Resend email API Next.js integration",
        "exa": "Resend email API Next.js React Email examples",
    },
    "Inngest": {
        "ref": "Inngest serverless functions events",
        "exa": "Inngest Next.js background jobs examples",
    },
    "Upstash": {
        "ref": "Upstash Redis rate limiting API",
        "exa": "Upstash Redis Next.js rate limiting examples",
    },
    "PostgreSQL": {
        "ref": "PostgreSQL SQL queries indexes performance",
        "exa": "PostgreSQL query optimization indexing best practices",
    },
    "Vercel": {
        "ref": "Vercel deployment configuration Next.js",
        "exa": "Vercel deployment Next.js configuration examples",
    },
    "Render": {
        "ref": "Render web service deployment configuration",
        "exa": "Render FastAPI Python deployment examples",
    },
}

# Maps library name → static metadata for Quick Reference section
_LIBRARY_METADATA: dict[str, dict[str, str]] = {
    "Next.js": {"url": "https://nextjs.org/docs", "package": "next"},
    "React": {"url": "https://react.dev", "package": "react"},
    "FastAPI": {"url": "https://fastapi.tiangolo.com", "package": "fastapi"},
    "Clerk": {"url": "https://clerk.com/docs", "package": "@clerk/nextjs"},
    "Supabase": {"url": "https://supabase.com/docs", "package": "@supabase/supabase-js"},
    "Stripe": {"url": "https://docs.stripe.com", "package": "stripe"},
    "Tailwind": {"url": "https://tailwindcss.com/docs", "package": "tailwindcss"},
    "shadcn": {"url": "https://ui.shadcn.com/docs", "package": "shadcn"},
    "Prisma": {"url": "https://www.prisma.io/docs", "package": "@prisma/client"},
    "Drizzle": {"url": "https://orm.drizzle.team/docs", "package": "drizzle-orm"},
    "LangChain": {"url": "https://python.langchain.com/docs", "package": "langchain"},
    "CopilotKit": {"url": "https://docs.copilotkit.ai", "package": "@copilotkit/react-core"},
    "Zustand": {"url": "https://zustand-demo.pmnd.rs", "package": "zustand"},
    "Zod": {"url": "https://zod.dev", "package": "zod"},
    "Playwright": {"url": "https://playwright.dev/docs", "package": "@playwright/test"},
    "Vitest": {"url": "https://vitest.dev", "package": "vitest"},
    "GSAP": {"url": "https://gsap.com/docs", "package": "gsap"},
    "Remotion": {"url": "https://remotion.dev/docs", "package": "remotion"},
    "Pydantic": {"url": "https://docs.pydantic.dev", "package": "pydantic"},
    "tRPC": {"url": "https://trpc.io/docs", "package": "@trpc/server"},
    "Convex": {"url": "https://docs.convex.dev", "package": "convex"},
    "Expo": {"url": "https://docs.expo.dev", "package": "expo"},
    "React Native": {"url": "https://reactnative.dev/docs", "package": "react-native"},
    "NextAuth": {"url": "https://next-auth.js.org/getting-started", "package": "next-auth"},
    "Auth.js": {"url": "https://authjs.dev", "package": "@auth/core"},
    "Lucia": {"url": "https://lucia-auth.com", "package": "lucia"},
    "Framer Motion": {"url": "https://motion.dev/docs", "package": "framer-motion"},
    "Radix": {"url": "https://www.radix-ui.com/primitives/docs", "package": "@radix-ui/react-slot"},
    "Headless UI": {"url": "https://headlessui.com", "package": "@headlessui/react"},
    "MagicUI": {"url": "https://magicui.design/docs", "package": "@magic-ui/core"},
    "Redis": {"url": "https://redis.io/docs", "package": "redis"},
    "Resend": {"url": "https://resend.com/docs", "package": "resend"},
    "Inngest": {"url": "https://www.inngest.com/docs", "package": "inngest"},
    "Upstash": {"url": "https://upstash.com/docs", "package": "@upstash/redis"},
    "PostgreSQL": {"url": "https://www.postgresql.org/docs", "package": "pg"},
    "Vercel": {"url": "https://vercel.com/docs", "package": "vercel"},
    "Render": {"url": "https://docs.render.com", "package": "render"},
}


def _slugify_library(library: str) -> str:
    """Convert a library name to a skill directory slug."""
    if library in _LIBRARY_SKILL_SLUGS:
        return _LIBRARY_SKILL_SLUGS[library]
    return re.sub(r"[^a-z0-9-]", "", library.lower().replace(" ", "-").replace(".", "")) + "-docs"


def _fetch_ref_for_skill(library: str, api_key: str) -> tuple[str, str | None]:
    """Fetch Ref API documentation for a library. Returns (library, content or None)."""
    queries = _LIBRARY_SEARCH_QUERIES.get(library, {})
    query = queries.get("ref", f"{library} API reference documentation")
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
                content = results[0].get("content", "")
                if content:
                    return library, content[:8000]
    except Exception:
        pass
    return library, None


def _fetch_exa_for_skill(library: str, api_key: str) -> tuple[str, str | None]:
    """Fetch Exa API code examples for a library. Returns (library, content or None)."""
    queries = _LIBRARY_SEARCH_QUERIES.get(library, {})
    query = queries.get("exa", f"{library} best practices examples {time.strftime('%Y')}")
    try:
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
                snippets: list[str] = []
                for r in results:
                    title = r.get("title", "")
                    url = r.get("url", "")
                    highlights = r.get("highlights", [])
                    text = "\n".join(highlights) if highlights else r.get("text", "")[:2000]
                    snippets.append(f"### {title}\nSource: {url}\n\n{text}")
                return library, "\n\n".join(snippets)
    except Exception:
        pass
    return library, None


def _load_skill_docs_cache(cache_path: Path | None) -> dict:
    """Load cached library documentation results."""
    if cache_path is None or not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _save_skill_docs_cache(cache_path: Path | None, cache: dict) -> None:
    """Save library documentation cache to disk."""
    if cache_path is None:
        return
    try:
        cache_path.write_text(json.dumps(cache, indent=2))
    except IOError as e:
        logger.warning("[Skill Docs] Could not write cache: %s", e)


def _fetch_all_library_docs(
    libraries: list[str],
    ref_key: str | None,
    exa_key: str | None,
    cache_path: Path | None,
) -> dict[str, dict]:
    """
    Fetch documentation for all libraries in parallel, with caching.

    Returns {library: {"ref_content": str|None, "exa_content": str|None}}.
    """
    cache = _load_skill_docs_cache(cache_path)
    now = time.time()
    results: dict[str, dict] = {}
    libs_to_fetch: list[str] = []

    # Check cache first
    for lib in libraries:
        cached = cache.get(lib)
        if cached and (now - cached.get("timestamp", 0)) < SKILL_DOCS_CACHE_TTL:
            results[lib] = {
                "ref_content": cached.get("ref_content"),
                "exa_content": cached.get("exa_content"),
            }
            logger.info("[Skill Docs] Cache hit: %s", lib)
        else:
            libs_to_fetch.append(lib)

    if not libs_to_fetch:
        return results

    # Parallel fetch — submit both Ref and Exa for each library
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures: dict = {}
            for lib in libs_to_fetch:
                if ref_key:
                    futures[executor.submit(_fetch_ref_for_skill, lib, ref_key)] = (lib, "ref")
                if exa_key:
                    futures[executor.submit(_fetch_exa_for_skill, lib, exa_key)] = (lib, "exa")

            partial: dict[str, dict] = {lib: {} for lib in libs_to_fetch}
            for future in as_completed(futures, timeout=30):
                try:
                    lib_name, content = future.result(timeout=5)
                    _, source = futures[future]
                    key = "ref_content" if source == "ref" else "exa_content"
                    partial[lib_name][key] = content
                except Exception:
                    pass

            for lib in libs_to_fetch:
                ref_content = partial[lib].get("ref_content")
                exa_content = partial[lib].get("exa_content")
                results[lib] = {"ref_content": ref_content, "exa_content": exa_content}
                cache[lib] = {
                    "ref_content": ref_content,
                    "exa_content": exa_content,
                    "timestamp": now,
                }
    except Exception as e:
        logger.warning("[Skill Docs] Error during parallel fetch: %s", e)

    _save_skill_docs_cache(cache_path, cache)
    return results


# ---------------------------------------------------------------------------
# Library Skill Assembler (Step 3)
# ---------------------------------------------------------------------------

MAX_SKILL_LINES = 500


def _build_library_skill(
    library: str,
    ref_content: str | None,
    exa_content: str | None,
) -> str:
    """
    Assemble a library documentation SKILL.md from fetched content.

    Returns the full skill content with YAML frontmatter, harness marker,
    and documentation/example sections. Enforces MAX_SKILL_LINES limit.
    """
    slug = _slugify_library(library)
    meta = _LIBRARY_METADATA.get(library, {})
    docs_url = meta.get("url", "")
    package = meta.get("package", "")

    description = (
        f"{library} documentation and patterns. Reference for API usage, "
        f"configuration, and common patterns. Use when implementing or "
        f"modifying code that uses {library}."
    )

    sections: list[str] = [
        _frontmatter(slug, description),
        f"# {library} — Documentation Reference\n",
    ]

    # Official Documentation section
    if ref_content:
        sections.append(f"## Official Documentation\n\n{ref_content}")
    else:
        note = f"No documentation pre-fetched. Use `ref_search_documentation` to look up {library} docs."
        sections.append(f"## Official Documentation\n\n{note}")

    # Code Examples section
    if exa_content:
        sections.append(f"## Code Examples & Patterns\n\n{exa_content}")

    # Quick Reference section (always present)
    quick_ref = "## Quick Reference\n"
    if docs_url:
        quick_ref += f"\n- Docs: {docs_url}"
    if package:
        quick_ref += f"\n- Package: `{package}`"
    sections.append(quick_ref)

    # Further Reading fallback
    if not ref_content and not exa_content and docs_url:
        sections.append(f"## Further Reading\n\nSee the official documentation at {docs_url}")

    content = "\n\n".join(sections)

    # Enforce line limit — truncate exa content first, then ref content
    lines = content.split("\n")
    if len(lines) > MAX_SKILL_LINES and exa_content:
        # Remove exa section and rebuild
        content = _build_library_skill(library, ref_content, None)
        lines = content.split("\n")

    if len(lines) > MAX_SKILL_LINES:
        # Hard truncate with note
        lines = lines[:MAX_SKILL_LINES - 3]
        lines.append("")
        lines.append(f"*Content truncated. See full docs at {docs_url or 'the official documentation'}.*")
        content = "\n".join(lines)

    return content


# ---------------------------------------------------------------------------
# Library Skill Generator (Step 4)
# ---------------------------------------------------------------------------

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

    Returns list of generated skill names (slugs).
    """
    ref_key = ref_api_key or os.environ.get("REF_API_KEY")
    exa_key = exa_api_key or os.environ.get("EXA_API_KEY")

    if not ref_key and not exa_key:
        logger.info("[Library Skills] No API keys set (REF_API_KEY, EXA_API_KEY) — skipping")
        return []

    libraries = stack.all_libraries[:MAX_LIBRARY_SKILLS]
    if not libraries:
        return []

    logger.info("[Library Skills] Generating skills for: %s", ", ".join(libraries))

    # Fetch documentation in parallel with caching
    cache_path = project_dir / ".skill_docs_cache.json"
    docs = _fetch_all_library_docs(libraries, ref_key, exa_key, cache_path)

    skills_dir = project_dir / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    generated: list[str] = []

    for library in libraries:
        lib_docs = docs.get(library, {})
        ref_content = lib_docs.get("ref_content")
        exa_content = lib_docs.get("exa_content")

        # Skip if no content at all
        if not ref_content and not exa_content:
            logger.info("[Library Skills] No content for %s — skipping", library)
            continue

        slug = _slugify_library(library)
        skill_dir = skills_dir / slug
        skill_path = skill_dir / "SKILL.md"

        # Preserve user-created skills
        if skill_path.exists() and not _is_harness_generated(skill_path):
            logger.info(
                "[Library Skills] Skipping %s — exists and not harness-generated",
                slug,
            )
            continue

        # Build and write skill
        try:
            content = _build_library_skill(library, ref_content, exa_content)
        except Exception as e:
            logger.warning("[Library Skills] Failed to build %s: %s", slug, e)
            continue

        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(content)
        generated.append(slug)
        logger.info("[Library Skills] Generated %s", slug)

    return generated
