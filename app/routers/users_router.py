from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import UserResponse, UserUpdate, ApiResponse, AdminSetPasswordRequest
from app.auth import get_current_user, require_admin
from app.services.activity_service import log_from_request
from app.services.user_service import (
    get_all_users, get_user_by_id, create_user, update_user,
    delete_user, sync_users_to_json, password_policy_error, set_user_password,
    generate_temporary_password,
)

router = APIRouter(prefix="/api/users", tags=["Users Management"])

@router.get("/status")
async def user_status(db: Session = Depends(get_db)):
    """Check database status and user count."""
    count = db.query(User).count()
    return {
        "success": True,
        "database_available": True,
        "users_count": count
    }

@router.get("/", response_model=List[UserResponse])
async def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all registered users (Admin only)."""
    users = get_all_users(db)
    return users

@router.post("/")
async def create_user_admin(
    request: Request,
    payload: dict,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Direct user creation by Administrator."""
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    role = payload.get("role", "guest")
    department = payload.get("department", "")
    email = payload.get("email")

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    policy_error = password_policy_error(password, username)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)
    
    try:
        new_user = create_user(db, username, password, role, department, email)
        log_from_request(db, request, "admin_create_user", f"Admin created user '{username}' (Role: {role})", user=admin)
        return {
            "success": True,
            "message": f"User '{username}' created successfully",
            "user": UserResponse.from_orm(new_user).dict()
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.put("/{user_id}")
async def update_user_admin(
    user_id: int,
    request: Request,
    updates: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update a user's role, department, status, or password (Admin only)."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    changes = updates.dict(exclude_unset=True)
    if changes.get("password") and user.id == admin.id:
        raise HTTPException(status_code=400, detail="Use Change Password to change your own password.")
    try:
        updated = update_user(db, user_id, changes)
    except ValueError as ve:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    log_from_request(
        db, request, "admin_update_user",
        f"Admin updated user '{user.username}' (ID: {user_id})"
        + (" including password" if changes.get("password") else ""),
        user=admin
    )
    return {
        "success": True,
        "message": f"User '{user.username}' updated successfully",
        "user": UserResponse.from_orm(updated).dict()
    }

def _password_target(db: Session, user_id: int, admin: User) -> User:
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="You can't reset your own password here. Use Change Password in the account menu.",
        )
    return user

@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reset a user's password to a random temporary password (Admin only).

    The temporary password is returned **once** and is not stored in plain text. The user is
    signed out everywhere and must choose a new password at their next sign-in.
    """
    user = _password_target(db, user_id, admin)
    temporary = generate_temporary_password()
    set_user_password(db, user, temporary, require_change=True)
    log_from_request(
        db, request, "admin_reset_password",
        f"Admin reset the password of '{user.username}' (ID: {user_id}) to a temporary password",
        user=admin
    )
    return {
        "success": True,
        "message": f"Password for '{user.username}' has been reset.",
        "temporary_password": temporary,
        "user": UserResponse.from_orm(user).dict(),
    }

@router.post("/{user_id}/password")
async def set_password_admin(
    user_id: int,
    request: Request,
    payload: AdminSetPasswordRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Set a specific new password for a user (Admin only).

    With `require_change` (default true) the user must choose their own password at next
    sign-in. Existing sessions for that user are signed out either way.
    """
    user = _password_target(db, user_id, admin)
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="The passwords do not match.")
    policy_error = password_policy_error(payload.new_password, user.username)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)
    set_user_password(db, user, payload.new_password, require_change=payload.require_change)
    log_from_request(
        db, request, "admin_change_password",
        f"Admin changed the password of '{user.username}' (ID: {user_id})"
        + ("; change required at next sign-in" if payload.require_change else ""),
        user=admin
    )
    return {
        "success": True,
        "message": f"Password for '{user.username}' has been changed.",
        "user": UserResponse.from_orm(user).dict(),
    }

@router.delete("/{user_id}")
async def delete_user_admin(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a user account (Admin only)."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
    
    uname = user.username
    delete_user(db, user_id)
    log_from_request(db, request, "admin_delete_user", f"Admin deleted user '{uname}' (ID: {user_id})", user=admin)
    return {
        "success": True,
        "message": f"User '{uname}' deleted successfully"
    }

@router.post("/sync")
async def sync_users(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Sync database users to users.json (Admin only)."""
    result = sync_users_to_json(db)
    log_from_request(db, request, "user_sync", result["message"], user=admin)
    return result
