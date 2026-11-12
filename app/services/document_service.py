import json
import random
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc
from app.models import Document, User, DocumentAttachment

def _format_doc(doc: Document) -> Dict[str, Any]:
    """Helper to convert Document ORM model to dictionary with parsed items and attachments."""
    items = []
    if doc.items:
        try:
            items = json.loads(doc.items)
        except Exception:
            items = []
            
    atts = []
    if doc.attachments:
        for a in doc.attachments:
            atts.append({
                "id": a.id,
                "document_id": a.document_id,
                "file_name": a.file_name,
                "original_name": a.original_name,
                "file_type": a.file_type,
                "file_size": a.file_size,
                "file_path": a.file_path if (a.file_path and a.file_path.startswith("/")) else f"/{a.file_path}",
                "uploaded_by": a.uploaded_by,
                "uploaded_by_username": a.uploader.username if a.uploader else None,
                "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None
            })

    return {
        "id": doc.id,
        "name": doc.name,
        "document_name": doc.name,
        "documentName": doc.name,
        "ref_no": doc.ref_no,
        "type": doc.type,
        "document_type": doc.type,
        "documentType": doc.type,
        "status": doc.status,
        "department": doc.department,
        "project_name": doc.project_name,
        "location": doc.location,
        "date_value": doc.date_value,
        "html_content": doc.html_content,
        "items": items,
        "original_type": doc.original_type,
        "original_index": doc.original_index,
        "created_by": doc.created_by,
        "created_by_username": doc.creator.username if doc.creator else None,
        "username": doc.creator.username if doc.creator else None,
        "creator_department": doc.creator.department if doc.creator else "",
        "approved_by": doc.approved_by,
        "approved_by_username": doc.approver.username if doc.approver else None,
        "approved_at": doc.approved_at.isoformat() if doc.approved_at else None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "posted_date": doc.posted_date.isoformat() if doc.posted_date else None,
        "completed_date": doc.completed_date.isoformat() if doc.completed_date else None,
        "unposted_date": doc.unposted_date.isoformat() if doc.unposted_date else None,
        "last_edited": doc.last_edited.isoformat() if doc.last_edited else None,
        "attachments": atts
    }

def save_document(
    db: Session,
    document_name: str,
    document_type: str,
    items: Any,
    user: User,
    status: str = "saved"
) -> Dict[str, Any]:
    """Save or update a document in database."""
    document_name = document_name.strip()
    if not document_name:
        return {"success": False, "message": "Document name is required"}

    # Extract htmlContent if present in items
    html_content = ""
    items_list = items if isinstance(items, list) else [items]
    if items_list and isinstance(items_list[0], dict):
        html_content = items_list[0].get("htmlContent", "")

    items_json = json.dumps(items)

    # Check if document already exists for this user or by name
    doc = db.query(Document).filter(
        Document.name == document_name,
        Document.created_by == user.id
    ).first()

    now = datetime.utcnow()
    if doc:
        doc.type = document_type.lower()
        doc.items = items_json
        doc.status = status
        if html_content:
            doc.html_content = html_content
        doc.updated_at = now
        db.commit()
        db.refresh(doc)
        return {"success": True, "message": "Document updated successfully", "id": doc.id}
    else:
        # Check if name is taken by another user
        existing_any = db.query(Document).filter(Document.name == document_name).first()
        if existing_any and user.role != "admin":
            # If exists but user has permission to edit via department or admin, update it
            if user.department and existing_any.creator and existing_any.creator.department == user.department:
                existing_any.type = document_type.lower()
                existing_any.items = items_json
                existing_any.status = status
                if html_content:
                    existing_any.html_content = html_content
                existing_any.updated_at = now
                db.commit()
                db.refresh(existing_any)
                return {"success": True, "message": "Document updated successfully", "id": existing_any.id}
        
        # New document
        ref_no = f"DOC-{now.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        new_doc = Document(
            name=document_name,
            ref_no=ref_no,
            type=document_type.lower(),
            items=items_json,
            html_content=html_content,
            created_by=user.id,
            status=status,
            department=user.department or None,
            created_at=now,
            updated_at=now
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        return {"success": True, "message": "Document saved successfully", "id": new_doc.id}

def get_document(db: Session, document_name_or_id: Union[str, int]) -> Optional[Dict[str, Any]]:
    """Retrieve single document by ID or by name."""
    if isinstance(document_name_or_id, int) or (isinstance(document_name_or_id, str) and document_name_or_id.isdigit()):
        doc = db.query(Document).filter(Document.id == int(document_name_or_id)).first()
    else:
        doc = db.query(Document).filter(Document.name == str(document_name_or_id)).first()
    
    if not doc:
        return None
    return _format_doc(doc)

def list_documents_for_user(db: Session, user: User, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """List documents scoped to user role & department."""
    is_admin = user.role == "admin"
    is_purchasing = (user.role in ("user", "department_admin") and (user.department or "").strip().lower() == "purchasing")
    dept = (user.department or "").strip()

    query = db.query(Document)

    if is_admin:
        # Admin sees everything
        if status_filter:
            query = query.filter(Document.status == status_filter)
    elif is_purchasing:
        # Purchasing sees pending_price_edit, posted, and unposted
        if status_filter:
            query = query.filter(Document.status == status_filter)
        else:
            query = query.filter(Document.status.in_(["pending_price_edit", "posted", "unposted"]))
    elif dept:
        # Users in a department see:
        # 1. Documents where creator is in same department, OR
        # 2. Documents created by themselves, OR
        # 3. Documents with status='unposted'
        query = query.join(Document.creator).filter(
            or_(
                User.department == dept,
                Document.created_by == user.id,
                Document.status == "unposted"
            )
        )
        if status_filter:
            query = query.filter(Document.status == status_filter)
    else:
        # Users without department see their own + unposted
        query = query.filter(
            or_(
                Document.created_by == user.id,
                Document.status == "unposted"
            )
        )
        if status_filter:
            query = query.filter(Document.status == status_filter)

    docs = query.order_by(desc(Document.updated_at)).all()
    
    # Deduplicate by document name
    seen = set()
    result = []
    for d in docs:
        if d.name not in seen:
            result.append(_format_doc(d))
            seen.add(d.name)
    return result

def update_document_status(db: Session, document_name: str, new_status: str, user: User) -> bool:
    """Update status of a document."""
    doc = db.query(Document).filter(Document.name == document_name).first()
    if not doc:
        return False

    # Check permission
    is_admin = user.role == "admin"
    is_purchasing = (user.department or "").strip().lower() == "purchasing"
    is_owner = doc.created_by == user.id
    same_dept = bool(user.department and doc.creator and doc.creator.department == user.department)

    if not (is_admin or is_purchasing or is_owner or same_dept):
        return False

    doc.status = new_status
    doc.updated_at = datetime.utcnow()
    if new_status == "posted":
        doc.posted_date = datetime.utcnow()
    elif new_status == "unposted":
        doc.unposted_date = datetime.utcnow()
    elif new_status == "completed":
        doc.completed_date = datetime.utcnow()

    db.commit()
    return True

def save_price_edit(
    db: Session,
    document_name: str,
    items: Any,
    status: str,
    user: User,
    target_department: Optional[str] = None
) -> Dict[str, Any]:
    """Save price edit changes from Purchasing / Admin / Creator."""
    doc = db.query(Document).filter(Document.name == document_name).first()
    if not doc:
        return {"success": False, "message": "Document not found in database"}

    # Extract html content if present
    items_list = items if isinstance(items, list) else [items]
    html_content = ""
    if items_list and isinstance(items_list[0], dict):
        html_content = items_list[0].get("htmlContent", "")

    doc.items = json.dumps(items)
    doc.status = status
    if html_content:
        doc.html_content = html_content
    if target_department:
        doc.department = target_department
    doc.updated_at = datetime.utcnow()
    doc.last_edited = datetime.utcnow()

    db.commit()
    return {"success": True, "message": "Document updated successfully"}

def delete_document(db: Session, document_name: str, user: User) -> bool:
    """Delete document with permission check."""
    doc = db.query(Document).filter(Document.name == document_name).first()
    if not doc:
        return False

    is_admin = user.role == "admin"
    is_purchasing = (user.department or "").strip().lower() == "purchasing"
    is_owner = doc.created_by == user.id
    same_dept = bool(user.department and doc.creator and doc.creator.department == user.department)

    if not (is_admin or is_purchasing or is_owner or same_dept):
        return False

    db.delete(doc)
    db.commit()
    return True

def list_documents_for_approval(db: Session, user: User) -> List[Dict[str, Any]]:
    """List posted documents waiting for department approval."""
    is_admin = user.role == "admin"
    is_dept_admin = user.role == "department_admin"

    if not (is_admin or is_dept_admin):
        return []

    query = db.query(Document).filter(Document.status == "posted")
    if not is_admin:
        query = query.filter(Document.department == user.department)

    docs = query.order_by(Document.department.asc(), desc(Document.updated_at)).all()
    return [_format_doc(d) for d in docs]

def approve_document(db: Session, document_name: str, approver: User) -> Dict[str, Any]:
    """Approve a posted document."""
    doc = db.query(Document).filter(
        Document.name == document_name,
        Document.status == "posted"
    ).first()
    
    if not doc:
        return {"success": False, "message": "Document not found or is not in 'posted' status"}

    doc.status = "approved"
    doc.approved_by = approver.id
    doc.approved_at = datetime.utcnow()
    doc.updated_at = datetime.utcnow()

    db.commit()
    return {"success": True, "message": "Document approved successfully"}

def list_approved_documents(db: Session) -> List[Dict[str, Any]]:
    """List all approved documents for Purchasing PO page."""
    docs = db.query(Document).filter(Document.status == "approved").order_by(desc(Document.approved_at)).all()
    return [_format_doc(d) for d in docs]
