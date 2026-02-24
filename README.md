# EverythingBagelAI Coding Agent Harness

An autonomous coding agent that builds entire applications from a simple text description. You write what you want, it builds it — and you can watch every step in Linear.

It automatically detects your existing Claude Code setup (MCP servers, plugins, skills) so it works with whatever you've already got configured.

> Based on [gatopilantra/Linear-Coding-Agent-Harness](https://github.com/gatopilantra/Linear-Coding-Agent-Harness) by Cole Medin.

---

## What This Does

You give it a description of what you want built (a text file called `app_spec.txt`). The harness then:

1. **Reads your spec** and breaks it into individual tasks (Linear issues)
2. **Works through each task** one by one — writing code, testing it, committing
3. **Tracks everything in Linear** so you can see exactly what's done, what's in progress, and what's left
4. **Stops automatically** when everything is complete

It works in two modes:
- **Greenfield** — build something brand new from scratch
- **Brownfield** — add features to an existing codebase

---

## How It Works

```
You write app_spec.txt
        |
        v
  Session 1: PLANNER
  Reads your spec, creates a Linear project,
  breaks the work into ~20-50 individual issues
        |
        v
  Session 2+: BUILDER
  Picks the highest-priority issue from Linear,
  writes the code, tests it, marks it Done,
  then moves to the next one
        |
        v
  All issues Done? --> Stops automatically
```

Each session gets a **fresh context window** — the builder reads Linear to know what's been done and what to do next. This means it can handle large projects without running out of context.

---

## Before You Start

You need three things:

### 1. Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
```

### 2. A Linear Account

Linear is a project management tool (like Jira but better). The agent uses it to track all its work.

1. Sign up at [linear.app](https://linear.app) if you don't have an account
2. Go to **Settings > API** (or visit `https://linear.app/YOUR-TEAM/settings/api`)
3. Create a new API key — copy it somewhere safe

### 3. Python 3.11+

```bash
python3 --version  # Check you have 3.11 or higher
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/EverythingBagelAI/EverythingBagelAI-Coding-Agent-Harness.git
cd EverythingBagelAI-Coding-Agent-Harness
pip install -r requirements.txt
```

### 2. Set your API keys

```bash
# Generate your Claude token
claude setup-token

# Set both keys (add these to your shell profile to make them permanent)
export CLAUDE_CODE_OAUTH_TOKEN='your-token-here'
export LINEAR_API_KEY='lin_api_xxxxxxxxxxxxx'
```

### 3. Write your app spec

Edit `prompts/app_spec.txt` with a description of what you want built. Be specific — include features, tech stack, file structure, and how it should work. There's an example in the file to get you started.

### 4. Run it

**New project (greenfield):**
```bash
python3 autonomous_agent_demo.py --project-dir ./my-app
```

**Adding to an existing project (brownfield):**
```bash
python3 autonomous_agent_demo.py --mode brownfield --existing-dir /path/to/your/repo
```

That's it. Open your Linear workspace to watch it work.

---

## What Happens When You Run It

### First session (10-20 minutes)

The planner agent reads your spec and creates Linear issues. Your terminal will look something like this:

```
======================================================================
  EVERYTHINGBAGELAI CODING AGENT HARNESS
======================================================================

  ECOSYSTEM DISCOVERY
  MCP Servers (5 total): linear, puppeteer, filesystem, memory, exa
  Plugins (3): document-skills, superpowers, recall
  Skills (2): ui-ux-pro-max, mermaid-visualizer

  SESSION 1: INITIALIZER
  [Tool: mcp__linear__create_issue]  <-- Creating issues in Linear
  [Tool: mcp__linear__create_issue]
  ...
```

This is normal — it's creating all the tasks. Don't close the terminal.

### Subsequent sessions (a few minutes each)

The builder picks up one issue at a time:

```
  SESSION 2: CODING AGENT
  [Tool: mcp__linear__list_issues]   <-- Checking what's left to do
  [Tool: Write]                      <-- Writing code
  [Tool: Bash]                       <-- Running it
  [Tool: mcp__puppeteer__screenshot] <-- Testing in the browser

  PROJECT COMPLETE                   <-- Done!
```

### In Linear

You'll see a project with all issues organised by priority. As the agent works, issues move from **Todo** to **In Progress** to **Done**. Each issue gets comments explaining what was implemented.

---

## Your Setup is Automatically Detected

When the harness starts, it scans your Claude Code configuration and picks up:

- **MCP servers** you've configured (globally and per-project)
- **Plugins** you've installed
- **Skills** you've added
- **Bash commands** you've approved in your settings

Everything merges together automatically. The agent gets access to all your tools alongside the ones it needs (Linear + Puppeteer).

If you have task management frameworks installed (like GSD or similar), the harness automatically excludes them to avoid conflicts — the agent uses Linear for task management instead.

---

## Customisation

### Change what gets built

Edit `prompts/app_spec.txt`. This is the only file you need to change. Write a clear description of your application including:
- What it does
- Technology stack
- Features (numbered list works well)
- File structure
- How to run it

### Use a different model

```bash
python3 autonomous_agent_demo.py --project-dir ./my-app --model claude-sonnet-4-5-20250929
```

Default is Claude Opus 4.5 (`claude-opus-4-5-20251101`).

### Limit the number of sessions

```bash
python3 autonomous_agent_demo.py --project-dir ./my-app --max-iterations 5
```

Useful for testing. The agent will stop after 5 sessions even if there are issues left. Run the same command again to continue where it left off.

### Add bash commands to the allowlist

The security layer only allows specific commands. If the agent needs a command that's blocked, add it to `security.py` in the `_DEFAULT_ALLOWED_COMMANDS` set.

Your existing Claude Code bash permissions (from `settings.local.json`) are automatically merged in — you shouldn't need to change this in most cases.

---

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--project-dir` | Where to create the new project | `./autonomous_demo_project` |
| `--mode` | `greenfield` (new) or `brownfield` (existing) | `greenfield` |
| `--existing-dir` | Path to existing repo (brownfield only) | — |
| `--max-iterations` | Stop after N sessions | Unlimited |
| `--model` | Claude model to use | `claude-opus-4-5-20251101` |

---

## Project Structure

```
EverythingBagelAI-Coding-Agent-Harness/
├── autonomous_agent_demo.py  # Entry point — run this
├── agent.py                  # Main agent loop and session logic
├── client.py                 # Claude SDK client configuration
├── discovery.py              # Detects your Claude Code setup automatically
├── security.py               # Bash command allowlist and validation
├── progress.py               # Tracks progress via .linear_project.json
├── prompts.py                # Loads prompt files
├── linear_config.py          # Linear API configuration
├── prompts/
│   ├── app_spec.txt              # YOUR APP DESCRIPTION GOES HERE
│   ├── initializer_prompt.md     # Planner agent instructions
│   ├── brownfield_initializer_prompt.md  # Brownfield planner instructions
│   └── coding_prompt.md          # Builder agent instructions
├── test_security.py          # Security tests
├── requirements.txt          # Python dependencies
└── generations/              # Where greenfield projects are created (gitignored)
```

---

## Troubleshooting

**"CLAUDE_CODE_OAUTH_TOKEN not set"**
Run `claude setup-token` in your terminal, then `export CLAUDE_CODE_OAUTH_TOKEN='the-token-it-gives-you'`.

**"LINEAR_API_KEY not set"**
Go to your Linear settings > API, create a key, then `export LINEAR_API_KEY='lin_api_...'`.

**First run seems to hang**
Normal. The planner is creating 20-50 Linear issues with detailed descriptions. Watch for `[Tool: mcp__linear__create_issue]` lines — that means it's working. Give it 10-20 minutes.

**"Command blocked by security hook"**
The agent tried to run a command that's not in the allowlist. If you trust the command, add it to `_DEFAULT_ALLOWED_COMMANDS` in `security.py`.

**"MCP server connection failed"**
Check that your `LINEAR_API_KEY` is valid and has read/write permissions.

---

## Based On

This project is a fork of [Linear-Coding-Agent-Harness](https://github.com/gatopilantra/Linear-Coding-Agent-Harness) by Cole Medin.

**What's different:**
- Automatically detects your Claude Code ecosystem (MCP servers, plugins, skills, bash permissions)
- Supports brownfield development (adding features to existing codebases)
- Auto-excludes conflicting task management frameworks
- Dynamic security allowlist (merges your existing permissions)
- Automatic completion detection (stops when all issues are Done)
- Migrated to Claude Agent SDK

---

## Licence

MIT — see [LICENSE](LICENSE) for details.
