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
import re
from dataclasses import dataclass, field
from pathlib import Path

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
