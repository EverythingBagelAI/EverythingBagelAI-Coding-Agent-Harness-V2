"""Tests for _extract_skill_description() fallback logic."""

from pathlib import Path

import pytest

from discovery import _extract_skill_description


class TestExtractSkillDescriptionFrontmatter:
    """YAML frontmatter extraction — existing behaviour preserved."""

    def test_extracts_description_from_skill_md_frontmatter(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A useful skill for testing.\n---\n\n# My Skill\n"
        )
        assert _extract_skill_description(skill_dir) == "A useful skill for testing."

    def test_extracts_description_from_claude_md_frontmatter(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "CLAUDE.md").write_text(
            "---\nname: my-skill\ndescription: From CLAUDE.md frontmatter.\n---\n\n# Skill\n"
        )
        assert _extract_skill_description(skill_dir) == "From CLAUDE.md frontmatter."

    def test_extracts_description_from_readme_frontmatter(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "README.md").write_text(
            "---\nname: my-skill\ndescription: From README frontmatter.\n---\n\n# Skill\n"
        )
        assert _extract_skill_description(skill_dir) == "From README frontmatter."

    def test_skill_md_takes_priority_over_claude_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: From SKILL.md.\n---\n\n# Skill\n"
        )
        (skill_dir / "CLAUDE.md").write_text(
            "---\nname: my-skill\ndescription: From CLAUDE.md.\n---\n\n# Skill\n"
        )
        assert _extract_skill_description(skill_dir) == "From SKILL.md."

    def test_truncates_long_descriptions(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        long_desc = "A" * 250
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: my-skill\ndescription: {long_desc}\n---\n\n# Skill\n"
        )
        result = _extract_skill_description(skill_dir)
        assert len(result) == 203  # 200 + "..."
        assert result.endswith("...")

    def test_skips_multiline_description_markers(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: |\n  multi-line content\n---\n\n# Skill\n"
        )
        result = _extract_skill_description(skill_dir)
        assert result != "|"
        assert result != ">"


class TestExtractSkillDescriptionParagraphFallback:
    """First-paragraph-after-heading fallback."""

    def test_extracts_first_paragraph_when_no_frontmatter(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "README.md").write_text(
            "# My Skill\n\nThis skill does something useful for developers.\n\n## Usage\n"
        )
        assert _extract_skill_description(skill_dir) == "This skill does something useful for developers."

    def test_joins_multiline_paragraph(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "README.md").write_text(
            "# My Skill\n\nFirst line of description.\nSecond line continues.\n\n## Details\n"
        )
        assert _extract_skill_description(skill_dir) == "First line of description. Second line continues."

    def test_skips_badges_and_images(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "README.md").write_text(
            "# My Skill\n\n[![Build](https://img.shields.io/badge)]\n\nActual description here.\n\n## More\n"
        )
        assert _extract_skill_description(skill_dir) == "Actual description here."

    def test_truncates_long_paragraph(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        long_para = "Word " * 60  # ~300 chars
        (skill_dir / "README.md").write_text(f"# Skill\n\n{long_para.strip()}\n\n## More\n")
        result = _extract_skill_description(skill_dir)
        assert len(result) <= 203


class TestExtractSkillDescriptionEdgeCases:
    """Edge cases and error handling."""

    def test_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()
        assert _extract_skill_description(skill_dir) == ""

    def test_nonexistent_directory_returns_empty(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "nonexistent"
        assert _extract_skill_description(skill_dir) == ""

    def test_file_with_no_heading_returns_empty(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "README.md").write_text("Just some text without a heading.\n")
        assert _extract_skill_description(skill_dir) == ""

    def test_frontmatter_with_quoted_description(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: my-skill\ndescription: "A quoted description."\n---\n\n# Skill\n'
        )
        assert _extract_skill_description(skill_dir) == "A quoted description."

    def test_frontmatter_with_single_quoted_description(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: 'Single quoted.'\n---\n\n# Skill\n"
        )
        assert _extract_skill_description(skill_dir) == "Single quoted."
