from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from luki_api.routes import chat, elr, health, metrics, conversation, memories, conversations, cognitive
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
    description="Unified HTTP interface for the LUKi agent & modules - Fixed CORS with explicit origins",  # Force redeploy 13:38
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Define custom CORS middleware function (will be registered later for correct order)
async def custom_cors_middleware(request: Request, call_next):
    """Custom CORS handler to ensure headers are ALWAYS added"""
    import logging
    logger = logging.getLogger(__name__)
    
    origin = request.headers.get("origin", "")
    
    # Use allowed origins from config (now a property that returns list)
    allowed_origins = settings.allowed_origins_list
    
    # Check if origin is allowed (including wildcard)
    is_allowed = "*" in allowed_origins or origin in allowed_origins or any(
        origin.startswith(allowed.rstrip('*')) for allowed in allowed_origins if allowed.endswith('*')
    )
    
    # Handle OPTIONS preflight
    if request.method == "OPTIONS":
        logger.info(f"🌐 CUSTOM CORS: OPTIONS preflight from {origin}")
        logger.info(f"🔍 Request headers: {dict(request.headers)}")
        logger.info(f"🔍 Access-Control-Request-Method: {request.headers.get('access-control-request-method')}")
        logger.info(f"🔍 Access-Control-Request-Headers: {request.headers.get('access-control-request-headers')}")
        
        from fastapi.responses import Response
        
        # Use wildcard for headers to ensure all are allowed
        requested_headers = request.headers.get('access-control-request-headers', '')
        allow_headers = requested_headers if requested_headers else "Authorization, Content-Type, X-User-ID, Accept, Origin, X-Requested-With"
        
        response = Response(
            content="",
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": origin if is_allowed else allowed_origins[0],
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
                "Access-Control-Allow-Headers": allow_headers,
                "Access-Control-Max-Age": "3600",
            }
        )
        logger.info(f"✅ CUSTOM CORS: Returning headers: {dict(response.headers)}")
        return response
    
    # For non-OPTIONS requests, call next and add CORS headers to response
    response = await call_next(request)
    
    # Add CORS headers to response
    response.headers["Access-Control-Allow-Origin"] = origin if is_allowed else allowed_origins[0]
    response.headers["Access-Control-Expose-Headers"] = "*"
    
    return response

# Order matters! Register in reverse order (last registered = runs first)
# Register other middleware first (they'll run after CORS)
app.middleware("http")(rate_limit.rate_limit_middleware)
app.middleware("http")(auth.auth_middleware)
app.middleware("http")(metrics_middleware.metrics_middleware)
app.middleware("http")(logging.request_logging_middleware)

# Register CORS middleware LAST so it runs FIRST
app.middleware("http")(custom_cors_middleware)

# Include routers
app.include_router(health.router, prefix="", tags=["health"])  # No prefix for health
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(conversation.router, prefix="/api", tags=["conversation"])
app.include_router(memories.router, prefix="", tags=["memories"])  # Includes /api/elr prefix
app.include_router(conversations.router, prefix="", tags=["conversations"])  # Includes /api/conversations prefix
app.include_router(elr.router, prefix="/v1/elr", tags=["elr"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
app.include_router(cognitive.router, prefix="", tags=["cognitive"])  # Life Story and cognitive module routes

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting LUKi API Gateway...")
    logger.info(f"Agent service URL: {settings.AGENT_SERVICE_URL}")
    logger.info(f"Memory service URL: {settings.MEMORY_SERVICE_URL}")
    logger.info(f"Cognitive service URL: {settings.COGNITIVE_SERVICE_URL}")

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
