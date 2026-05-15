"""Main entry point for running the application."""
import asyncio
import sys

import uvicorn

from app.core import setup_logging, get_logger
from app.main import app

logger = get_logger("main")


def run_fastapi():
    """Run FastAPI server."""
    setup_logging()
    logger.info("Starting FastAPI server...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None,  # Use our custom logging
    )


def run_mcp():
    """Run MCP server."""
    setup_logging()
    logger.info("Starting MCP server...")
    from app.mcp import mcp_server
    asyncio.run(mcp_server.start())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        run_mcp()
    else:
        run_fastapi()
