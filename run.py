"""
Application Runner Script
Launches BOM / BOQ Studio Pro using Uvicorn.
"""
import os
import uvicorn
from app.config import settings

if __name__ == "__main__":
    host = os.getenv("HOST", settings.HOST)
    port = int(os.getenv("PORT", settings.PORT))
    reload = os.getenv("RELOAD", "true").lower() in ("true", "1", "yes")

    print("==================================================")
    print(f"🚀 Launching {settings.APP_TITLE} v{settings.APP_VERSION}")
    print(f"📡 Server URL: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
    print(f"📚 OpenAPI Documentation: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/docs")
    print("==================================================")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
