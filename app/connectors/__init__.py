"""Connectors module with all external service integrations."""
from app.connectors.base import BaseConnector, UnifiedWorkItem
from app.connectors.calendar import CalendarConnector, CalendarConnectorFactory
from app.connectors.gmail import GmailConnector, GmailConnectorFactory
from app.connectors.jira import JiraConnector, JiraConnectorFactory
from app.connectors.slack import SlackConnector, SlackConnectorFactory

__all__ = [
    "BaseConnector",
    "UnifiedWorkItem",
    "GmailConnector",
    "GmailConnectorFactory",
    "SlackConnector",
    "SlackConnectorFactory",
    "JiraConnector",
    "JiraConnectorFactory",
    "CalendarConnector",
    "CalendarConnectorFactory",
]
