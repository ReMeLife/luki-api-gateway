from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    # API metadata
    VERSION: str = "0.1.0"
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # Auth settings
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    API_KEY_HEADER: str = "X-API-Key"
    
    # Rate limiting settings
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    
    # Memory service settings
    MEMORY_SERVICE_URL: str = "http://localhost:8002"
    
    # Agent service settings
    AGENT_SERVICE_URL: str = "http://localhost:9000"
    
    # Redis settings (for rate limiting)
    REDIS_URL: str = "redis://localhost:6379"

settings = Settings()
