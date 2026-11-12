from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import UserResponse, UserUpdate, ApiResponse
from app.auth import get_current_user, require_admin
from app.services.activity_service import log_from_request
from app.services.user_service import (
    get_all_users, get_user_by_id, create_user, update_user,
    delete_user, sync_users_to_json
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
    
    updated = update_user(db, user_id, updates.dict(exclude_unset=True))
    log_from_request(
        db, request, "admin_update_user",
        f"Admin updated user '{user.username}' (ID: {user_id})",
        user=admin
    )
    return {
        "success": True,
        "message": f"User '{user.username}' updated successfully",
        "user": UserResponse.from_orm(updated).dict()
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
