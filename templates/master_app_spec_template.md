# Master App Spec Template

Copy this file to `prompts/master_app_spec.md` and fill it in. Keep the total under 1,500 words. The Architect Agent will expand it into full epic specs.

---

# [App Name]

## Purpose

[2-3 sentences. What does this app do? Who is it for? What is the single most important thing it does?]

## Tech Stack

- Frontend: [e.g. Next.js 15 with App Router, TypeScript, Tailwind CSS, shadcn/ui]
- Backend: [e.g. FastAPI, Python, or Next.js API routes]
- Database: [e.g. Supabase (PostgreSQL)]
- Auth: [e.g. Clerk]
- Deployment: [e.g. Vercel (frontend), Render (backend)]
- Key libraries: [e.g. Stripe for payments, Resend for email]

## Key User Flows

[Numbered list. 5-15 items. Describe what a user actually does — not features, flows.]

1. User signs up and completes onboarding
2. User creates a [resource]
3. User [does main action]
   ...

## Feature List

[Numbered list. One sentence each. 10-30 items. Group loosely by epic.]

### Foundation

1. [Feature]
2. [Feature]

### [Core Feature Area]

3. [Feature]
4. [Feature]

### [Another Area]

...

## Core Data Model

[Key entities only. 3-8 items. List key fields — not full schema.]

- **User**: id, email, name, created_at, preferences
- **[Entity]**: id, user_id, [key fields]

## External Services

[List each third-party service or API the app uses]

- [Service]: [what it's used for]
- Ref MCP: look up documentation for any library before implementing
- Playwright: all browser-based feature testing

## Design System

- Primary colour: [hex or description]
- Component library: [e.g. shadcn/ui with Tailwind]
- Layout: [e.g. sidebar + main content, full-width, etc.]
- Theme: [light/dark/both]

## Anti-Patterns

[5-10 things the agent must never do in this specific project]

- Never use `any` TypeScript type
- Never store API keys in client-side code
- [Project-specific patterns to avoid]

## Success Criteria

[What does "done" mean for the full app? 5-8 specific criteria]

- All user flows testable end-to-end with Playwright
- [Specific functionality criterion]
