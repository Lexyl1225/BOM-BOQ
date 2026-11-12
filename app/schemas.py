from datetime import datetime
from typing import Optional, List, Any, Dict, Union
from pydantic import BaseModel, Field

# Generic Response
class ApiResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None

# Auth & User Schemas
class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    new_username: str
    new_password: str
    confirm_password: Optional[str] = None
    role: str = "guest"  # admin, department_admin, user, guest
    department: Optional[str] = ""
    admin_auth_username: Optional[str] = None
    admin_auth_password: Optional[str] = None

class UserUpdate(BaseModel):
    role: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    department: Optional[str] = ""
    email: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None

# Document Schemas
class DocumentSaveRequest(BaseModel):
    action: Optional[str] = "save"
    documentName: str
    documentType: str = "bom"  # 'bom' or 'boq'
    items: Union[List[Dict[str, Any]], Dict[str, Any], Any] = []
    status: Optional[str] = "saved"
    targetDepartment: Optional[str] = None

class DocumentStatusUpdateRequest(BaseModel):
    action: Optional[str] = "update_status"
    documentName: str
    status: str

class DocumentPriceEditRequest(BaseModel):
    action: Optional[str] = "save_price_edit"
    documentName: str
    items: Union[List[Dict[str, Any]], Dict[str, Any], Any] = []
    status: Optional[str] = "pending_price_edit"
    targetDepartment: Optional[str] = None
    documentType: Optional[str] = "bom"

class DocumentApproveRequest(BaseModel):
    action: Optional[str] = "approve"
    documentName: str

class DocumentAttachmentResponse(BaseModel):
    id: int
    document_id: int
    file_name: str
    original_name: str
    file_type: str
    file_size: int
    file_path: str
    uploaded_by: int
    uploaded_by_username: Optional[str] = None
    uploaded_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: int
    name: str
    ref_no: str
    type: str
    status: str
    department: Optional[str] = None
    project_name: Optional[str] = None
    location: Optional[str] = None
    date_value: Optional[str] = None
    html_content: Optional[str] = None
    items: Optional[Any] = None
    created_by: int
    created_by_username: Optional[str] = None
    username: Optional[str] = None
    creator_department: Optional[str] = None
    approved_by: Optional[int] = None
    approved_by_username: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    posted_date: Optional[datetime] = None
    unposted_date: Optional[datetime] = None
    attachments: Optional[List[DocumentAttachmentResponse]] = []

    class Config:
        from_attributes = True

# Cost Estimate Schemas
class EstimateCreate(BaseModel):
    action: Optional[str] = "save"
    estimateName: str
    department: Optional[str] = None
    materialsTotal: float = 0.0
    laborTotal: float = 0.0
    mealAllowance: float = 0.0
    transportationAllowance: float = 0.0
    mobilizationDemobilization: float = 0.0
    customItems: Optional[Any] = []
    sourceDocuments: Optional[Any] = []
    grandTotal: float = 0.0

class EstimateUpdate(BaseModel):
    action: Optional[str] = "update"
    id: int
    estimateName: str
    department: Optional[str] = None
    materialsTotal: float = 0.0
    laborTotal: float = 0.0
    mealAllowance: float = 0.0
    transportationAllowance: float = 0.0
    mobilizationDemobilization: float = 0.0
    customItems: Optional[Any] = []
    sourceDocuments: Optional[Any] = []
    grandTotal: float = 0.0

class EstimateResponse(BaseModel):
    id: int
    estimate_name: str
    department: Optional[str] = None
    materials_total: float
    labor_total: float
    meal_allowance: float
    transportation_allowance: float
    mobilization_demobilization: float
    custom_items: Optional[Any] = []
    source_documents: Optional[Any] = []
    grand_total: float
    created_by: int
    created_by_username: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Activity Log Schemas
class ActivityLogCreate(BaseModel):
    action: str
    details: Optional[str] = ""
    page: Optional[str] = ""

class ActivityLogResponse(BaseModel):
    id: int
    log_id: str
    timestamp: datetime
    username: str
    user_id: Optional[int] = None
    role: Optional[str] = None
    department: Optional[str] = None
    action: str
    details: Optional[str] = None
    page: Optional[str] = None
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True
