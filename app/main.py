"""FastAPI application factory and configuration."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import settings, setup_logging
from app.core.container import Container

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    # Startup
    setup_logging()
    logger.info(f"Starting Workload Management MCP Server (version={settings.APP_VERSION})")
    await Container.initialize()

    yield

    # Shutdown
    logger.info("Shutting down Workload Management MCP Server")
    await Container.shutdown()


def create_app() -> FastAPI:
    """Factory function to create FastAPI application."""

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ============================================================
    # Health check endpoints
    # ============================================================

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": settings.APP_VERSION}

    @app.get("/ready")
    async def readiness_check():
        """Readiness probe for Kubernetes."""
        try:
            async for _ in Container.get_db_session():
                pass
            return {"status": "ready"}
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return {"status": "not_ready"}, 503

    # ============================================================
    # Include routers
    # ============================================================

    # API v1 routes (to be added in Phase 2)
    # app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    # app.include_router(connectors_router, prefix="/api/v1/connectors", tags=["connectors"])
    # app.include_router(workload_router, prefix="/api/v1/workload", tags=["workload"])

    return app


# Create app instance
app = create_app()
