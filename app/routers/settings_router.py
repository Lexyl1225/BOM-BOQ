"""
REST API Router for application settings (Administrator only).

Unlike /api/admin/api-keys this router is NOT exempt from the department API key
check: it is only ever called from signed-in admin pages, which send the key.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.services.activity_service import log_from_request
from app.services.settings_service import is_public_help_enabled, set_public_help_enabled

router = APIRouter(prefix="/api/admin/settings", tags=["Settings"])

@router.get("/public-help")
async def get_public_help(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Whether the public Quick Help page (/quick-help) is published."""
    return {"success": True, "enabled": is_public_help_enabled(db)}

@router.put("/public-help")
async def update_public_help(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Publish or hide the public Quick Help page. Body: {"enabled": true|false}."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    enabled = data.get("enabled") if isinstance(data, dict) else None
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail='Body must be {"enabled": true} or {"enabled": false}')

    set_public_help_enabled(db, enabled, admin)
    log_from_request(
        db, request, "public_help_" + ("enabled" if enabled else "disabled"),
        "Public Quick Help page " + ("published at /quick-help" if enabled else "hidden from the public"),
        user=admin,
    )
    return {
        "success": True,
        "enabled": enabled,
        "message": "Public Quick Help is now " + ("visible" if enabled else "hidden") + ".",
    }
