"""
REST API Router for Documents (BOM and BOQ)
Handles saving, loading, listing, price editing, status updating, department approvals, and PO retrieval.
"""

from typing import Optional, List, Any, Union
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import (
    DocumentSaveRequest, DocumentStatusUpdateRequest,
    DocumentPriceEditRequest, DocumentApproveRequest, ApiResponse
)
from app.auth import (
    get_current_user, require_department_admin_or_admin,
    require_purchasing_or_admin
)
from app.services.activity_service import log_from_request
from app.services.document_service import (
    save_document, get_document, list_documents_for_user,
    update_document_status, save_price_edit, delete_document,
    list_documents_for_approval, approve_document, list_approved_documents
)

router = APIRouter(prefix="/api/documents", tags=["Documents"])

# ==========================================
# Listing & Creation
# ==========================================

@router.get("/")
async def list_documents(
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List documents accessible to current user based on role and department."""
    docs = list_documents_for_user(db, user, status_filter=status)
    return {
        "success": True,
        "documents": docs,
        "count": len(docs)
    }

@router.post("/")
@router.post("/save")
async def save_doc(
    request: Request,
    payload: DocumentSaveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save or update a BOM/BOQ document."""
    if user.role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guests are not allowed to save documents. Please contact an administrator."
        )

    result = save_document(
        db=db,
        document_name=payload.documentName,
        document_type=payload.documentType,
        items=payload.items,
        user=user,
        status=payload.status or "saved"
    )
    if result["success"]:
        log_from_request(
            db, request, "save",
            f"Document: {payload.documentName} ({payload.documentType.upper()})",
            user=user
        )
    return result

@router.post("/load")
async def load_doc_post(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Load document by documentName in body."""
    doc_name = payload.get("documentName")
    if not doc_name:
        raise HTTPException(status_code=400, detail="Document name required")
    
    doc = get_document(db, doc_name)
    if not doc:
        return {"success": False, "message": "Document not found"}
    return {"success": True, "document": doc}

# ==========================================
# Status & Price Edit Endpoints
# ==========================================

@router.post("/update_status")
async def update_status_endpoint(
    request: Request,
    payload: DocumentStatusUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update status of a document."""
    success = update_document_status(db, payload.documentName, payload.status, user)
    if success:
        log_from_request(db, request, payload.status, f"Document: {payload.documentName}", user=user)
        return {"success": True, "message": "Status updated successfully"}
    return {"success": False, "message": "Failed to update status or access denied"}

@router.post("/save_price_edit")
@router.post("/price-edit")
async def save_price_edit_endpoint(
    request: Request,
    payload: DocumentPriceEditRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save unit price edits from Purchasing / MCE page."""
    result = save_price_edit(
        db=db,
        document_name=payload.documentName,
        items=payload.items,
        status=payload.status or "pending_price_edit",
        user=user,
        target_department=payload.targetDepartment
    )
    if result["success"]:
        details = f"Document: {payload.documentName}"
        if payload.targetDepartment:
            details += f" posted to department: {payload.targetDepartment}"
        log_from_request(db, request, "save_price_edit", details, user=user)
    return result

@router.post("/{doc_id_or_name}/price-edit")
async def save_price_edit_by_path(
    doc_id_or_name: str,
    request: Request,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save unit price edit referencing document by ID or Name."""
    doc = get_document(db, doc_id_or_name)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    items = payload.get("items", [])
    target_dept = payload.get("post_to_department") or payload.get("targetDepartment")
    status_val = payload.get("status") or ("posted" if target_dept else "pending_price_edit")
    
    result = save_price_edit(
        db=db,
        document_name=doc["name"],
        items=items,
        status=status_val,
        user=user,
        target_department=target_dept
    )
    if result["success"]:
        details = f"Document: {doc['name']}"
        if target_dept:
            details += f" posted to department: {target_dept}"
        log_from_request(db, request, "save_price_edit", details, user=user)
    return result

# ==========================================
# Approvals & Purchase Orders
# ==========================================

@router.get("/approvals")
@router.get("/approvals/list")
async def get_approvals_list(
    user: User = Depends(require_department_admin_or_admin),
    db: Session = Depends(get_db)
):
    """List posted documents for department admin approval."""
    docs = list_documents_for_approval(db, user)
    return {"success": True, "documents": docs}

@router.post("/approvals/approve")
async def approve_document_endpoint(
    request: Request,
    payload: DocumentApproveRequest,
    user: User = Depends(require_department_admin_or_admin),
    db: Session = Depends(get_db)
):
    """Approve a posted document."""
    result = approve_document(db, payload.documentName, user)
    if result["success"]:
        log_from_request(db, request, "approve", f"Approved document: {payload.documentName}", user=user)
    return result

@router.post("/{doc_id_or_name}/approve")
async def approve_document_by_path(
    doc_id_or_name: str,
    request: Request,
    user: User = Depends(require_department_admin_or_admin),
    db: Session = Depends(get_db)
):
    """Approve document by ID or name in path."""
    doc = get_document(db, doc_id_or_name)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    result = approve_document(db, doc["name"], user)
    if result["success"]:
        log_from_request(db, request, "approve", f"Approved document: {doc['name']}", user=user)
    return result

@router.get("/approved")
@router.get("/approved/list")
@router.get("/approved-for-po")
async def get_approved_list(
    user: User = Depends(require_purchasing_or_admin),
    db: Session = Depends(get_db)
):
    """List approved documents for Purchasing Purchase Order page."""
    docs = list_approved_documents(db)
    return {"success": True, "documents": docs}

# ==========================================
# Sync & Deletion
# ==========================================

@router.get("/sync/all")
@router.post("/sync/all")
async def sync_all_documents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Organize user's documents into status buckets for localStorage sync."""
    docs = list_documents_for_user(db, user)
    organized = {
        "saved": {},
        "posted": {},
        "pending_price_edit": {},
        "unposted": {}
    }
    for d in docs:
        st = d.get("status", "saved")
        if st in organized:
            organized[st][d["name"]] = {
                "type": d["type"],
                ("bomItems" if d["type"] == "bom" else "boqItems"): d.get("items", [])
            }
    return {"success": True, "documents": organized}

@router.post("/delete")
async def delete_doc_post(
    request: Request,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete document by name in body."""
    doc_name = payload.get("documentName")
    if not doc_name:
        raise HTTPException(status_code=400, detail="Document name required")

    success = delete_document(db, doc_name, user)
    if success:
        log_from_request(db, request, "delete", f"Document: {doc_name}", user=user)
        return {"success": True, "message": "Document deleted successfully"}
    return {"success": False, "message": "Failed to delete document or access denied"}

@router.delete("/{document_name}")
async def delete_doc_delete(
    document_name: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete document by path parameter."""
    success = delete_document(db, document_name, user)
    if success:
        log_from_request(db, request, "delete", f"Document: {document_name}", user=user)
        return {"success": True, "message": "Document deleted successfully"}
    return {"success": False, "message": "Failed to delete document or access denied"}

# ==========================================
# Single Document Retrieval (Wildcard placed last)
# ==========================================

@router.get("/{name_or_id}")
async def get_doc_by_param(
    name_or_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get single document by ID or name."""
    doc = get_document(db, name_or_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "document": doc}
