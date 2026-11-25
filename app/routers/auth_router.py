from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import UserLogin, UserCreate, UserResponse, ApiResponse, PasswordChangeRequest
from app.auth import (
    get_password_hash, create_access_token, check_user_password, password_stamp,
    get_current_user, get_current_user_optional
)
from app.services.activity_service import log_from_request
from app.services.settings_service import is_guest_signup_enabled
from app.services.user_service import (
    get_user_by_username, update_last_login, password_policy_error, set_user_password,
    PASSWORD_POLICY_TEXT,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def _issue_session(response: Response, user: User) -> str:
    """Create a session token for the user and set it as the HTTP-only cookie."""
    token = create_access_token({
        "sub": user.username,
        "role": user.role,
        "department": user.department or "",
        "user_id": user.id,
        "pwd": password_stamp(user),
    })
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        path="/"
    )
    return token

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
    
    if not check_user_password(user, pwd):
        log_from_request(db, request, "login_failed", f"Failed password for user '{uname}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password. Please try again."
        )
    
    # Update last login
    update_last_login(db, user.username)
    
    # Create token and set the HTTP-only session cookie
    token = _issue_session(response, user)
    
    # Log successful login
    log_from_request(db, request, "login", "User logged in successfully", user=user, page="login")
    
    user_resp = UserResponse.from_orm(user)
    return {
        "success": True,
        "message": "Login successful",
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "must_change_password": user.password_change_required,
        "redirect": "/change_password" if user.password_change_required else "/",
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
    - Guest: requires existing User, Department Admin or Admin authorization, and only
      while an Administrator allows Guest sign-ups (Administration → Guest Sign-up)
    Authorizing accounts must be active. Unknown roles are rejected.
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
    if urole not in ("admin", "department_admin", "user", "guest"):
        raise HTTPException(status_code=400, detail="Invalid account role.")
    if urole == "guest" and not is_guest_signup_enabled(db):
        raise HTTPException(status_code=403, detail="Guest account creation is currently disabled by the Administrator.")
    if not uname or not pwd:
        raise HTTPException(status_code=400, detail="Username and password are required")
    if pwd != cpwd:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    policy_error = password_policy_error(pwd, uname)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)
    
    existing = get_user_by_username(db, uname)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists. Please choose another.")
    
    # Hierarchy authorization checks
    if urole == "admin":
        if not auth_uname or not auth_pwd:
            raise HTTPException(status_code=403, detail="Admin authorization credentials are required to create an Admin account.")
        auth_user = get_user_by_username(db, auth_uname)
        if not auth_user or auth_user.role != "admin" or not check_user_password(auth_user, auth_pwd):
            raise HTTPException(status_code=403, detail="Invalid admin credentials. Only existing admins can create Admin accounts.")
            
    elif urole == "department_admin":
        if not auth_uname or not auth_pwd:
            raise HTTPException(status_code=403, detail="Admin authorization credentials are required to create a Department Admin account.")
        if not udept.strip():
            raise HTTPException(status_code=400, detail="Department is required for Department Admin accounts.")
        auth_user = get_user_by_username(db, auth_uname)
        if not auth_user or auth_user.role != "admin" or not check_user_password(auth_user, auth_pwd):
            raise HTTPException(status_code=403, detail="Invalid admin credentials. Only existing admins can create Department Admin accounts.")
            
    elif urole == "user":
        if not auth_uname or not auth_pwd:
            raise HTTPException(status_code=403, detail="Existing User or Admin credentials are required to create a User account.")
        auth_user = get_user_by_username(db, auth_uname)
        if not auth_user or auth_user.role not in ("user", "admin", "department_admin") or not check_user_password(auth_user, auth_pwd):
            raise HTTPException(status_code=403, detail="Invalid authorization credentials. Only existing users or admins can authorize new User accounts.")

    elif urole == "guest":
        if not auth_uname or not auth_pwd:
            raise HTTPException(status_code=403, detail="Authorizing credentials of an existing User or Admin are required to create a Guest account.")
        auth_user = get_user_by_username(db, auth_uname)
        if not auth_user or auth_user.role not in ("user", "admin", "department_admin") or not check_user_password(auth_user, auth_pwd):
            raise HTTPException(status_code=403, detail="Invalid authorization credentials. Only existing users or admins can authorize new Guest accounts.")

    # Suspended / deactivated accounts may not authorize new accounts
    if not auth_user.is_active:
        raise HTTPException(status_code=403, detail="The authorizing account is inactive and cannot approve new accounts.")

    # Create user
    pw_hash = get_password_hash(pwd)
    new_user = User(
        username=uname,
        password=pw_hash,
        role=urole,
        department=udept.strip(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_active=True,
        # The user chose this password themselves, so no first-login change is needed
        password_changed_at=datetime.utcnow(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Register the department (issuing its API key on first use)
    from app.services.api_key_service import ensure_department
    ensure_department(db, new_user.department)

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


@router.post("/change-password")
async def change_password(
    request: Request,
    response: Response,
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change the signed-in user's own password (any role, including Administrators).

    Required on first sign-in and after an Administrator reset; available at any time otherwise.
    Other sessions for this account are signed out; this session gets a fresh token.
    """
    if not check_user_password(user, payload.current_password):
        log_from_request(db, request, "password_change_failed", "Incorrect current password", user=user)
        raise HTTPException(status_code=400, detail="Your current password is incorrect.")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="The new passwords do not match.")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="Choose a password that is different from your current one.")
    policy_error = password_policy_error(payload.new_password, user.username)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)

    was_required = user.password_change_required
    set_user_password(db, user, payload.new_password, require_change=False)
    token = _issue_session(response, user)
    log_from_request(
        db, request, "password_change",
        "Changed password (required at sign-in)" if was_required else "Changed password",
        user=user,
    )
    return {
        "success": True,
        "message": "Your password has been changed.",
        "token": token,
        "access_token": token,
        "token_type": "bearer",
    }
