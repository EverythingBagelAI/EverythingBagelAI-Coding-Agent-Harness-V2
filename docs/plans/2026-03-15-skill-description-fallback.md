# Skill Description Fallback Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `_extract_skill_description()` try multiple files (SKILL.md, CLAUDE.md, README.md) and fall back to first-paragraph extraction when no YAML frontmatter exists.

**Architecture:** Change the function signature from accepting a specific file path to accepting a skill directory. Try candidate files in priority order, with two extraction strategies per file (YAML frontmatter, then first paragraph after heading).

**Tech Stack:** Python 3.11+, pytest

---

### Task 1: Write failing tests for YAML frontmatter extraction from SKILL.md

**Files:**

- Create: `tests/test_extract_skill_description.py`

**Step 1: Write the failing tests**

```python
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
        # "|" is a YAML multiline marker — function should skip it and try paragraph fallback
        # Since SKILL.md has a heading, it should extract "multi-line content" as paragraph
        # Actually the current logic returns "" for "|" — the new fallback will pick up the heading paragraph
        result = _extract_skill_description(skill_dir)
        # No paragraph after heading in this file, so empty is acceptable
        # The key test is that it doesn't return "|"
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
```

**Step 2: Run tests to verify they fail**

Run: `cd "/Users/jordanheap/Coding Projects/EverythingBagelAI-Coding-Agent-Harness-V2" && python -m pytest tests/test_extract_skill_description.py -v`
Expected: FAIL — `_extract_skill_description` takes `skill_md: Path` not `skill_dir: Path`, and lacks paragraph fallback

---

### Task 2: Rewrite `_extract_skill_description()` with fallback logic

**Files:**

- Modify: `discovery.py:270-287`

**Step 1: Replace the function**

Replace lines 270-287 with:

````python
def _extract_skill_description(skill_dir: Path) -> str:
    """
    Extract description from a skill directory.

    Tries files in order: SKILL.md, CLAUDE.md, README.md
    For each file, tries:
      1. YAML frontmatter `description:` field
      2. First paragraph after # heading

    Returns empty string if nothing found.
    """
    candidates = ["SKILL.md", "CLAUDE.md", "README.md"]

    for filename in candidates:
        filepath = skill_dir / filename
        if not filepath.is_file():
            continue

        try:
            content = filepath.read_text(errors="replace")
        except (IOError, PermissionError):
            continue

        # Try 1: YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].splitlines():
                    stripped = line.strip()
                    if stripped.startswith("description:"):
                        desc = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                        if desc and desc not in ("|", ">"):
                            return desc[:200] + "..." if len(desc) > 200 else desc

        # Try 2: First paragraph after # heading
        lines = content.splitlines()
        found_heading = False
        paragraph_lines: list[str] = []

        for line in lines:
            if line.strip() == "---":
                continue

            if not found_heading:
                if line.startswith("# "):
                    found_heading = True
                continue

            stripped = line.strip()
            if stripped:
                if stripped.startswith(("[", "<", "!", "```")):
                    continue
                paragraph_lines.append(stripped)
            elif paragraph_lines:
                break

        if paragraph_lines:
            desc = " ".join(paragraph_lines)
            return desc[:200] + "..." if len(desc) > 200 else desc

    return ""
````

**Step 2: Run tests to verify they pass**

Run: `cd "/Users/jordanheap/Coding Projects/EverythingBagelAI-Coding-Agent-Harness-V2" && python -m pytest tests/test_extract_skill_description.py -v`
Expected: All PASS

---

### Task 3: Update the caller in `load_user_skills()`

**Files:**

- Modify: `discovery.py:304`

**Step 1: Change the call site**

Replace:

```python
description = _extract_skill_description(entry / "SKILL.md")
```

With:

```python
description = _extract_skill_description(entry)
```

**Step 2: Run full test suite**

Run: `cd "/Users/jordanheap/Coding Projects/EverythingBagelAI-Coding-Agent-Harness-V2" && python -m pytest tests/test_extract_skill_description.py test_skills.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add discovery.py tests/test_extract_skill_description.py
git commit -m "feat: add fallback file and paragraph extraction to skill description discovery"
```
