"""
End-to-End Test Suite for BOM / BOQ Studio Pro FastAPI Application
Tests all endpoints, security layers, document lifecycles, and legacy compatibility.
"""

import sys
import os
import uuid
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, SessionLocal
from app.models import User, Document, DocumentAttachment, CostEstimate, ActivityLog
from app.config import settings
from app.auth import decode_access_token
from app.services.api_key_service import key_for_user


class KeyedTestClient(TestClient):
    """TestClient that attaches the department API key (X-API-Key) of whichever user a
    request is authenticated as, just like app.js does in the browser."""

    def request(self, method, url, **kwargs):
        if str(url).startswith("/api/"):
            headers = dict(kwargs.get("headers") or {})
            if "X-API-Key" not in headers:
                token = None
                auth = headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    token = auth[7:]
                elif (kwargs.get("cookies") or {}).get(settings.COOKIE_NAME):
                    token = kwargs["cookies"][settings.COOKIE_NAME]
                else:
                    token = self.cookies.get(settings.COOKIE_NAME)
                payload = decode_access_token(token) if token else None
                if payload and payload.get("sub"):
                    with SessionLocal() as db:
                        user = db.query(User).filter(User.username == payload["sub"]).first()
                        key = key_for_user(db, user)
                    if key:
                        headers["X-API-Key"] = key
                        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)

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

    client = KeyedTestClient(app, follow_redirects=False)

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

    def first_login(username, password, new_password):
        """Sign in a seeded user, completing the first-login password change if required."""
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        if r.status_code == 401:
            # Suite re-run on the same database: the password was already changed
            r = client.post("/api/auth/login", json={"username": username, "password": new_password})
        assert r.status_code == 200, r.text
        body = r.json()
        token = body["token"]
        if not body["must_change_password"]:
            return token
        hdrs = {"Authorization": f"Bearer {token}"}
        # Blocked until the password is changed (pages redirect, API returns 403)
        r = client.get("/", cookies={"bom_session_token": token})
        assert r.status_code == 303 and r.headers["location"] == "/change_password"
        r = client.get("/change_password", cookies={"bom_session_token": token})
        assert r.status_code == 200 and "Set your password" in r.text
        r = client.get("/api/documents/", headers=hdrs)
        assert r.status_code == 403 and r.json()["error"] == "password_change_required", r.text
        assert client.get("/api/auth/me", headers=hdrs).status_code == 200
        r = client.post("/api/auth/change-password", headers=hdrs, json={
            "current_password": password, "new_password": new_password, "confirm_password": new_password})
        assert r.status_code == 200, r.text
        new_token = r.json()["token"]
        # The old token is signed out; the new one works
        assert client.get("/api/auth/me", headers=hdrs).status_code == 401
        assert client.get("/api/documents/", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
        return new_token

    # Login as Engineering User (first sign-in: must choose a password)
    engr_token = first_login("Engr. Alex", "123456", "EngrPass2026")
    engr_cookies = {"bom_session_token": engr_token}
    engr_headers = {"Authorization": f"Bearer {engr_token}"}
    # The shared test password no longer works once a real password is set
    r = client.post("/api/auth/login", json={"username": "Engr. Alex", "password": "123456"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", json={"username": "Engr. Alex", "password": "EngrPass2026"})
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    print("  ✓ Engineering user login successful (first-login password change enforced)")

    # Login as Purchasing User
    purch_token = first_login("Mark", "123456", "MarkPass2026")
    purch_cookies = {"bom_session_token": purch_token}
    print("  ✓ Purchasing user login successful")

    # Password management (Admin reset / change, self-service change)
    print("\n[Step 3b] Testing Password Management...")
    temp_name = f"pwtest_{uuid.uuid4().hex[:6]}"
    r = client.post("/api/users/", headers=admin_headers, json={"username": temp_name, "password": "short", "role": "user", "department": "Design and Construction"})
    assert r.status_code == 400, "weak password must be rejected"
    r = client.post("/api/users/", headers=admin_headers, json={"username": temp_name, "password": "Initial123", "role": "user", "department": "Design and Construction"})
    assert r.status_code == 200, r.text
    temp_id = r.json()["user"]["id"]
    assert r.json()["user"]["password_change_required"] is True
    print("  ✓ Admin-created users must change their password at first sign-in")

    # Non-admins can't use the admin password endpoints
    r = client.post(f"/api/users/{temp_id}/reset-password", headers=engr_headers)
    assert r.status_code == 403
    # Admin can't reset their own password from the admin endpoints
    admin_id = me["id"]
    r = client.post(f"/api/users/{admin_id}/reset-password", headers=admin_headers)
    assert r.status_code == 400

    temp_token = first_login(temp_name, "Initial123", "Chosen456")
    r = client.post(f"/api/users/{temp_id}/reset-password", headers=admin_headers)
    assert r.status_code == 200, r.text
    temporary = r.json()["temporary_password"]
    assert len(temporary) >= 8 and r.json()["user"]["password_change_required"] is True
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {temp_token}"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": temp_name, "password": "Chosen456"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": temp_name, "password": temporary})
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    print("  ✓ Admin reset issues a one-time temporary password and signs the user out")

    r = client.post(f"/api/users/{temp_id}/password", headers=admin_headers, json={"new_password": "AdminSet789", "confirm_password": "AdminSet789", "require_change": False})
    assert r.status_code == 200 and r.json()["user"]["password_change_required"] is False
    r = client.post("/api/auth/login", json={"username": temp_name, "password": "AdminSet789"})
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    temp_headers = {"Authorization": f"Bearer {r.json()['token']}"}
    r = client.post(f"/api/users/{temp_id}/password", headers=admin_headers, json={"new_password": "AdminSet789", "confirm_password": "Mismatch789"})
    assert r.status_code == 400
    print("  ✓ Admin can set a specific password (with or without forcing a change)")

    # Self-service change at any time
    r = client.post("/api/auth/change-password", headers=temp_headers, json={"current_password": "wrong", "new_password": "Another321", "confirm_password": "Another321"})
    assert r.status_code == 400
    r = client.post("/api/auth/change-password", headers=temp_headers, json={"current_password": "AdminSet789", "new_password": "Another321", "confirm_password": "Another321"})
    assert r.status_code == 200
    r = client.get("/change_password", cookies={"bom_session_token": r.json()["token"]})
    assert r.status_code == 200 and "Change Password" in r.text
    assert client.post("/api/auth/change-password", headers=admin_headers, json={"current_password": "x", "new_password": "y", "confirm_password": "y"}).status_code == 400
    client.delete(f"/api/users/{temp_id}", headers=admin_headers)
    print("  ✓ Any signed-in user can change their own password")

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
        ("/user_logs", "Audit Logs"),
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

    # Role protection: Audit Logs page is admin-only (direct URL and legacy .php alias)
    for url in ("/user_logs", "/user_logs.php"):
        r = client.get(url, cookies=engr_cookies)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        r = client.get(url, cookies=purch_cookies)
        assert r.status_code == 303
    print("  ✓ Role protection: Non-admins redirected away from /user_logs")

    # Non-admin dashboard/pages must not expose Audit Logs links or the activity feed
    for url in ("/", "/bom", "/estimate"):
        r = client.get(url, cookies=engr_cookies)
        assert r.status_code == 200
        assert 'href="/user_logs"' not in r.text, f"Audit Logs link leaked on {url}"
    assert "Recent System Activity" not in client.get("/", cookies=engr_cookies).text
    r = client.get("/", cookies=admin_cookies)
    assert 'href="/user_logs"' in r.text and "Recent System Activity" in r.text
    print("  ✓ Audit Logs navigation hidden for non-admins, visible for admins")

    # 5. Test Document REST APIs
    print("\n[Step 5] Testing Document REST APIs...")
    # List documents
    r = client.get("/api/documents/", headers=engr_headers)
    assert r.status_code == 200
    docs = r.json()
    assert docs["success"] is True
    print(f"  ✓ GET /api/documents/ returned {docs['count']} documents")

    # Create new BOM document
    test_doc_name = f"FastAPI_Automated_Test_BOM_{uuid.uuid4().hex[:8]}"  # unique per run (approved docs are locked)
    new_doc_payload = {
        "documentName": test_doc_name,
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
    assert loaded["document"]["document_name"] == test_doc_name
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

    # Approved documents are locked for non-admins (REST + legacy APIs)
    purch_headers = {"Authorization": f"Bearer {purch_token}"}
    r = client.post("/api/documents/update_status", json={"documentName": test_doc_name, "status": "pending_price_edit"}, headers=engr_headers)
    assert r.status_code == 403 and r.json().get("locked") is True
    r = client.post("/api/documents/", json={**new_doc_payload, "status": "saved"}, headers=engr_headers)
    assert r.status_code == 403
    r = client.post(f"/api/documents/{created_doc_id}/price-edit", json=edit_payload, headers=purch_headers)
    assert r.status_code == 403
    r = client.post("/api/document_api.php", json={"action": "save", "documentName": test_doc_name, "documentType": "bom", "items": [], "status": "saved"}, headers=engr_headers)
    assert r.status_code == 403 and r.json()["success"] is False
    r = client.post("/api/document_api.php", json={"action": "update_status", "documentName": test_doc_name, "status": "pending_price_edit"}, headers=purch_headers)
    assert r.status_code == 403
    r = client.get(f"/api/documents/{created_doc_id}", headers=engr_headers)
    assert r.json()["document"]["status"] == "approved"
    print("  ✓ Approved document locked: non-admin edit / MCE send / price edit rejected (403)")

    # Only Administrators may delete approved documents (owner, department and Purchasing are blocked)
    r = client.post("/api/documents/delete", json={"documentName": test_doc_name}, headers=engr_headers)
    assert r.status_code == 403 and r.json().get("locked") is True
    r = client.delete(f"/api/documents/{test_doc_name}", headers=purch_headers)
    assert r.status_code == 403
    r = client.post("/api/document_api.php", json={"action": "delete", "documentName": test_doc_name}, headers=purch_headers)
    assert r.status_code == 403
    assert client.get(f"/api/documents/{created_doc_id}", headers=engr_headers).status_code == 200
    print("  ✓ Approved document delete rejected for owner and Purchasing (403)")

    # Administrator may still send an approved document back to MCE price edit
    r = client.post("/api/documents/update_status", json={"documentName": test_doc_name, "status": "pending_price_edit"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["success"] is True
    print("  ✓ Admin can send an approved document back to MCE Price Edit")

    # Re-approve, then confirm an Administrator can delete an approved document
    client.post("/api/documents/update_status", json={"documentName": test_doc_name, "status": "approved"}, headers=admin_headers)
    r = client.post("/api/documents/delete", json={"documentName": test_doc_name}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["success"] is True
    assert client.get(f"/api/documents/{created_doc_id}", headers=admin_headers).status_code == 404
    print("  ✓ Admin can delete an approved document")

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

    guest_client = KeyedTestClient(app, follow_redirects=False)  # no cookies carried over from earlier logins
    for path in ("/api/logs/?limit=5", "/api/logs/stats"):
        r = guest_client.get(path, headers=engr_headers)
        assert r.status_code == 403, f"{path} should be admin-only, got {r.status_code}"
        r = guest_client.get(path)
        assert r.status_code == 401, f"{path} should require auth, got {r.status_code}"
    r = client.get("/api/logs/stats", headers=admin_headers)
    assert r.status_code == 200 and r.json()["success"] is True
    print("  ✓ Audit Logs API restricted to admins (403 for users, 401 for guests)")

    # Department API key enforcement
    bare = TestClient(app, follow_redirects=False)
    r = bare.get("/api/documents/", headers=engr_headers)
    assert r.status_code == 401 and r.json()["error"] == "api_key_missing", r.text
    r = bare.get("/api/documents/", headers={**engr_headers, "X-API-Key": "not-a-real-key"})
    assert r.status_code == 401, r.text
    with SessionLocal() as db:
        purch_key = key_for_user(db, db.query(User).filter(User.username == "Mark").first())
    r = bare.get("/api/documents/", headers={**engr_headers, "X-API-Key": purch_key})
    assert r.status_code == 403 and r.json()["error"] == "api_key_department_mismatch", r.text
    print("  ✓ API rejects missing/invalid keys (401) and other departments' keys (403)")

    # Client-side activity logging remains available to all sessions (write-only)
    r = client.post("/api/logs/", json={"action": "page_view", "details": "test", "page": "/bom"}, headers=engr_headers)
    assert r.status_code == 200
    print("  ✓ POST /api/logs/ client logging still accepted for non-admins")

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
