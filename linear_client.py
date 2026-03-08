"""
Direct Linear API client for harness orchestration.
Used by the Python orchestrator for state queries — NOT by the agent.
The agent continues to use the Linear MCP for issue management.
"""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_PROJECT_MARKER = ".linear_project.json"
MAX_RETRIES = 3

HUMAN_GATE_MARKER = "[HUMAN GATE]"
SNAPSHOT_MARKER = "[SNAPSHOT]"


def _parse_retry_after(headers, fallback: int) -> int:
    """Safely parse retry-after header, falling back to provided default."""
    value = headers.get("retry-after", "")
    try:
        return max(1, int(float(value)))
    except (ValueError, TypeError):
        return fallback


def _headers() -> dict:
    """Return authorisation headers for the Linear GraphQL API."""
    from linear_config import get_linear_api_key
    api_key = get_linear_api_key()
    return {"Authorization": api_key, "Content-Type": "application/json"}


async def _query(query: str, variables: dict | None = None) -> dict:
    """Execute a GraphQL query against the Linear API with retry and backoff."""
    logger.debug("Linear API query: %.100s", query.strip())
    headers = _headers()
    last_response = None
    for attempt in range(MAX_RETRIES):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LINEAR_API_URL,
                json={"query": query, "variables": variables or {}},
                headers=headers,
                timeout=30,
            )
        last_response = response
        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers, 2 ** attempt)
            print(f"  Linear rate limited. Retrying in {retry_after}s...")
            await asyncio.sleep(retry_after)
            continue
        if response.status_code >= 500 and attempt < MAX_RETRIES - 1:
            print(f"  Linear server error ({response.status_code}). Retrying in {2 ** attempt}s...")
            await asyncio.sleep(2 ** attempt)
            continue
        if response.status_code >= 400:
            logger.error(
                "Linear API error %s: %s",
                response.status_code,
                response.text[:200],
            )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise RuntimeError(f"Linear API error: {data['errors']}")
        return data["data"]
    logger.error(
        "Linear API retries exhausted, last status %s: %s",
        last_response.status_code,
        last_response.text[:200],
    )
    last_response.raise_for_status()


async def _get_all_issues(project_id: str) -> list[dict]:
    """Fetch ALL issues for a project, paginating through results."""
    query = """
    query GetProjectIssues($projectId: String!, $after: String) {
        project(id: $projectId) {
            issues(first: 250, after: $after) {
                nodes {
                    id
                    title
                    description
                    priority
                    state { name type }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
    }
    """
    all_issues = []
    cursor = None

    while True:
        data = await _query(query, {"projectId": project_id, "after": cursor})
        project = data.get("project")
        if not project:
            return []

        issues_data = project.get("issues", {})
        all_issues.extend(issues_data.get("nodes", []))

        page_info = issues_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return all_issues


def filter_current_issue(issues: list[dict]) -> Optional[dict]:
    """Filter pre-fetched issues to find the highest-priority incomplete non-meta issue."""
    eligible = []
    for issue in issues:
        title = issue["title"]
        if title.upper().startswith(HUMAN_GATE_MARKER) or title.upper().startswith(SNAPSHOT_MARKER):
            continue
        state_type = issue.get("state", {}).get("type", "")
        if state_type in ("completed", "cancelled"):
            continue
        eligible.append(issue)
    if not eligible:
        return None
    eligible.sort(key=lambda i: i.get("priority", 0) or 999)
    return eligible[0]


def filter_human_gate_issue(issues: list[dict]) -> Optional[dict]:
    """Filter pre-fetched issues to find the human gate issue."""
    gate_issues = [i for i in issues if i["title"].upper().startswith(HUMAN_GATE_MARKER)]
    return gate_issues[-1] if gate_issues else None


def filter_all_issues_complete(issues: list[dict]) -> bool:
    """Check if all non-gate, non-snapshot issues are completed/cancelled."""
    if not issues:
        return False
    for issue in issues:
        title = issue["title"]
        if title.upper().startswith(HUMAN_GATE_MARKER) or title.upper().startswith(SNAPSHOT_MARKER):
            continue
        if issue.get("state", {}).get("type", "") not in ("completed", "cancelled"):
            return False
    return True


def filter_snapshot_issue(issues: list[dict]) -> Optional[dict]:
    """Filter pre-fetched issues to find the snapshot issue."""
    for issue in issues:
        if issue.get("title", "").upper().startswith(SNAPSHOT_MARKER):
            return issue
    return None


async def get_current_issue(project_id: str) -> Optional[dict]:
    """
    Fetch the highest-priority incomplete issue in the project
    that is NOT a Human Gate or Snapshot issue.

    Returns dict with: id, title, description, priority, state.name
    Returns None if no eligible issues remain.
    """
    issues = await _get_all_issues(project_id)
    return filter_current_issue(issues)


async def get_human_gate_issue(project_id: str) -> Optional[dict]:
    """
    Find the most recent [HUMAN GATE] issue in the project.
    Returns dict with id, title, description, state.type
    Returns None if not found.
    """
    issues = await _get_all_issues(project_id)
    return filter_human_gate_issue(issues)


async def is_human_gate_resolved(issue_id: str) -> bool:
    """Returns True if the gate issue state type is 'completed'."""
    query = """
    query GetIssue($id: String!) {
      issue(id: $id) {
        state { type }
      }
    }
    """
    data = await _query(query, {"id": issue_id})
    issue = data.get("issue")
    if not issue:
        return False
    state = issue.get("state", {})
    return state.get("type") == "completed"


async def get_snapshot_issue(project_id: str) -> Optional[dict]:
    """Get the [SNAPSHOT] issue for a project."""
    issues = await _get_all_issues(project_id)
    return filter_snapshot_issue(issues)


async def get_all_issues_complete(project_id: str) -> bool:
    """
    Returns True if all non-gate, non-snapshot issues in the project
    are in a completed or cancelled state.
    """
    issues = await _get_all_issues(project_id)
    if not issues:
        logger.warning("Project %s returned no issues from Linear API", project_id)
        return False
    return filter_all_issues_complete(issues)
