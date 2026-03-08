# Master App Spec: Claude.ai Clone — AI Chat Interface

## 1. Purpose & Overview

### What It Does

A fully functional clone of claude.ai — Anthropic's conversational AI interface. The application provides a modern chat interface for interacting with Claude via the Anthropic API, with streaming responses, artifact rendering, conversation management, project organisation, and advanced model configuration.

### Who It's For

Individual developers and small teams who want a self-hosted Claude interface with full control over their data, custom instructions, and conversation organisation. No cloud account required — runs locally with the user's own Anthropic API key.

### Core Problem

Anthropic's hosted claude.ai is excellent but offers no self-hosting option, no local data ownership, and limited customisation of the interface. Users who want to organise conversations into projects, maintain a prompt library, or run the interface on their own infrastructure have no official solution.

### Value Proposition

- Full data ownership — all conversations stored in a local SQLite database
- Project-based organisation with custom instructions per project
- Artifact system for code, HTML, SVG, React components, and Mermaid diagrams
- Prompt library for reusable templates
- Usage tracking and cost estimation
- Sharing via tokenised read-only links

---

## 2. Tech Stack

### Frontend

| Concern | Choice | Rationale |
|---|---|---|
| Framework | React 18 with Vite | Fast HMR, minimal config, wide ecosystem |
| Styling | Tailwind CSS (via CDN) | Utility-first, matches claude.ai aesthetic |
| State management | React hooks + Context API | No external state library needed for this scope |
| Routing | React Router v6 | Standard SPA routing |
| Markdown rendering | react-markdown + remark-gfm + rehype-highlight | GitHub-flavoured markdown with syntax highlighting |
| Code highlighting | highlight.js or Prism.js | Syntax colouring for code blocks |
| LaTeX rendering | KaTeX | Lightweight math equation rendering |
| Mermaid | mermaid.js | Diagram rendering from markdown-like syntax |
| Port | Configured via environment — default `5173` | Vite default |

### Backend

| Concern | Choice | Rationale |
|---|---|---|
| Runtime | Node.js 18+ with Express | Simple, well-understood HTTP server |
| Database | SQLite via better-sqlite3 | Zero-config, file-based, no separate DB server |
| AI integration | @anthropic-ai/sdk | Official Anthropic SDK for Claude API |
| Streaming | Server-Sent Events (SSE) | Native browser support, unidirectional streaming |
| File uploads | multer | Multipart form handling for image uploads |
| Port | Configured via environment — default `3001` | Separate from frontend |

### Communication Pattern

Frontend and backend communicate via RESTful JSON endpoints. Streaming responses use SSE — the frontend opens an EventSource connection to the backend, which proxies the Claude API stream and forwards chunks as `data:` events.

---

## 3. Environment Config

### Required Environment Variables

| Variable | Location | Purpose | Example |
|---|---|---|---|
| `VITE_ANTHROPIC_API_KEY` | `.env` (project root) | Anthropic API key for Claude requests | `sk-ant-api03-...` |
| `VITE_API_BASE_URL` | `.env` (project root) | Backend API URL | `http://localhost:3001` |
| `PORT` | `server/.env` | Backend server port | `3001` |
| `DATABASE_PATH` | `server/.env` | SQLite database file location | `./data/claude_clone.db` |

### Third-Party Accounts

| Service | Required | Purpose | Setup |
|---|---|---|---|
| Anthropic | Yes | Claude API access | Create account at console.anthropic.com, generate API key under API Keys |

### Local Services

No external services required. SQLite runs embedded — no database server to install or configure.

---

## 4. Prerequisites

### Development Environment

- **Node.js**: v18.0.0 or later (required for native fetch and ESM support)
- **pnpm**: v8+ (package manager — frontend dependencies pre-installed)
- **npm**: v9+ (for backend dependency installation if pnpm not used)
- **OS**: macOS, Linux, or Windows with WSL2
- **Browser**: Chrome 90+, Firefox 90+, Safari 15+, Edge 90+ (required for EventSource and modern CSS)

### Pre-installed

- Frontend dependencies are pre-installed via pnpm in the project root
- Backend code lives in `/server` — install backend dependencies with `npm install` from that directory

### Not Required

- Docker (optional for deployment, not needed for development)
- Any cloud database service
- Any authentication provider

---

## 5. User Flows

### Flow 1: First-Time Setup and First Conversation

1. User clones the repository and runs `pnpm dev` (frontend) and `node server/index.js` (backend)
2. Browser opens to `http://localhost:5173`
3. Welcome screen displays with API key input prompt
4. User enters their Anthropic API key
5. App validates the key by making a test request to the Claude API
6. On success, key is stored (encrypted in SQLite) and welcome screen shows example prompts
7. User clicks an example prompt or types their own message
8. Message sends, typing indicator appears, Claude's response streams in word by word
9. Conversation auto-saves with an auto-generated title based on the first exchange
10. Conversation appears in the sidebar under "Today"

### Flow 2: Multi-Turn Conversation with Artifacts

1. User starts a new conversation via the "New Chat" button
2. User asks Claude to "Build a React component that displays a sortable data table"
3. Claude responds with explanation text and a code artifact
4. Artifact panel slides in from the right, displaying the React component code with syntax highlighting
5. User clicks "Preview" tab to see a live render of the component
6. User says "Add a search filter above the table"
7. Claude responds with an updated artifact (version 2)
8. Version selector in the artifact panel shows v1 and v2; user can toggle between them
9. User clicks "Download" to save the component as a `.jsx` file
10. User clicks "Full Screen" to expand the artifact panel for detailed review

### Flow 3: Project Creation and Conversation Organisation

1. User clicks the project selector dropdown in the sidebar header
2. User clicks "New Project" and enters a name: "API Documentation"
3. User sets project-specific custom instructions: "Always respond with TypeScript examples. Use JSDoc comments on all functions."
4. User creates a new conversation within the project
5. Claude's responses now follow the project-specific instructions
6. User drags two existing conversations from the sidebar into the project
7. User creates a folder within the project called "Endpoints" and moves conversations into it
8. Project analytics show total tokens used and number of conversations

### Flow 4: Searching and Resuming Work

1. User presses Cmd+K to open the command palette
2. User types "data table" to search across all conversations
3. Search results show matching conversations and specific messages containing "data table"
4. User clicks a result — the app navigates to that conversation and scrolls to the matching message
5. User continues the conversation from where they left off

### Flow 5: Sharing a Conversation

1. User right-clicks a conversation in the sidebar and selects "Share"
2. Share modal appears with a toggle for "Public link"
3. User enables the public link — a unique share URL is generated
4. User copies the link and sends it to a colleague
5. Colleague opens the link — sees a read-only view of the conversation with all messages and artifacts
6. Share modal shows view count incrementing

### Flow 6: Customising Model and Parameters

1. User clicks the model selector badge in the chat header
2. Dropdown shows three models with context window sizes and pricing info
3. User switches from Claude Sonnet 4.5 to Claude Opus 4.1
4. User clicks the settings gear icon next to the model selector
5. Advanced parameters panel expands: temperature slider (0-1), max tokens input, top-p slider
6. User sets temperature to 0.2 for more deterministic responses
7. Next message uses the updated model and parameters
8. Token usage display updates to show Opus pricing

### Flow 7: Editing a Message and Branching

1. User hovers over a previous user message — an edit icon appears
2. User clicks edit, modifies the message text, and clicks "Save & Resubmit"
3. The conversation branches — original response is preserved, new response streams in
4. Branch indicator appears showing "Branch A" and "Branch B"
5. User can toggle between branches to compare Claude's responses

### Flow 8: Exporting and Prompt Library

1. User opens the prompt library via the sidebar or Cmd+K
2. User browses prompts by category (coding, writing, analysis)
3. User selects a prompt template: "Code Review: Review the following code for bugs, performance issues, and best practices"
4. Prompt populates the input field with a placeholder for the user's code
5. After a useful conversation, user clicks "Export" and chooses Markdown format
6. Exported file downloads with all messages, code blocks, and metadata

---

## 6. Core Features

### Chat Interface

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.1 | Message input with auto-resizing textarea | Textarea grows from 1 line to max 8 lines as user types. Shift+Enter inserts newline. Enter sends message. |
| 6.2 | Streaming message display | Claude's response renders character by character via SSE. No visible buffering lag. Partial markdown renders correctly during stream. |
| 6.3 | Markdown rendering | Headings, bold, italic, lists, links, blockquotes, tables, and horizontal rules render with correct styling. GFM-compatible. |
| 6.4 | Code blocks with syntax highlighting | Fenced code blocks render with language-specific highlighting. Copy button in top-right corner. Language label displayed. |
| 6.5 | LaTeX/math equation rendering | Inline `$...$` and block `$$...$$` equations render via KaTeX. Malformed LaTeX shows source text with error indicator. |
| 6.6 | Image upload and display | User can attach images via button or paste from clipboard. Images display inline in the message. Supported formats: PNG, JPEG, GIF, WebP. Max file size: 5MB. |
| 6.7 | Message editing | Hover on a user message reveals edit icon. Clicking opens inline editor with current text. Save & Resubmit re-sends to Claude from that point. |
| 6.8 | Message regeneration | Hover on an assistant message reveals regenerate icon. Clicking re-sends the preceding user message and streams a new response. |
| 6.9 | Stop generation | During streaming, a stop button appears in place of the send button. Clicking immediately stops the SSE stream and keeps the partial response. |
| 6.10 | Typing indicator | Three animated dots appear left-aligned (assistant position) while waiting for the first chunk of Claude's response. Disappears when streaming begins. |
| 6.11 | Character count and token estimation | Below the input field: character count (live) and estimated token count (updated on pause, using ~4 chars/token heuristic). |
| 6.12 | Keyboard shortcuts | Enter: send. Shift+Enter: newline. Cmd+K: command palette. Cmd+N: new conversation. Cmd+/: toggle sidebar. Escape: close modals. |

### Artifact System

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.13 | Artifact detection | When Claude's response contains an artifact block (identified by `<artifact>` tags or code blocks >20 lines), the artifact is extracted and rendered in the side panel. |
| 6.14 | Code artifact viewer | Code artifacts render with syntax highlighting matching the specified language. Line numbers displayed. |
| 6.15 | HTML/SVG live preview | HTML and SVG artifacts render in a sandboxed iframe. User can toggle between code view and preview. |
| 6.16 | React component preview | React/JSX artifacts render in a sandboxed environment with React and ReactDOM loaded. Errors display in the preview pane with stack traces. |
| 6.17 | Mermaid diagram rendering | Mermaid syntax artifacts render as SVG diagrams. Supported types: flowchart, sequence, class, state, gantt, pie. |
| 6.18 | Text document artifacts | Markdown and plain text artifacts render with formatting in a document-style view. |
| 6.19 | Artifact editing | User can edit artifact content directly in the panel. Changes are local until user clicks "Re-prompt" to ask Claude to iterate on the edited version. |
| 6.20 | Full-screen artifact view | Toggle button expands artifact panel to full viewport width. Chat area hides. Second toggle returns to split view. |
| 6.21 | Download artifact content | Download button saves artifact as a file. Filename derived from artifact title. Extension matches artifact type (.js, .html, .svg, .md). |
| 6.22 | Artifact versioning | Each re-prompt or regeneration creates a new version. Version selector dropdown shows version history. User can view and restore any previous version. |

### Conversation Management

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.23 | Create new conversation | "New Chat" button in sidebar header. Creates a conversation with no messages and no title. Title auto-generates after first exchange. |
| 6.24 | Conversation list in sidebar | Conversations listed in reverse chronological order, grouped by: Today, Yesterday, Previous 7 Days, Previous 30 Days, Older. |
| 6.25 | Rename conversation | Double-click conversation title in sidebar or click edit icon. Inline text input appears. Enter to save, Escape to cancel. |
| 6.26 | Delete conversation | Right-click context menu or swipe on mobile. Confirmation dialog: "Delete this conversation? This cannot be undone." Soft-deletes (sets `is_deleted` flag). |
| 6.27 | Search conversations | Search input at top of sidebar. Filters conversations by title match in real-time (debounced 300ms). Results highlight matching text. |
| 6.28 | Pin conversation | Right-click > "Pin to top". Pinned conversations appear above the date-grouped list with a pin icon. |
| 6.29 | Archive conversation | Right-click > "Archive". Conversation moves to an archive section. "Show Archived" toggle at bottom of sidebar reveals archived conversations. |
| 6.30 | Conversation folders | User can create folders in the sidebar. Drag conversations into folders. Folders are collapsible. Folders can be nested one level deep. |
| 6.31 | Duplicate conversation | Right-click > "Duplicate". Creates a copy of the conversation with all messages. Title appended with "(Copy)". |
| 6.32 | Export conversation | Right-click > "Export". Modal with format options: JSON (full data), Markdown (readable), PDF (formatted). Download triggers immediately on selection. |
| 6.33 | Conversation timestamps | Sidebar shows relative time ("2h ago", "Yesterday"). Tooltip on hover shows absolute datetime. |

### Projects

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.34 | Create project | Project selector dropdown > "New Project". Modal with name, description, and colour picker. |
| 6.35 | Project knowledge base | Upload documents (txt, md, pdf) to a project. Documents are included as context in all project conversations via system prompt injection. Max total: 50KB of text. |
| 6.36 | Project custom instructions | Text area in project settings. Instructions are prepended as a system message to every conversation in the project. Markdown preview available. |
| 6.37 | Move conversations between projects | Drag conversation to a different project in the sidebar, or right-click > "Move to Project" > select project from list. |
| 6.38 | Project settings | Modal with tabs: General (name, description, colour), Instructions, Knowledge Base, Danger Zone (delete project). |
| 6.39 | Project analytics | Display in project settings: total conversations, total messages, total tokens used, estimated cost, date range of activity. |

### Model Selection

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.40 | Model selector dropdown | Dropdown in chat header. Shows model name, context window size, and relative pricing tier. Default: Claude Sonnet 4.5. |
| 6.41 | Available models | Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`), Claude Haiku 4.5 (`claude-haiku-4-5-20251001`), Claude Opus 4.1 (`claude-opus-4-1-20250805`). |
| 6.42 | Switch model mid-conversation | Selecting a new model applies to the next message only. Previous messages in the conversation retain their original model indicator. Model badge appears on each message. |
| 6.43 | Model info display | Each model in the dropdown shows: name, context window (tokens), input/output pricing per 1M tokens. |

### Custom Instructions

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.44 | Global custom instructions | Settings > Custom Instructions. Textarea for instructions applied to all conversations. Max 4,000 characters. |
| 6.45 | Project-specific instructions | Override or extend global instructions within a project. Displayed priority: conversation > project > global. |
| 6.46 | Conversation-specific system prompt | Per-conversation system prompt field. Accessible via settings icon in chat header. |
| 6.47 | Custom instruction templates | Pre-built templates: "Code Assistant", "Writing Editor", "Data Analyst", "Tutor". User can create and save their own. |

### Settings & Preferences

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.48 | Theme selection | Light, Dark, and Auto (follows OS preference). Theme applies immediately without page reload. |
| 6.49 | Font size adjustment | Slider: 12px to 20px. Default 16px. Applies to message text only — UI chrome stays fixed. |
| 6.50 | Message density | Three options: Compact (8px gap between messages), Comfortable (16px gap, default), Spacious (24px gap). |
| 6.51 | Code theme selection | Dropdown with code highlighting themes: GitHub Light, GitHub Dark, Monokai, Dracula, One Dark. Default follows app theme. |
| 6.52 | API key management | View masked key (`sk-ant-...XXXX`), test key validity, replace key. Key stored encrypted in SQLite. |

### Advanced Features

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.53 | Temperature control | Slider 0.0 to 1.0 with 0.1 increments. Default 1.0. Displayed value updates in real-time. Tooltip explains the parameter. |
| 6.54 | Max tokens adjustment | Number input. Range: 256 to model's max output. Default: 4096. Validation prevents exceeding model limit. |
| 6.55 | Top-p control | Slider 0.0 to 1.0 with 0.05 increments. Default 1.0. |
| 6.56 | Thinking mode toggle | Toggle switch to enable extended thinking. When enabled, Claude's thinking process displays in a collapsible section above the response. |
| 6.57 | Conversation branching | Edit a previous message to create a branch. Both branches are preserved. Branch navigator shows branch tree. |
| 6.58 | Command palette | Cmd+K opens an overlay. Search across: conversations, actions (new chat, settings, export), prompts. Arrow keys navigate, Enter selects, Escape closes. |

### Usage Tracking

| # | Feature | Acceptance Criteria |
|---|---|---|
| 6.59 | Per-message token display | Each assistant message shows input tokens, output tokens, and estimated cost in a collapsible footer. |
| 6.60 | Daily/monthly usage dashboard | Settings > Usage. Bar chart showing tokens per day for the current month. Summary: total tokens, total estimated cost, average per conversation. |
| 6.61 | Usage by model breakdown | Table showing per-model usage: total requests, input tokens, output tokens, estimated cost. |

---

## 7. Data Model

### Entity Relationship Overview

```
users 1──* projects
users 1──* conversations
users 1──* prompt_library
users 1──* api_keys
users 1──* conversation_folders

projects 1──* conversations
projects 1──* conversation_folders

conversations 1──* messages
conversations 1──* artifacts
conversations 1──* shared_conversations
conversations *──1 conversation_folder_items

messages 1──* artifacts
messages *──1 messages (parent_message_id, self-referencing for branching)

conversation_folders 1──* conversation_folder_items
conversation_folders *──1 conversation_folders (parent_folder_id, one level nesting)

usage_tracking *──1 users
usage_tracking *──1 conversations
usage_tracking *──1 messages
```

### Table: users

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | Generated server-side via `crypto.randomUUID()` |
| email | TEXT | UNIQUE, NOT NULL | Used for identification — no auth provider |
| name | TEXT | NOT NULL | Display name |
| avatar_url | TEXT | NULLABLE | URL or base64 data URI |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| last_login | TEXT (ISO 8601) | NULLABLE | Updated on each session start |
| preferences | TEXT (JSON) | NOT NULL, DEFAULT '{}' | `{ theme, font_size, message_density, code_theme }` |
| custom_instructions | TEXT | NULLABLE | Global custom instructions, max 4000 chars |

### Table: projects

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| user_id | TEXT | NOT NULL, FK → users.id ON DELETE CASCADE | |
| name | TEXT | NOT NULL | Max 100 characters |
| description | TEXT | NULLABLE | Max 500 characters |
| color | TEXT | NOT NULL, DEFAULT '#CC785C' | Hex colour for sidebar indicator |
| custom_instructions | TEXT | NULLABLE | Prepended as system message to project conversations |
| knowledge_base_path | TEXT | NULLABLE | Path to uploaded documents directory |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| updated_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| is_archived | INTEGER | NOT NULL, DEFAULT 0 | 0 = active, 1 = archived |
| is_pinned | INTEGER | NOT NULL, DEFAULT 0 | |

**Indexes**: `idx_projects_user_id` on `user_id`. `idx_projects_user_archived` on `(user_id, is_archived)`.

**Cascade**: Deleting a user deletes all their projects. Deleting a project sets `project_id = NULL` on child conversations (does not delete them).

### Table: conversations

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| user_id | TEXT | NOT NULL, FK → users.id ON DELETE CASCADE | |
| project_id | TEXT | NULLABLE, FK → projects.id ON DELETE SET NULL | NULL = unorganised conversation |
| title | TEXT | NULLABLE | NULL until auto-generated after first exchange |
| model | TEXT | NOT NULL, DEFAULT 'claude-sonnet-4-5-20250929' | Model ID used for next message |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| updated_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| last_message_at | TEXT (ISO 8601) | NULLABLE | Updated when a new message is added |
| is_archived | INTEGER | NOT NULL, DEFAULT 0 | |
| is_pinned | INTEGER | NOT NULL, DEFAULT 0 | |
| is_deleted | INTEGER | NOT NULL, DEFAULT 0 | Soft delete |
| settings | TEXT (JSON) | NOT NULL, DEFAULT '{}' | `{ temperature, max_tokens, top_p, system_prompt }` |
| token_count | INTEGER | NOT NULL, DEFAULT 0 | Running total of all message tokens |
| message_count | INTEGER | NOT NULL, DEFAULT 0 | Running count of messages |

**Indexes**: `idx_conversations_user_id` on `user_id`. `idx_conversations_project_id` on `project_id`. `idx_conversations_user_deleted` on `(user_id, is_deleted)`. `idx_conversations_last_message` on `last_message_at DESC`.

**Cascade**: Deleting a user deletes all their conversations. Deleting a conversation cascades to messages, artifacts, shared_conversations, conversation_folder_items, and usage_tracking.

### Table: messages

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| conversation_id | TEXT | NOT NULL, FK → conversations.id ON DELETE CASCADE | |
| role | TEXT | NOT NULL, CHECK(role IN ('user', 'assistant', 'system')) | |
| content | TEXT | NOT NULL | Message text content |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| edited_at | TEXT (ISO 8601) | NULLABLE | Set when user edits a message |
| tokens | INTEGER | NULLABLE | Actual token count from API response |
| finish_reason | TEXT | NULLABLE | 'end_turn', 'max_tokens', 'stop_sequence', NULL for user messages |
| images | TEXT (JSON) | NULLABLE | Array of `{ data: base64, media_type: string }` |
| parent_message_id | TEXT | NULLABLE, FK → messages.id ON DELETE SET NULL | For conversation branching |

**Indexes**: `idx_messages_conversation_id` on `conversation_id`. `idx_messages_created_at` on `(conversation_id, created_at)`.

**Cascade**: Deleting a conversation deletes all its messages. Deleting a parent message sets `parent_message_id = NULL` on child branch messages (preserves branches).

### Table: artifacts

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| message_id | TEXT | NOT NULL, FK → messages.id ON DELETE CASCADE | |
| conversation_id | TEXT | NOT NULL, FK → conversations.id ON DELETE CASCADE | Denormalised for query performance |
| type | TEXT | NOT NULL, CHECK(type IN ('code', 'html', 'svg', 'react', 'mermaid', 'text')) | |
| title | TEXT | NOT NULL | Display name for the artifact |
| identifier | TEXT | NOT NULL | Stable ID for versioning across re-prompts |
| language | TEXT | NULLABLE | Programming language for code artifacts |
| content | TEXT | NOT NULL | Raw artifact content |
| version | INTEGER | NOT NULL, DEFAULT 1 | Increments on each update to same identifier |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| updated_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

**Indexes**: `idx_artifacts_message_id` on `message_id`. `idx_artifacts_conversation_id` on `conversation_id`. `idx_artifacts_identifier` on `(conversation_id, identifier, version)`.

**Cascade**: Deleting a message or conversation deletes associated artifacts.

### Table: shared_conversations

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| conversation_id | TEXT | NOT NULL, FK → conversations.id ON DELETE CASCADE | |
| share_token | TEXT | NOT NULL, UNIQUE | URL-safe random token (32 chars) |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| expires_at | TEXT (ISO 8601) | NULLABLE | NULL = never expires |
| view_count | INTEGER | NOT NULL, DEFAULT 0 | Incremented on each view |
| is_public | INTEGER | NOT NULL, DEFAULT 1 | |

**Indexes**: `idx_shared_token` on `share_token`.

### Table: prompt_library

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| user_id | TEXT | NOT NULL, FK → users.id ON DELETE CASCADE | |
| title | TEXT | NOT NULL | Max 200 characters |
| description | TEXT | NULLABLE | |
| prompt_template | TEXT | NOT NULL | Template text, may include `{{placeholders}}` |
| category | TEXT | NOT NULL | One of: coding, writing, analysis, creative, general |
| tags | TEXT (JSON) | NOT NULL, DEFAULT '[]' | Array of string tags |
| is_public | INTEGER | NOT NULL, DEFAULT 0 | |
| usage_count | INTEGER | NOT NULL, DEFAULT 0 | |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| updated_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### Table: conversation_folders

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| user_id | TEXT | NOT NULL, FK → users.id ON DELETE CASCADE | |
| project_id | TEXT | NULLABLE, FK → projects.id ON DELETE CASCADE | NULL = root-level folder |
| name | TEXT | NOT NULL | Max 100 characters |
| parent_folder_id | TEXT | NULLABLE, FK → conversation_folders.id ON DELETE CASCADE | One level of nesting maximum |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| position | INTEGER | NOT NULL, DEFAULT 0 | Sort order within parent |

### Table: conversation_folder_items

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| folder_id | TEXT | NOT NULL, FK → conversation_folders.id ON DELETE CASCADE | |
| conversation_id | TEXT | NOT NULL, FK → conversations.id ON DELETE CASCADE | |

**Constraint**: UNIQUE on `(folder_id, conversation_id)`.

### Table: usage_tracking

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| user_id | TEXT | NOT NULL, FK → users.id ON DELETE CASCADE | |
| conversation_id | TEXT | NOT NULL, FK → conversations.id ON DELETE CASCADE | |
| message_id | TEXT | NOT NULL, FK → messages.id ON DELETE CASCADE | |
| model | TEXT | NOT NULL | Model ID used for this request |
| input_tokens | INTEGER | NOT NULL | From API response `usage.input_tokens` |
| output_tokens | INTEGER | NOT NULL | From API response `usage.output_tokens` |
| cost_estimate | REAL | NOT NULL | Calculated: (input_tokens * input_price + output_tokens * output_price) |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

**Indexes**: `idx_usage_user_id` on `user_id`. `idx_usage_created_at` on `created_at`. `idx_usage_model` on `model`.

### Table: api_keys

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | TEXT (UUID) | PRIMARY KEY | |
| user_id | TEXT | NOT NULL, FK → users.id ON DELETE CASCADE | |
| key_name | TEXT | NOT NULL | User-assigned label |
| api_key_hash | TEXT | NOT NULL | SHA-256 hash of the actual key |
| created_at | TEXT (ISO 8601) | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| last_used_at | TEXT (ISO 8601) | NULLABLE | |
| is_active | INTEGER | NOT NULL, DEFAULT 1 | |

---

## 8. Data Flows

### Message Submission Flow

```
User types message → Frontend validates (non-empty, under token limit)
  → POST /api/conversations/:id/messages { content, images? }
  → Backend inserts user message into `messages` table
  → Backend opens SSE connection to Claude API with conversation history
  → Backend streams chunks to frontend via SSE on GET /api/messages/stream
  → Frontend appends chunks to assistant message bubble in real-time
  → On stream completion:
    → Backend inserts complete assistant message into `messages` table
    → Backend updates conversation.last_message_at, token_count, message_count
    → Backend inserts usage_tracking row with token counts
    → Backend scans response for artifact blocks and inserts into `artifacts` table
    → Frontend receives [DONE] event, enables regenerate button
```

### Artifact Rendering Pipeline

```
Claude response contains artifact block (detected by <artifact> tags or long code fence)
  → Backend extracts: type, title, identifier, language, content
  → Backend checks for existing artifact with same identifier in conversation
    → If exists: increment version number
    → If new: create with version 1
  → Backend inserts artifact row and includes artifact metadata in SSE stream
  → Frontend receives artifact metadata event
  → Frontend opens artifact panel and routes to appropriate renderer:
    → code → highlight.js with language detection
    → html/svg → sandboxed iframe with srcdoc
    → react → sandboxed iframe with React/ReactDOM + Babel transpilation
    → mermaid → mermaid.js render to SVG
    → text → react-markdown renderer
```

### Conversation Sync Pattern

All data is persisted to SQLite immediately — there is no optimistic local-only state. The frontend fetches conversation state from the backend on every navigation.

```
User clicks conversation in sidebar
  → GET /api/conversations/:id (metadata + settings)
  → GET /api/conversations/:id/messages (full message history)
  → GET /api/conversations/:id/artifacts (all artifacts for the conversation)
  → Frontend renders messages and populates artifact panel if artifacts exist
```

### Streaming Protocol Detail

```
Frontend: EventSource('GET /api/messages/stream?conversationId=X&messageId=Y')

Backend SSE events:
  event: message_start
  data: { "message_id": "uuid", "model": "claude-sonnet-4-5-20250929" }

  event: content_delta
  data: { "text": "partial text chunk" }

  event: artifact_start
  data: { "artifact_id": "uuid", "type": "code", "title": "...", "language": "typescript" }

  event: artifact_delta
  data: { "content": "partial artifact content" }

  event: artifact_end
  data: { "artifact_id": "uuid", "version": 1 }

  event: message_end
  data: { "finish_reason": "end_turn", "usage": { "input_tokens": 150, "output_tokens": 423 } }

  event: error
  data: { "code": "rate_limit", "message": "Rate limit exceeded. Retry after 30 seconds." }
```

### Caching Strategy

- **No application-level cache** — SQLite is fast enough for single-user scenarios
- **Conversation list**: Fetched fresh on sidebar mount and after any mutation (create, delete, rename)
- **Message history**: Fetched once per conversation switch. Appended locally during streaming. Not re-fetched unless user refreshes
- **Artifacts**: Loaded with messages. Version history fetched on-demand when user opens version selector

---

## 9. API Contracts

### Authentication

**POST /api/auth/login**
```
Request:  { "email": "string", "name": "string" }
Response: { "user": { "id": "uuid", "email": "string", "name": "string", "preferences": {} } }
Status:   200 OK | 400 Bad Request
Notes:    Creates user if not exists. No password — single-user local app.
```

**GET /api/auth/me**
```
Request:  (none — user identified by session or default user)
Response: { "user": { "id": "uuid", "email": "string", "name": "string", "preferences": {}, "custom_instructions": "string|null" } }
Status:   200 OK | 404 Not Found
```

**PUT /api/auth/profile**
```
Request:  { "name"?: "string", "avatar_url"?: "string", "preferences"?: {} }
Response: { "user": { ...updated fields } }
Status:   200 OK | 400 Bad Request
```

### Conversations

**GET /api/conversations**
```
Request:  Query params: ?project_id=uuid&is_archived=0&search=query&limit=50&offset=0
Response: { "conversations": [{ "id", "title", "model", "last_message_at", "message_count", "is_pinned", "is_archived", "project_id" }], "total": number }
Status:   200 OK
Notes:    Excludes is_deleted=1. Ordered by is_pinned DESC, last_message_at DESC.
```

**POST /api/conversations**
```
Request:  { "project_id"?: "uuid", "model"?: "string", "settings"?: { "temperature": 1.0, "max_tokens": 4096 } }
Response: { "conversation": { "id", "title": null, "model", "settings", "created_at" } }
Status:   201 Created
```

**GET /api/conversations/:id**
```
Response: { "conversation": { ...all fields } }
Status:   200 OK | 404 Not Found
```

**PUT /api/conversations/:id**
```
Request:  { "title"?: "string", "model"?: "string", "settings"?: {}, "project_id"?: "uuid|null" }
Response: { "conversation": { ...updated fields } }
Status:   200 OK | 404 Not Found
```

**DELETE /api/conversations/:id**
```
Response: { "success": true }
Status:   200 OK | 404 Not Found
Notes:    Soft delete — sets is_deleted=1.
```

**POST /api/conversations/:id/duplicate**
```
Response: { "conversation": { ...new conversation with copied messages } }
Status:   201 Created
Notes:    Copies all messages and artifacts. Title appended with "(Copy)".
```

**POST /api/conversations/:id/export**
```
Request:  { "format": "json" | "markdown" | "pdf" }
Response: File download with appropriate Content-Type and Content-Disposition headers.
Status:   200 OK | 404 Not Found
```

**PUT /api/conversations/:id/archive**
```
Request:  { "is_archived": true | false }
Response: { "conversation": { ...updated } }
Status:   200 OK
```

**PUT /api/conversations/:id/pin**
```
Request:  { "is_pinned": true | false }
Response: { "conversation": { ...updated } }
Status:   200 OK
```

**POST /api/conversations/:id/branch**
```
Request:  { "from_message_id": "uuid", "new_content": "string" }
Response: { "message": { ...new user message }, "branch_id": "uuid" }
Status:   201 Created
Notes:    Creates a new message with parent_message_id pointing to the message before from_message_id.
```

### Messages

**GET /api/conversations/:id/messages**
```
Request:  Query params: ?branch_id=uuid (optional — filters to specific branch)
Response: { "messages": [{ "id", "role", "content", "created_at", "edited_at", "tokens", "finish_reason", "images", "parent_message_id" }] }
Status:   200 OK
Notes:    Ordered by created_at ASC. Includes system messages.
```

**POST /api/conversations/:id/messages**
```
Request:  { "content": "string", "images"?: [{ "data": "base64", "media_type": "image/png" }] }
Response: Initiates SSE stream (see Streaming Protocol in section 8).
Status:   200 OK (SSE stream) | 400 Bad Request | 429 Rate Limited
Notes:    This endpoint both inserts the user message and triggers the Claude API call.
```

**PUT /api/messages/:id**
```
Request:  { "content": "string" }
Response: { "message": { ...updated, "edited_at": "ISO8601" } }
Status:   200 OK | 404 Not Found
Notes:    Only user messages can be edited.
```

**DELETE /api/messages/:id**
```
Response: { "success": true }
Status:   200 OK | 404 Not Found
```

**POST /api/messages/:id/regenerate**
```
Response: Initiates SSE stream with new Claude response.
Status:   200 OK (SSE stream)
Notes:    Deletes the existing assistant message and creates a new one.
```

### Artifacts

**GET /api/conversations/:id/artifacts**
```
Response: { "artifacts": [{ "id", "message_id", "type", "title", "identifier", "language", "version", "created_at" }] }
Status:   200 OK
Notes:    Returns latest version of each artifact by default. Content excluded for performance — fetch individually.
```

**GET /api/artifacts/:id**
```
Response: { "artifact": { ...all fields including content } }
Status:   200 OK | 404 Not Found
```

**PUT /api/artifacts/:id**
```
Request:  { "content": "string" }
Response: { "artifact": { ...updated, new version number } }
Status:   200 OK
Notes:    Creates a new version, does not overwrite existing.
```

**GET /api/artifacts/:id/versions**
```
Response: { "versions": [{ "version", "created_at", "content" }] }
Status:   200 OK
```

### Projects

**GET /api/projects**
```
Response: { "projects": [{ "id", "name", "description", "color", "is_archived", "is_pinned", "conversation_count" }] }
Status:   200 OK
```

**POST /api/projects**
```
Request:  { "name": "string", "description"?: "string", "color"?: "#hex", "custom_instructions"?: "string" }
Response: { "project": { ...all fields } }
Status:   201 Created
```

**PUT /api/projects/:id**
```
Request:  { "name"?: "string", "description"?: "string", "color"?: "#hex", "custom_instructions"?: "string" }
Response: { "project": { ...updated } }
Status:   200 OK | 404 Not Found
```

**DELETE /api/projects/:id**
```
Response: { "success": true }
Status:   200 OK
Notes:    Conversations in the project have project_id set to NULL (not deleted).
```

**POST /api/projects/:id/knowledge**
```
Request:  multipart/form-data with file upload
Response: { "file": { "name": "string", "size": number, "path": "string" } }
Status:   201 Created | 413 Payload Too Large (>50KB)
```

### Sharing

**POST /api/conversations/:id/share**
```
Request:  { "expires_at"?: "ISO8601" }
Response: { "share_token": "string", "url": "string" }
Status:   201 Created
```

**GET /api/share/:token**
```
Response: { "conversation": { "title", "messages": [...], "artifacts": [...] } }
Status:   200 OK | 404 Not Found | 410 Gone (expired)
Notes:    Increments view_count. No authentication required.
```

### Search

**GET /api/search/conversations?q=query**
```
Response: { "results": [{ "conversation_id", "title", "snippet", "matched_on": "title|content" }] }
Status:   200 OK
Notes:    Searches conversation titles and message content. Returns max 20 results.
```

### Claude API Proxy

**POST /api/claude/chat/stream**
```
Request:  { "conversation_id": "uuid", "message": "string", "images"?: [...] }
Response: SSE stream (see section 8 Streaming Protocol)
Status:   200 OK | 400 Bad Request | 429 Rate Limited | 500 API Error
```

**GET /api/claude/models**
```
Response: { "models": [{ "id", "name", "context_window", "input_price_per_1m", "output_price_per_1m" }] }
Status:   200 OK
```

### Settings

**GET /api/settings**
```
Response: { "preferences": { "theme", "font_size", "message_density", "code_theme" }, "custom_instructions": "string|null" }
Status:   200 OK
```

**PUT /api/settings**
```
Request:  { "preferences"?: {}, "custom_instructions"?: "string" }
Response: { ...updated settings }
Status:   200 OK
```

### Usage

**GET /api/usage/daily**
```
Request:  Query params: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
Response: { "daily": [{ "date": "YYYY-MM-DD", "input_tokens": number, "output_tokens": number, "cost_estimate": number, "request_count": number }] }
Status:   200 OK
```

**GET /api/usage/by-model**
```
Response: { "models": [{ "model": "string", "total_requests": number, "input_tokens": number, "output_tokens": number, "cost_estimate": number }] }
Status:   200 OK
```

### Folders

**GET /api/folders**
```
Response: { "folders": [{ "id", "name", "parent_folder_id", "project_id", "position", "conversation_ids": ["uuid"] }] }
Status:   200 OK
```

**POST /api/folders**
```
Request:  { "name": "string", "project_id"?: "uuid", "parent_folder_id"?: "uuid" }
Response: { "folder": { ...all fields } }
Status:   201 Created
```

**POST /api/folders/:id/items**
```
Request:  { "conversation_id": "uuid" }
Response: { "success": true }
Status:   200 OK
```

---

## 10. Design System

### Colour Tokens

| Token | Light Mode | Dark Mode | Usage |
|---|---|---|---|
| `--color-primary` | `#CC785C` | `#CC785C` | Primary accent, CTA buttons, active states |
| `--color-primary-hover` | `#B8674D` | `#D98B6F` | Button hover state |
| `--color-bg` | `#FFFFFF` | `#1A1A1A` | Page background |
| `--color-surface` | `#F5F5F5` | `#2A2A2A` | Cards, sidebar, input backgrounds |
| `--color-surface-hover` | `#EBEBEB` | `#333333` | Hover state on surface elements |
| `--color-surface-active` | `#E0E0E0` | `#3D3D3D` | Active/selected sidebar items |
| `--color-text` | `#1A1A1A` | `#E5E5E5` | Primary text |
| `--color-text-secondary` | `#6B6B6B` | `#999999` | Timestamps, labels, help text |
| `--color-text-tertiary` | `#999999` | `#666666` | Placeholders, disabled text |
| `--color-border` | `#E5E5E5` | `#404040` | Dividers, input borders, card borders |
| `--color-border-focus` | `#CC785C` | `#CC785C` | Focus ring on inputs |
| `--color-code-bg` | `#F6F8FA` | `#1E1E1E` | Code block background |
| `--color-user-bubble` | `#F0EDE8` | `#3A3530` | User message bubble background |
| `--color-error` | `#DC2626` | `#EF4444` | Error messages, destructive actions |
| `--color-success` | `#16A34A` | `#22C55E` | Success indicators, confirmed actions |
| `--color-warning` | `#D97706` | `#F59E0B` | Warnings, approaching limits |

### Typography Scale

| Element | Size | Weight | Line Height | Font |
|---|---|---|---|---|
| Page title | 24px (text-2xl) | 600 (semibold) | 1.3 | System sans-serif |
| Section heading | 18px (text-lg) | 600 (semibold) | 1.4 | System sans-serif |
| Body / messages | 16px (text-base) | 400 (normal) | 1.7 (leading-relaxed) | System sans-serif |
| Small / metadata | 13px (text-sm) | 400 (normal) | 1.5 | System sans-serif |
| Caption / timestamp | 12px (text-xs) | 400 (normal) | 1.4 | System sans-serif |
| Code inline | 14px | 400 (normal) | 1.5 | JetBrains Mono, Consolas, Monaco, monospace |
| Code block | 14px | 400 (normal) | 1.6 | JetBrains Mono, Consolas, Monaco, monospace |
| Input text | 16px (text-base) | 400 (normal) | 1.5 | System sans-serif |

**System sans-serif stack**: `Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`

### Spacing System

Base unit: 4px. All spacing uses multiples of 4.

| Token | Value | Usage |
|---|---|---|
| `space-1` | 4px | Inline icon gaps, tight padding |
| `space-2` | 8px | Between related items (button icon + label) |
| `space-3` | 12px | Input padding, small card padding |
| `space-4` | 16px | Standard card padding, message gaps (comfortable density) |
| `space-5` | 20px | Section spacing within modals |
| `space-6` | 24px | Between sections, spacious message density |
| `space-8` | 32px | Major layout gaps (sidebar sections) |
| `space-10` | 40px | Page-level padding |

### Component Variants

**Buttons**

| Variant | Background | Text | Border | Border Radius | Padding |
|---|---|---|---|---|---|
| Primary | `--color-primary` | white | none | 8px | 8px 16px |
| Secondary | transparent | `--color-text` | 1px `--color-border` | 8px | 8px 16px |
| Ghost | transparent | `--color-text-secondary` | none | 8px | 8px 12px |
| Destructive | `--color-error` | white | none | 8px | 8px 16px |
| Icon | transparent | `--color-text-secondary` | none | 6px | 8px |
| Disabled (any) | opacity 0.5 | — | — | — | pointer-events: none |

**Message Bubbles**

| Variant | Background | Alignment | Max Width | Padding | Border Radius |
|---|---|---|---|---|---|
| User | `--color-user-bubble` | right | 80% | 12px 16px | 16px 16px 4px 16px |
| Assistant | transparent | left | 80% | 12px 0 | none |
| System | `--color-surface` | centre | 90% | 8px 12px | 8px |

**Inputs**

| State | Border | Background | Shadow |
|---|---|---|---|
| Default | 1px `--color-border` | `--color-surface` | none |
| Focus | 2px `--color-border-focus` | `--color-bg` | 0 0 0 3px rgba(204, 120, 92, 0.15) |
| Error | 2px `--color-error` | `--color-bg` | 0 0 0 3px rgba(220, 38, 38, 0.15) |
| Disabled | 1px `--color-border` | `--color-surface` | none, opacity 0.6 |

---

## 11. UI Pages & Layout

### Main Layout (Three-Column)

```
┌──────────────────────────────────────────────────────────┐
│ ┌─────────┐ ┌──────────────────────┐ ┌────────────────┐ │
│ │ Sidebar │ │     Chat Area        │ │  Artifact      │ │
│ │  260px   │ │    flex-1 (fill)     │ │   Panel        │ │
│ │          │ │                      │ │   480px        │ │
│ │          │ │                      │ │                │ │
│ │          │ │                      │ │  (hidden when  │ │
│ │          │ │                      │ │   no artifact) │ │
│ └─────────┘ └──────────────────────┘ └────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Responsive Breakpoints

| Breakpoint | Width | Layout | Changes |
|---|---|---|---|
| Mobile | < 768px | Single column | Sidebar hidden behind hamburger menu (slides in as overlay). Artifact panel opens as full-screen overlay. Input area fixed to bottom. Send button larger (48x48px touch target). |
| Tablet | 768px–1199px | Two columns | Sidebar 240px, collapsible. Chat fills remaining width. Artifact panel opens as overlay (slides from right, 60% width). |
| Desktop | >= 1200px | Three columns | Sidebar 260px (resizable 200–400px). Chat fills middle. Artifact panel 480px (resizable 320–640px). Both sidebar and panel collapsible. |

### Sidebar (Left)

| Element | Position | Details |
|---|---|---|
| New Chat button | Top, full width | Height 40px. Primary button variant. Icon: plus sign. |
| Project selector | Below New Chat | Dropdown. Shows current project name or "All Conversations". |
| Search input | Below project selector | Height 36px. Placeholder: "Search conversations...". Magnifying glass icon. |
| Conversation list | Scrollable area | Grouped by date headers (Today, Yesterday, Previous 7 Days, etc.). Each item: title (truncated at 1 line), relative timestamp, model icon. Active item has `--color-surface-active` background. |
| Folder tree | Interspersed with conversations | Collapsible folder headers with caret icon. Indented 16px per nesting level. |
| Settings link | Bottom, pinned | Gear icon + "Settings" label. Separated by border-top. |
| User profile | Bottom, below settings | Avatar (32px circle) + name. |

### Chat Area (Centre)

| Element | Position | Details |
|---|---|---|
| Header bar | Top, fixed | Height 56px. Contains: conversation title (editable on click), model selector badge, settings gear icon. Border-bottom. |
| Message area | Scrollable, fills height | Messages rendered top-to-bottom. Auto-scrolls to bottom on new message. "Scroll to bottom" FAB appears when user scrolls up more than 200px. Padding: 24px horizontal, 16px between messages. |
| Welcome screen | Centre of message area | Shown when conversation has no messages. Contains: greeting, 4 example prompt cards in a 2x2 grid, brief description of capabilities. |
| Input area | Bottom, fixed | Textarea with auto-resize. Max height: 200px. Attachment button (left). Send/Stop button (right, 36x36px). Character count below textarea. Border-top. Padding: 16px. |

### Artifact Panel (Right)

| Element | Position | Details |
|---|---|---|
| Header | Top, fixed | Height 48px. Artifact title + type badge (e.g., "TypeScript", "HTML"). Close button (X) on right. |
| Tab bar | Below header | Tabs when multiple artifacts exist. Each tab: artifact title truncated to 20 chars. Active tab underlined with `--color-primary`. |
| Toolbar | Below tabs | Full-screen toggle, download button, version selector dropdown, edit/re-prompt button. Height 40px. |
| Content area | Scrollable, fills height | Renders based on artifact type. Code: syntax-highlighted with line numbers. Preview: sandboxed iframe. |

### Modals

All modals: centred overlay, max-width 640px, max-height 80vh, backdrop with rgba(0,0,0,0.5), border-radius 12px, padding 24px. Close on Escape key or backdrop click.

| Modal | Trigger | Content |
|---|---|---|
| Settings | Sidebar gear icon | Tabbed: General, Appearance, Custom Instructions, API Keys, Usage, Keyboard Shortcuts. |
| Share | Right-click > Share | Toggle public link, copy URL button, expiration date picker, view count display. |
| Export | Right-click > Export | Three format cards (JSON, Markdown, PDF) with descriptions. Click to download. |
| Project Settings | Project gear icon | Tabbed: General, Instructions, Knowledge Base, Danger Zone. |
| Command Palette | Cmd+K | Search input at top, results list below. Sections: Conversations, Actions, Prompts. |

---

## 12. Component States

### Message Bubble

| State | Visual |
|---|---|
| Default | Content rendered with markdown. Hover reveals action icons (edit, copy, regenerate) in top-right corner. |
| Streaming | Content appears character by character. No action icons visible. Cursor blink animation at end of text. |
| Edited | Small "(edited)" label in `--color-text-tertiary` below message content. |
| Error | Red-tinted background. Error message text: "Failed to generate response. Click to retry." Retry icon button. |
| Branch indicator | Small branch icon with "Branch A" / "Branch B" label. Click to switch branches. |

### Artifact Viewer

| State | Visual |
|---|---|
| Loading | Skeleton loader: three animated grey bars (60%, 80%, 40% width) pulsing. |
| Empty | Grey dashed border box. Text: "No artifacts in this conversation." |
| Rendered (code) | Syntax-highlighted code with line numbers. Scroll for long content. |
| Rendered (preview) | Sandboxed iframe showing live HTML/React output. |
| Preview error | Red banner at top of preview area: "Preview failed to render: [error message]". Raw code shown below. |
| Full-screen | Panel expands to 100vw. Chat area hidden. "Exit Full Screen" button in toolbar. |

### Sidebar Conversation Item

| State | Visual |
|---|---|
| Default | Title text + relative timestamp. Padding 8px 12px. |
| Hover | Background: `--color-surface-hover`. Three-dot menu icon appears on right. |
| Active/Selected | Background: `--color-surface-active`. Left border: 3px solid `--color-primary`. |
| Pinned | Pin icon before title. Appears above date-grouped sections. |
| Archived | Italic title. Greyed out. Only visible when "Show Archived" is toggled on. |
| Rename mode | Title replaced with text input. Focus ring visible. Enter to save, Escape to cancel. |

### Model Selector

| State | Visual |
|---|---|
| Default | Badge showing current model name (e.g., "Sonnet 4.5"). Chevron-down icon. |
| Open | Dropdown with three model options. Each shows: model name, context window, price tier. Selected model has check mark. |
| Disabled (during streaming) | Badge greyed out, no chevron. Tooltip: "Cannot change model while generating." |

### Input Area

| State | Visual |
|---|---|
| Empty | Placeholder text: "Message Claude...". Send button disabled (greyed out). |
| Has content | Send button enabled (primary colour). Character count visible below. |
| Streaming | Send button replaced with Stop button (red square icon). Textarea disabled. |
| Image attached | Image thumbnail(s) appear above the textarea with X button to remove each. |
| Error | Red border on textarea. Error text below: specific message (e.g., "Message too long — reduce to under 100,000 characters"). |

### Settings Modal

| State | Visual |
|---|---|
| Loading | Skeleton loaders for each settings section. |
| Default | Tabs with current settings values populated. Save button disabled until changes are made. |
| Dirty (unsaved changes) | Save button enabled (primary colour). Dot indicator on the modified tab. |
| Saving | Save button shows spinner. Inputs disabled during save. |
| Saved | Brief green "Saved" toast notification (2 seconds). Save button returns to disabled. |

---

## 13. Interactions & Animations

### Message Send

1. User presses Enter or clicks Send
2. User message fades in from bottom (opacity 0→1, translateY 8px→0, 200ms ease-out)
3. Send button transforms to Stop button (crossfade, 150ms)
4. Typing indicator fades in at assistant position (200ms)
5. First chunk arrives — typing indicator fades out (100ms), assistant message bubble fades in (150ms)
6. Text streams character by character — no animation per character, just DOM text append
7. On completion, action icons (copy, regenerate) fade in (200ms delay after final chunk)

### Typing Indicator

Three dots bouncing in sequence. Each dot: 6px diameter, `--color-text-tertiary`. Animation: translateY 0→-6px→0, 600ms ease-in-out, each dot delayed 150ms from the previous.

### Artifact Panel Slide-In

Panel slides from right: translateX(100%)→translateX(0), 300ms ease-out. Chat area shrinks to accommodate (width transition 300ms). On close: reverse animation.

### Sidebar Collapse

Sidebar width transitions from 260px→0, 250ms ease-in-out. Content fades out (opacity 150ms). Toggle button remains visible as a floating hamburger icon in the top-left.

### Modal Transitions

Open: backdrop fades in (opacity 0→1, 200ms). Modal scales up from 0.95→1.0 and fades in (opacity + transform, 200ms ease-out). Close: reverse, 150ms.

### Code Block Copy Feedback

User clicks copy button → button icon changes from clipboard to checkmark → text "Copied!" appears briefly → reverts to clipboard icon after 2 seconds. Transition: crossfade, 150ms.

### Scroll-to-Bottom

When user scrolls up >200px from bottom, a circular "scroll to bottom" button fades in at bottom-right of chat area (opacity 0→1, 200ms). Click: smooth scroll to bottom (behavior: smooth). On reaching bottom: button fades out.

### Drag-and-Drop (Conversations to Folders)

Drag start: conversation item lifts with box-shadow, slight scale (1.02). Drag over folder: folder background highlights with `--color-primary` at 10% opacity, border becomes dashed. Drop: item animates into folder position. Folder expands if collapsed.

### Context Menu

Right-click on conversation: menu appears at cursor position. Fade in + scale from 0.95 (150ms). Items: hover background `--color-surface-hover`. Click: menu fades out (100ms), action executes.

---

## 14. Content & Copy

### Tone of Voice

Neutral, concise, helpful. No exclamation marks. No "great" or "awesome". Match the understated, professional tone of claude.ai itself.

### Page Titles

- Welcome screen: "How can I help you today?"
- Settings modal: "Settings"
- Share modal: "Share conversation"
- Export modal: "Export conversation"
- Command palette: placeholder "Search conversations, actions, and prompts..."
- Usage dashboard: "Usage"

### Button Labels

| Button | Label |
|---|---|
| New conversation | "New chat" |
| Send message | "Send" (sr-only — icon-only button) |
| Stop generation | "Stop" (sr-only — icon-only button) |
| Regenerate response | "Regenerate" |
| Edit message | "Edit" |
| Copy message | "Copy" |
| Copy code block | "Copy code" |
| Download artifact | "Download" |
| Full-screen artifact | "Full screen" |
| Close artifact panel | "Close" |
| Save settings | "Save" |
| Cancel | "Cancel" |
| Delete conversation | "Delete" |
| Confirm delete | "Delete conversation" |
| Share | "Create link" |
| Copy share link | "Copy link" |
| Export JSON | "Export as JSON" |
| Export Markdown | "Export as Markdown" |
| Export PDF | "Export as PDF" |

### Empty State Messages

| Context | Message |
|---|---|
| No conversations | "No conversations yet. Start a new chat to begin." |
| No search results | "No conversations match your search." |
| No artifacts | "No artifacts in this conversation." |
| No projects | "No projects yet. Create one to organise your conversations." |
| Empty folder | "This folder is empty. Drag conversations here to organise them." |
| No usage data | "No usage data yet. Start a conversation to begin tracking." |
| Prompt library empty | "Your prompt library is empty. Save prompts from conversations or create new ones." |

### Error Messages

| Error | User-Facing Message |
|---|---|
| API key invalid | "Invalid API key. Check your key at console.anthropic.com and try again." |
| API key missing | "No API key configured. Add your Anthropic API key in Settings > API Keys." |
| Rate limited (429) | "Rate limit reached. Waiting [N] seconds before retrying..." |
| Claude API error (500) | "Claude is temporarily unavailable. Try again in a moment." |
| Network disconnected | "Connection lost. Check your internet and try again." |
| Message too long | "Message exceeds the maximum length. Shorten your message and try again." |
| Context window exceeded | "This conversation is too long for the selected model. Start a new conversation or switch to a model with a larger context window." |
| File too large | "File exceeds the 5MB limit. Choose a smaller file." |
| Unsupported file type | "Unsupported file type. Accepted formats: PNG, JPEG, GIF, WebP." |
| Export failed | "Export failed. Try again or choose a different format." |

### Placeholder Text

| Input | Placeholder |
|---|---|
| Chat input | "Message Claude..." |
| Search conversations | "Search conversations..." |
| Conversation title | "Untitled conversation" |
| Project name | "Project name" |
| Project description | "Describe this project..." |
| Custom instructions | "Add instructions that Claude should follow in every conversation..." |
| Folder name | "Folder name" |
| Prompt title | "Prompt title" |
| Prompt template | "Write your prompt template here. Use {{variable}} for placeholders..." |
| Command palette | "Search conversations, actions, and prompts..." |

### Tooltip Text

| Element | Tooltip |
|---|---|
| Temperature slider | "Controls randomness. Lower values (0.0) produce more focused responses. Higher values (1.0) produce more creative responses." |
| Max tokens slider | "Maximum number of tokens in Claude's response. One token is roughly 4 characters." |
| Top-p slider | "Controls diversity via nucleus sampling. 1.0 considers all tokens. Lower values focus on more likely tokens." |
| Thinking mode toggle | "When enabled, Claude shows its reasoning process before answering." |
| Token count | "Estimated tokens for this message. Actual count may differ slightly." |
| Pin conversation | "Pin to top of sidebar" |
| Archive conversation | "Move to archive" |

### Onboarding Copy

Welcome screen (shown on first visit):

**Heading**: "How can I help you today?"

**Example prompt cards** (2x2 grid):
1. "Explain quantum computing in simple terms" — category: Learning
2. "Write a Python function to sort a list of dictionaries by a key" — category: Coding
3. "Help me draft a professional email to decline a meeting" — category: Writing
4. "Compare the pros and cons of React vs Vue for a new project" — category: Analysis

---

## 15. Auth & Permissions

### Authentication Model

This is a single-user, self-hosted application. There is no multi-user authentication system. The app creates a default user on first launch and uses that user for all operations.

### API Key Validation Flow

```
1. User enters API key in settings or welcome screen
2. Frontend sends POST /api/auth/validate-key { key: "sk-ant-..." }
3. Backend makes a minimal Claude API request (e.g., "Hi" with max_tokens: 1)
4. If 200: key is valid
   → Backend hashes key with SHA-256 and stores hash in api_keys table
   → Backend stores encrypted key in environment or secure config for runtime use
   → Frontend shows success indicator and proceeds
5. If 401: key is invalid
   → Frontend shows error: "Invalid API key."
6. If 403: key lacks permissions
   → Frontend shows error: "API key lacks required permissions."
7. If 429: rate limited during validation
   → Frontend shows error: "Rate limited. Try again in a moment."
```

### Session Management

- No login/logout flow — user is always authenticated as the default user
- Session state is client-side only (React state + localStorage for preferences)
- API key is loaded from server environment on startup — never sent to the frontend after initial validation
- All API requests from frontend to backend are unauthenticated (single-user assumption)

### What Happens When API Key Is Invalid or Expired

- On startup, backend validates the stored API key
- If invalid: backend returns 401 on any Claude proxy request
- Frontend catches 401 and shows a banner: "Your API key is no longer valid. Update it in Settings > API Keys."
- All chat functionality is disabled until a valid key is provided
- Conversation browsing, search, and export continue to work (no API key needed for local data)

---

## 16. Error States & Edge Cases

### Claude API Errors

| Error | Status | Handling |
|---|---|---|
| Rate limit exceeded | 429 | Display warning with countdown timer based on `retry-after` header. Auto-retry when timer expires. Show partial response if streaming had started. |
| Server error | 500 | Display "Claude is temporarily unavailable. Try again in a moment." Show retry button. Log error details to console. |
| Overloaded | 529 | Display "Claude is experiencing high demand. Try again shortly." Do not auto-retry — let user decide. |
| Invalid request | 400 | Display specific error from API response body. Common cause: malformed message content or unsupported image format. |
| Context window exceeded | 400 (specific) | Display "This conversation exceeds the context window for [model]. Start a new conversation or switch to a model with more context." Offer model switch inline. |

### Network Errors

| Scenario | Handling |
|---|---|
| Network disconnection mid-stream | Keep partial response visible. Show banner: "Connection lost. Partial response saved." Reconnect button attempts to resume (or re-send last message). |
| Backend server down | Frontend shows "Unable to connect to server. Make sure the backend is running on port [PORT]." Check connection every 5 seconds silently. Remove banner when connection restored. |
| SSE connection timeout (>60s no data) | Close connection. Display "Response timed out. Try again or try a shorter prompt." |

### Rendering Errors

| Scenario | Handling |
|---|---|
| Malformed markdown in response | react-markdown renders what it can. Unparseable sections display as raw text. Never crash the UI. |
| Invalid LaTeX | Display raw LaTeX source with light red background. Small label: "LaTeX error". |
| Artifact code fails to preview | Preview pane shows error message from the sandbox. Code view remains available. Toggle defaults to code view on error. |
| Mermaid syntax error | Display error message from mermaid.js parser. Show raw source below for reference. |
| HTML artifact with scripts | Scripts blocked by sandbox. Display warning: "Scripts are disabled in preview for security." |

### Data Edge Cases

| Scenario | Handling |
|---|---|
| Conversation title auto-generation fails | Title stays NULL. Display "Untitled conversation" in sidebar. User can rename manually. |
| SQLite write conflict (concurrent writes) | better-sqlite3 is synchronous and serialised — this cannot occur in normal operation. If the DB file is locked by another process, return 503 with "Database is temporarily locked. Try again." |
| Conversation with 1000+ messages | Paginate message loading: load last 100 messages on open, "Load earlier messages" button at top. |
| Very long message (>50KB) | Render with virtual scrolling or truncated display with "Show full message" expander. |
| Image paste with unsupported format | Show error inline below input: "Unsupported image format. Use PNG, JPEG, GIF, or WebP." |
| Duplicate conversation titles | Allowed — conversations are identified by UUID, not title. |
| Delete last conversation in folder | Folder remains. Shows empty state message. |
| Delete project with conversations | Conversations remain with `project_id` set to NULL. They appear in the "All Conversations" view. |

---

## 17. Accessibility

### Keyboard Navigation Map

| Key | Action | Context |
|---|---|---|
| Tab | Move focus to next interactive element | Global |
| Shift+Tab | Move focus to previous interactive element | Global |
| Enter | Send message / Confirm action / Select menu item | Input area / Modal / Menu |
| Shift+Enter | Insert newline | Input area |
| Escape | Close modal / Close artifact panel / Cancel edit | Global |
| Cmd+K | Open command palette | Global |
| Cmd+N | New conversation | Global |
| Cmd+/ | Toggle sidebar | Global |
| Arrow Up/Down | Navigate conversation list / menu items | Sidebar / Dropdown |
| Arrow Left/Right | Switch between artifact tabs | Artifact panel |
| Home/End | Jump to first/last conversation | Sidebar |

### Screen Reader Announcements

| Event | Announcement (aria-live="polite") |
|---|---|
| Message sent | "Message sent. Waiting for response." |
| Streaming starts | "Claude is responding." |
| Streaming complete | "Response complete. [N] tokens used." |
| Artifact detected | "Artifact generated: [title]. Artifact panel opened." |
| Conversation switched | "Switched to conversation: [title]." |
| Error occurred | "Error: [error message]" |
| Conversation deleted | "Conversation deleted." |
| Settings saved | "Settings saved." |

### ARIA Labels

| Element | aria-label |
|---|---|
| Send button | "Send message" |
| Stop button | "Stop generating" |
| New chat button | "Start new conversation" |
| Sidebar toggle | "Toggle sidebar" |
| Search input | "Search conversations" |
| Model selector | "Select AI model" |
| Theme toggle | "Switch theme" |
| Artifact close | "Close artifact panel" |
| Artifact full screen | "Toggle full screen" |
| Copy code button | "Copy code to clipboard" |
| Conversation item | "Conversation: [title], [timestamp]" |
| Regenerate button | "Regenerate response" |
| Edit button | "Edit message" |
| Delete button | "Delete conversation" |
| Settings button | "Open settings" |

### Focus Management

- **Modal open**: Focus moves to first focusable element inside the modal. Focus is trapped within the modal (Tab cycles within modal only). On close, focus returns to the element that opened the modal.
- **Artifact panel open**: Focus moves to the artifact panel header. Panel is included in the Tab order.
- **Conversation switch**: Focus moves to the chat input area.
- **Message sent**: Focus remains on the chat input area.
- **Delete confirmation**: Focus moves to the "Cancel" button (not the destructive action).

### Reduced Motion

When `prefers-reduced-motion: reduce` is active:
- All transitions set to 0ms duration
- Typing indicator uses opacity blink instead of bounce
- No slide animations for sidebar or artifact panel — instant show/hide
- No message fade-in — instant render
- Scroll-to-bottom uses instant scroll instead of smooth scroll

### Minimum Contrast Ratios

- Normal text: 4.5:1 minimum (WCAG AA)
- Large text (18px+ or 14px+ bold): 3:1 minimum
- Interactive element boundaries: 3:1 against adjacent colours
- All colour token pairs verified for both light and dark mode

---

## 18. Testing Scenarios

### TS-01: Send a message and receive a streaming response

**Given** a user with a valid API key and an open conversation
**When** they type "Hello" in the input field and press Enter
**Then** the user message appears immediately in the chat, a typing indicator shows below it, Claude's response streams in character by character, and the typing indicator disappears when the first chunk arrives. After completion, the regenerate button appears on the assistant message.

### TS-02: Stop generation mid-stream

**Given** a streaming response is in progress
**When** the user clicks the Stop button
**Then** streaming stops immediately, the partial response is preserved and displayed, the Stop button reverts to the Send button, and the user can send a new message.

### TS-03: Artifact detection and rendering

**Given** a user asks Claude to "Create an HTML page with a styled button"
**When** Claude's response includes an artifact block with type "html"
**Then** the artifact panel slides in from the right, the HTML renders in a sandboxed iframe in the preview tab, the code tab shows the raw HTML with syntax highlighting, and the download button saves the file as `.html`.

### TS-04: Create and switch conversations

**Given** a user with an existing conversation open
**When** they click "New chat" in the sidebar
**Then** a new empty conversation opens with the welcome screen, the previous conversation appears in the sidebar under the appropriate date group, and clicking the previous conversation restores its full message history.

### TS-05: Search conversations

**Given** a user with 10+ conversations, one titled "Python sorting algorithms"
**When** they type "sorting" in the sidebar search input
**Then** the conversation list filters to show only matching conversations, "sorting" is highlighted in the matched title, and clearing the search restores the full list.

### TS-06: Edit a user message and branch

**Given** a conversation with at least one user-assistant exchange
**When** the user hovers over their first message, clicks edit, changes the text, and clicks "Save & Resubmit"
**Then** a new branch is created, Claude generates a new response to the edited message, the original branch is preserved and accessible via the branch navigator, and the user can switch between branches.

### TS-07: API key validation failure

**Given** a user on the welcome screen
**When** they enter an invalid API key (e.g., "invalid-key")
**Then** the app displays "Invalid API key. Check your key at console.anthropic.com and try again.", the input field shows an error state (red border), and chat functionality remains disabled.

### TS-08: Rate limit handling

**Given** a user sending messages rapidly
**When** the Claude API returns a 429 status with `retry-after: 30`
**Then** the app displays "Rate limit reached. Waiting 30 seconds before retrying...", a countdown timer is visible, the message auto-retries when the timer expires, and no duplicate messages are created.

### TS-09: Dark mode toggle

**Given** a user in light mode
**When** they open Settings > Appearance and select "Dark"
**Then** the entire UI transitions to dark mode colours without page reload, the theme preference is persisted (survives browser refresh), and all colour tokens update correctly (backgrounds, text, borders, code blocks).

### TS-10: Export conversation as Markdown

**Given** a conversation with 5 messages and 2 code blocks
**When** the user right-clicks the conversation and selects "Export > Markdown"
**Then** a `.md` file downloads with all messages formatted as markdown, code blocks preserved with language annotations, user messages prefixed with "**User:**", and assistant messages prefixed with "**Claude:**".

### TS-11: Project custom instructions applied

**Given** a project with custom instructions "Always respond in bullet points"
**When** the user creates a new conversation in that project and sends a message
**Then** Claude's response follows the custom instructions (uses bullet points), and the system prompt sent to the API includes the project's custom instructions.

### TS-12: Mobile responsive layout

**Given** a viewport width of 375px (mobile)
**When** the page loads
**Then** the sidebar is hidden, a hamburger menu icon is visible in the top-left, tapping the hamburger slides in the sidebar as an overlay, and the input area is fixed to the bottom of the screen with a 48x48px send button.

### TS-13: Keyboard navigation

**Given** focus is on the chat input
**When** the user presses Cmd+K
**Then** the command palette opens with focus on its search input. Pressing Escape closes it and returns focus to the chat input. Arrow keys navigate results. Enter selects the highlighted result.

### TS-14: Network disconnection during streaming

**Given** a streaming response is in progress
**When** the network connection drops
**Then** the partial response is preserved, a banner appears: "Connection lost. Partial response saved.", and a "Retry" button allows re-sending the last message.

### TS-15: Conversation exceeds context window

**Given** a conversation with 100,000+ tokens of history using Claude Haiku (200K context)
**When** the user sends a message that pushes the total past the context limit
**Then** the API returns an error, the app displays "This conversation exceeds the context window for Claude Haiku 4.5. Start a new conversation or switch to a model with more context.", and a "Switch to Opus" shortcut button is shown inline.

---

## 19. External Integrations

### Anthropic Claude API

| Aspect | Detail |
|---|---|
| **Base URL** | `https://api.anthropic.com/v1` |
| **Auth** | `x-api-key` header with the user's API key |
| **API version** | `2023-06-01` (via `anthropic-version` header) |
| **SDK** | `@anthropic-ai/sdk` (Node.js) |
| **Endpoint used** | `POST /v1/messages` (both streaming and non-streaming) |
| **Streaming** | `stream: true` in request body. Response is SSE with `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop` events. |
| **Models** | `claude-sonnet-4-5-20250929` (default), `claude-haiku-4-5-20251001`, `claude-opus-4-1-20250805` |
| **Max output tokens** | Sonnet: 8192, Haiku: 8192, Opus: 4096 (check current docs — these change) |
| **Image support** | `source.type: "base64"`, `source.media_type: "image/png|image/jpeg|image/gif|image/webp"` |
| **Rate limits** | Tier-dependent. Handle 429 responses with `retry-after` header. |
| **Error codes** | 400 (invalid request), 401 (auth error), 403 (permission), 429 (rate limit), 500 (server error), 529 (overloaded) |

### No Other External Integrations

This is a self-contained application. No analytics, no error tracking services, no external auth providers, no CDN for user-uploaded content. All data stays local in SQLite.

---

## 20. Anti-Patterns

### TypeScript / JavaScript

1. **Do not use `any` type.** Use `unknown` with type narrowing, or define proper interfaces for all data shapes.
2. **Do not use `as` type casting** unless there is genuinely no alternative. Prefer type guards and discriminated unions.
3. **Do not use `useEffect` for data fetching.** Fetch data in event handlers, on mount via a custom hook with cleanup, or through a data-fetching library.
4. **Do not store the raw API key in React state or localStorage.** The API key lives on the backend only. Frontend never sees the decrypted key after initial validation.
5. **Do not use `dangerouslySetInnerHTML` to render Claude's responses.** Use react-markdown with sanitisation plugins. Arbitrary HTML from an LLM is an XSS vector.
6. **Do not block the main thread during markdown parsing.** For very long messages (>10KB), parse markdown in a Web Worker or use incremental rendering.
7. **Do not use inline styles when a Tailwind class exists for the same property.** Consistency over convenience.
8. **Do not create God components.** If a component exceeds 200 lines, extract sub-components. The chat area, sidebar, and artifact panel should each be composed of smaller components.
9. **Do not swallow errors with empty catch blocks.** Every catch must either handle the error (show to user, retry) or re-throw.
10. **Do not use `console.log` in production code.** Use a structured logger or remove before committing.

### Backend / API

11. **Do not expose the Anthropic API key in any API response.** The key is server-side only. Responses never include it.
12. **Do not proxy Claude API requests without rate-limit handling.** Always check for 429 responses and surface the retry-after delay to the frontend.
13. **Do not use raw SQL string concatenation.** Use parameterised queries (`?` placeholders) for all user input to prevent SQL injection.
14. **Do not return raw database rows as API responses.** Map to response DTOs that exclude internal fields (e.g., `api_key_hash` should never leave the server).
15. **Do not use `SELECT *` in production queries.** Specify exact columns needed. This matters for the messages table which may contain large content fields.

### Architecture

16. **Do not store conversation history only in React state.** Every message must be persisted to SQLite before the next API call. If the browser crashes mid-conversation, no messages should be lost.
17. **Do not send the entire conversation history to the Claude API on every message without token counting.** Track cumulative tokens and warn the user before exceeding the model's context window.
18. **Do not render artifact previews (HTML, React) without sandboxing.** Use an iframe with `sandbox="allow-scripts"` and no `allow-same-origin`. This prevents Claude-generated code from accessing the parent application's DOM or cookies.
19. **Do not allow nested folders deeper than one level.** The data model supports `parent_folder_id`, but the UI is designed for a single level of nesting only. Enforce this constraint on both frontend and backend.
20. **Do not auto-retry on 500 or 529 errors.** Only auto-retry on 429 with a `retry-after` header. For server errors, let the user decide when to retry.

---

## 21. Success Criteria

### Functionality Verification

| Criteria | Verification |
|---|---|
| Streaming chat works end-to-end | Send a message, observe character-by-character streaming, verify complete response stored in database. |
| Artifact detection is accurate | Send prompts that produce code, HTML, SVG, Mermaid, and React artifacts. Verify each type renders correctly in the artifact panel. |
| Conversation CRUD is reliable | Create 10 conversations, rename 3, delete 2, archive 1, pin 1. Verify sidebar reflects all operations. Refresh page — state persists. |
| Project organisation works | Create 2 projects with custom instructions. Move conversations between them. Verify instructions apply. Delete a project — conversations survive with null project_id. |
| Image upload displays correctly | Upload PNG, JPEG, and WebP images. Verify they display in the message and are sent to Claude. Verify Claude responds with image-aware content. |
| Export produces valid output | Export a conversation with code blocks in all three formats. Verify JSON is valid and parseable, Markdown renders correctly in a viewer, PDF is readable. |
| Search returns relevant results | Create 5 conversations on different topics. Search for keywords. Verify results are relevant and snippets highlight the match. |
| Model switching persists | Switch models mid-conversation. Verify the new model is used for the next message. Verify the model badge on each message shows the correct model. |

### User Experience Verification

| Criteria | Verification |
|---|---|
| Interface matches claude.ai design language | Side-by-side comparison of sidebar, chat area, input field, and message bubbles. Colour palette, typography, and spacing match the design tokens specified in section 10. |
| Responsive on all device sizes | Test at 375px (mobile), 768px (tablet), 1440px (desktop). Verify layout changes match section 11 breakpoint specifications. |
| Animations are smooth | All transitions run at 60fps. Test sidebar collapse, modal open/close, artifact panel slide, message fade-in. No jank or flash of unstyled content. |
| Latency is acceptable | Time from Enter to first streamed character: under 2 seconds on a standard connection. Conversation switch: under 500ms for conversations with <100 messages. Sidebar search: results appear within 300ms of typing. |
| Dark mode is complete | Switch to dark mode. Verify every surface, text colour, border, code block, and modal uses dark mode tokens. No white flashes. No unreadable text. |

### Technical Quality Verification

| Criteria | Verification |
|---|---|
| No unhandled errors in console | Use the app for 30 minutes across all features. Browser console shows zero errors (warnings acceptable for third-party libraries). |
| Error handling covers all API states | Test with: invalid API key (401), rate limiting (429 — use a script to trigger), network disconnection (disable network mid-stream). Verify user-facing error messages match section 16. |
| Database integrity | After 50+ conversations with edits, branches, deletes, and project moves: run `PRAGMA integrity_check` — result is "ok". All foreign key constraints hold. |
| API key security | Verify API key never appears in: frontend source, network requests (except initial validation), API response bodies, browser localStorage, browser sessionStorage. |
| Streaming efficiency | During a long response (>2000 tokens), monitor memory usage. Should not grow unboundedly. DOM updates should batch — not one re-render per character. |
| Code quality | No `any` types in TypeScript. No unused imports. No console.log statements. All components under 200 lines. All API endpoints return typed responses. |
