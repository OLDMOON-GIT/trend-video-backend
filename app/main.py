"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.api.v1 import story, video, trends


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Trend Video Backend API...")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"Image Provider: {settings.image_provider}")

    # Create necessary directories
    import os
    os.makedirs(settings.storage_path, exist_ok=True)
    os.makedirs(settings.output_path, exist_ok=True)
    os.makedirs(settings.temp_path, exist_ok=True)

    yield

    # Shutdown
    logger.info("Shutting down Trend Video Backend API...")


# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "status": "ok",
        "service": "Trend Video Backend API",
        "version": settings.api_version,
        "llm_provider": settings.llm_provider,
        "image_provider": settings.image_provider,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# Include API routers
app.include_router(story.router, prefix="/api/v1/story", tags=["Story"])
app.include_router(video.router, prefix="/api/v1/video", tags=["Video"])
app.include_router(trends.router, prefix="/api/v1/trends", tags=["Trends"])


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info"
    )
