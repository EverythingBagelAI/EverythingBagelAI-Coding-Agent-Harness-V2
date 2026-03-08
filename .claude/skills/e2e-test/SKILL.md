# E2E Testing Skill — Playwright

Use this skill whenever you need to write, run, or fix end-to-end browser tests.

## When to Use This Skill

- After implementing any user-facing feature
- When an issue's acceptance criteria includes UI behaviour
- When debugging a feature that appears to work in code but may not in the browser
- Before marking any UI-related issue as Done

## Prerequisites

Playwright must be installed in the project. If not installed:

```bash
npm install -D @playwright/test
npx playwright install chromium
```

Create `playwright.config.ts` at project root if it doesn't exist:

```typescript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000", // override with BASE_URL env var
    headless: true,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
});
```

> **Note:** Set `BASE_URL` to match your dev server port (Vite: 5173, FastAPI: 8000, Next.js: 3000).

## The Four-Phase Testing Approach

### Phase 1: Plan

Before writing any test code, think through:

1. What is the user flow being tested? (e.g. "User logs in, creates a conversation, sends a message, sees streaming response")
2. What are the entry points? (URL to navigate to)
3. What are the success states? (What elements should be visible/contain what text?)
4. What are the failure states to check? (Error messages, empty states)

Write a brief comment block at the top of the test file documenting this plan.

### Phase 2: Write

Write the test. Key rules:

- Use `page.getByRole`, `page.getByText`, `page.getByLabel` over CSS selectors — they are more resilient
- Use `await expect(locator).toBeVisible()` not `await page.waitForSelector()`
- Use `await expect(page).toHaveURL()` to assert navigation
- Add `await page.waitForLoadState('networkidle')` after navigation when testing dynamic content
- Group related tests in `test.describe` blocks
- One `test()` per user flow — not per assertion

### Phase 3: Run

```bash
npx playwright test [filename]
```

### Phase 4: Fix

If tests fail:

1. Read the error output carefully — Playwright gives precise failure reasons
2. Check if the failure is an **app bug** (feature doesn't work) or a **test bug** (wrong selector, wrong timing)
3. For app bugs: fix the feature code, re-run
4. For test bugs: fix the selector or add appropriate waits, re-run
5. Never mark `test.skip()` without a TODO comment explaining why
6. Run `npx playwright test` (full suite) before marking any issue Done — ensure you haven't broken previous tests

## Common Patterns

### Testing a form submission

```typescript
test("user can submit contact form", async ({ page }) => {
  await page.goto("/contact");
  await page.getByLabel("Name").fill("Jordan Test");
  await page.getByLabel("Email").fill("test@example.com");
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("Message sent")).toBeVisible();
});
```

### Testing navigation

```typescript
test("sidebar navigation works", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
});
```

### Testing streaming/async content

```typescript
test("chat response streams in", async ({ page }) => {
  await page.goto("/chat");
  await page.getByRole("textbox").fill("Hello");
  await page.getByRole("button", { name: "Send" }).click();
  // Wait for streaming to complete — look for the stop button to disappear
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop" })).not.toBeVisible({
    timeout: 30000,
  });
  // Now assert the response content
  await expect(page.locator(".assistant-message")).not.toBeEmpty();
});
```

### Testing authentication flows

```typescript
test("unauthenticated user is redirected to login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL("/login");
});
```

## File Organisation

```
e2e/
├── auth.spec.ts          # Authentication flows
├── navigation.spec.ts    # Sidebar, routing, page loads
├── chat.spec.ts          # Core chat functionality
├── [feature].spec.ts     # One file per major feature area
```

## Running Tests

```bash
npx playwright test                    # Run all tests
npx playwright test auth.spec.ts       # Run one file
npx playwright test --headed           # Watch mode (see browser)
npx playwright test --reporter=list    # Verbose output
```

## What Passing Looks Like

```
  ✓ homepage loads and shows navigation (843ms)
  ✓ user can sign in and see dashboard (1204ms)
  ✓ form submission shows success message (967ms)

  3 passed (3.1s)
```

When all tests show ✓ and the summary line shows N passed with no failures, the test requirement is met.

## Shared Setup with beforeEach

For tests that share setup steps (e.g. logging in before every test):

```javascript
test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.fill("[name=email]", "test@example.com");
  await page.fill("[name=password]", "testpass123");
  await page.click("[type=submit]");
  await page.waitForURL("/dashboard");
});
```

Use `test.describe` blocks to scope `beforeEach` to a group of related tests.

## When Tests Cannot Be Written

Tests may be skipped ONLY for:

- Third-party OAuth flows that require human interaction (e.g. Google sign-in)
- Hardware-dependent features (camera, microphone, bluetooth)
- Features that require a human to physically complete a step

Do NOT skip tests for:

- Streaming responses (test that streaming starts and content arrives)
- Animation or transitions (test the end state)
- "Complex" features (simplify the test scope instead)

If you believe a test cannot be written, document the specific reason as a
code comment before proceeding.
