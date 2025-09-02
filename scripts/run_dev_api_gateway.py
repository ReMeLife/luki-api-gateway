#!/usr/bin/env python3
"""
Development server script for LUKi API Gateway
"""

import os
import sys
import uvicorn
from pathlib import Path

# Add the luki_api package to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    """Run the API Gateway development server"""
    print("🚀 Starting LUKi API Gateway Development Server")
    print("=" * 60)
    
    # Check if .env file exists
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        print("⚠️  No .env file found. Using default configuration.")
        print("   Copy env.example to .env and configure your settings.")
    
    # Import after path setup
    from luki_api.config import settings
    
    print(f"🌐 Server will start on: http://{settings.HOST}:{settings.PORT}")
    print(f"📚 API Documentation: http://{settings.HOST}:{settings.PORT}/docs")
    print(f"🔄 Debug mode: {settings.DEBUG}")
    print(f"🤖 Agent service: {settings.AGENT_SERVICE_URL}")
    print(f"🧠 Memory service: {settings.MEMORY_SERVICE_URL}")
    print("=" * 60)
    
    try:
        uvicorn.run(
            "luki_api.main:app",
            host=settings.HOST,
            port=settings.PORT,
            reload=settings.DEBUG,
            log_level=settings.LOG_LEVEL.lower(),
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n👋 API Gateway server stopped")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
