from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from luki_api.routes import chat, elr, health, metrics
from luki_api.middleware import auth, rate_limit, logging, metrics as metrics_middleware
from luki_api.config import settings
from luki_api.clients.agent_client import agent_client
import logging as python_logging

# Configure logging
python_logging.basicConfig(level=python_logging.INFO)
logger = python_logging.getLogger(__name__)

# Create FastAPI app instance
app = FastAPI(
    title="LUKi API Gateway",
    description="Unified HTTP interface for the LUKi agent & modules",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware - logging first to capture all requests
app.middleware("http")(logging.request_logging_middleware)
# Add metrics middleware after logging but before auth to capture all requests
app.middleware("http")(metrics_middleware.metrics_middleware)
app.middleware("http")(auth.auth_middleware)
app.middleware("http")(rate_limit.rate_limit_middleware)

# Include routers
app.include_router(health.router, prefix="", tags=["health"])  # No prefix for health
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(elr.router, prefix="/v1/elr", tags=["elr"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting LUKi API Gateway...")
    logger.info(f"Agent service URL: {settings.AGENT_SERVICE_URL}")
    logger.info(f"Memory service URL: {settings.MEMORY_SERVICE_URL}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    logger.info("Shutting down LUKi API Gateway...")
    await agent_client.close()
    logger.info("Agent client closed")

@app.get("/")
async def root():
    return {"message": "LUKi API Gateway"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "luki_api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
