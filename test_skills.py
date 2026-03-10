"""
Skill Generation Tests
======================

Tests for tech stack detection, skill generation, idempotency,
and brownfield handling.
"""

import json
import textwrap
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from skills import (
    GENERATED_MARKER,
    MAX_LIBRARY_SKILLS,
    SKILL_DOCS_CACHE_TTL,
    TechStack,
    _build_code_review_skill,
    _build_deployment_check_skill,
    _build_library_skill,
    _build_linear_workflow_skill,
    _build_project_reference_skill,
    _build_test_runner_skill,
    _is_harness_generated,
    _slugify_library,
    detect_tech_stack,
    generate_library_skills,
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


# ---------------------------------------------------------------------------
# generate_library_skills() tests
# ---------------------------------------------------------------------------

def _mock_ref_response(content: str = "# API Reference\n\nSample documentation.") -> httpx.Response:
    """Build a mock Ref API response."""
    return httpx.Response(
        200,
        json={"results": [{"content": content}]},
        request=httpx.Request("GET", "https://api.ref.tools/v1/search"),
    )


def _mock_exa_response(
    title: str = "Example",
    url: str = "https://example.com",
    highlights: list[str] | None = None,
) -> httpx.Response:
    """Build a mock Exa API response."""
    return httpx.Response(
        200,
        json={
            "results": [
                {
                    "title": title,
                    "url": url,
                    "text": "Full text content",
                    "highlights": highlights or ["Highlight snippet one.", "Highlight snippet two."],
                }
            ]
        },
        request=httpx.Request("POST", "https://api.exa.ai/search"),
    )


class TestGenerateLibrarySkills:
    """Tests for per-library documentation skill generation."""

    def _make_stack(self, libraries: list[str] | None = None) -> TechStack:
        return TechStack(
            frontend_framework="nextjs",
            backend_framework="fastapi",
            all_libraries=libraries or ["Next.js", "Clerk", "FastAPI"],
        )

    @patch("skills.httpx.get", return_value=_mock_ref_response())
    @patch("skills.httpx.post", return_value=_mock_exa_response())
    def test_generates_skills_for_detected_libraries(
        self, mock_post, mock_get, tmp_project: Path
    ) -> None:
        """With mocked API responses, generates one skill per library."""
        stack = self._make_stack()
        generated = generate_library_skills(
            tmp_project, stack, ref_api_key="test-ref", exa_api_key="test-exa"
        )
        assert len(generated) == 3
        assert "nextjs-docs" in generated
        assert "clerk-docs" in generated
        assert "fastapi-docs" in generated

        # Verify files exist
        for slug in generated:
            skill_path = tmp_project / ".claude" / "skills" / slug / "SKILL.md"
            assert skill_path.exists()
            content = skill_path.read_text()
            assert GENERATED_MARKER in content
            assert "---" in content  # frontmatter

    def test_graceful_degradation_no_api_keys(self, tmp_project: Path) -> None:
        """Returns empty list when no API keys are set."""
        stack = self._make_stack()
        with patch.dict("os.environ", {}, clear=True):
            generated = generate_library_skills(tmp_project, stack)
        assert generated == []

    @patch("skills.httpx.get", return_value=_mock_ref_response())
    @patch("skills.httpx.post", return_value=_mock_exa_response())
    def test_respects_harness_marker(
        self, mock_post, mock_get, tmp_project: Path
    ) -> None:
        """Overwrites harness-generated, preserves user-created."""
        stack = self._make_stack(["Next.js"])

        # Create a user-created skill (no marker)
        user_dir = tmp_project / ".claude" / "skills" / "nextjs-docs"
        user_dir.mkdir(parents=True, exist_ok=True)
        user_content = "---\nname: nextjs-docs\ndescription: My custom docs.\n---\n\n# My Docs\n"
        (user_dir / "SKILL.md").write_text(user_content)

        generated = generate_library_skills(
            tmp_project, stack, ref_api_key="test-ref", exa_api_key="test-exa"
        )
        assert "nextjs-docs" not in generated
        assert (user_dir / "SKILL.md").read_text() == user_content

    @patch("skills.httpx.get", return_value=_mock_ref_response())
    @patch("skills.httpx.post", return_value=_mock_exa_response())
    def test_skill_under_500_lines(
        self, mock_post, mock_get, tmp_project: Path
    ) -> None:
        """Generated library skills stay under 500 lines."""
        stack = self._make_stack()
        generated = generate_library_skills(
            tmp_project, stack, ref_api_key="test-ref", exa_api_key="test-exa"
        )
        for slug in generated:
            content = (tmp_project / ".claude" / "skills" / slug / "SKILL.md").read_text()
            line_count = content.count("\n") + 1
            assert line_count <= 500, f"{slug} has {line_count} lines"

    @patch("skills.httpx.get", return_value=_mock_ref_response())
    @patch("skills.httpx.post", return_value=_mock_exa_response())
    def test_caching_prevents_refetch(
        self, mock_post, mock_get, tmp_project: Path
    ) -> None:
        """Second call uses cache instead of hitting APIs."""
        stack = self._make_stack(["Next.js"])

        # First call — hits APIs
        generate_library_skills(
            tmp_project, stack, ref_api_key="test-ref", exa_api_key="test-exa"
        )
        first_call_count = mock_get.call_count + mock_post.call_count

        # Reset call counts
        mock_get.reset_mock()
        mock_post.reset_mock()

        # Second call — should use cache
        generate_library_skills(
            tmp_project, stack, ref_api_key="test-ref", exa_api_key="test-exa"
        )
        second_call_count = mock_get.call_count + mock_post.call_count
        assert second_call_count == 0, f"Expected 0 API calls on second run, got {second_call_count}"

    @patch("skills.httpx.get", return_value=_mock_ref_response())
    @patch("skills.httpx.post", return_value=_mock_exa_response())
    def test_library_cap_at_15(
        self, mock_post, mock_get, tmp_project: Path
    ) -> None:
        """No more than 15 library skills generated."""
        # Create a stack with 20 libraries
        libs = [f"Lib{i}" for i in range(20)]
        stack = self._make_stack(libs)
        generated = generate_library_skills(
            tmp_project, stack, ref_api_key="test-ref", exa_api_key="test-exa"
        )
        assert len(generated) <= MAX_LIBRARY_SKILLS

    @patch("skills.httpx.get", return_value=_mock_ref_response())
    @patch("skills.httpx.post", return_value=_mock_exa_response())
    def test_fallback_queries_for_unknown_libraries(
        self, mock_post, mock_get, tmp_project: Path
    ) -> None:
        """Libraries not in _LIBRARY_SEARCH_QUERIES get sensible defaults."""
        stack = self._make_stack(["SomeObscureLib"])
        generated = generate_library_skills(
            tmp_project, stack, ref_api_key="test-ref", exa_api_key="test-exa"
        )
        assert len(generated) == 1
        slug = generated[0]
        assert slug == "someobscurelib-docs"

        content = (tmp_project / ".claude" / "skills" / slug / "SKILL.md").read_text()
        assert "SomeObscureLib" in content
        assert GENERATED_MARKER in content


class TestBuildLibrarySkill:
    """Tests for the library skill assembler."""

    def test_valid_frontmatter(self) -> None:
        content = _build_library_skill("Next.js", "Some docs", "Some examples")
        lines = content.strip().split("\n")
        assert lines[0] == "---"
        assert "name: nextjs-docs" in content
        assert "description:" in content

    def test_has_marker(self) -> None:
        content = _build_library_skill("Clerk", "Docs content", None)
        assert GENERATED_MARKER in content

    def test_ref_only(self) -> None:
        content = _build_library_skill("FastAPI", "API reference text", None)
        assert "Official Documentation" in content
        assert "API reference text" in content
        assert "Code Examples" not in content

    def test_exa_only(self) -> None:
        content = _build_library_skill("Stripe", None, "Code example text")
        assert "No documentation pre-fetched" in content
        assert "Code Examples & Patterns" in content
        assert "Code example text" in content

    def test_quick_reference_section(self) -> None:
        content = _build_library_skill("Supabase", "Docs", None)
        assert "Quick Reference" in content
        assert "supabase.com/docs" in content

    def test_under_500_lines_with_large_content(self) -> None:
        large_ref = "Line of documentation.\n" * 600
        content = _build_library_skill("Next.js", large_ref, "Some examples")
        line_count = content.count("\n") + 1
        assert line_count <= 500


class TestSlugifyLibrary:
    """Tests for library name slugification."""

    def test_known_library(self) -> None:
        assert _slugify_library("Next.js") == "nextjs-docs"

    def test_unknown_library(self) -> None:
        assert _slugify_library("MyCustomLib") == "mycustomlib-docs"

    def test_library_with_spaces(self) -> None:
        assert _slugify_library("React Native") == "react-native-docs"

    def test_library_with_dots(self) -> None:
        assert _slugify_library("Auth.js") == "authjs-docs"
