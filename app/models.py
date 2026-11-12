from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="guest")  # admin, department_admin, user, guest
    department = Column(String(100), nullable=True, default="")
    email = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_username", "username"),
        Index("idx_role", "role"),
    )

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    ref_no = Column(String(100), nullable=False, index=True)
    type = Column(String(10), nullable=False, index=True)  # 'bom' or 'boq'
    status = Column(String(30), default="pending", index=True)  # pending, saved, pending_price_edit, posted, approved, completed, unposted
    department = Column(String(100), nullable=True)
    project_name = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    date_value = Column(String(30), nullable=True)
    html_content = Column(Text, nullable=True)
    items = Column(Text, nullable=True)  # JSON text
    original_type = Column(String(10), nullable=True)
    original_index = Column(Integer, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    posted_date = Column(DateTime, nullable=True)
    completed_date = Column(DateTime, nullable=True)
    unposted_date = Column(DateTime, nullable=True)
    last_edited = Column(DateTime, nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], backref="created_documents")
    approver = relationship("User", foreign_keys=[approved_by], backref="approved_documents")
    attachments = relationship("DocumentAttachment", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_doc_name_creator", "name", "created_by"),
        Index("idx_doc_status_dept", "status", "department"),
    )

class DocumentAttachment(Base):
    __tablename__ = "document_attachments"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="attachments")
    uploader = relationship("User", foreign_keys=[uploaded_by])

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    log_id = Column(String(50), unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    username = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    role = Column(String(20), nullable=True)
    department = Column(String(100), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    details = Column(Text, nullable=True)
    page = Column(String(100), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

class CostEstimate(Base):
    __tablename__ = "cost_estimates"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    estimate_name = Column(String(255), nullable=False)
    department = Column(String(100), nullable=True)
    materials_total = Column(Float, default=0.0, nullable=False)
    labor_total = Column(Float, default=0.0, nullable=False)
    meal_allowance = Column(Float, default=0.0, nullable=False)
    transportation_allowance = Column(Float, default=0.0, nullable=False)
    mobilization_demobilization = Column(Float, default=0.0, nullable=False)
    custom_items = Column(Text, nullable=True)  # JSON text
    source_documents = Column(Text, nullable=True)  # JSON text
    grand_total = Column(Float, default=0.0, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    creator = relationship("User", foreign_keys=[created_by], backref="created_estimates")
