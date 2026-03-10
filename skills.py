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
