from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from luki_api.routes import chat, elr, health
from luki_api.middleware import auth, rate_limit, logging
from luki_api.config import settings
import logging as python_logging

# Configure logging
python_logging.basicConfig(level=python_logging.INFO)
logger = python_logging.getLogger(__name__)

# Create FastAPI app instance
app = FastAPI(
    title="LUKi API Gateway",
    description="Unified HTTP interface for the LUKi agent & modules",
    version="0.1.0"
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
app.middleware("http")(auth.auth_middleware)
app.middleware("http")(rate_limit.rate_limit_middleware)

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(chat.router, prefix="/v1/chat", tags=["chat"])
app.include_router(elr.router, prefix="/v1/elr", tags=["elr"])

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
