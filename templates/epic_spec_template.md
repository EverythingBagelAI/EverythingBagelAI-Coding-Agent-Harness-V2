# Epic Spec Template

This is the format the Architect Agent produces for each epic. You can edit generated epic specs before running the harness.

---

# Epic N: [Name]

## Meta

- depends_on: [epic numbers, or "none"]
- builds: [2-sentence summary of what this epic produces]
- estimated_issues: [10-25]

## Purpose

[2-3 sentences. What does this epic achieve?]

## Features

[Numbered list. One sentence each. These become Linear issues.]

1. [Feature]
2. [Feature]

## UI/UX Notes

[Epic-specific UI decisions. Reference shared_context.md design system rather than repeating it.]

## Data Model

[Only tables/entities introduced or changed in this epic. Key fields only.]

## API Contracts

[Only endpoints created or consumed in this epic.]

## External Integrations

- Use Ref (`ref_search_documentation`) to look up: [specific libraries used in this epic]
- Use Playwright for all browser-based feature testing
- [Other MCPs by intent, not implementation]

## Testing Criteria

[5-10 acceptance criteria. Format: "Given [state], when [action], then [outcome]."]

1. Given a logged-in user, when they [action], then [outcome]

## Human Gate

[Include only if NOT the final epic. The Architect Agent auto-generates this based on what the next epic needs.]

### Required before Epic [N+1] can proceed:

- [ ] [ENV_VAR]: [description and where to get it]
- [ ] [Manual step]: [instructions]

When complete, mark this issue Done in Linear and re-run:
`python autonomous_agent_demo.py --project-dir ./my-project --mode epic`
