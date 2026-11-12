"""
End-to-End Test Suite for BOM / BOQ Studio Pro FastAPI Application
Tests all endpoints, security layers, document lifecycles, and legacy compatibility.
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, SessionLocal
from app.models import User, Document, DocumentAttachment, CostEstimate, ActivityLog

def run_tests():
    print("==================================================")
    print("🧪 Running Comprehensive FastAPI Test Suite")
    print("==================================================")

    # 1. Initialize DB and Seed
    print("\n[Step 1] Initializing Database & Seed Data...")
    init_db()
    with SessionLocal() as db:
        user_count = db.query(User).count()
        doc_count = db.query(Document).count()
        attach_count = db.query(DocumentAttachment).count()
        log_count = db.query(ActivityLog).count()
        est_count = db.query(CostEstimate).count()
        print(f" -> DB Stats: {user_count} Users | {doc_count} Documents | {attach_count} Attachments | {log_count} Logs | {est_count} Estimates")
        assert user_count >= 30, f"Expected at least 30 users, got {user_count}"
        assert doc_count >= 10, f"Expected at least 10 documents, got {doc_count}"

    client = TestClient(app, follow_redirects=False)

    # 2. Test Public and Unauthenticated Routes
    print("\n[Step 2] Testing Route Protection & Redirects...")
    # Unauthenticated / should redirect to /login
    r = client.get("/")
    assert r.status_code == 303, f"Expected 303 for unauthenticated /, got {r.status_code}"
    assert r.headers["location"] == "/login"
    print("  ✓ GET / redirects to /login for unauthenticated users")

    # GET /login returns 200
    r = client.get("/login")
    assert r.status_code == 200, f"Expected 200 for /login, got {r.status_code}"
    assert "Sign In" in r.text
    print("  ✓ GET /login serves login HTML")

    # GET /login.php also returns 200
    r = client.get("/login.php")
    assert r.status_code == 200
    print("  ✓ GET /login.php works seamlessly")

    # Static assets
    r = client.get("/static/css/main.css")
    assert r.status_code == 200
    print("  ✓ GET /static/css/main.css loaded")

    r = client.get("/static/js/app.js")
    assert r.status_code == 200
    print("  ✓ GET /static/js/app.js loaded")

    # 3. Test Authentication
    print("\n[Step 3] Testing Authentication Flow...")
    # Bad credentials
    r = client.post("/api/auth/login", json={"username": "Admin", "password": "WrongPassword!"})
    assert r.status_code == 401
    assert "detail" in r.json()
    print("  ✓ Reject invalid password")

    # Admin Login
    r = client.post("/api/auth/login", json={"username": "Admin", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    admin_token = data["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_cookies = {"bom_session_token": admin_token}
    print("  ✓ Admin login successful (JWT token generated)")

    # Current user info
    r = client.get("/api/auth/me", headers=admin_headers)
    assert r.status_code == 200
    me = r.json()
    assert me["username"] == "Admin"
    assert me["role"] == "admin"
    print(f"  ✓ /api/auth/me verified: {me['username']} ({me['role']})")

    # Login as Engineering User
    r = client.post("/api/auth/login", json={"username": "Engr. Alex", "password": "123456"})
    assert r.status_code == 200
    engr_token = r.json()["token"]
    engr_cookies = {"bom_session_token": engr_token}
    engr_headers = {"Authorization": f"Bearer {engr_token}"}
    print("  ✓ Engineering user login successful")

    # Login as Purchasing User
    r = client.post("/api/auth/login", json={"username": "Mark", "password": "123456"})
    assert r.status_code == 200
    purch_token = r.json()["token"]
    purch_cookies = {"bom_session_token": purch_token}
    print("  ✓ Purchasing user login successful")

    # 4. Test Authenticated HTML Pages
    print("\n[Step 4] Testing Authenticated HTML Pages...")
    # Admin dashboard
    r = client.get("/", cookies=admin_cookies)
    assert r.status_code == 200
    assert "Welcome back, Admin" in r.text
    print("  ✓ GET / with admin session renders Dashboard")

    # Page routes
    pages_to_test = [
        ("/bom", "Create BOM"),
        ("/boq", "Create BOQ"),
        ("/save_bomboq", "Saved Documents"),
        ("/estimate", "Cost Estimates"),
        ("/user_logs", "Activity Logs"),
        ("/price_edit_bomboq", "MCE Pricing"),
        ("/approver", "Department Approvals"),
        ("/approved_for_po", "Approved for PO"),
        ("/users_admin", "User Management"),
    ]
    for url, title_snip in pages_to_test:
        r = client.get(url, cookies=admin_cookies)
        assert r.status_code == 200, f"Page {url} failed with {r.status_code}"
        print(f"  ✓ GET {url} -> 200 OK")

    # Role protection: Engineering user trying to access /users_admin -> redirected to /
    r = client.get("/users_admin", cookies=engr_cookies)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    print("  ✓ Role protection: Non-admin redirected away from /users_admin")

    # 5. Test Document REST APIs
    print("\n[Step 5] Testing Document REST APIs...")
    # List documents
    r = client.get("/api/documents/", headers=engr_headers)
    assert r.status_code == 200
    docs = r.json()
    assert docs["success"] is True
    print(f"  ✓ GET /api/documents/ returned {docs['count']} documents")

    # Create new BOM document
    new_doc_payload = {
        "documentName": "FastAPI_Automated_Test_BOM",
        "documentType": "bom",
        "items": [
            {
                "itemNo": "1",
                "description": "High Voltage Transformer 50kVA",
                "brand": "ABB",
                "qty": 2,
                "unit": "sets",
                "unitPrice": 125000,
                "amount": 250000,
                "category": "Equipment"
            },
            {
                "itemNo": "2",
                "description": "Copper Cable 50mm2",
                "brand": "Phelps Dodge",
                "qty": 100,
                "unit": "meters",
                "unitPrice": 450,
                "amount": 45000,
                "category": "Electrical"
            }
        ],
        "status": "pending_price_edit",
        "department": "Engineering"
    }
    r = client.post("/api/documents/", json=new_doc_payload, headers=engr_headers)
    assert r.status_code == 200
    create_res = r.json()
    assert create_res["success"] is True
    created_doc_id = create_res["id"]
    print(f"  ✓ POST /api/documents/ created doc ID {created_doc_id}")

    # Load the created document
    r = client.get(f"/api/documents/{created_doc_id}", headers=engr_headers)
    assert r.status_code == 200
    loaded = r.json()
    assert loaded["success"] is True
    assert loaded["document"]["document_name"] == "FastAPI_Automated_Test_BOM"
    assert len(loaded["document"]["items"]) == 2
    print(f"  ✓ GET /api/documents/{created_doc_id} retrieved correctly")

    # 6. Test Workflow: Price Edit & Department Approval
    print("\n[Step 6] Testing Workflow: MCE Price Edit & Approval...")
    # Purchasing edits prices
    edit_payload = {
        "items": [
            {
                "itemNo": "1",
                "description": "High Voltage Transformer 50kVA",
                "brand": "ABB",
                "qty": 2,
                "unit": "sets",
                "unitPrice": 120000,  # Adjusted unit price
                "amount": 240000,
                "category": "Equipment"
            }
        ],
        "post_to_department": "Engineering"
    }
    r = client.post(f"/api/documents/{created_doc_id}/price-edit", json=edit_payload, headers={"Authorization": f"Bearer {purch_token}"})
    assert r.status_code == 200
    assert r.json()["success"] is True
    print("  ✓ Purchasing MCE price edit and posting to Engineering successful")

    # Department Admin approves document
    # Admin approves
    r = client.post(f"/api/documents/{created_doc_id}/approve", json={"notes": "Approved for purchase"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
    print("  ✓ Document approved by Department Admin")

    # Verify document now in approved list for PO
    r = client.get("/api/documents/approved-for-po", headers={"Authorization": f"Bearer {purch_token}"})
    assert r.status_code == 200
    po_list = r.json()
    assert po_list["success"] is True
    matching = [d for d in po_list["documents"] if d["id"] == created_doc_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "approved"
    print(f"  ✓ Verified document ID {created_doc_id} appears in Approved for PO list")

    # 7. Test Cost Estimates API
    print("\n[Step 7] Testing Cost Estimates API...")
    est_payload = {
        "estimateName": "BOM Automation Substation Project",
        "department": "Engineering",
        "materialsTotal": 295000,
        "laborTotal": 85000,
        "mealAllowance": 12000,
        "transportationAllowance": 15000,
        "mobilizationDemobilization": 25000,
        "customItems": [
            {"description": "Contingency Fund", "amount": 20000}
        ],
        "sourceDocuments": [created_doc_id]
    }
    r = client.post("/api/estimates/", json=est_payload, headers=engr_headers)
    assert r.status_code == 200
    est_res = r.json()
    assert est_res["success"] is True
    new_est_id = est_res["id"]
    print(f"  ✓ POST /api/estimates/ created estimate ID {new_est_id} with grand total {est_res['data']['grand_total']}")

    # 8. Test Legacy PHP API Backward Compatibility
    print("\n[Step 8] Testing Legacy PHP API Compatibility...")
    # api/document_api.php?action=list
    r = client.get("/api/document_api.php?action=list", cookies=engr_cookies)
    assert r.status_code == 200
    leg_doc = r.json()
    assert leg_doc["success"] is True
    assert "documents" in leg_doc
    print(f"  ✓ GET /api/document_api.php?action=list returned {len(leg_doc['documents'])} documents")

    # api/estimate_api.php?action=list
    r = client.get("/api/estimate_api.php?action=list", cookies=engr_cookies)
    assert r.status_code == 200
    leg_est = r.json()
    assert leg_est["success"] is True
    assert "estimates" in leg_est
    print(f"  ✓ GET /api/estimate_api.php?action=list returned {len(leg_est['estimates'])} estimates")

    # api/user_api.php?action=list (requires admin)
    r = client.post("/api/user_api.php", json={"action": "list"}, cookies=admin_cookies)
    assert r.status_code == 200
    leg_users = r.json()
    assert leg_users["success"] is True
    assert len(leg_users["users"]) >= 30
    print(f"  ✓ POST /api/user_api.php action=list returned {len(leg_users['users'])} users")

    # 9. Test Audit Logs API
    print("\n[Step 9] Testing Audit Logs API...")
    r = client.get("/api/logs/?limit=5", headers=admin_headers)
    assert r.status_code == 200
    logs_res = r.json()
    assert logs_res["success"] is True
    assert len(logs_res["logs"]) == 5
    print(f"  ✓ GET /api/logs/ retrieved recent logs successfully")

    # 10. Test OpenAPI Documentation
    print("\n[Step 10] Testing OpenAPI Specification & Docs...")
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["info"]["title"] == "BOM / BOQ Studio Pro"
    assert "/api/documents/" in spec["paths"]
    assert "/api/auth/login" in spec["paths"]
    print(f"  ✓ OpenAPI spec generated with {len(spec['paths'])} API routes")

    r = client.get("/docs")
    assert r.status_code == 200
    print("  ✓ Swagger UI (/docs) accessible")

    print("\n==================================================")
    print("🎉 ALL TESTS PASSED SUCCESSFULLY! (10/10 Suites)")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
