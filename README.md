# EverythingBagelAI Coding Agent Harness V2

**Autonomous multi-epic coding harness built on the Claude Agent SDK.**

This harness turns a written spec into a working codebase by decomposing it into ordered epics, creating Linear issues for each one, and running Claude coding sessions until every issue is resolved. It maintains architectural context across epics so later work builds correctly on earlier decisions, and pauses at human gates when manual setup is needed. Built on [Anthropic's two-agent pattern](https://github.com/anthropics/claude-agent-sdk-demos) and [Cole Medin's Linear Coding Agent Harness](https://github.com/coleam00/Linear-Coding-Agent-Harness).

---

## How It Works

**V1 mode (Greenfield/Brownfield)** is a single-loop agent. Give it a spec and a project directory (greenfield) or point it at an existing codebase (brownfield), and it creates Linear issues then works through them one at a time. Simple, direct, good for smaller projects that fit in a single build sequence.

**V2 mode (Epic)** is a multi-stage pipeline for larger projects. An Architect agent reads your master spec and decomposes it into 4–7 ordered epics, each with its own sub-spec. The harness then works through epics sequentially: an Epic Initialiser creates Linear issues from the sub-spec, a coding agent resolves them one per session, and a snapshot session updates `shared_context.md` with the current architectural state before moving to the next epic. Human gate issues pause execution for manual setup (API keys, OAuth apps, DNS) and resume when you mark them done in Linear.

---

## Prerequisites

- **macOS or Linux** — Windows is not supported (relies on `fcntl` file locking)
- **Python 3.11+**
- **Node.js 18+**
- **Claude Code CLI** (`claude --version`) — run `claude setup-token` to generate a `CLAUDE_CODE_OAUTH_TOKEN`
- A [Linear](https://linear.app) account with API access
- An Anthropic API key (via Claude Code OAuth token)

---

## Installation

```bash
git clone https://github.com/EverythingBagelAI/EverythingBagelAI-Coding-Agent-Harness-V2.git
cd EverythingBagelAI-Coding-Agent-Harness-V2
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

`requirements-dev.txt` contains test dependencies (`pytest`) if you want to run the security tests.

---

## Configuration

Set these environment variables before running:

| Variable                    | Required | Description                                                                                                                                                        |
| --------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `CLAUDE_CODE_OAUTH_TOKEN`   | Yes      | Claude Code OAuth token — run `claude setup-token` to generate                                                                                                     |
| `LINEAR_API_KEY`            | Yes      | Linear API key (Settings → API → Create Key)                                                                                                                       |
| `REF_API_KEY`               | No       | [Ref.tools](https://ref.tools) API key for library doc pre-fetching. Without it, the harness runs fine but the agent relies on training knowledge for library docs |
| `HARNESS_SESSION_TIMEOUT`   | No       | Coding session timeout in seconds (default: 1800 = 30 min)                                                                                                         |
| `HARNESS_ARCHITECT_TIMEOUT` | No       | Architect session timeout in seconds (default: 3600 = 60 min)                                                                                                      |

**The harness configures the Linear MCP connection automatically using `LINEAR_API_KEY`. You do not need to set up Linear OAuth or the Linear MCP server manually.**

---

## Quick Start — V2 Epic Mode

This is the main workflow for large projects.

**1. Write your master spec:**

```bash
cp templates/master_app_spec_template.md prompts/master_app_spec.md
# Edit prompts/master_app_spec.md with your app description (500–1500 words)
```

**2. Generate epics:**

```bash
python generate_epics.py --project-dir ./my-project
```

This produces an `epics/` directory and `shared_context.md` inside `./my-project`. Review the generated epics before continuing — this is your cheapest quality gate. Edit human gate checklists, fix epic ordering, and split or merge epics as needed.

**3. Run the coding loop:**

```bash
python autonomous_agent_demo.py --project-dir ./my-project --mode epic
```

**4. Monitor progress in Linear.** Each epic gets its own Linear project with issues the agent works through sequentially.

**5. Resolve human gates when they appear.** The harness pauses and prints exactly what setup is required. Complete the steps, mark the gate issue Done in Linear, then re-run the same command.

**6. Resume after any interruption** by running the same command again — the harness picks up where it left off.

---

## Quick Start — V1 Modes

For smaller projects that fit in a single build sequence.

**Greenfield** — new project from a spec:

```bash
# Write your spec
cp templates/master_app_spec_template.md prompts/app_spec.txt

# Run
python autonomous_agent_demo.py --project-dir ./my-project --mode greenfield
```

In greenfield mode, relative `--project-dir` paths are placed inside a `generations/` subdirectory. Use an absolute path to control placement exactly, e.g. `--project-dir /Users/you/projects/my-app`.

**Brownfield** — extend an existing codebase:

```bash
python autonomous_agent_demo.py --mode brownfield --existing-dir /path/to/existing/repo
```

Do not use the same project directory for V1 and V2 modes.

---

## Key Concepts

**Epics** are groups of related Linear issues generated from your spec. The harness works through epics sequentially — each epic gets a fresh agent context, avoiding the context window saturation that breaks long single-loop builds.

**Snapshot sessions** run after each epic completes. A dedicated session reviews all commits from the epic and updates `shared_context.md` with the current architectural state — new endpoints, data model changes, established patterns. This gives subsequent epics accurate context about what was actually built, which may differ from what was originally specced.

**Human gates** are issues titled `[HUMAN GATE] ...` that pause the harness until manually resolved in Linear. The Architect agent creates these at epic boundaries where external setup is needed (API keys, third-party accounts, DNS configuration). The gate description includes a checklist of exactly what to do.

**Skills** are reusable agent instructions in `.claude/skills/`. The harness copies these into your project at startup so the coding agent can reference them. Currently includes `e2e-test` (Playwright testing patterns) and `api-test` (pytest + httpx patterns).

---

## Security Model

The harness runs an allowlist-based security layer on all bash commands the agent executes. Only explicitly permitted commands run — everything else is blocked. Sensitive commands get additional validation: `git push` is blocked entirely (no code is pushed to remote repos without human review), file operations are restricted to relative paths within the project directory, `rm` blocks path traversal, and `pkill` is limited to dev-related processes. MCP tool access is scoped per session type so the architect, initialiser, and coding agents each see only the tools they need.

---

## File Structure

```
├── autonomous_agent_demo.py        # Main entry point
├── generate_epics.py               # Architect agent — decomposes spec into epics
├── epic_orchestrator.py            # Epic mode loop — gate checking, sessions, snapshots
├── agent.py                        # Agent session logic
├── config.py                       # Model and timeout configuration
├── security.py                     # Bash command allowlist and validators
├── prompts/
│   ├── coding_prompt.md            # Instructions for the coding agent
│   ├── epic_initializer_prompt.md  # Instructions for the epic initialiser
│   └── architect_prompt.md         # Instructions for the architect agent
├── .claude/skills/
│   ├── e2e-test/SKILL.md           # Playwright E2E testing patterns
│   └── api-test/SKILL.md           # API testing patterns (httpx + pytest)
├── templates/
│   ├── master_app_spec_template.md # Template for writing your app spec
│   └── epic_spec_template.md       # Template for individual epic specs
├── requirements.txt
└── requirements-dev.txt            # Dev dependencies (pytest)
```

---

## Important Notes

- **macOS/Linux only.** Windows is not supported due to `fcntl` file locking.
- **V1 and V2 modes must not share a project directory.** They write different schemas to `.linear_project.json` and will conflict.
- **`claude-progress.txt`** tracks epic state in your project directory. Do not commit it or edit it manually.
- **Default model is Opus** (most capable but most expensive). Pass `--model` to override, e.g. `--model claude-sonnet-4-5` for a cheaper option.
- **`SNAPSHOT_FAILURE.txt`** appearing in your project directory means a snapshot session failed. Review and update `shared_context.md` manually before continuing.
- **First run takes 10–20 minutes.** The initialiser is creating a Linear project and 15–30 issues. Watch for `[Tool: ...]` output — it is working.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest test_security.py
```
