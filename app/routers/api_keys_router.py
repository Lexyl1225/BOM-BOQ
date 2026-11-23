"""
REST API Router for Department API Key Management (Administrator only).

Mounted under /api/admin/api-keys, which the API key middleware exempts so an
Administrator can always recover access after revoking or deactivating a key.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import Department, User
from app.services.activity_service import log_from_request
from app.services.api_key_service import (
    decrypt_key, describe_departments, mask_key, regenerate_key, revoke_key, set_key_active,
)

router = APIRouter(prefix="/api/admin/api-keys", tags=["API Key Management"])

def _get_department(db: Session, department_id: int) -> Department:
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept

@router.get("")
@router.get("/")
async def list_department_keys(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """List all departments with their masked API key and status."""
    return {"success": True, "departments": describe_departments(db)}

@router.post("/{department_id}/generate")
async def generate_department_key(
    department_id: int, request: Request,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Generate a key, or replace the existing one (the old key stops working immediately)."""
    dept = _get_department(db, department_id)
    replacing = dept.api_key is not None
    raw = regenerate_key(db, dept, admin)
    log_from_request(
        db, request, "api_key_regenerate" if replacing else "api_key_generate",
        f"{'Regenerated' if replacing else 'Generated'} API key for department: {dept.name}", user=admin,
    )
    return {
        "success": True,
        "message": f"API key {'regenerated' if replacing else 'generated'} for {dept.name}.",
        "department": dept.name,
        "api_key": raw,
        "masked_key": mask_key(dept.api_key),
    }

@router.post("/{department_id}/activate")
async def activate_department_key(
    department_id: int, request: Request,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    dept = _get_department(db, department_id)
    if not set_key_active(db, dept, True):
        raise HTTPException(status_code=400, detail="This department has no API key. Generate one first.")
    log_from_request(db, request, "api_key_activate", f"Activated API key for department: {dept.name}", user=admin)
    return {"success": True, "message": f"API key for {dept.name} activated."}

@router.post("/{department_id}/deactivate")
async def deactivate_department_key(
    department_id: int, request: Request,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    dept = _get_department(db, department_id)
    if not set_key_active(db, dept, False):
        raise HTTPException(status_code=400, detail="This department has no API key.")
    log_from_request(db, request, "api_key_deactivate", f"Deactivated API key for department: {dept.name}", user=admin)
    return {"success": True, "message": f"API key for {dept.name} deactivated."}

@router.delete("/{department_id}")
async def revoke_department_key(
    department_id: int, request: Request,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Permanently revoke (delete) the department's key."""
    dept = _get_department(db, department_id)
    if not revoke_key(db, dept):
        raise HTTPException(status_code=400, detail="This department has no API key.")
    log_from_request(db, request, "api_key_revoke", f"Revoked API key for department: {dept.name}", user=admin)
    return {"success": True, "message": f"API key for {dept.name} revoked."}

@router.post("/{department_id}/reveal")
async def reveal_department_key(
    department_id: int, request: Request,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Return the full key so an Administrator can configure an external client. Audited."""
    dept = _get_department(db, department_id)
    raw = decrypt_key(dept.api_key)
    if not raw:
        raise HTTPException(status_code=400, detail="No readable key for this department. Generate a new one.")
    log_from_request(db, request, "api_key_reveal", f"Revealed API key for department: {dept.name}", user=admin)
    return {"success": True, "api_key": raw}
