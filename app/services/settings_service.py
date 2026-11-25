"""Application-wide settings that Administrators can change at runtime."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AppSetting, User

# Whether the read-only user manual is published at /quick-help (and linked from /login).
PUBLIC_HELP_KEY = "public_help_enabled"
PUBLIC_HELP_DEFAULT = True

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

def is_public_help_enabled(db: Session) -> bool:
    return get_bool(db, PUBLIC_HELP_KEY, PUBLIC_HELP_DEFAULT)

def set_public_help_enabled(db: Session, enabled: bool, user: Optional[User] = None) -> bool:
    return set_bool(db, PUBLIC_HELP_KEY, enabled, user)
