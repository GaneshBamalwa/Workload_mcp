"""Jira connector for issue ingestion.

NOTE: atlassian-python-api is fully synchronous. All API calls are wrapped
in asyncio.to_thread() so they don't block the MCP event loop.

Authentication:
  Jira Cloud  → basic auth with user email + API token
  Jira Server → basic auth with username + password

Required env vars:
  JIRA_URL        e.g. https://yourcompany.atlassian.net
  JIRA_EMAIL      e.g. dev@yourcompany.com
  JIRA_API_TOKEN  API token from https://id.atlassian.com/manage-profile/security/api-tokens
"""
import asyncio
from datetime import datetime
from typing import Any, Optional

import structlog
from atlassian import Jira

from app.connectors.base import BaseConnector, UnifiedWorkItem

logger = structlog.get_logger(__name__)

# Jira priority → urgency score
PRIORITY_TO_URGENCY = {
    "Blocker": 1.0,
    "Critical": 0.95,
    "Highest": 0.9,
    "High": 0.75,
    "Medium": 0.5,
    "Low": 0.3,
    "Lowest": 0.1,
}


class JiraConnector(BaseConnector):
    """Jira connector for issue ingestion."""

    connector_type = "jira"
    scope_required = []

    def __init__(self, url: str, user_email: str, api_token: str):
        """Initialize Jira connector.

        Args:
            url:       Jira base URL, e.g. https://yourcompany.atlassian.net
            user_email: Email address of the Jira user
            api_token: API token (NOT OAuth client secret)
        """
        # BaseConnector expects (access_token, user_id)
        super().__init__(access_token=api_token, user_id=user_email)
        self.url = url
        self.user_email = user_email
        self.api_token = api_token
        # Jira() is sync – we call its methods via asyncio.to_thread()
        self.client = Jira(url=url, username=user_email, password=api_token, cloud=True)
        logger.debug("Jira connector initialized", url=url, user=user_email)

    async def test_connection(self) -> bool:
        """Test Jira connection."""
        try:
            info = await asyncio.to_thread(self.client.get_server_info)
            logger.info("Jira connection test successful", server=info.get("baseUrl"))
            return True
        except Exception as e:
            logger.error("Jira connection test failed", error=str(e))
            return False

    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get open Jira issues assigned to the current user."""
        try:
            jql_parts = [
                f'assignee = "{self.user_email}"',
                'statusCategory != Done',
            ]
            if sync_cursor:
                jql_parts.append(f'updated >= "{sync_cursor}"')

            jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"

            response = await asyncio.to_thread(
                self.client.jql,
                jql,
                limit=min(limit, 100),
                fields=[
                    "summary", "description", "status", "priority",
                    "assignee", "duedate", "created", "updated",
                    "issuetype", "project", "labels",
                ],
            )

            issues: list[dict] = response.get("issues", [])
            next_cursor = None
            if issues:
                # Use the last updated date as the next incremental cursor
                next_cursor = issues[-1].get("fields", {}).get("updated")

            logger.info("Fetched issues from Jira", count=len(issues))
            return issues, next_cursor

        except Exception as e:
            logger.error("Jira fetch failed", error=str(e))
            raise

    async def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize Jira issue to unified work item."""
        fields = item.get("fields", {})
        key = item.get("key", "")
        summary = fields.get("summary", "")
        description = fields.get("description") or ""
        if isinstance(description, dict):
            # Jira Cloud returns description as Atlassian Document Format (ADF)
            description = _extract_adf_text(description)

        priority = fields.get("priority") or {}
        priority_name = priority.get("name", "Medium")
        urgency = PRIORITY_TO_URGENCY.get(priority_name, 0.5)

        due_date = None
        if fields.get("duedate"):
            try:
                due_date = datetime.fromisoformat(fields["duedate"])
            except (ValueError, TypeError):
                pass

        status = fields.get("status") or {}
        status_name = status.get("name", "")
        requires_response = status_name.lower() not in ["done", "closed", "resolved", "cancelled"]

        assignee = fields.get("assignee") or {}
        project = fields.get("project") or {}

        work_item = UnifiedWorkItem(
            source="jira",
            source_id=key,
            title=f"[{key}] {summary}",
            description=description[:500] if description else None,
            urgency=urgency,
            importance=0.8,
            created_by=assignee.get("emailAddress") or assignee.get("displayName"),
            requires_response=requires_response,
            requires_deep_work=True,
            confidence_score=0.95,
            category="bug" if fields.get("issuetype", {}).get("name", "").lower() == "bug" else "task",
            due_date=due_date,
            metadata={
                "jira_key": key,
                "status": status_name,
                "priority": priority_name,
                "project": project.get("key"),
                "issue_type": fields.get("issuetype", {}).get("name"),
                "labels": fields.get("labels", []),
                "url": f"{self.url}/browse/{key}",
            },
        )
        return work_item.to_dict()


def _extract_adf_text(node: Any, depth: int = 0) -> str:
    """Recursively extract plain text from Atlassian Document Format (ADF) JSON."""
    if depth > 10:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        parts = []
        for child in node.get("content", []):
            parts.append(_extract_adf_text(child, depth + 1))
        return " ".join(p for p in parts if p)
    if isinstance(node, list):
        return " ".join(_extract_adf_text(n, depth + 1) for n in node)
    return ""


class JiraConnectorFactory:
    """Factory for creating Jira connectors."""

    @staticmethod
    def create_from_credentials(jira_url: str, user_email: str, api_token: str) -> JiraConnector:
        """Create connector from Jira API token credentials."""
        return JiraConnector(jira_url, user_email, api_token)
