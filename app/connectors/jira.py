"""Jira connector for issue ingestion."""
from datetime import datetime
from typing import Any, Optional

import structlog
from atlassian import Jira

from app.connectors.base import BaseConnector, UnifiedWorkItem

logger = structlog.get_logger(__name__)

# Jira priority to urgency mapping
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
    scope_required = []  # OAuth scopes handled by atlassian-python-api

    def __init__(self, url: str, user: str, api_token: str):
        """Initialize Jira connector."""
        # Store separately from base class access_token
        self.url = url
        self.user = user
        self.api_token = api_token
        self.access_token = api_token  # For compatibility
        self.user_id = user  # Set user_id to email
        self.client = Jira(url=url, username=user, password=api_token)
        logger.debug("Jira connector initialized", url=url)

    async def test_connection(self) -> bool:
        """Test Jira connection."""
        try:
            server_info = self.client.get_server_info()
            logger.info(
                "Jira connection test successful",
                server_url=server_info.get("baseUrl"),
            )
            return True
        except Exception as e:
            logger.error("Jira connection test failed", error=str(e))
            return False

    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get issues from Jira."""
        try:
            # Build JQL query
            jql_parts = [
                'assignee = currentUser()',  # Issues assigned to user
                'status NOT IN (Done, Closed, Resolved)',  # Open issues
            ]

            if sync_cursor:
                # Cursor format: "timestamp:offset"
                jql_parts.append(f'updated >= "{sync_cursor}"')

            jql = " AND ".join(jql_parts)

            # Get issues
            issues_response = self.client.jql(
                jql,
                limit=min(limit, 100),
            )

            issues = issues_response.get("issues", [])
            next_cursor = None

            # Create cursor for next sync
            if issues:
                last_issue = issues[-1]
                next_cursor = last_issue.get("fields", {}).get("updated")

            logger.info("Fetched issues from Jira", count=len(issues))
            return issues, next_cursor

        except Exception as e:
            logger.error("Jira fetch failed", error=str(e))
            raise

    async def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize Jira issue to unified work item."""
        try:
            fields = item.get("fields", {})
            key = item.get("key", "")
            summary = fields.get("summary", "")
            description = fields.get("description", "")
            assignee = fields.get("assignee", {})
            priority = fields.get("priority", {})
            due_date_str = fields.get("duedate")
            created_str = fields.get("created")
            status = fields.get("status", {})

            # Parse dates
            due_date = None
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            created_date = None
            if created_str:
                try:
                    created_date = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            # Extract urgency from priority
            priority_name = priority.get("name", "Medium")
            urgency = PRIORITY_TO_URGENCY.get(priority_name, 0.5)

            # Determine if requires response (open issues assigned to user)
            requires_response = status.get("name", "").lower() not in ["done", "closed", "resolved"]

            # Create unified work item
            work_item = UnifiedWorkItem(
                source="jira",
                source_id=key,
                title=f"[{key}] {summary}",
                description=description,
                urgency=urgency,
                importance=0.8,  # Jira tickets are typically important
                created_by=assignee.get("emailAddress") or assignee.get("name"),
                requires_response=requires_response,
                requires_deep_work=True,  # Jira tickets usually need focused work
                confidence_score=0.95,
                category="task",
                due_date=due_date,
                metadata={
                    "jira_key": key,
                    "status": status.get("name"),
                    "priority": priority_name,
                    "assignee": assignee.get("name"),
                    "issue_type": fields.get("issuetype", {}).get("name"),
                    "created": created_date.isoformat() if created_date else None,
                    "project": fields.get("project", {}).get("key"),
                },
            )

            return work_item.to_dict()

        except Exception as e:
            logger.error("Jira issue normalization failed", error=str(e))
            raise


class JiraConnectorFactory:
    """Factory for creating Jira connectors."""

    @staticmethod
    def create_from_oauth(
        jira_url: str,
        user_email: str,
        api_token: str,
    ) -> JiraConnector:
        """Create connector from Jira credentials."""
        return JiraConnector(jira_url, user_email, api_token)
