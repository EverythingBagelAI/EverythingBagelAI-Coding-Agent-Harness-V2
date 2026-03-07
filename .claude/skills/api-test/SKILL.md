# API Testing Skill — httpx + pytest

Use this skill whenever you need to write, run, or fix backend API tests.

## When to Use This Skill

- After implementing or modifying any API route or endpoint
- After creating or changing database operations (CRUD, migrations, queries)
- After implementing auth middleware, guards, or token validation
- After building webhook handlers, background jobs, or async processors
- Before marking any backend-related issue as Done

**Use this skill instead of Playwright when:**

- The feature has no browser UI (API-only endpoint, webhook, background job)
- You need to verify HTTP status codes, response body shape, or error responses
- You need to assert database state after a mutation
- You need to test auth guards by calling endpoints directly without/with tokens

**Use Playwright instead when:**

- The feature is purely frontend (component rendering, navigation, styling)
- You need to test a full user flow through the browser

**Use both when:**

- A feature spans frontend and backend (e.g. form → API → result displayed in UI)

## Prerequisites

### Python / FastAPI

```bash
pip install pytest httpx pytest-asyncio
```

Create `pytest.ini` if it doesn't exist:

```ini
[pytest]
testpaths = api_tests
asyncio_mode = auto
```

### TypeScript / Next.js API routes

```bash
npm install -D vitest @types/node
```

Create `vitest.config.ts` if it doesn't exist:

```typescript
import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    include: ["api-tests/**/*.test.ts"],
    testTimeout: 15000,
  },
});
```

## The Four-Phase Approach

### Phase 1: Plan

Before writing any test code, answer:

1. What endpoint(s) does this issue create or modify? (HTTP method + path)
2. What is the expected success response? (status code + body shape)
3. What are the failure cases? (missing auth, invalid input, not found, conflict)
4. Does this endpoint mutate state? What follow-up GET can assert persistence?

### Phase 2: Write

- One test file per endpoint or closely related group
- Test happy path first, then error cases
- Assert status codes explicitly — never just `assert response.ok`
- Assert response body shape — check key fields exist with correct types
- For mutations, verify persistence via a follow-up GET or direct DB check
- Use pytest fixtures for shared setup (auth tokens, test clients)

### Phase 3: Run

```bash
# Python
pytest api_tests/ -v

# TypeScript
npx vitest run api-tests/
```

### Phase 4: Fix

1. Read the full error output — don't just look at the last line
2. Determine if the failure is an app bug or a test bug
3. Fix the correct one, re-run
4. Never skip or comment out a failing test without a TODO
5. Run the full suite before marking the issue Done

## Test Patterns

### Pattern 1: Auth Endpoint

```python
# api_tests/test_auth.py
import httpx, pytest

BASE_URL = "http://localhost:8000"

@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=10)

@pytest.fixture
def auth_token(client):
    r = client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "testpass123"})
    assert r.status_code == 200
    return r.json()["access_token"]

class TestLogin:
    def test_valid_credentials(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "testpass123"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_invalid_password(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "wrong"})
        assert r.status_code == 401

    def test_missing_fields(self, client):
        r = client.post("/api/v1/auth/login", json={})
        assert r.status_code == 422

class TestAuthMe:
    def test_with_valid_token(self, client, auth_token):
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        assert r.status_code == 200
        assert "id" in r.json()

    def test_without_token(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401
```

### Pattern 2: CRUD Endpoint

```python
# api_tests/test_projects.py
class TestProjectCRUD:
    def test_create(self, authed_client):
        r = authed_client.post("/api/v1/projects", json={"name": "Test", "description": "Desc"})
        assert r.status_code == 201
        assert "id" in r.json()
        assert r.json()["name"] == "Test"

    def test_create_missing_required_field(self, authed_client):
        r = authed_client.post("/api/v1/projects", json={"description": "No name"})
        assert r.status_code == 422

    def test_list(self, authed_client):
        r = authed_client.get("/api/v1/projects")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_not_found(self, authed_client):
        r = authed_client.get("/api/v1/projects/does-not-exist")
        assert r.status_code == 404

    def test_delete_then_404(self, authed_client):
        pid = authed_client.post("/api/v1/projects", json={"name": "ToDelete"}).json()["id"]
        assert authed_client.delete(f"/api/v1/projects/{pid}").status_code == 204
        assert authed_client.get(f"/api/v1/projects/{pid}").status_code == 404
```

### Pattern 3: Database State Assertion

```python
# api_tests/test_data_integrity.py
class TestDataIntegrity:
    def test_create_persists(self, authed_client):
        item_id = authed_client.post("/api/v1/items", json={"title": "Persist"}).json()["id"]
        assert authed_client.get(f"/api/v1/items/{item_id}").json()["title"] == "Persist"

    def test_update_persists(self, authed_client):
        item_id = authed_client.post("/api/v1/items", json={"title": "Before"}).json()["id"]
        authed_client.put(f"/api/v1/items/{item_id}", json={"title": "After"})
        assert authed_client.get(f"/api/v1/items/{item_id}").json()["title"] == "After"

    def test_cannot_access_other_users_data(self, authed_client, other_user_client):
        item_id = authed_client.post("/api/v1/items", json={"title": "Private"}).json()["id"]
        assert other_user_client.get(f"/api/v1/items/{item_id}").status_code in (403, 404)
```

### Pattern 4: Error Response Handling

```python
# api_tests/test_error_handling.py
class TestErrorResponses:
    def test_missing_required_field_422(self, authed_client):
        r = authed_client.post("/api/v1/items", json={})
        assert r.status_code == 422
        assert "detail" in r.json()

    def test_unauthenticated_401(self):
        r = httpx.get("http://localhost:8000/api/v1/items")
        assert r.status_code == 401

    def test_not_found_404(self, authed_client):
        assert authed_client.get("/api/v1/items/nonexistent").status_code == 404

    def test_duplicate_unique_field_409(self, authed_client):
        authed_client.post("/api/v1/items", json={"slug": "unique"})
        r = authed_client.post("/api/v1/items", json={"slug": "unique"})
        assert r.status_code == 409
```

## File Organisation

```
api_tests/
├── conftest.py            # Shared fixtures (clients, auth tokens, test users)
├── test_auth.py
├── test_[resource].py     # One file per resource/endpoint group
├── test_data_integrity.py
└── test_error_handling.py
```

### conftest.py Example

```python
# api_tests/conftest.py
import httpx
import pytest

BASE_URL = "http://localhost:8000"

@pytest.fixture(scope="session")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=10)

@pytest.fixture(scope="session")
def auth_token(client):
    r = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpass123",
    })
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]

@pytest.fixture(scope="session")
def authed_client(auth_token):
    return httpx.Client(
        base_url=BASE_URL,
        timeout=10,
        headers={"Authorization": f"Bearer {auth_token}"},
    )

@pytest.fixture(scope="session")
def other_user_client():
    """Client authenticated as a different user for isolation tests."""
    c = httpx.Client(base_url=BASE_URL, timeout=10)
    r = c.post("/api/v1/auth/login", json={
        "email": "other@example.com",
        "password": "testpass123",
    })
    assert r.status_code == 200
    c.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return c
```

## Test Isolation

Tests must not depend on each other or on pre-existing database state.

- Use unique values for fields that must be unique (e.g. `f"test-{uuid4().hex[:8]}"`)
- Create test data in each test or fixture, never assume it exists
- If your test creates records, clean them up in a fixture teardown:

```python
@pytest.fixture
def created_item(authed_client):
    r = authed_client.post("/api/v1/items", json={"title": "Test Item"})
    item_id = r.json()["id"]
    yield item_id
    authed_client.delete(f"/api/v1/items/{item_id}")  # cleanup
```

## What Passing Looks Like

```
api_tests/test_auth.py::TestLogin::test_valid_credentials PASSED
api_tests/test_auth.py::TestLogin::test_invalid_password PASSED
api_tests/test_auth.py::TestAuthMe::test_with_valid_token PASSED
====== 5 passed in 2.34s ======
```

All tests must show PASSED before the issue is marked Done.
