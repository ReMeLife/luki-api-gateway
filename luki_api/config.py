from pydantic_settings import BaseSettings
from typing import List, Optional
import os

class Settings(BaseSettings):
    # API metadata
    VERSION: str = "0.2.0"  # Updated for Together AI integration
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = int(os.getenv("PORT", 8080))  # Railway uses PORT env var
    DEBUG: bool = False  # Disable debug for production
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = ["https://yourdomain.com", "https://luki-ai.io", "http://localhost:3000", "https://chat-interface-ai.netlify.app"]
    
    # Auth settings
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    API_KEY_HEADER: str = "X-API-Key"
    
    # Rate limiting settings
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100  # Increased for development
    
    # Memory service settings - Railway deployment URLs
    MEMORY_SERVICE_URL: str = os.getenv("LUKI_MEMORY_SERVICE_URL", "http://localhost:8002")
    MEMORY_SERVICE_TIMEOUT: int = 30
    
    # Agent service settings - Railway deployment URLs
    AGENT_SERVICE_URL: str = os.getenv("LUKI_CORE_AGENT_URL", "http://localhost:9000")
    AGENT_SERVICE_TIMEOUT: int = 240  # Extended timeout to align with core-agent structured output
    
    # Redis settings (for rate limiting and session storage)
    REDIS_URL: str = "redis://localhost:6379"
    
    # Streaming settings
    ENABLE_STREAMING: bool = True
    STREAM_CHUNK_SIZE: int = 1024
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    STRUCTURED_LOGGING: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_prefix = "LUKI_API_"

settings = Settings()
