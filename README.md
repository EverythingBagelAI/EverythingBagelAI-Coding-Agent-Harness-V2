# EverythingBagelAI Coding Agent Harness V2

> Multi-epic autonomous coding harness built on the Claude Agent SDK. Decomposes large projects into ordered epics, builds each one autonomously with human review gates between them, and maintains architectural context across the full build.

Built on top of [Cole Medin's Linear Coding Agent Harness](https://github.com/coleam00/Linear-Coding-Agent-Harness), which itself implements [Anthropic's two-agent harness pattern](https://github.com/anthropics/claude-agent-sdk-demos).

---

## What's Different from V1 / Cole's Original

**V1** (EverythingBagelAI-Coding-Agent-Harness) extended Cole's harness with MCP auto-discovery, brownfield support, and dynamic bash permissions. V2 adds:

- **Epic decomposition** — an Architect Agent reads your master spec and produces ordered, dependency-resolved epic sub-specs. The harness builds one epic at a time.
- **Programmatic context injection** — Python pre-fetches the current Linear issue and architectural context before each agent session. The agent receives facts, not instructions to go discover state. This eliminates the most common class of autonomous agent failures.
- **Human review gates** — auto-generated between epics requiring external setup (API keys, OAuth apps, DNS). The harness pauses, prints exactly what you need to do, and resumes where it left off when you re-run.
- **Playwright over Puppeteer** — full e2e testing skill with plan → write → heal phases.
- **Shared context + deviation tracking** — `shared_context.md` and `build_deviations.md` accumulate architectural decisions across all epics, so later epics build correctly on top of earlier ones.
- **Direct Linear API** — harness state management uses the Linear GraphQL API directly from Python, not via MCP. MCP is reserved for the agent's work.

---

## Requirements

- **OS:** macOS or Linux (Unix/POSIX). Windows is not supported due to `fcntl` file locking.
- **Python:** 3.11+
- **Node.js:** 18+

## Prerequisites

```bash
node --version     # v18+
python3 --version  # 3.11+
claude --version   # latest Claude Code CLI
```

Environment variables required:

```bash
export CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token'
export LINEAR_API_KEY='lin_api_...'        # linear.app → Settings → API
```

Optional:

- `REF_API_KEY` — Used to pre-fetch library documentation for the coding agent. Get one at https://ref.tools. If absent, the harness runs without doc pre-fetching.
  Without caching, Ref API calls are made fresh every session. On long epic runs this may hit rate limits.
- `HARNESS_SESSION_TIMEOUT` — Maximum time in seconds for a single agent session (default: 1800 = 30 minutes). Increase for complex issues.

MCP servers (add once via Claude Code CLI, auto-discovered by harness):

```bash
# Linear — OAuth, run once then authenticate in Claude Code
claude mcp add linear --transport http https://mcp.linear.app/mcp

# Ref — documentation lookup (get key from ref.tools)
claude mcp add ref --transport http https://api.ref.tools/mcp \
  --header "x-ref-api-key: YOUR_REF_API_KEY"

# Exa — web research
claude mcp add exa --transport stdio -e EXA_API_KEY=your_key -- npx -y exa-mcp-server
```

Playwright (install once globally):

```bash
npm install -D @playwright/test
npx playwright install chromium
```

---

## Setup

```bash
# 1. Clone
git clone https://github.com/EverythingBagelAI/EverythingBagelAI-Coding-Agent-Harness-V2.git
cd EverythingBagelAI-Coding-Agent-Harness-V2

# 2. Install Python dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Note: claude-agent-sdk is the Anthropic Claude Agent SDK.
# If pip cannot find it, install from: pip install claude-agent-sdk

# 3. Write your master spec (500-1500 words)
cp templates/master_app_spec_template.md prompts/master_app_spec.md
# edit prompts/master_app_spec.md

# 4. Generate epic sub-specs
python generate_epics.py --project-dir ./my-project
# Produces epics/ directory and shared_context.md
# Review and edit before running — this is your cheapest quality gate

# 5. Run
python autonomous_agent_demo.py --project-dir ./my-project --mode epic
```

---

## Usage

### Epic Mode (new in V2)

For large projects — anything that would overflow a single agent's context or take more than a few hours to build.

```bash
python autonomous_agent_demo.py --project-dir ./my-project --mode epic
```

The harness will:

1. Run an Architect Agent to decompose your spec into ordered epics
2. For each epic: run an Epic Initializer to create a Linear project + issues, then loop coding agent sessions until all issues are resolved
3. Pause at human gates and print exactly what setup is required
4. Resume from where it left off when you re-run after completing a gate

**Human gate example:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏸  HUMAN GATE — Epic 2 complete, setup required
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- [ ] CLERK_PUBLISHABLE_KEY: from Clerk dashboard → API Keys
- [ ] CLERK_SECRET_KEY: from Clerk dashboard → API Keys
- [ ] Create Clerk application with email/password provider enabled

Once complete:
1. Mark the gate issue Done in Linear
2. Re-run: python autonomous_agent_demo.py --project-dir ./my-project --mode epic
```

### Greenfield Mode (V1, unchanged)

For smaller projects that fit in a single build sequence. Create `prompts/app_spec.txt` in the harness root with your application specification, then run:

```bash
python autonomous_agent_demo.py --project-dir ./my-project --mode greenfield
```

The agent reads `app_spec.txt` to understand what to build.

> **Note:** In greenfield mode, relative `--project-dir` paths are placed inside a `generations/` subdirectory. For example, `--project-dir ./my-project` creates the project at `./generations/my-project`. Use an absolute path to bypass this behaviour.

### Brownfield Mode (V1, unchanged)

For extending an existing codebase. Also requires `prompts/app_spec.txt` describing the work to be done:

```bash
python autonomous_agent_demo.py --project-dir ./existing-project --mode brownfield \
  --existing-dir /path/to/existing/code
```

---

## Writing a Good Master Spec

The master spec is the single most important quality input. A well-written 1,000-word spec produces dramatically better epics than a vague 3,000-word one.

Use the template at `templates/master_app_spec_template.md`. Key sections:

- **Purpose** — one paragraph. What the app does and who it's for.
- **Tech stack** — be specific: Next.js 15, Supabase, Clerk, Vercel. The Architect Agent uses this to write accurate API contracts.
- **Key user flows** — 8-15 numbered flows describing what a user _does_, not what features exist.
- **Feature list** — loosely grouped by natural epic boundary.
- **Anti-patterns** — 5-10 things the agent must never do in this specific project. This section has outsized impact on output quality.

After running `generate_epics.py`, **review the epics before running the harness**. Edit:

- Human gate checklists — make sure they reflect what you actually need to set up
- Epic ordering — if the Architect got a dependency wrong, fix it in `epics/spec_index.json`
- Feature scope — split an epic if it has 25+ issues; merge if one has fewer than 8

---

## File Structure

```
├── autonomous_agent_demo.py      # Entry point — greenfield/brownfield/epic modes
├── epic_orchestrator.py          # Epic mode loop: gate checking, initializer, coding sessions
├── agent.py                      # Agent session logic
├── linear_client.py              # Direct Linear GraphQL client for harness state management
├── client.py                     # Claude Agent SDK + MCP configuration
├── discovery.py                  # Auto-detects global Claude Code MCP config and merges it
├── progress.py                   # Session + epic state persistence (claude-progress.txt)
├── prompts.py                    # Prompt loading + programmatic context injection
├── security.py                   # Bash command allowlist
├── generate_epics.py             # Standalone Architect Agent script (run before harness)
│
├── prompts/
│   ├── master_app_spec.md        # Your app description (you write this)
│   ├── architect_prompt.md       # Architect Agent system prompt
│   ├── initializer_prompt.md     # V1 initializer (greenfield/brownfield)
│   ├── epic_initializer_prompt.md  # Epic Initializer system prompt
│   └── coding_prompt.md          # Coding Agent system prompt
│
├── templates/
│   ├── master_app_spec_template.md  # Start here when writing a new spec
│   └── epic_spec_template.md        # Format reference for individual epic specs
│
└── .claude/
    └── skills/
        └── e2e-test/
            └── SKILL.md          # Playwright testing skill (plan → write → heal)
```

**Generated per project** (lives alongside your application code):

> **Do not commit** `.linear_project.json` or `claude-progress.txt` — these are transient harness state files. Add them to your project's `.gitignore`.

```
my-project/
├── .linear_project.json      # Current epic's Linear project ID (do not commit)
├── claude-progress.txt       # Session + epic state (do not commit — edit to reset if needed)
├── shared_context.md         # Cross-epic design system, data model, API contracts
├── build_deviations.md       # Agent decisions that diverged from the spec
├── epics/
│   ├── spec_index.md         # Human-readable epic dependency graph
│   ├── spec_index.json       # Machine-readable index (used by harness)
│   ├── epic-01-foundation.md
│   └── epic-02-auth.md
└── [application code]
```

---

## Troubleshooting

**`CLAUDE_CODE_OAUTH_TOKEN not set`**

```bash
export CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token'
```

**`LINEAR_API_KEY not set`**
Get your key from linear.app → Settings → API → Create Key.

**Harness appears to hang on first run**
Normal. The Epic Initializer is creating a Linear project and 15-30 issues. Watch for `[Tool: mcp__linear__create_issue]` output. Can take 5-10 minutes.

**`Error: Claude Code cannot be launched inside another Claude Code session`**
You're running the harness from inside an active Claude Code session. Exit Claude Code first and run from a regular terminal.

**Agent picks up the wrong issue or repeats a completed one**
The harness fetches the current issue directly from Linear before each session. If an issue shows as incomplete but was actually finished, mark it Done in Linear and re-run.

**Human gate not detected / harness doesn't pause**
Gate detection looks for issues with titles starting `[HUMAN GATE]`. If the Epic Initializer named it differently, rename the issue in Linear to start with `[HUMAN GATE]` and re-run.

**`epics/spec_index.json not found`**
Re-run `python generate_epics.py`. The JSON index is required — the markdown version is for human reading only.

**Playwright not found in later epics**
Run manually in the project directory:

```bash
npm install -D @playwright/test && npx playwright install chromium
```

---

## Lineage

### Anthropic's Two-Agent Harness Pattern

The foundation. Anthropic's harness research established the core pattern: a short-lived **Initializer** session that creates a structured task list, followed by repeated **Coding Agent** sessions that each work one task and hand off via shared state. Key insight: agents fail by trying to do too much in one session. Splitting initialisation from implementation, and keeping each coding session focused on one issue, avoids both one-shotting and premature completion.

Key design decisions from Anthropic's pattern: task lists as JSON not markdown (agents corrupt markdown), a non-negotiable session startup ritual (pwd → read progress → read task list → run init.sh → implement ONE task → verify → commit → update progress).

### Cole Medin's Linear Coding Agent Harness

[github.com/coleam00/Linear-Coding-Agent-Harness](https://github.com/coleam00/Linear-Coding-Agent-Harness)

Cole implemented Anthropic's pattern with Linear as the task tracker and Puppeteer MCP for browser testing. The key improvement: Linear gives real-time visibility into agent progress and survives session restarts cleanly — the agent queries Linear to find what to work on next rather than reading a local file that could be stale or corrupted.

### EverythingBagelAI V1

[github.com/EverythingBagelAI/EverythingBagelAI-Coding-Agent-Harness](https://github.com/EverythingBagelAI/EverythingBagelAI-Coding-Agent-Harness)

Extended Cole's harness with:

- **`discovery.py`** — auto-detects the global Claude Code MCP config (`~/.claude.json`) and merges all configured servers into every agent session. Add a new MCP to Claude Code once; every harness run picks it up automatically.
- **Brownfield mode** — point the harness at an existing codebase and it generates issues for extending or refactoring rather than greenfield building.
- **Dynamic bash permissions** — merges the project's existing Claude Code bash allowlist with the harness security policy.
- **Migrated to Claude Agent SDK** — moved from subprocess invocation to the proper Python SDK.

### EverythingBagelAI V2 (this repo)

Built to handle projects too large for a single linear build sequence. The core problems with V1 on large projects: context window saturation after 20+ issues, no way to inject external service setup mid-build, and architectural drift across long sessions where later issues contradict decisions made in earlier ones.

V2 solutions:

- **Epic decomposition** — an Architect Agent pre-decomposes the spec into 4-7 ordered epics of 10-25 issues each. Each epic gets a fresh agent context.
- **Programmatic context injection** — Python assembles the complete prompt for each agent session, including the specific issue to work on fetched directly from Linear. The agent never discovers state — it receives facts. This is the single biggest reliability improvement over V1.
- **Human gates** — natural epic boundaries that require external service setup become explicit pause points with auto-generated checklists.
- **Cross-epic memory** — `shared_context.md` and `build_deviations.md` carry architectural decisions forward so Epic 4 builds correctly on top of what Epic 1 actually built, which may differ from what was originally specced.
- **Playwright** — replaced Puppeteer MCP with Playwright CLI. Simpler, more reliable, no MCP server process to manage.
- **Direct Linear API** — `linear_client.py` handles all harness orchestration state queries via GraphQL directly. MCP Linear tools are reserved for the agent's own issue management work.
