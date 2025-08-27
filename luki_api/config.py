from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    # API metadata
    VERSION: str = "0.2.0"  # Updated for Together AI integration
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8081
    DEBUG: bool = True  # Enable debug for development
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # Auth settings
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    API_KEY_HEADER: str = "X-API-Key"
    
    # Rate limiting settings
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100  # Increased for development
    
    # Memory service settings
    MEMORY_SERVICE_URL: str = "http://localhost:8002"
    MEMORY_SERVICE_TIMEOUT: int = 30
    
    # Agent service settings (LUKi Core Agent with Together AI)
    AGENT_SERVICE_URL: str = "http://localhost:9000"
    AGENT_SERVICE_TIMEOUT: int = 120  # Longer timeout for LLM responses
    
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
