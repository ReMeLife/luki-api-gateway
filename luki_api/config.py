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
    
    # CORS settings - can be overridden via LUKI_API_ALLOWED_ORIGINS env var (comma-separated)
    ALLOWED_ORIGINS: str = os.getenv(
        "LUKI_API_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,https://chat-interface-ai.netlify.app,https://remelife.com,https://www.remelife.com,https://remelife.app,https://www.remelife.app,https://remelife-main.netlify.app,*"
    )
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse ALLOWED_ORIGINS string into list"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    # Auth settings
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    API_KEY_HEADER: str = "X-API-Key"
    
    # Rate limiting settings
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 20  # Production rate limit for cost protection
    
    # Memory service settings - Railway deployment URLs
    MEMORY_SERVICE_URL: str = os.getenv("LUKI_MEMORY_SERVICE_URL", "http://localhost:8002")
    MEMORY_SERVICE_TIMEOUT: int = 30
    
    # Agent service settings - Railway deployment URLs
    AGENT_SERVICE_URL: str = os.getenv("LUKI_CORE_AGENT_URL", "http://localhost:9000")
    AGENT_SERVICE_TIMEOUT: int = 240  # Extended timeout to align with core-agent structured output
    
    # Redis settings (for rate limiting and session storage)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
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
