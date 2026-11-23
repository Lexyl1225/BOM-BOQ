import json
import logging
import secrets
import string
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.config import BASE_DIR
from app.models import User
from app.auth import get_password_hash

logger = logging.getLogger("bom_app")

# ---------------------------------------------------------------------------
# Password policy & lifecycle
# ---------------------------------------------------------------------------
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72  # bcrypt only uses the first 72 bytes
PASSWORD_POLICY_TEXT = (
    f"At least {PASSWORD_MIN_LENGTH} characters, with at least one letter and one number."
)

def password_policy_error(password: str, username: Optional[str] = None) -> Optional[str]:
    """Return a message describing why the password is unacceptable, or None if it's fine."""
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
    if len(password.encode("utf-8")) > PASSWORD_MAX_LENGTH:
        return f"Password must be at most {PASSWORD_MAX_LENGTH} characters long."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Password must contain at least one letter and one number."
    if username and password.strip().lower() == username.strip().lower():
        return "Password must not be the same as the username."
    return None

def generate_temporary_password(length: int = 12) -> str:
    """Random temporary password that satisfies the policy (no look-alike characters)."""
    letters = "".join(c for c in string.ascii_letters if c not in "IlO")
    digits = "23456789"
    alphabet = letters + digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c in digits for c in pwd) and any(c in letters for c in pwd):
            return pwd

def set_user_password(db: Session, user: User, new_password: str, require_change: bool) -> User:
    """Store a new password. require_change=True makes the user pick a new one at
    next sign-in (Administrator reset). Older sessions stop working (see auth.password_stamp)."""
    user.password = get_password_hash(new_password)
    user.must_change_password = bool(require_change)
    user.password_changed_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()

def get_all_users(db: Session) -> List[User]:
    return db.query(User).order_by(User.id.asc()).all()

def create_user(
    db: Session,
    username: str,
    password: str,
    role: str = "guest",
    department: str = "",
    email: Optional[str] = None
) -> User:
    username = username.strip()
    existing = get_user_by_username(db, username)
    if existing:
        raise ValueError(f"Username '{username}' already exists.")
    
    password_hash = get_password_hash(password)
    user = User(
        username=username,
        password=password_hash,
        role=role,
        department=department or "",
        email=email,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _register_department(db, user.department)
    return user

def _register_department(db: Session, department: Optional[str]) -> None:
    """Make sure the department exists and has an API key (issued on first use)."""
    from app.services.api_key_service import ensure_department
    ensure_department(db, department)

def update_user(db: Session, user_id: int, updates: Dict[str, Any]) -> Optional[User]:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    
    if "role" in updates and updates["role"] is not None:
        user.role = updates["role"]
    if "department" in updates and updates["department"] is not None:
        user.department = updates["department"]
    if "email" in updates:
        user.email = updates["email"]
    if "is_active" in updates and updates["is_active"] is not None:
        user.is_active = updates["is_active"]
    if "password" in updates and updates["password"]:
        error = password_policy_error(updates["password"], user.username)
        if error:
            raise ValueError(error)
        user.password = get_password_hash(updates["password"])
        user.password_changed_at = datetime.utcnow()
        require = updates.get("require_password_change")
        user.must_change_password = True if require is None else bool(require)
        
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    if "department" in updates and updates["department"] is not None:
        _register_department(db, user.department)
    return user

def delete_user(db: Session, user_id: int) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True

def update_last_login(db: Session, username: str):
    user = get_user_by_username(db, username)
    if user:
        user.last_login = datetime.utcnow()
        db.commit()

def sync_users_to_json(db: Session) -> Dict[str, Any]:
    """Sync all active database users back to users.json for offline backup."""
    users = get_all_users(db)
    export_list = []
    for u in users:
        export_list.append({
            "username": u.username,
            "password": u.password,
            "role": u.role,
            "department": u.department or "",
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""
        })
    users_file = BASE_DIR / "users.json"
    with open(users_file, "w", encoding="utf-8") as f:
        json.dump(export_list, f, indent=4)
    return {"success": True, "message": f"Successfully backed up {len(export_list)} users to JSON"}
