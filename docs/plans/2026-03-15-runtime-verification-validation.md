# Runtime Verification — Validation Report

**Date:** 2026-03-15
**Plan:** 2026-03-15-runtime-verification-plan.md

## Validation Results

### Check 1: Prompt Cross-References

**PASS** — All cross-references are consistent across the four files.

- **Coding prompt references "Test Steps" and "Runtime Guardrails"**: Confirmed. The coding prompt references both terms extensively (lines 59-60, 68, 74, 95, 97, 101, 119-120, 145, 250). These match the exact section headings defined in the epic initializer's Issue Format (lines 133 and 151).

- **Coding prompt references `mcp__puppeteer__puppeteer_*` tools**: Confirmed. The coding prompt uses `mcp__puppeteer__puppeteer_navigate`, `mcp__puppeteer__puppeteer_screenshot`, `mcp__puppeteer__puppeteer_click`, `mcp__puppeteer__puppeteer_fill`, and `mcp__puppeteer__puppeteer_select` (lines 37-38, 77-80). The MCP server is named "puppeteer" in discovery.py (line 681), which produces the `mcp__puppeteer__puppeteer_*` tool namespace. Consistent.

- **Epic writer's Testing Criteria mentions runtime-behavioural criteria**: Confirmed. The epic writer prompt requires "At least 2 criteria must be runtime-behavioural for UI-facing epics" (line 48) and explicitly states "These runtime criteria guide the Epic Initializer when writing Test Steps and Runtime Guardrails for individual issues" (lines 54-55). This establishes the pipeline: writer creates runtime criteria -> initializer uses them to write Test Steps and Runtime Guardrails -> coding agent follows them.

- **Initializer's `ref_search_documentation` instructions align with coding prompt**: Confirmed. The initializer generates Runtime Guardrails by calling `ref_search_documentation` (lines 152-155, 171-176, 182). The coding prompt instructs the agent to "Follow the Runtime Guardrails in the issue description" (line 68) and to call `ref_search_documentation` itself when needed (lines 64-65, 129-138). The initializer pre-fetches library docs into the guardrails; the coding agent can also look up docs at implementation time.

### Check 2: Discovery.py MCP Injection

**PASS** — All MCP injection details are correct.

- **Correct package name**: The Puppeteer server entry uses `puppeteer-mcp-server` (line 685). This was verified as a real, functional npm package in Task 5.

- **Server name matches SESSION_MCP_SCOPES**: The server is named `"puppeteer"` (line 681). SESSION_MCP_SCOPES for `"coding"` includes `"puppeteer"` (line 40). The `_filter_mcps_by_session` function does case-insensitive substring matching (line 609), so `"puppeteer"` in the scope list matches the `"puppeteer"` server name. Consistent.

- **"ref" scope added to "epic_initializer"**: Confirmed. SESSION_MCP_SCOPES has `"epic_initializer": ["linear", "ref"]` (line 39). This gives the initializer access to `ref_search_documentation` for generating Runtime Guardrails.

- **Correct transport configuration**: The Puppeteer MCP uses stdio transport with npx (lines 683-686): `"type": "stdio"`, `"command": "npx"`, `"args": ["-y", "puppeteer-mcp-server"]`. This is the standard pattern for MCP servers distributed as npm packages. The `-y` flag auto-confirms the npx install prompt.

### Check 3: No Contradictions

**PASS** — All old content that would contradict the new system has been removed.

- **"Never run npx playwright test on regular issues"**: Removed. Grep returns no matches. The new prompt correctly separates Playwright (snapshot/tagged issues only) from Puppeteer MCP (browser verification for all UI issues with Test Steps).

- **"Never install Playwright during regular issues"**: Removed. Grep returns no matches. Playwright installation is now scoped to snapshot issues (line 156) and tagged issues.

- **"Clean State Rule"**: Removed. Replaced with "Quality Bar" section (line 303) which defines production-quality standards: zero console errors, all features work end-to-end, no visual glitches, no uncommitted changes, no failing tests.

- **Single-paragraph Implementation Loop replaced with 9-step version**: Confirmed. The Implementation Loop (lines 55-111) now has 9 clearly numbered steps: Read issue -> Look up docs -> Implement -> Verify build -> Verify in browser -> Fix and re-verify -> Commit -> Update Linear -> Move to next issue.

- **Old "Issue Quality Rules" replaced with "Issue Format"**: Confirmed. The epic initializer now has a formal "Issue Format" section (line 108) with a structured template including Feature Description, Category, Implementation Notes, Test Steps, Runtime Guardrails, and Acceptance Criteria.

### Check 4: Section Ordering

**PASS** — All prompt files have logical section ordering with no forward references.

**coding_prompt.md** flow:

1. Session Startup — what to do first (includes regression check using Puppeteer)
2. Implementation Loop — the main workflow (references Test Steps and Runtime Guardrails which come from the issue)
3. Session Completion — when to stop
4. Ref Documentation Usage — supplementary guidance
5. Testing Rules — when to use Playwright vs browser verification
6. The Snapshot Issue — special issue handling
7. The Human Gate Issue — special issue handling
8. Anti-Patterns — things to never do
9. Runtime Quality Rules — always-on code quality standards
10. V1 Mode Limitation — edge case note
11. Quality Bar — overall standard

The Implementation Loop references "Test Steps" and "Runtime Guardrails" — these come from the Linear issue description (injected by the harness), not from later sections of this prompt. No forward references within the prompt itself.

**epic_initializer_prompt.md** flow:

1. Context Files — what's injected
2. Linear Structure — project/issue creation order
3. Issue Sizing — how to group features
4. Issue Format — the template for issues (defines Test Steps and Runtime Guardrails)
5. Generating Runtime Guardrails — detailed process for using ref_search_documentation
6. Linear Issue Format Examples — concrete examples
7. What You Must NOT Do — constraints
8. Pre-Commit Setup — .gitignore
9. After Creating Issues — final steps

Issue Format (section 4) defines the template before Generating Runtime Guardrails (section 5) explains the process — logical order (what, then how).

**epic_writer_prompt.md** flow:

1. Your Output — what to write
2. Writing Rules — constraints
3. Using Ref and Exa — research tools
4. Quality Check — final verification

Testing Criteria in the template (section 1) references runtime-behavioural criteria and mentions the Epic Initializer — this is a forward-looking instruction for output, not a forward reference within the prompt. Correct.

### Check 5: Python Syntax

**PASS** — `python3 -c "import ast; ast.parse(open('discovery.py').read())"` completed successfully. discovery.py is syntactically valid Python.

## Manual Validation Required

The following checks require running the harness with a real project:

1. Epic writer produces spec with runtime testing criteria (at least 2 runtime-behavioural criteria for UI-facing epics)
2. Epic initializer calls `ref_search_documentation` and generates Runtime Guardrails for each feature issue
3. Coding agent follows Test Steps with Puppeteer MCP (navigate, click, screenshot, check console errors)
4. Regression check at session startup catches intentional bugs via Puppeteer
5. Browser verification catches console errors, subscription churn, and visual glitches
6. Session-scoped MCP filtering correctly loads Puppeteer only for coding sessions (not architect, epic_writer, etc.)
7. The Puppeteer MCP server starts successfully via npx in the harness environment

## Summary

**All 5 automated checks PASS.** The implementation across the four files is internally consistent:

- The prompt pipeline flows correctly: epic writer defines runtime testing criteria -> epic initializer uses those criteria plus `ref_search_documentation` to generate Test Steps and Runtime Guardrails -> coding agent follows those sections using Puppeteer MCP for browser verification.
- The MCP infrastructure is correctly wired: discovery.py injects the Puppeteer server with the right package name and transport, SESSION_MCP_SCOPES ensures it's available in coding sessions, and the coding prompt references the correct tool namespace.
- All contradictory legacy content has been removed.
- Section ordering is logical across all prompt files.
- Python syntax is valid.

No issues found. Ready for manual integration testing with a real project.
