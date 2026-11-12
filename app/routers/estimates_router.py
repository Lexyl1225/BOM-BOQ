from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import EstimateCreate, EstimateUpdate, EstimateResponse
from app.auth import get_current_user
from app.services.activity_service import log_from_request
from app.services.estimate_service import (
    save_estimate, list_estimates, get_estimate_by_id,
    update_estimate, delete_estimate
)

router = APIRouter(prefix="/api/estimates", tags=["Cost Estimates"])

@router.get("/")
async def get_estimates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List Project Cost Estimates scoped to user/department."""
    estimates = list_estimates(db, user)
    return {"success": True, "estimates": estimates}

@router.post("/")
async def create_estimate(
    request: Request,
    payload: EstimateCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save a new Project Cost Estimate."""
    if user.role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guests are not allowed to save estimates."
        )

    result = save_estimate(db, payload.dict(), user)
    if result["success"]:
        log_from_request(
            db, request, "save_estimate",
            f"Saved cost estimate: {payload.estimateName} (Total: {payload.grandTotal:,.2f})",
            user=user
        )
    return result

@router.get("/{estimate_id}")
async def get_estimate(
    estimate_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve single estimate by ID."""
    est = get_estimate_by_id(db, estimate_id)
    if not est:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return {"success": True, "estimate": est}

@router.put("/{estimate_id}")
async def edit_estimate(
    estimate_id: int,
    request: Request,
    payload: EstimateUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing cost estimate."""
    if user.role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guests are not allowed to edit estimates."
        )

    result = update_estimate(db, estimate_id, payload.dict(), user)
    if result["success"]:
        log_from_request(
            db, request, "update_estimate",
            f"Updated cost estimate: {payload.estimateName} (ID: {estimate_id})",
            user=user
        )
    return result

@router.delete("/{estimate_id}")
async def remove_estimate(
    estimate_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a cost estimate."""
    if user.role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guests are not allowed to delete estimates."
        )

    result = delete_estimate(db, estimate_id, user)
    if result["success"]:
        log_from_request(
            db, request, "delete_estimate",
            f"Deleted cost estimate ID: {estimate_id}",
            user=user
        )
    return result
