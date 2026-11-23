"""
Department API Key Service

Every /api request must carry a valid API key (header ``X-API-Key``). Each department
owns exactly one key, and a signed-in user may only use the key of their own department.

Storage
-------
* ``key_hash``      SHA-256 of the key — used to look the key up and validate it.
* ``key_encrypted`` Fernet-encrypted copy — lets the web UI attach the department's key
                    to the browser requests of signed-in users, and lets Administrators
                    reveal a key to configure an external client.
* ``key_prefix`` / ``key_last4`` — for the masked display.

Keys are produced by ``generate_api_key()`` in the project-root ``api-key-gen.py``.
"""

import base64
import hashlib
import importlib.util
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings
from app.models import Department, DepartmentApiKey, User

logger = logging.getLogger("bom_app")

API_KEY_HEADER = "X-API-Key"
UNASSIGNED_SLUG = "unassigned"
UNASSIGNED_NAME = "Unassigned (no department)"
LAST_USED_WRITE_INTERVAL = timedelta(seconds=60)

# ---------------------------------------------------------------------------
# Key generation (delegates to api-key-gen.py)
# ---------------------------------------------------------------------------

_generator = None

def _load_generator():
    """Import generate_api_key() from api-key-gen.py (hyphenated name → load by path)."""
    global _generator
    if _generator is None:
        path = BASE_DIR / "api-key-gen.py"
        spec = importlib.util.spec_from_file_location("api_key_gen", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"API key generator not found at {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _generator = module.generate_api_key
    return _generator

def generate_raw_key() -> str:
    return _load_generator()()

# ---------------------------------------------------------------------------
# Crypto helpers
# ---------------------------------------------------------------------------

def _fernet() -> Fernet:
    secret = os.getenv("API_KEY_ENCRYPTION_KEY") or settings.SECRET_KEY
    digest = hashlib.sha256(b"bom-department-api-key:" + secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

def decrypt_key(record: Optional[DepartmentApiKey]) -> Optional[str]:
    if not record:
        return None
    try:
        return _fernet().decrypt(record.key_encrypted.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning(
            "Could not decrypt API key for department id %s (encryption secret changed?). "
            "Regenerate the key on the API Keys page.", record.department_id
        )
        return None

def mask_key(record: Optional[DepartmentApiKey]) -> str:
    if not record:
        return ""
    return f"{record.key_prefix}{'•' * 12}{record.key_last4}"

# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

def department_slug(name: Optional[str]) -> str:
    slug = (name or "").strip().lower()
    return slug or UNASSIGNED_SLUG

def user_department_slug(user: Optional[User]) -> str:
    return department_slug(user.department if user else "")

def get_department_by_slug(db: Session, slug: str) -> Optional[Department]:
    return db.query(Department).filter(Department.slug == slug).first()

def ensure_department(db: Session, name: Optional[str], created_by: Optional[User] = None) -> Department:
    """Return the department for `name`, creating it (with a fresh API key) if new.

    Keys are only auto-issued when a department is first registered, so a key that an
    Administrator revoked stays revoked across restarts.
    """
    slug = department_slug(name)
    dept = get_department_by_slug(db, slug)
    if dept:
        return dept
    display = UNASSIGNED_NAME if slug == UNASSIGNED_SLUG else (name or "").strip()
    dept = Department(name=display, slug=slug)
    db.add(dept)
    db.flush()
    _issue_key(db, dept, created_by)
    db.commit()
    db.refresh(dept)
    logger.info("Registered department '%s' and issued its API key.", display)
    return dept

def sync_departments(db: Session) -> int:
    """Register every department referenced by a user. Returns how many were added."""
    added = 0
    names = [row[0] for row in db.query(User.department).distinct().all()]
    seen = set()
    for name in names:
        slug = department_slug(name)
        if slug in seen:
            continue
        seen.add(slug)
        if not get_department_by_slug(db, slug):
            ensure_department(db, name)
            added += 1
    return added

# ---------------------------------------------------------------------------
# Key lifecycle
# ---------------------------------------------------------------------------

def _issue_key(db: Session, dept: Department, actor: Optional[User]) -> str:
    raw = generate_raw_key()
    record = dept.api_key
    if record is None:
        record = DepartmentApiKey(department_id=dept.id)
        db.add(record)
        dept.api_key = record
    record.key_hash = hash_key(raw)
    record.key_encrypted = _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")
    record.key_prefix = raw[:6]
    record.key_last4 = raw[-4:]
    record.is_active = True
    record.created_at = datetime.utcnow()
    record.created_by = actor.id if actor else None
    record.last_used_at = None
    record.last_used_ip = None
    return raw

def regenerate_key(db: Session, dept: Department, actor: Optional[User]) -> str:
    """Generate (or replace) the department's key. The previous key stops working immediately."""
    raw = _issue_key(db, dept, actor)
    db.commit()
    return raw

def set_key_active(db: Session, dept: Department, active: bool) -> bool:
    if not dept.api_key:
        return False
    dept.api_key.is_active = active
    db.commit()
    return True

def revoke_key(db: Session, dept: Department) -> bool:
    """Permanently delete the department's key. A new one must be generated to restore access."""
    if not dept.api_key:
        return False
    db.delete(dept.api_key)
    db.commit()
    return True

def describe_departments(db: Session) -> List[Dict]:
    sync_departments(db)
    # Users whose department differs only by case/spacing share one slug
    counts: Dict[str, int] = {}
    for name, n in db.query(User.department, func.count(User.id)).group_by(User.department).all():
        counts[department_slug(name)] = counts.get(department_slug(name), 0) + n

    rows = []
    for dept in db.query(Department).order_by(Department.name).all():
        key = dept.api_key
        rows.append({
            "id": dept.id,
            "name": dept.name,
            "slug": dept.slug,
            "user_count": counts.get(dept.slug, 0),
            "has_key": key is not None,
            "masked_key": mask_key(key),
            "is_active": bool(key and key.is_active),
            "created_at": key.created_at.isoformat() if key and key.created_at else None,
            "created_by": key.creator.username if key and key.creator else None,
            "last_used_at": key.last_used_at.isoformat() if key and key.last_used_at else None,
            "last_used_ip": key.last_used_ip if key else None,
        })
    return rows

# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

@dataclass
class KeyCheck:
    ok: bool
    status_code: int = 200
    code: str = ""
    message: str = ""

def validate_request_key(
    db: Session,
    raw_key: Optional[str],
    user: Optional[User],
    client_ip: Optional[str] = None,
) -> KeyCheck:
    if not raw_key:
        return KeyCheck(False, 401, "api_key_missing",
                        f"API key required. Send your department's key in the {API_KEY_HEADER} header.")

    record = db.query(DepartmentApiKey).filter(DepartmentApiKey.key_hash == hash_key(raw_key.strip())).first()
    if not record:
        return KeyCheck(False, 401, "api_key_invalid", "Invalid API key.")
    if not record.is_active:
        return KeyCheck(False, 401, "api_key_inactive",
                        f"The API key for {record.department.name} has been deactivated. Contact an Administrator.")

    if user is not None and record.department.slug != user_department_slug(user):
        return KeyCheck(False, 403, "api_key_department_mismatch",
                        "This API key does not belong to your department.")

    now = datetime.utcnow()
    if record.last_used_at is None or now - record.last_used_at > LAST_USED_WRITE_INTERVAL:
        record.last_used_at = now
        record.last_used_ip = client_ip
        db.commit()
    return KeyCheck(True)

def key_for_user(db: Session, user: Optional[User]) -> Optional[str]:
    """Plain key for the user's department (for the web UI), or None if missing/inactive."""
    if not user:
        return None
    dept = get_department_by_slug(db, user_department_slug(user))
    if not dept or not dept.api_key or not dept.api_key.is_active:
        return None
    return decrypt_key(dept.api_key)
