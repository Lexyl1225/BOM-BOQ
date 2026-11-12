"""
Legacy PHP API Compatibility Router
Emulates original PHP endpoints (document_api.php, user_api.php, estimate_api.php, upload_api.php)
ensuring 100% backward compatibility for all AJAX/Fetch requests.
"""

import os
import json
from typing import Optional, Any
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.config import BASE_DIR
from app.database import get_db
from app.models import User, DocumentAttachment
from app.auth import get_current_user_optional, require_purchasing_or_admin
from app.services.activity_service import log_from_request
from app.services.document_service import (
    save_document, get_document, list_documents_for_user,
    update_document_status, save_price_edit, delete_document,
    list_documents_for_approval, approve_document, list_approved_documents
)
from app.services.estimate_service import (
    save_estimate, list_estimates, update_estimate, delete_estimate
)
from app.services.user_service import (
    get_all_users, sync_users_to_json
)

router = APIRouter(prefix="/api", tags=["Legacy Compatibility"])

async def parse_request_data(request: Request) -> dict:
    """Parse JSON body or Form data gracefully."""
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
    return {}

# ==========================================
# Legacy Document API (api/document_api.php)
# ==========================================

async def _handle_legacy_document_api(request: Request, user: Optional[User], db: Session):
    if not user:
        return {"success": False, "message": "Not authenticated"}

    data = await parse_request_data(request)
    action = data.get("action") or request.query_params.get("action")

    if action == "save":
        res = save_document(
            db=db,
            document_name=data.get("documentName", ""),
            document_type=data.get("documentType", "bom"),
            items=data.get("items", []),
            user=user,
            status=data.get("status", "saved")
        )
        if res["success"]:
            log_from_request(db, request, "save", f"Document: {data.get('documentName')}", user=user)
        return res

    elif action == "load":
        doc_name = data.get("documentName") or request.query_params.get("documentName")
        if not doc_name:
            return {"success": False, "message": "Document name required"}
        doc = get_document(db, doc_name)
        if not doc:
            return {"success": False, "message": "Document not found"}
        return {"success": True, "document": doc}

    elif action == "list":
        status_filter = data.get("status") or request.query_params.get("status")
        docs = list_documents_for_user(db, user, status_filter=status_filter)
        return {"success": True, "documents": docs, "count": len(docs)}

    elif action == "update_status":
        doc_name = data.get("documentName")
        status_val = data.get("status")
        success = update_document_status(db, doc_name, status_val, user)
        if success:
            log_from_request(db, request, status_val, f"Document: {doc_name}", user=user)
            return {"success": True, "message": "Status updated"}
        return {"success": False, "message": "Update failed or unauthorized"}

    elif action == "save_price_edit":
        res = save_price_edit(
            db=db,
            document_name=data.get("documentName", ""),
            items=data.get("items", []),
            status=data.get("status", "pending_price_edit"),
            user=user,
            target_department=data.get("targetDepartment")
        )
        if res["success"]:
            details = f"Document: {data.get('documentName')}"
            if data.get("targetDepartment"):
                details += f" posted to department: {data.get('targetDepartment')}"
            log_from_request(db, request, "save_price_edit", details, user=user)
        return res

    elif action == "delete":
        doc_name = data.get("documentName") or request.query_params.get("documentName")
        success = delete_document(db, doc_name, user)
        if success:
            log_from_request(db, request, "delete", f"Document: {doc_name}", user=user)
            return {"success": True, "message": "Document deleted"}
        return {"success": False, "message": "Delete failed or unauthorized"}

    elif action == "list_for_approval":
        if user.role not in ("admin", "department_admin"):
            return {"success": False, "message": "Unauthorized"}
        docs = list_documents_for_approval(db, user)
        return {"success": True, "documents": docs}

    elif action == "approve":
        if user.role not in ("admin", "department_admin"):
            return {"success": False, "message": "Unauthorized"}
        res = approve_document(db, data.get("documentName", ""), user)
        if res["success"]:
            log_from_request(db, request, "approve", f"Approved document: {data.get('documentName')}", user=user)
        return res

    elif action == "list_approved":
        is_purchasing = (user.role in ("user", "department_admin") and (user.department or "").strip().lower() == "purchasing")
        if not (user.role == "admin" or is_purchasing):
            return {"success": False, "message": "Unauthorized"}
        docs = list_approved_documents(db)
        return {"success": True, "documents": docs}

    elif action == "sync":
        docs = list_documents_for_user(db, user)
        organized = {"saved": {}, "posted": {}, "pending_price_edit": {}, "unposted": {}}
        for d in docs:
            st = d.get("status", "saved")
            if st in organized:
                organized[st][d["name"]] = {
                    "type": d["type"],
                    ("bomItems" if d["type"] == "bom" else "boqItems"): d.get("items", [])
                }
        return {"success": True, "documents": organized}

    elif action == "get_attachments":
        doc_id = data.get("documentId") or data.get("document_id") or request.query_params.get("documentId") or request.query_params.get("document_id")
        if not doc_id:
            return {"success": False, "message": "Document ID required"}
        atts = db.query(DocumentAttachment).filter(DocumentAttachment.document_id == int(doc_id)).order_by(DocumentAttachment.uploaded_at.desc()).all()
        results = []
        for a in atts:
            results.append({
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
        return {"success": True, "attachments": results}

    elif action == "delete_attachment":
        is_admin = user.role == "admin"
        is_purchasing = (user.department or "").strip().lower() == "purchasing"
        if not (is_admin or is_purchasing):
            return {"success": False, "message": "Access denied. Only Purchasing department or Admin can delete attachments."}
        att_id = data.get("attachmentId") or data.get("attachment_id") or request.query_params.get("attachmentId") or request.query_params.get("attachment_id")
        if not att_id:
            return {"success": False, "message": "Attachment ID required"}
        att = db.query(DocumentAttachment).filter(DocumentAttachment.id == int(att_id)).first()
        if not att:
            return {"success": False, "message": "Attachment not found"}

        full_path = BASE_DIR / att.file_path
        if full_path.exists():
            try:
                os.remove(full_path)
            except Exception:
                pass
        orig_name = att.original_name
        db.delete(att)
        db.commit()
        log_from_request(db, request, "delete_attachment", f"Deleted file: {orig_name}", user=user)
        return {"success": True, "message": "Attachment deleted successfully"}

    return {"success": False, "message": f"Unknown action: {action}"}

@router.get("/document_api.php")
async def legacy_document_api_get(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    return await _handle_legacy_document_api(request, user, db)

@router.post("/document_api.php")
async def legacy_document_api_post(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    return await _handle_legacy_document_api(request, user, db)

# ==========================================
# Legacy User API (api/user_api.php)
# ==========================================

async def _handle_legacy_user_api(request: Request, user: Optional[User], db: Session):
    data = await parse_request_data(request)
    action = data.get("action") or request.query_params.get("action")

    if action == "status":
        return {"success": True, "database_available": True}

    if not user or user.role != "admin":
        return {"success": False, "message": "Admin access required"}

    if action == "list":
        users = get_all_users(db)
        user_list = [
            {
                "id": u.id,
                "username": u.username,
                "role": u.role,
                "department": u.department or "",
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "is_active": u.is_active
            }
            for u in users
        ]
        return {"success": True, "users": user_list, "count": len(user_list)}

    elif action in ("sync", "sync_to_json"):
        res = sync_users_to_json(db)
        return res

    return {"success": False, "message": f"Unknown action: {action}"}

@router.get("/user_api.php")
async def legacy_user_api_get(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    return await _handle_legacy_user_api(request, user, db)

@router.post("/user_api.php")
async def legacy_user_api_post(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    return await _handle_legacy_user_api(request, user, db)

# ==========================================
# Legacy Estimate API (api/estimate_api.php)
# ==========================================

async def _handle_legacy_estimate_api(request: Request, user: Optional[User], db: Session):
    if not user:
        return {"success": False, "message": "Not authenticated"}

    data = await parse_request_data(request)
    action = data.get("action") or request.query_params.get("action")

    if action == "list":
        estimates = list_estimates(db, user)
        return {"success": True, "estimates": estimates}

    elif action == "save":
        res = save_estimate(db, data, user)
        if res["success"]:
            log_from_request(db, request, "save_estimate", f"Saved cost estimate: {data.get('estimateName')}", user=user)
        return res

    elif action == "update":
        est_id = int(data.get("id", 0))
        res = update_estimate(db, est_id, data, user)
        if res["success"]:
            log_from_request(db, request, "update_estimate", f"Updated cost estimate: {data.get('estimateName')}", user=user)
        return res

    elif action == "delete":
        est_id = int(data.get("id", 0))
        res = delete_estimate(db, est_id, user)
        if res["success"]:
            log_from_request(db, request, "delete_estimate", f"Deleted cost estimate ID: {est_id}", user=user)
        return res

    return {"success": False, "message": f"Unknown action: {action}"}

@router.get("/estimate_api.php")
async def legacy_estimate_api_get(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    return await _handle_legacy_estimate_api(request, user, db)

@router.post("/estimate_api.php")
async def legacy_estimate_api_post(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    return await _handle_legacy_estimate_api(request, user, db)

# ==========================================
# Legacy Upload API (api/upload_api.php)
# ==========================================

@router.post("/upload_api.php")
async def legacy_upload_api(
    request: Request,
    document_id: int = Form(...),
    file: UploadFile = File(...),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """100% backward-compatible handler for api/upload_api.php."""
    if not user:
        return {"success": False, "message": "Not authenticated"}

    is_admin = user.role == "admin"
    is_purchasing = (user.department or "").strip().lower() == "purchasing"
    if not (is_admin or is_purchasing):
        return {"success": False, "message": "Access denied. Only Purchasing department can upload files."}

    from app.routers.uploads_router import upload_attachment
    try:
        res = await upload_attachment(
            request=request,
            document_id=document_id,
            file=file,
            user=user,
            db=db
        )
        return res
    except HTTPException as e:
        return {"success": False, "message": e.detail}
    except Exception as e:
        return {"success": False, "message": str(e)}
