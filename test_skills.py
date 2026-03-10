"""
Skill Generation Tests
======================

Tests for tech stack detection, skill generation, idempotency,
and brownfield handling.
"""

import json
import textwrap
from pathlib import Path

import pytest

from skills import (
    GENERATED_MARKER,
    TechStack,
    _build_code_review_skill,
    _build_deployment_check_skill,
    _build_linear_workflow_skill,
    _build_project_reference_skill,
    _build_test_runner_skill,
    _is_harness_generated,
    detect_tech_stack,
    generate_project_skills,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NEXTJS_FASTAPI_SPEC = textwrap.dedent("""\
    # MyApp

    ## Tech Stack
    - Frontend: Next.js 15 with Tailwind CSS and shadcn/ui
    - Auth: Clerk
    - Backend: FastAPI
    - Database: Supabase
    - Deployment: Vercel (frontend), Render (backend)
    - Payments: Stripe
""")

MINIMAL_SPEC = "A simple app."

REACT_ONLY_SPEC = textwrap.dedent("""\
    # React App
    Built with React and Tailwind CSS.
    Uses Zustand for state management.
""")


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal temp project directory."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def brownfield_project(tmp_path: Path) -> Path:
    """Create a brownfield project with package.json and requirements.txt."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)

    package_json = {
        "dependencies": {
            "next": "15.0.0",
            "@clerk/nextjs": "^5.0.0",
            "@supabase/supabase-js": "^2.0.0",
            "tailwindcss": "^3.0.0",
            "stripe": "^14.0.0",
        },
        "devDependencies": {
            "vitest": "^1.0.0",
            "@playwright/test": "^1.40.0",
        },
    }
    (tmp_path / "package.json").write_text(json.dumps(package_json))

    requirements = "fastapi==0.110.0\nuvicorn==0.27.0\nsupabase==2.0.0\nstripe==8.0.0\n"
    (tmp_path / "requirements.txt").write_text(requirements)

    (tmp_path / "next.config.ts").write_text("export default {};")
    (tmp_path / "tailwind.config.ts").write_text("export default {};")

    return tmp_path


# ---------------------------------------------------------------------------
# detect_tech_stack() tests
# ---------------------------------------------------------------------------

class TestDetectTechStack:
    """Tests for tech stack detection."""

    def test_nextjs_fastapi_full_stack(self, tmp_project: Path) -> None:
        stack = detect_tech_stack(NEXTJS_FASTAPI_SPEC, tmp_project)
        assert stack.frontend_framework == "nextjs"
        assert stack.backend_framework == "fastapi"
        assert stack.database == "supabase"
        assert stack.auth_provider == "clerk"
        assert stack.frontend_deploy == "vercel"
        assert stack.backend_deploy == "render"
        assert "tailwind" in stack.styling
        assert "stripe" in stack.integrations

    def test_minimal_spec_returns_defaults(self, tmp_project: Path) -> None:
        stack = detect_tech_stack(MINIMAL_SPEC, tmp_project)
        assert stack.frontend_framework is None
        assert stack.backend_framework is None
        assert stack.frontend_test_runner == "vitest"
        assert stack.e2e_test_runner == "playwright"
        assert stack.backend_test_runner == "pytest"

    def test_react_only(self, tmp_project: Path) -> None:
        stack = detect_tech_stack(REACT_ONLY_SPEC, tmp_project)
        assert stack.frontend_framework in ("react-vite", "nextjs")
        assert "tailwind" in stack.styling
        assert stack.state_management == "zustand"

    def test_brownfield_package_json_detection(self, brownfield_project: Path) -> None:
        stack = detect_tech_stack("", brownfield_project, mode="brownfield")
        assert stack.frontend_framework == "nextjs"
        assert stack.auth_provider == "clerk"
        assert stack.database == "supabase"
        assert "tailwind" in stack.styling
        assert "stripe" in stack.integrations

    def test_brownfield_python_deps_detection(self, brownfield_project: Path) -> None:
        stack = detect_tech_stack("", brownfield_project, mode="brownfield")
        assert stack.backend_framework == "fastapi"

    def test_brownfield_config_files(self, brownfield_project: Path) -> None:
        stack = detect_tech_stack("", brownfield_project, mode="brownfield")
        # next.config.ts and tailwind.config.ts exist in fixture
        assert stack.frontend_framework == "nextjs"
        assert "tailwind" in stack.styling

    def test_codebase_wins_over_spec(self, brownfield_project: Path) -> None:
        """Codebase detection has priority over spec text."""
        # Spec says Vue, but codebase has Next.js
        stack = detect_tech_stack("Built with Vue.js", brownfield_project, mode="brownfield")
        assert stack.frontend_framework == "nextjs"  # codebase wins

    def test_all_libraries_populated(self, tmp_project: Path) -> None:
        stack = detect_tech_stack(NEXTJS_FASTAPI_SPEC, tmp_project)
        assert len(stack.all_libraries) > 0
        # At least the major ones should be detected
        libs_lower = [lib.lower() for lib in stack.all_libraries]
        assert any("next" in l for l in libs_lower)
        assert any("fastapi" in l for l in libs_lower)


# ---------------------------------------------------------------------------
# Skill builder tests
# ---------------------------------------------------------------------------

class TestSkillBuilders:
    """Tests for individual skill builder functions."""

    def _parse_frontmatter(self, content: str) -> dict:
        """Extract YAML frontmatter from SKILL.md content."""
        lines = content.strip().split("\n")
        assert lines[0] == "---", "SKILL.md must start with ---"
        end_idx = lines.index("---", 1)
        frontmatter = {}
        for line in lines[1:end_idx]:
            key, _, value = line.partition(": ")
            frontmatter[key.strip()] = value.strip()
        return frontmatter

    def _make_ctx(self, **kwargs) -> dict:
        return {"mode": "greenfield", "is_epic": False, "project_dir": "/tmp/test", **kwargs}

    def _full_stack(self) -> TechStack:
        return TechStack(
            frontend_framework="nextjs",
            backend_framework="fastapi",
            database="supabase",
            auth_provider="clerk",
            styling=["tailwind"],
            ui_libraries=["shadcn"],
            integrations=["stripe"],
            ai_libraries=["langchain"],
            frontend_deploy="vercel",
            backend_deploy="render",
        )

    def test_test_runner_valid_frontmatter(self) -> None:
        content = _build_test_runner_skill(self._full_stack(), self._make_ctx())
        fm = self._parse_frontmatter(content)
        assert fm["name"] == "test-runner"
        assert "description" in fm
        assert len(fm["description"]) <= 1024

    def test_test_runner_under_500_lines(self) -> None:
        content = _build_test_runner_skill(self._full_stack(), self._make_ctx())
        assert content.count("\n") < 500

    def test_test_runner_has_marker(self) -> None:
        content = _build_test_runner_skill(self._full_stack(), self._make_ctx())
        assert GENERATED_MARKER in content

    def test_test_runner_includes_frontend_section(self) -> None:
        content = _build_test_runner_skill(self._full_stack(), self._make_ctx())
        assert "Vitest" in content
        assert "React Testing Library" in content

    def test_test_runner_includes_backend_section(self) -> None:
        content = _build_test_runner_skill(self._full_stack(), self._make_ctx())
        assert "pytest" in content
        assert "httpx" in content

    def test_test_runner_no_frontend_when_missing(self) -> None:
        stack = TechStack(backend_framework="fastapi")
        content = _build_test_runner_skill(stack, self._make_ctx())
        assert "Vitest" not in content
        assert "pytest" in content

    def test_code_review_valid_frontmatter(self) -> None:
        content = _build_code_review_skill(self._full_stack(), self._make_ctx())
        fm = self._parse_frontmatter(content)
        assert fm["name"] == "code-review"
        assert len(fm["description"]) <= 1024

    def test_code_review_under_500_lines(self) -> None:
        content = _build_code_review_skill(self._full_stack(), self._make_ctx())
        assert content.count("\n") < 500

    def test_code_review_includes_nextjs_checks(self) -> None:
        content = _build_code_review_skill(self._full_stack(), self._make_ctx())
        assert "Server Components" in content
        assert "App Router" in content

    def test_code_review_includes_fastapi_checks(self) -> None:
        content = _build_code_review_skill(self._full_stack(), self._make_ctx())
        assert "Pydantic V2" in content
        assert "async def" in content

    def test_code_review_includes_clerk_checks(self) -> None:
        content = _build_code_review_skill(self._full_stack(), self._make_ctx())
        assert "clerkMiddleware" in content

    def test_code_review_includes_supabase_checks(self) -> None:
        content = _build_code_review_skill(self._full_stack(), self._make_ctx())
        assert "RLS" in content

    def test_code_review_includes_stripe_checks(self) -> None:
        content = _build_code_review_skill(self._full_stack(), self._make_ctx())
        assert "Stripe" in content or "webhook" in content.lower()

    def test_code_review_includes_langchain_checks(self) -> None:
        content = _build_code_review_skill(self._full_stack(), self._make_ctx())
        assert "LCEL" in content
        assert "LLMChain" in content

    def test_project_reference_valid_frontmatter(self) -> None:
        content = _build_project_reference_skill(self._full_stack(), self._make_ctx())
        fm = self._parse_frontmatter(content)
        assert fm["name"] == "project-reference"

    def test_project_reference_under_500_lines(self) -> None:
        content = _build_project_reference_skill(self._full_stack(), self._make_ctx())
        assert content.count("\n") < 500

    def test_project_reference_epic_mode(self) -> None:
        content = _build_project_reference_skill(
            self._full_stack(), self._make_ctx(is_epic=True)
        )
        assert "spec_index.md" in content

    def test_project_reference_standard_mode(self) -> None:
        content = _build_project_reference_skill(
            self._full_stack(), self._make_ctx(is_epic=False)
        )
        assert "app_spec.txt" in content

    def test_deployment_check_valid_frontmatter(self) -> None:
        content = _build_deployment_check_skill(self._full_stack(), self._make_ctx())
        fm = self._parse_frontmatter(content)
        assert fm["name"] == "deployment-check"

    def test_deployment_check_under_500_lines(self) -> None:
        content = _build_deployment_check_skill(self._full_stack(), self._make_ctx())
        assert content.count("\n") < 500

    def test_deployment_check_env_vars(self) -> None:
        content = _build_deployment_check_skill(self._full_stack(), self._make_ctx())
        assert "CLERK_SECRET_KEY" in content
        assert "SUPABASE" in content
        assert "STRIPE" in content

    def test_linear_workflow_valid_frontmatter(self) -> None:
        content = _build_linear_workflow_skill(self._full_stack(), self._make_ctx())
        fm = self._parse_frontmatter(content)
        assert fm["name"] == "linear-workflow"

    def test_linear_workflow_under_500_lines(self) -> None:
        content = _build_linear_workflow_skill(self._full_stack(), self._make_ctx())
        assert content.count("\n") < 500

    def test_linear_workflow_has_snapshot_section(self) -> None:
        content = _build_linear_workflow_skill(self._full_stack(), self._make_ctx())
        assert "[SNAPSHOT]" in content

    def test_linear_workflow_has_human_gate_section(self) -> None:
        content = _build_linear_workflow_skill(self._full_stack(), self._make_ctx())
        assert "[HUMAN GATE]" in content


# ---------------------------------------------------------------------------
# generate_project_skills() end-to-end tests
# ---------------------------------------------------------------------------

class TestGenerateProjectSkills:
    """End-to-end tests for skill generation."""

    def test_generates_all_five_skills(self, tmp_project: Path) -> None:
        generated = generate_project_skills(tmp_project, NEXTJS_FASTAPI_SPEC)
        assert len(generated) == 5
        assert "test-runner" in generated
        assert "code-review" in generated
        assert "project-reference" in generated
        assert "deployment-check" in generated
        assert "linear-workflow" in generated

    def test_creates_skill_files(self, tmp_project: Path) -> None:
        generate_project_skills(tmp_project, NEXTJS_FASTAPI_SPEC)
        skills_dir = tmp_project / ".claude" / "skills"
        for name in ("test-runner", "code-review", "project-reference", "deployment-check", "linear-workflow"):
            assert (skills_dir / name / "SKILL.md").exists()

    def test_creates_references_dir(self, tmp_project: Path) -> None:
        generate_project_skills(tmp_project, NEXTJS_FASTAPI_SPEC)
        assert (tmp_project / ".claude" / "skills" / "project-reference" / "references").is_dir()

    def test_idempotent_overwrite(self, tmp_project: Path) -> None:
        """Running twice overwrites harness-generated skills without error."""
        generate_project_skills(tmp_project, NEXTJS_FASTAPI_SPEC)
        first_content = (tmp_project / ".claude" / "skills" / "test-runner" / "SKILL.md").read_text()
        generate_project_skills(tmp_project, NEXTJS_FASTAPI_SPEC)
        second_content = (tmp_project / ".claude" / "skills" / "test-runner" / "SKILL.md").read_text()
        assert first_content == second_content

    def test_preserves_user_created_skills(self, tmp_project: Path) -> None:
        """User-created skills (without harness marker) are not overwritten."""
        skill_dir = tmp_project / ".claude" / "skills" / "test-runner"
        skill_dir.mkdir(parents=True, exist_ok=True)
        user_content = "---\nname: test-runner\ndescription: My custom test runner.\n---\n\n# My Tests\n"
        (skill_dir / "SKILL.md").write_text(user_content)

        generated = generate_project_skills(tmp_project, NEXTJS_FASTAPI_SPEC)
        assert "test-runner" not in generated
        assert (skill_dir / "SKILL.md").read_text() == user_content

    def test_overwrites_harness_generated_skills(self, tmp_project: Path) -> None:
        """Harness-generated skills (with marker) are overwritten."""
        skill_dir = tmp_project / ".claude" / "skills" / "test-runner"
        skill_dir.mkdir(parents=True, exist_ok=True)
        old_content = f"---\nname: test-runner\ndescription: Old.\n---\n{GENERATED_MARKER}\n\n# Old\n"
        (skill_dir / "SKILL.md").write_text(old_content)

        generated = generate_project_skills(tmp_project, NEXTJS_FASTAPI_SPEC)
        assert "test-runner" in generated
        new_content = (skill_dir / "SKILL.md").read_text()
        assert new_content != old_content
        assert GENERATED_MARKER in new_content

    def test_brownfield_with_codebase(self, brownfield_project: Path) -> None:
        """Brownfield mode detects stack from package.json and requirements.txt."""
        generated = generate_project_skills(
            brownfield_project, "", mode="brownfield"
        )
        assert len(generated) == 5

        # Verify the test-runner skill contains Next.js-specific patterns
        content = (brownfield_project / ".claude" / "skills" / "test-runner" / "SKILL.md").read_text()
        assert "Vitest" in content
        assert "pytest" in content

    def test_minimal_spec_still_generates(self, tmp_project: Path) -> None:
        """Even a minimal spec generates all 5 skills (with generic content)."""
        generated = generate_project_skills(tmp_project, MINIMAL_SPEC)
        assert len(generated) == 5

    def test_all_skills_under_500_lines(self, tmp_project: Path) -> None:
        """Every generated skill is under 500 lines."""
        generate_project_skills(tmp_project, NEXTJS_FASTAPI_SPEC)
        skills_dir = tmp_project / ".claude" / "skills"
        for name in ("test-runner", "code-review", "project-reference", "deployment-check", "linear-workflow"):
            content = (skills_dir / name / "SKILL.md").read_text()
            line_count = content.count("\n")
            assert line_count < 500, f"{name} has {line_count} lines (max 500)"


# ---------------------------------------------------------------------------
# _is_harness_generated() tests
# ---------------------------------------------------------------------------

class TestIsHarnessGenerated:
    """Tests for harness marker detection."""

    def test_returns_true_for_marked_file(self, tmp_path: Path) -> None:
        path = tmp_path / "SKILL.md"
        path.write_text(f"---\nname: test\n---\n{GENERATED_MARKER}\n\n# Test")
        assert _is_harness_generated(path) is True

    def test_returns_false_for_unmarked_file(self, tmp_path: Path) -> None:
        path = tmp_path / "SKILL.md"
        path.write_text("---\nname: test\n---\n\n# Test")
        assert _is_harness_generated(path) is False

    def test_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.md"
        assert _is_harness_generated(path) is False
