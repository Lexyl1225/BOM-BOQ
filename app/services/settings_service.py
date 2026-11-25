"""Application-wide settings that Administrators can change at runtime."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AppSetting, User

# Whether the read-only user manual is published at /quick-help (and linked from /login).
PUBLIC_HELP_KEY = "public_help_enabled"
PUBLIC_HELP_DEFAULT = True

# Whether new Guest accounts may be created from the sign-in page (Create Account).
GUEST_SIGNUP_KEY = "guest_signup_enabled"
GUEST_SIGNUP_DEFAULT = True

_TRUE = {"1", "true", "yes", "on"}

def get_bool(db: Session, key: str, default: bool) -> bool:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None or row.value is None:
        return default
    return row.value.strip().lower() in _TRUE

def set_bool(db: Session, key: str, value: bool, user: Optional[User] = None) -> bool:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        row = AppSetting(key=key)
        db.add(row)
    row.value = "true" if value else "false"
    row.updated_at = datetime.utcnow()
    row.updated_by = user.id if user else None
    db.commit()
    return value

def get_meta(db: Session, key: str) -> dict:
    """When a setting was last changed and by whom (empty when never changed)."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        return {"updated_at": None, "updated_by": None}
    by = None
    if row.updated_by:
        u = db.query(User).filter(User.id == row.updated_by).first()
        by = u.username if u else None
    return {"updated_at": row.updated_at.isoformat() if row.updated_at else None, "updated_by": by}

def is_public_help_enabled(db: Session) -> bool:
    return get_bool(db, PUBLIC_HELP_KEY, PUBLIC_HELP_DEFAULT)

def set_public_help_enabled(db: Session, enabled: bool, user: Optional[User] = None) -> bool:
    return set_bool(db, PUBLIC_HELP_KEY, enabled, user)

def is_guest_signup_enabled(db: Session) -> bool:
    return get_bool(db, GUEST_SIGNUP_KEY, GUEST_SIGNUP_DEFAULT)

def set_guest_signup_enabled(db: Session, enabled: bool, user: Optional[User] = None) -> bool:
    return set_bool(db, GUEST_SIGNUP_KEY, enabled, user)
