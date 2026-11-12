from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import UserLogin, UserCreate, UserResponse, ApiResponse
from app.auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, get_current_user_optional
)
from app.services.activity_service import log_from_request
from app.services.user_service import get_user_by_username, update_last_login

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

async def _extract_request_data(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return await request.json()
        except Exception:
            return {}
    elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        try:
            form = await request.form()
            return dict(form)
        except Exception:
            return {}
    try:
        return await request.json()
    except Exception:
        return {}

@router.post("/login")
async def login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    User login supporting both JSON payload and standard Form submission.
    Sets session cookie and returns JWT access token.
    """
    data = await _extract_request_data(request)
    uname = str(data.get("username") or "").strip()
    pwd = str(data.get("password") or "")
    
    uname = uname.strip()
    if not uname or not pwd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required"
        )
    
    user = get_user_by_username(db, uname)
    if not user or not user.is_active:
        log_from_request(db, request, "login_failed", f"Failed login attempt for '{uname}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password. Please try again."
        )
    
    if not verify_password(pwd, user.password, user.username):
        log_from_request(db, request, "login_failed", f"Failed password for user '{uname}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password. Please try again."
        )
    
    # Update last login
    update_last_login(db, user.username)
    
    # Create token
    token = create_access_token({
        "sub": user.username,
        "role": user.role,
        "department": user.department or "",
        "user_id": user.id
    })
    
    # Set HTTP-only Cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        path="/"
    )
    
    # Log successful login
    log_from_request(db, request, "login", "User logged in successfully", user=user, page="login")
    
    user_resp = UserResponse.from_orm(user)
    return {
        "success": True,
        "message": "Login successful",
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "user": user_resp.dict()
    }

@router.post("/register")
async def register(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Role-based registration endpoint enforcing permission rules:
    - Admin: requires existing Admin authorization
    - Department Admin: requires existing Admin authorization and department
    - User: requires existing User or Admin authorization and department
    - Guest: no authorization needed
    """
    data = await _extract_request_data(request)
    uname = str(data.get("new_username") or "").strip()
    pwd = str(data.get("new_password") or "")
    cpwd = str(data.get("confirm_password") or pwd)
    urole = str(data.get("role") or "guest").strip().lower()
    udept = str(data.get("department") or "").strip()
    auth_uname = str(data.get("admin_auth_username") or "").strip()
    auth_pwd = str(data.get("admin_auth_password") or "")


    uname = uname.strip()
    if not uname or not pwd:
        raise HTTPException(status_code=400, detail="Username and password are required")
    if pwd != cpwd:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(pwd) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
    
    existing = get_user_by_username(db, uname)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists. Please choose another.")
    
    # Hierarchy authorization checks
    if urole == "admin":
        if not auth_uname or not auth_pwd:
            raise HTTPException(status_code=403, detail="Admin authorization credentials are required to create an Admin account.")
        auth_user = get_user_by_username(db, auth_uname)
        if not auth_user or auth_user.role != "admin" or not verify_password(auth_pwd, auth_user.password, auth_user.username):
            raise HTTPException(status_code=403, detail="Invalid admin credentials. Only existing admins can create Admin accounts.")
            
    elif urole == "department_admin":
        if not auth_uname or not auth_pwd:
            raise HTTPException(status_code=403, detail="Admin authorization credentials are required to create a Department Admin account.")
        if not udept.strip():
            raise HTTPException(status_code=400, detail="Department is required for Department Admin accounts.")
        auth_user = get_user_by_username(db, auth_uname)
        if not auth_user or auth_user.role != "admin" or not verify_password(auth_pwd, auth_user.password, auth_user.username):
            raise HTTPException(status_code=403, detail="Invalid admin credentials. Only existing admins can create Department Admin accounts.")
            
    elif urole == "user":
        if not auth_uname or not auth_pwd:
            raise HTTPException(status_code=403, detail="Existing User or Admin credentials are required to create a User account.")
        auth_user = get_user_by_username(db, auth_uname)
        if not auth_user or auth_user.role not in ("user", "admin", "department_admin") or not verify_password(auth_pwd, auth_user.password, auth_user.username):
            raise HTTPException(status_code=403, detail="Invalid authorization credentials. Only existing users or admins can authorize new User accounts.")

    # Create user
    pw_hash = get_password_hash(pwd)
    new_user = User(
        username=uname,
        password=pw_hash,
        role=urole,
        department=udept.strip(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_from_request(
        db, request, "create_account",
        f"User account created: {uname} (Role: {urole}, Dept: {udept})",
        user=new_user, page="register"
    )

    return {
        "success": True,
        "message": f"{urole.capitalize()} account created successfully! You can now log in.",
        "user_id": new_user.id
    }

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional)
):
    """Clear session cookie and log activity."""
    response.delete_cookie(key=settings.COOKIE_NAME, path="/")
    if user:
        log_from_request(db, request, "logout", "User logged out", user=user)
    return {"success": True, "message": "Successfully logged out"}

@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """Return currently authenticated user profile."""
    u_dict = UserResponse.from_orm(user).dict()
    return {
        "success": True,
        "user": u_dict,
        **u_dict
    }

