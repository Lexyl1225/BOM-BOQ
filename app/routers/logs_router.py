import math
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, distinct, or_
from app.database import get_db
from app.models import ActivityLog, User
from app.schemas import ActivityLogResponse, ActivityLogCreate
from app.auth import get_current_user, get_current_user_optional
from app.services.activity_service import log_from_request

router = APIRouter(prefix="/api/logs", tags=["Activity Logs"])

@router.get("/")
async def get_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    limit: Optional[int] = Query(None, ge=1, le=500),
    username: Optional[str] = None,
    action: Optional[str] = None,
    log_date: Optional[str] = Query(None, alias="date"),
    search: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve activity logs with filtering and pagination."""
    effective_per_page = limit if limit is not None else per_page
    query = db.query(ActivityLog)

    if username and username.strip():
        query = query.filter(ActivityLog.username == username.strip())
    
    if action and action.strip():
        query = query.filter(ActivityLog.action == action.strip())

    if log_date and log_date.strip():
        # Match YYYY-MM-DD
        try:
            d = datetime.strptime(log_date.strip(), "%Y-%m-%d").date()
            query = query.filter(func.date(ActivityLog.timestamp) == d)
        except ValueError:
            pass

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ActivityLog.username.ilike(term),
                ActivityLog.action.ilike(term),
                ActivityLog.details.ilike(term),
                ActivityLog.page.ilike(term)
            )
        )

    total_logs = query.count()
    total_pages = math.ceil(total_logs / effective_per_page) if total_logs > 0 else 1
    offset = (page - 1) * effective_per_page

    logs = query.order_by(desc(ActivityLog.timestamp)).offset(offset).limit(effective_per_page).all()

    return {
        "success": True,
        "page": page,
        "per_page": effective_per_page,
        "total_logs": total_logs,
        "total_pages": total_pages,
        "logs": [
            {
                "id": l.id,
                "log_id": l.log_id,
                "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else "",
                "username": l.username,
                "user_id": l.user_id,
                "role": l.role or "guest",
                "department": l.department or "",
                "action": l.action,
                "details": l.details or "",
                "page": l.page or "",
                "ip_address": l.ip_address or ""
            }
            for l in logs
        ]
    }

@router.get("/stats")
async def get_log_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get activity log statistics."""
    total = db.query(ActivityLog).count()
    today_count = db.query(ActivityLog).filter(func.date(ActivityLog.timestamp) == date.today()).count()
    unique_users = [u[0] for u in db.query(distinct(ActivityLog.username)).all() if u[0]]
    unique_actions = [a[0] for a in db.query(distinct(ActivityLog.action)).all() if a[0]]

    return {
        "success": True,
        "total_activities": total,
        "activities_today": today_count,
        "unique_users_count": len(unique_users),
        "unique_users": sorted(unique_users),
        "unique_actions": sorted(unique_actions)
    }

@router.post("/")
async def create_log(
    request: Request,
    payload: ActivityLogCreate,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Client-side logging hook."""
    log_from_request(
        db=db,
        request=request,
        action=payload.action,
        details=payload.details or "",
        user=user,
        page=payload.page or ""
    )
    return {"success": True}
