"""
OpenAPI / Swagger UI (/docs) customisation.

Documents how the API is secured so "Try it out" works from /docs:
* ``ApiKeyHeader`` (X-API-Key) — required on every /api endpoint except the exempt ones
  listed in app/api_key_middleware.py.
* ``BearerAuth``  — the JWT returned by POST /api/auth/login. In a browser that is already
  signed in, the session cookie is sent automatically, so the Bearer token is optional there.
"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api_key_middleware import is_exempt

API_DESCRIPTION = """
Enterprise Bill of Materials & Quantities Management System.

## Authentication

Most endpoints need **two** credentials:

| Credential | How to send it | Where to get it |
|---|---|---|
| **Department API key** | `X-API-Key` header | Administration → **API Keys** (`/api_keys`), or `python api-key-gen.py --department "<name>"` |
| **User session** | `Authorization: Bearer <token>`, or the session cookie | `POST /api/auth/login` |

The API key must belong to the **same department** as the signed-in user.

| Problem | Status | `error` |
|---|---|---|
| Missing key | 401 | `api_key_missing` |
| Unknown key | 401 | `api_key_invalid` |
| Deactivated key | 401 | `api_key_inactive` |
| Key from another department | 403 | `api_key_department_mismatch` |

### Passwords
Users (except Administrators) must choose their own password at first sign-in, and after an Administrator
resets it. Until they do, every API call except `GET /api/auth/me`, `POST /api/auth/logout` and
`POST /api/auth/change-password` returns **403** with `error: password_change_required`.
Changing a password signs out the account's other sessions (older tokens return 401).

**Endpoints that don't need a key:** `GET /api/health`, `POST /api/auth/login`, `POST /api/auth/register`, `POST /api/auth/logout`,
and the Administrator-only `/api/admin/api-keys/*` endpoints (so an Administrator can always restore access).

### Trying it out here
1. Call **POST /api/auth/login**. If you're already signed in to the app in this browser, skip this step: your session cookie is sent automatically.
2. Click **Authorize**, paste your department's key into **ApiKeyHeader**, and (optionally) the login `token` into **BearerAuth**.
"""

TAGS_METADATA = [
    {"name": "Authentication", "description": "Sign in, register, sign out, change your own password and current-user info. Login, register and logout don't need an API key."},
    {"name": "Documents", "description": "BOM / BOQ documents: save, load, price edit, approvals and Purchase Order lists."},
    {"name": "Cost Estimates", "description": "Project cost estimates."},
    {"name": "Uploads & Attachments", "description": "Purchase Order attachments (PDF, JPG, PNG up to 10 MB)."},
    {"name": "Activity Logs", "description": "Audit trail (reading is Administrator-only)."},
    {"name": "Users Management", "description": "User accounts, including password reset / change for other users (Administrator-only)."},
    {"name": "API Key Management", "description": "Department API keys (Administrator-only). Exempt from the API key requirement."},
    {"name": "Legacy Compatibility", "description": "Endpoints kept for the original PHP front end (`*.php`)."},
    {"name": "System", "description": "Health checks."},
]

KEY_ERRORS = {
    "401": {"description": "Not authenticated, or missing / invalid / deactivated API key"},
    "403": {"description": "Not permitted, or the API key belongs to another department"},
}

def install_openapi(app: FastAPI) -> None:
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=API_DESCRIPTION,
            routes=app.routes,
            tags=TAGS_METADATA,
        )
        components = schema.setdefault("components", {})
        components["securitySchemes"] = {
            "ApiKeyHeader": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Your department's API key (Administration → API Keys).",
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "The `token` returned by POST /api/auth/login. Optional if your browser already has a session cookie.",
            },
        }

        for path, operations in schema.get("paths", {}).items():
            if not path.startswith("/api/"):
                continue
            for operation in operations.values():
                if not isinstance(operation, dict):
                    continue
                if path.startswith("/api/admin/api-keys"):
                    # Exempt from API keys, but Administrator session required
                    operation["security"] = [{"BearerAuth": []}, {}]
                elif is_exempt(path):
                    operation["security"] = []
                else:
                    # Key + Bearer token, or key + session cookie (cookie isn't modelled)
                    operation["security"] = [{"ApiKeyHeader": [], "BearerAuth": []}, {"ApiKeyHeader": []}]
                    responses = operation.setdefault("responses", {})
                    for code, body in KEY_ERRORS.items():
                        responses.setdefault(code, body)

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
