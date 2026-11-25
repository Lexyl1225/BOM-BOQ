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
from app.services.settings_service import (
    is_guest_signup_enabled, is_public_help_enabled,
    set_guest_signup_enabled, set_public_help_enabled,
)

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
        "message": "You have " + ("enabled" if enabled else "disabled") + " the Public Help page on the login page.",
    }

@router.get("/guest-signup")
async def get_guest_signup(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Whether Guest accounts may be created from the sign-in page."""
    return {"success": True, "enabled": is_guest_signup_enabled(db)}

@router.put("/guest-signup")
async def update_guest_signup(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Allow or block Guest account creation on the sign-in page. Body: {"enabled": true|false}.
    Even when allowed, a Guest sign-up still needs an existing user's authorizing credentials."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    enabled = data.get("enabled") if isinstance(data, dict) else None
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail='Body must be {"enabled": true} or {"enabled": false}')

    set_guest_signup_enabled(db, enabled, admin)
    log_from_request(
        db, request, "guest_signup_" + ("enabled" if enabled else "disabled"),
        "Guest account creation " + ("allowed (with authorizing credentials)" if enabled else "disabled"),
        user=admin,
    )
    return {
        "success": True,
        "enabled": enabled,
        "message": "You have " + ("enabled" if enabled else "disabled") + " Guest account creation.",
    }
