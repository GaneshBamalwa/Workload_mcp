"""
MCP Server — registers all workload management tools.
"""
import json
from typing import Any, Awaitable, Callable

from mcp.server import Server
from mcp.types import CallToolResult, TextContent, Tool

from app.core import get_logger
from app.mcp import tools as mcp_tools

logger = get_logger("mcp.server")

server = Server("workload-management-mcp")

_tool_handlers: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {}
_tool_schemas: dict[str, Tool] = {}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return list(_tool_schemas.values())


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    if name not in _tool_handlers:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({"error": f"Tool not found: {name}"}))],
            isError=True,
        )
    handler = _tool_handlers[name]
    try:
        logger.info("Tool called", tool_name=name)
        result = await handler(arguments)
        # Ensure result is JSON-safe
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, default=str))])
    except Exception as e:
        logger.error("Tool execution failed", tool_name=name, error=str(e))
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({"error": str(e)}))],
            isError=True,
        )


def _register(name: str, description: str, schema: dict[str, Any], handler) -> None:
    _tool_handlers[name] = handler
    _tool_schemas[name] = Tool(name=name, description=description, inputSchema=schema)
    logger.info("Tool registered", tool_name=name)


class MCPServer:
    """MCP Server wrapper with workload management tools."""

    def __init__(self):
        self.server = server
        self._setup_tools()

    def _setup_tools(self) -> None:
        # ── get_workload ───────────────────────────────────────────────────────
        _register(
            "get_workload",
            (
                "Fetch ALL open work items for a developer from every configured integration "
                "(Slack messages & DMs, Jira issues, Gmail unread emails, Google Calendar meetings). "
                "Returns a unified list sorted by source."
            ),
            {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier (informational only, used for logging)",
                    },
                },
            },
            mcp_tools.get_workload,
        )

        # ── test_connections ───────────────────────────────────────────────────
        _register(
            "test_connections",
            "Test connectivity to all configured integrations (Slack, Jira, Gmail, Calendar). "
            "Run this first to verify your .env credentials are working.",
            {
                "type": "object",
                "properties": {},
            },
            mcp_tools.test_connections,
        )

        # ── schedule_day ───────────────────────────────────────────────────────
        _register(
            "schedule_day",
            (
                "Build a time-blocked schedule for the day using REAL data from all integrations. "
                "Calendar meetings are placed first as fixed blocks; Jira/Slack tasks fill the gaps "
                "ordered by urgency × importance."
            ),
            {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Target date in YYYY-MM-DD format (defaults to today)",
                    },
                    "preferences": {
                        "type": "object",
                        "description": "Optional scheduling preferences e.g. {work_start: '09:00'}",
                    },
                },
            },
            mcp_tools.schedule_day,
        )

        # ── prioritize_tasks ───────────────────────────────────────────────────
        _register(
            "prioritize_tasks",
            (
                "Rank ALL open work items fetched from Slack, Jira, Gmail and Calendar using the "
                "Eisenhower matrix (urgency × importance). Returns items tagged P1/P2/P3."
            ),
            {
                "type": "object",
                "properties": {},
            },
            mcp_tools.prioritize_tasks,
        )

        # ── estimate_effort ────────────────────────────────────────────────────
        _register(
            "estimate_effort",
            "Estimate effort (hours) for a given task description using keyword heuristics.",
            {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Description of the task to estimate",
                    },
                },
                "required": ["task_description"],
            },
            mcp_tools.estimate_effort,
        )

        # ── detect_blockers ────────────────────────────────────────────────────
        _register(
            "detect_blockers",
            (
                "Scan real work items from all integrations for blockers: overdue responses, "
                "items containing 'blocked / waiting / pending / stuck' keywords, etc."
            ),
            {
                "type": "object",
                "properties": {},
            },
            mcp_tools.detect_blockers,
        )

        # ── summarize_context ──────────────────────────────────────────────────
        _register(
            "summarize_context",
            (
                "Generate a concise natural-language summary of the developer's current workload "
                "across all integrations — counts, urgent items, upcoming meetings."
            ),
            {
                "type": "object",
                "properties": {},
            },
            mcp_tools.summarize_context,
        )

        # ── detect_overload ────────────────────────────────────────────────────
        _register(
            "detect_overload",
            (
                "Assess burnout risk by analysing the volume and urgency of real work items. "
                "Returns a risk score (low / moderate / high) and actionable recommendations."
            ),
            {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier",
                    },
                },
            },
            mcp_tools.detect_overload,
        )

        logger.info("MCP Server ready", tool_count=len(_tool_handlers))

    async def start(self) -> None:
        """Start MCP server over stdio."""
        logger.info("Starting MCP server…")
        try:
            from mcp.server.stdio import stdio_server

            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options(),
                )
        except Exception as e:
            logger.error("MCP server error", error=str(e))
            raise


mcp_server = MCPServer()
