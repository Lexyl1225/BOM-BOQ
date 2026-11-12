"""
Main FastAPI Application Entrypoint
BOM / BOQ Studio Pro — Next-Gen Engineering Management Framework
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, BASE_DIR
from app.database import init_db
from app.routers import (
    auth_router,
    users_router,
    documents_router,
    estimates_router,
    uploads_router,
    logs_router,
    legacy_router,
    pages_router
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("bom_app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: sets up DB tables and initial seeds on startup."""
    logger.info("Initializing BOM / BOQ Studio Pro database schema...")
    try:
        init_db()
        logger.info("Database and initial data seeds verified successfully.")
    except Exception as e:
        logger.error(f"Error during startup database initialization: {e}", exc_info=True)
    yield
    logger.info("Shutting down BOM / BOQ Studio Pro application.")

# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware (allows seamless cross-origin communication if integrated with other internal microservices)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
static_dir = BASE_DIR / "app" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount Uploads Directory
uploads_dir = Path(settings.UPLOAD_DIR)
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Root-level Static Asset Aliases (for backward compatibility with legacy template links)
@app.get("/themes.css", include_in_schema=False)
async def get_themes_css():
    return FileResponse(static_dir / "css" / "themes.css", media_type="text/css")

@app.get("/themes.js", include_in_schema=False)
async def get_themes_js():
    return FileResponse(static_dir / "js" / "themes.js", media_type="application/javascript")

@app.get("/document_sync.js", include_in_schema=False)
async def get_document_sync_js():
    return FileResponse(static_dir / "js" / "document_sync.js", media_type="application/javascript")

# Health Check Endpoints
@app.get("/health", tags=["System"])
@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check endpoint for Docker container, orchestration, and monitoring."""
    return {
        "status": "ok",
        "app": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "hostname": settings.TS_HOSTNAME,
        "funnel_url": settings.FUNNEL_URL
    }

# Global Exception Handlers
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>404 - Page Not Found | BOM Studio Pro</title>
                <link rel="stylesheet" href="/static/css/main.css">
            </head>
            <body style="display:flex;align-items:center;justify-content:center;height:100vh;background:#f8fafc;font-family:sans-serif;">
                <div style="text-align:center;padding:40px;background:#fff;border-radius:12px;box-shadow:0 10px 25px rgba(0,0,0,0.05);max-width:480px;">
                    <div style="font-size:56px;margin-bottom:12px;">🔍</div>
                    <h1 style="font-size:24px;color:#1e293b;margin-bottom:8px;">404 - Page Not Found</h1>
                    <p style="color:#64748b;font-size:14px;margin-bottom:24px;">The requested resource or page does not exist or has been moved.</p>
                    <a href="/" class="btn btn-primary" style="display:inline-block;padding:10px 20px;text-decoration:none;border-radius:6px;background:#3b82f6;color:#fff;font-weight:600;">Return to Dashboard</a>
                </div>
            </body>
            </html>
            """,
            status_code=404
        )
    return JSONResponse(
        status_code=404,
        content={"success": False, "detail": "Resource not found"}
    )

@app.exception_handler(500)
async def custom_500_handler(request: Request, exc):
    logger.error(f"Internal server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": "An internal server error occurred."}
    )

# Include Routers
# HTML Page Router (Dashboard, Login, BOM/BOQ Builders, Approvals, Legacy .php aliases)
app.include_router(pages_router.router)

# REST API Routers
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(documents_router.router)
app.include_router(estimates_router.router)
app.include_router(uploads_router.router)
app.include_router(logs_router.router)

# Legacy PHP API Endpoint Compatibility (/api/document_api.php, /api/user_api.php, etc.)
app.include_router(legacy_router.router)
