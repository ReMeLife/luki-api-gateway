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
    
    # Cognitive module settings - Railway deployment URLs
    COGNITIVE_SERVICE_URL: str = os.getenv("LUKI_COGNITIVE_SERVICE_URL", "http://localhost:8101")
    COGNITIVE_SERVICE_TIMEOUT: int = 60
    
    # Security service settings - Railway deployment URLs
    SECURITY_SERVICE_URL: str = os.getenv("LUKI_SECURITY_SERVICE_URL", "http://localhost:8103")
    SECURITY_SERVICE_TIMEOUT: int = 30
    
    # Redis settings (for rate limiting and session storage)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Streaming settings
    ENABLE_STREAMING: bool = True
    STREAM_CHUNK_SIZE: int = 1024
    
    # Solana wallet / NFT settings
    HELIUS_API_KEY: str = os.getenv("HELIUS_API_KEY", "")
    GENESIS_LUKI_COLLECTION_ADDRESS: str = os.getenv("GENESIS_LUKI_COLLECTION_ADDRESS", "")
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    STRUCTURED_LOGGING: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_prefix = "LUKI_API_"

settings = Settings()


def validate_service_urls() -> list[str]:
    """
    Validate all service URLs are properly configured.
    
    Returns:
        List of validation warnings
    """
    warnings = []
    
    service_urls = {
        "Memory Service": settings.MEMORY_SERVICE_URL,
        "Agent Service": settings.AGENT_SERVICE_URL,
        "Cognitive Service": settings.COGNITIVE_SERVICE_URL,
        "Security Service": settings.SECURITY_SERVICE_URL,
    }
    
    for service_name, url in service_urls.items():
        if not url:
            warnings.append(f"{service_name} URL is not configured")
        elif not url.startswith(("http://", "https://")):
            warnings.append(f"{service_name} URL missing protocol: {url}")
        elif url.endswith("/"):
            warnings.append(f"{service_name} URL should not end with '/': {url}")
    
    return warnings


def get_cors_origins() -> list[str]:
    """
    Get parsed CORS origins with validation.
    
    Returns:
        List of allowed CORS origins
    """
    origins = settings.allowed_origins_list
    
    # Filter out empty strings
    origins = [o for o in origins if o.strip()]
    
    # Warn about wildcard in production
    if "*" in origins:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("CORS wildcard (*) is enabled - not recommended for production")
    
    return origins


def is_production_environment() -> bool:
    """
    Check if running in production environment.
    
    Returns:
        True if production, False otherwise
    """
    import os
    env = os.getenv("ENVIRONMENT", "production").lower()
    return env == "production"


def get_service_timeout(service_name: str) -> int:
    """
    Get timeout for a specific service.
    
    Args:
        service_name: Name of the service
    
    Returns:
        Timeout in seconds
    """
    timeouts = {
        "memory": settings.MEMORY_SERVICE_TIMEOUT,
        "agent": settings.AGENT_SERVICE_TIMEOUT,
        "cognitive": settings.COGNITIVE_SERVICE_TIMEOUT,
        "security": settings.SECURITY_SERVICE_TIMEOUT,
    }
    return timeouts.get(service_name.lower(), 30)
