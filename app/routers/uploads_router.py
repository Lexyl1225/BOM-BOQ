import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import (
    APIRouter, Depends, HTTPException, status, Request,
    UploadFile, File, Form
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.config import settings, BASE_DIR
from app.database import get_db
from app.models import User, Document, DocumentAttachment
from app.auth import get_current_user, require_purchasing_or_admin
from app.services.activity_service import log_from_request

router = APIRouter(prefix="/api/uploads", tags=["Uploads & Attachments"])

MAGIC_SIGNATURES = {
    "pdf": b"%PDF",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n"
}

MIME_MAP = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png"
}

@router.post("/")
async def upload_attachment(
    request: Request,
    document_id: int = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_purchasing_or_admin),
    db: Session = Depends(get_db)
):
    """Upload PO attachment (PDF, JPG, PNG up to 10MB). Purchasing & Admin only."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    filename = file.filename or "attachment"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF, JPG, and PNG files are allowed."
        )

    # Read first chunk to verify magic bytes
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds maximum allowed size (10 MB)")

    # Validate header signature
    sig = MAGIC_SIGNATURES.get(ext)
    if sig and not content.startswith(sig):
        raise HTTPException(status_code=400, detail="File content does not match its extension.")

    # Unique filename
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    short_hash = uuid.uuid4().hex[:8]
    clean_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    stored_name = f"{ts}_{short_hash}_{clean_name}"
    
    file_path = settings.UPLOAD_DIR / stored_name
    with open(file_path, "wb") as f:
        f.write(content)

    rel_path = f"uploads/{stored_name}"
    mime = MIME_MAP.get(ext, file.content_type or "application/octet-stream")

    attachment = DocumentAttachment(
        document_id=doc.id,
        file_name=stored_name,
        original_name=filename,
        file_type=mime,
        file_size=len(content),
        file_path=rel_path,
        uploaded_by=user.id,
        uploaded_at=datetime.utcnow()
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    log_from_request(
        db, request, "upload_file",
        f"Uploaded {filename} for document: {doc.name}",
        user=user
    )

    return {
        "success": True,
        "message": "File uploaded successfully",
        "attachment": {
            "id": attachment.id,
            "document_id": attachment.document_id,
            "file_name": attachment.file_name,
            "original_name": attachment.original_name,
            "file_type": attachment.file_type,
            "file_size": attachment.file_size,
            "file_path": attachment.file_path,
            "uploaded_by_username": user.username,
            "uploaded_at": attachment.uploaded_at.isoformat()
        }
    }

@router.get("/{document_id}")
async def list_attachments(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all attachments for a document."""
    atts = db.query(DocumentAttachment).filter(DocumentAttachment.document_id == document_id).all()
    results = []
    for a in atts:
        results.append({
            "id": a.id,
            "document_id": a.document_id,
            "file_name": a.file_name,
            "original_name": a.original_name,
            "file_type": a.file_type,
            "file_size": a.file_size,
            "file_path": a.file_path,
            "uploaded_by": a.uploaded_by,
            "uploaded_by_username": a.uploader.username if a.uploader else None,
            "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None
        })
    return {"success": True, "attachments": results}

@router.get("/file/{identifier}")
async def serve_file(
    identifier: str,
    db: Session = Depends(get_db)
):
    """Serve attachment file for viewing or downloading in browser."""
    # Identifier can be attachment ID or filename
    att = None
    if identifier.isdigit():
        att = db.query(DocumentAttachment).filter(DocumentAttachment.id == int(identifier)).first()
    if not att:
        att = db.query(DocumentAttachment).filter(DocumentAttachment.file_name == identifier).first()

    if att:
        path = BASE_DIR / att.file_path
        if path.exists():
            return FileResponse(
                path=str(path),
                media_type=att.file_type,
                filename=att.original_name
            )

    # Fallback to direct path in uploads/
    direct_path = settings.UPLOAD_DIR / identifier
    if direct_path.exists():
        ext = identifier.rsplit(".", 1)[-1].lower() if "." in identifier else ""
        mime = MIME_MAP.get(ext, "application/octet-stream")
        return FileResponse(path=str(direct_path), media_type=mime)

    raise HTTPException(status_code=404, detail="File not found")

@router.delete("/{attachment_id}")
async def delete_attachment_endpoint(
    attachment_id: int,
    request: Request,
    user: User = Depends(require_purchasing_or_admin),
    db: Session = Depends(get_db)
):
    """Delete an attachment file and DB record."""
    att = db.query(DocumentAttachment).filter(DocumentAttachment.id == attachment_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    full_path = BASE_DIR / att.file_path
    if full_path.exists():
        try:
            os.remove(full_path)
        except Exception:
            pass

    orig = att.original_name
    db.delete(att)
    db.commit()

    log_from_request(db, request, "delete_attachment", f"Deleted file: {orig}", user=user)
    return {"success": True, "message": "Attachment deleted successfully"}
