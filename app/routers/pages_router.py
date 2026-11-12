"""
HTML Page Router for BOM / BOQ Studio Pro
Serves rendered Jinja2 templates and provides seamless backward-compatibility redirects for .php URLs.
"""

from typing import Optional
from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, Document, CostEstimate, ActivityLog
from app.auth import get_current_user_optional

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")

def _require_auth(user: Optional[User]) -> Optional[RedirectResponse]:
    """Helper to redirect unauthenticated users to the login page."""
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return None

# ==========================================
# Authentication Pages
# ==========================================

@router.get("/login", response_class=HTMLResponse)
@router.get("/login.php", response_class=HTMLResponse)
def login_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"user": None, "hide_nav": True, "active_page": "login"}
    )

@router.get("/logout")
@router.get("/logout.php")
def logout_page():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.COOKIE_NAME)
    return response

# ==========================================
# Dashboard & Main Pages
# ==========================================

@router.get("/", response_class=HTMLResponse)
@router.get("/index.php", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect

    # Calculate real-time KPI metrics
    metrics = {
        "total_documents": db.query(Document).count(),
        "pending_price_edit": db.query(Document).filter(Document.status == "pending_price_edit").count(),
        "posted_for_approval": db.query(Document).filter(Document.status == "posted").count(),
        "approved_for_po": db.query(Document).filter(Document.status == "approved").count(),
        "total_estimates": db.query(CostEstimate).count(),
        "total_users": db.query(User).filter(User.is_active == True).count(),
    }

    recent_logs = (
        db.query(ActivityLog)
        .order_by(ActivityLog.timestamp.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "active_page": "home",
            "metrics": metrics,
            "recent_logs": recent_logs,
        }
    )

# ==========================================
# Document Creation & Management Pages
# ==========================================

@router.get("/bom", response_class=HTMLResponse)
@router.get("/bom.php", response_class=HTMLResponse)
def bom_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect
    return templates.TemplateResponse(
        request=request,
        name="bom.html",
        context={"user": user, "active_page": "bom"}
    )

@router.get("/boq", response_class=HTMLResponse)
@router.get("/bom_labor.php", response_class=HTMLResponse)
@router.get("/boq.php", response_class=HTMLResponse)
def boq_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect
    return templates.TemplateResponse(
        request=request,
        name="boq.html",
        context={"user": user, "active_page": "boq"}
    )

@router.get("/save_bomboq", response_class=HTMLResponse)
@router.get("/save_bomboq.php", response_class=HTMLResponse)
def save_bomboq_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect
    return templates.TemplateResponse(
        request=request,
        name="save_bomboq.html",
        context={"user": user, "active_page": "save_bomboq"}
    )

# ==========================================
# Workflow & Pricing Pages
# ==========================================

@router.get("/price_edit_bomboq", response_class=HTMLResponse)
@router.get("/price_edit_bomboq.php", response_class=HTMLResponse)
def price_edit_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect
    
    # Permission check: Admin or Purchasing
    is_admin = user.role == "admin"
    is_purchasing = (user.department or "").strip().lower() == "purchasing"
    if not (is_admin or is_purchasing):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="price_edit_bomboq.html",
        context={"user": user, "active_page": "price_edit"}
    )

@router.get("/approver", response_class=HTMLResponse)
@router.get("/approver.php", response_class=HTMLResponse)
def approver_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect

    # Permission check: Department Admin or Admin
    if user.role not in ["department_admin", "admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="approver.html",
        context={"user": user, "active_page": "approver"}
    )

@router.get("/approved_for_po", response_class=HTMLResponse)
@router.get("/approved_for_po.php", response_class=HTMLResponse)
def approved_for_po_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect

    # Permission check: Admin or Purchasing
    is_admin = user.role == "admin"
    is_purchasing = (user.department or "").strip().lower() == "purchasing"
    if not (is_admin or is_purchasing):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="approved_for_po.html",
        context={"user": user, "active_page": "po"}
    )

# ==========================================
# Cost Estimation & Audit Logs
# ==========================================

@router.get("/estimate", response_class=HTMLResponse)
@router.get("/estimate.php", response_class=HTMLResponse)
def estimate_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect
    return templates.TemplateResponse(
        request=request,
        name="estimate.html",
        context={"user": user, "active_page": "estimate"}
    )

@router.get("/user_logs", response_class=HTMLResponse)
@router.get("/user_logs.php", response_class=HTMLResponse)
def user_logs_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect
    return templates.TemplateResponse(
        request=request,
        name="user_logs.html",
        context={"user": user, "active_page": "logs"}
    )

# ==========================================
# Admin Management Pages
# ==========================================

@router.get("/users_admin", response_class=HTMLResponse)
@router.get("/users_admin.php", response_class=HTMLResponse)
def users_admin_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    auth_redirect = _require_auth(user)
    if auth_redirect:
        return auth_redirect

    # Admin only
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="users_admin.html",
        context={"user": user, "active_page": "users_admin"}
    )
