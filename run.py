"""Main entry point for running the application."""
import asyncio
import sys

import uvicorn

from app.core import setup_logging, get_logger

logger = get_logger("main")
def run_fastapi():
    """Run FastAPI server."""
    from app.main import app
    setup_logging()
    logger.info("Starting FastAPI server...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None,  # Use our custom logging
    )


def run_mcp():
    """Run MCP server."""
    # Redirect stdout to stderr for startup to prevent breaking MCP protocol
    import sys
    import os
    
    # Save original stdout
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    
    try:
        setup_logging()
        logger.info("Starting MCP server...")
        from app.mcp import mcp_server
        
        # Restore stdout before starting the server as the SDK will use it
        sys.stdout = original_stdout
        
        asyncio.run(mcp_server.start())
    except Exception as e:
        sys.stdout = original_stdout
        logger.error(f"Failed to start MCP server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Check for 'mcp' in any argument to be more flexible (handles mcp, mcp@x, etc.)
    if any("mcp" in arg.lower() for arg in sys.argv):
        run_mcp()
    else:
        run_fastapi()
