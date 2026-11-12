import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.config import BASE_DIR
from app.models import User
from app.auth import get_password_hash

logger = logging.getLogger("bom_app")

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
    return user

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
        user.password = get_password_hash(updates["password"])
        
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
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
