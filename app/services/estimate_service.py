import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models import CostEstimate, User

def _format_estimate(est: CostEstimate) -> Dict[str, Any]:
    custom_items = []
    if est.custom_items:
        try:
            custom_items = json.loads(est.custom_items)
        except Exception:
            custom_items = []

    source_docs = []
    if est.source_documents:
        try:
            source_docs = json.loads(est.source_documents)
        except Exception:
            source_docs = []

    return {
        "id": est.id,
        "estimate_name": est.estimate_name,
        "department": est.department,
        "materials_total": est.materials_total,
        "labor_total": est.labor_total,
        "meal_allowance": est.meal_allowance,
        "transportation_allowance": est.transportation_allowance,
        "mobilization_demobilization": est.mobilization_demobilization,
        "custom_items": custom_items,
        "source_documents": source_docs,
        "grand_total": est.grand_total,
        "created_by": est.created_by,
        "created_by_username": est.creator.username if est.creator else None,
        "created_at": est.created_at.isoformat() if est.created_at else None
    }

def save_estimate(db: Session, data: Dict[str, Any], user: User) -> Dict[str, Any]:
    name = data.get("estimateName", "").strip()
    if not name:
        return {"success": False, "message": "Estimate name is required"}

    custom_items = data.get("customItems", [])
    source_docs = data.get("sourceDocuments", [])

    est = CostEstimate(
        estimate_name=name,
        department=data.get("department") or user.department or None,
        materials_total=float(data.get("materialsTotal", 0.0)),
        labor_total=float(data.get("laborTotal", 0.0)),
        meal_allowance=float(data.get("mealAllowance", 0.0)),
        transportation_allowance=float(data.get("transportationAllowance", 0.0)),
        mobilization_demobilization=float(data.get("mobilizationDemobilization", 0.0)),
        custom_items=json.dumps(custom_items),
        source_documents=json.dumps(source_docs),
        grand_total=float(data.get("grandTotal", 0.0)),
        created_by=user.id,
        created_at=datetime.utcnow()
    )
    db.add(est)
    db.commit()
    db.refresh(est)
    formatted = _format_estimate(est)
    return {"success": True, "message": "Estimate saved successfully", "id": est.id, "data": formatted, "estimate": formatted}

def list_estimates(db: Session, user: User) -> List[Dict[str, Any]]:
    is_admin = user.role == "admin"
    dept = (user.department or "").strip()

    query = db.query(CostEstimate)
    if is_admin:
        pass
    elif dept:
        # User in dept sees estimates for that department or created by self
        query = query.filter(
            (CostEstimate.department == dept) | (CostEstimate.created_by == user.id)
        )
    else:
        query = query.filter(CostEstimate.created_by == user.id)

    estimates = query.order_by(desc(CostEstimate.created_at)).all()
    return [_format_estimate(e) for e in estimates]

def get_estimate_by_id(db: Session, estimate_id: int) -> Optional[Dict[str, Any]]:
    est = db.query(CostEstimate).filter(CostEstimate.id == estimate_id).first()
    if not est:
        return None
    return _format_estimate(est)

def update_estimate(db: Session, estimate_id: int, data: Dict[str, Any], user: User) -> Dict[str, Any]:
    est = db.query(CostEstimate).filter(CostEstimate.id == estimate_id).first()
    if not est:
        return {"success": False, "message": "Estimate not found"}

    is_admin = user.role == "admin"
    is_owner = est.created_by == user.id
    same_dept = bool(user.department and est.department == user.department)

    if not (is_admin or is_owner or same_dept):
        return {"success": False, "message": "Access denied: cannot edit this estimate"}

    if "estimateName" in data and data["estimateName"]:
        est.estimate_name = data["estimateName"].strip()
    if "department" in data:
        est.department = data["department"]
    if "materialsTotal" in data:
        est.materials_total = float(data["materialsTotal"])
    if "laborTotal" in data:
        est.labor_total = float(data["laborTotal"])
    if "mealAllowance" in data:
        est.meal_allowance = float(data["mealAllowance"])
    if "transportationAllowance" in data:
        est.transportation_allowance = float(data["transportationAllowance"])
    if "mobilizationDemobilization" in data:
        est.mobilization_demobilization = float(data["mobilizationDemobilization"])
    if "customItems" in data:
        est.custom_items = json.dumps(data["customItems"])
    if "sourceDocuments" in data:
        est.source_documents = json.dumps(data["sourceDocuments"])
    if "grandTotal" in data:
        est.grand_total = float(data["grandTotal"])

    db.commit()
    return {"success": True, "message": "Estimate updated successfully"}

def delete_estimate(db: Session, estimate_id: int, user: User) -> Dict[str, Any]:
    est = db.query(CostEstimate).filter(CostEstimate.id == estimate_id).first()
    if not est:
        return {"success": False, "message": "Estimate not found"}

    is_admin = user.role == "admin"
    is_owner = est.created_by == user.id
    same_dept = bool(user.department and est.department == user.department)

    if not (is_admin or is_owner or same_dept):
        return {"success": False, "message": "Access denied: cannot delete this estimate"}

    db.delete(est)
    db.commit()
    return {"success": True, "message": "Estimate deleted successfully"}
