"""
Direct Linear API client for harness orchestration.
Used by the Python orchestrator for state queries — NOT by the agent.
The agent continues to use the Linear MCP for issue management.
"""

import os
import time
from typing import Optional

import httpx

LINEAR_API_URL = "https://api.linear.app/graphql"


def _headers() -> dict:
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        raise EnvironmentError("LINEAR_API_KEY not set")
    return {"Authorization": api_key, "Content-Type": "application/json"}


MAX_RETRIES = 3


def _query(query: str, variables: dict | None = None) -> dict:
    headers = _headers()
    last_response = None
    for attempt in range(MAX_RETRIES):
        response = httpx.post(
            LINEAR_API_URL,
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=30,
        )
        last_response = response
        if response.status_code == 429:
            retry_after = int(response.headers.get("retry-after", str(2 ** attempt)))
            print(f"  Linear rate limited. Retrying in {retry_after}s...")
            time.sleep(retry_after)
            continue
        if response.status_code >= 500 and attempt < MAX_RETRIES - 1:
            print(f"  Linear server error ({response.status_code}). Retrying in {2 ** attempt}s...")
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise RuntimeError(f"Linear API error: {data['errors']}")
        return data["data"]
    last_response.raise_for_status()
    return {}


def get_current_issue(project_id: str) -> Optional[dict]:
    """
    Fetch the highest-priority incomplete issue in the project
    that is NOT a Human Gate or Snapshot issue.

    Returns dict with: id, title, description, priority, state.name
    Returns None if no eligible issues remain.
    """
    query = """
    query GetIssues($projectId: String!) {
      project(id: $projectId) {
        issues(
          filter: {
            state: { type: { nin: ["completed", "cancelled"] } }
          }
          orderBy: priority
        ) {
          nodes {
            id
            title
            description
            priority
            state { name type }
          }
        }
      }
    }
    """
    data = _query(query, {"projectId": project_id})
    issues = data["project"]["issues"]["nodes"]
    for issue in issues:
        title = issue["title"]
        if title.startswith("[HUMAN GATE]") or title.startswith("[SNAPSHOT]"):
            continue
        return issue
    return None


def get_human_gate_issue(project_id: str) -> Optional[dict]:
    """
    Find the most recent [HUMAN GATE] issue in the project.
    Returns dict with id, title, description, state.type
    Returns None if not found.
    """
    query = """
    query GetHumanGate($projectId: String!) {
      project(id: $projectId) {
        issues(
          filter: { title: { startsWith: "[HUMAN GATE]" } }
          orderBy: createdAt
        ) {
          nodes {
            id
            title
            description
            state { name type }
          }
        }
      }
    }
    """
    data = _query(query, {"projectId": project_id})
    issues = data["project"]["issues"]["nodes"]
    return issues[-1] if issues else None


def is_human_gate_resolved(issue_id: str) -> bool:
    """Returns True if the gate issue state type is 'completed'."""
    query = """
    query GetIssue($id: String!) {
      issue(id: $id) {
        state { type }
      }
    }
    """
    data = _query(query, {"id": issue_id})
    return data["issue"]["state"]["type"] == "completed"


def get_snapshot_issue(project_id: str) -> Optional[dict]:
    """Get the [SNAPSHOT] issue for a project."""
    query = """
    query GetProjectIssues($projectId: String!) {
        project(id: $projectId) {
            issues {
                nodes {
                    id
                    title
                    description
                    state { type name }
                }
            }
        }
    }
    """
    data = _query(query, {"projectId": project_id})
    project = data.get("project")
    if not project:
        return None
    issues = project.get("issues", {}).get("nodes", [])
    for issue in issues:
        if "[SNAPSHOT]" in issue.get("title", "").upper():
            return issue
    return None


def get_all_issues_complete(project_id: str) -> bool:
    """
    Returns True if all non-gate, non-snapshot issues in the project
    are in a completed or cancelled state.
    """
    query = """
    query GetAllIssues($projectId: String!) {
      project(id: $projectId) {
        issues {
          nodes {
            title
            state { type }
          }
        }
      }
    }
    """
    data = _query(query, {"projectId": project_id})
    issues = data["project"]["issues"]["nodes"]
    for issue in issues:
        title = issue["title"]
        if title.startswith("[HUMAN GATE]") or title.startswith("[SNAPSHOT]"):
            continue
        if issue["state"]["type"] not in ("completed", "cancelled"):
            return False
    return True
