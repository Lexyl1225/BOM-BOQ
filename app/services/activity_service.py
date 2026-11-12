import uuid
from datetime import datetime
from typing import Optional
from fastapi import Request
from sqlalchemy.orm import Session
from app.models import ActivityLog, User

def log_activity(
    db: Session,
    action: str,
    details: str = "",
    page: str = "",
    username: str = "Unknown",
    user_id: Optional[int] = None,
    role: Optional[str] = None,
    department: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> ActivityLog:
    """Insert a new activity log record into database."""
    log_id = f"log_{uuid.uuid4().hex[:13]}"
    
    log = ActivityLog(
        log_id=log_id,
        timestamp=datetime.utcnow(),
        username=username,
        user_id=user_id,
        role=role,
        department=department,
        action=action,
        details=details,
        page=page,
        ip_address=ip_address or "Unknown",
        user_agent=user_agent or "Unknown"
    )
    
    try:
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    except Exception:
        db.rollback()
        raise

def log_from_request(
    db: Session,
    request: Request,
    action: str,
    details: str = "",
    user: Optional[User] = None,
    page: Optional[str] = None
) -> Optional[ActivityLog]:
    """Helper to extract IP, user agent, and user info from Request and log."""
    try:
        ip = request.client.host if request.client else "Unknown"
        if "x-forwarded-for" in request.headers:
            ip = request.headers["x-forwarded-for"].split(",")[0].strip()
            
        ua = request.headers.get("user-agent", "Unknown")
        
        username = user.username if user else "Guest"
        user_id = user.id if user else None
        role = user.role if user else "guest"
        dept = user.department if user else ""
        page_name = page or request.url.path
        
        return log_activity(
            db=db,
            action=action,
            details=details,
            page=page_name,
            username=username,
            user_id=user_id,
            role=role,
            department=dept,
            ip_address=ip,
            user_agent=ua
        )
    except Exception:
        return None
