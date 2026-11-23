"""
API key enforcement for every /api endpoint.

A request to /api/* is rejected with HTTP 401 unless it carries a valid, active
department API key in the ``X-API-Key`` header. When the request is also made by a
signed-in user, the key must belong to that user's department (otherwise HTTP 403).

Exempt endpoints (they cannot work with a department key, by design):
* /api/health                 — container / uptime probes
* /api/auth/login, /register  — the user's department is not known before sign-in
* /api/auth/logout            — clearing a session must always succeed
* /api/admin/api-keys/*       — Administrator-only key management. Exempt so an
                                Administrator can always recover after revoking or
                                deactivating a key (including their own department's).
"""

from typing import Optional

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import database
from app.auth import decode_access_token, extract_token_from_request
from app.models import User
from app.services.api_key_service import API_KEY_HEADER, validate_request_key

EXEMPT_EXACT = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/logout",
}
EXEMPT_PREFIXES = ("/api/admin/api-keys",)

def is_exempt(path: str) -> bool:
    path = path.rstrip("/") or "/"
    return path in EXEMPT_EXACT or any(path.startswith(p) for p in EXEMPT_PREFIXES)

def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None

def _check(request: Request, raw_key: Optional[str]):
    with database.SessionLocal() as db:
        user = None
        token = extract_token_from_request(request)
        payload = decode_access_token(token) if token else None
        if payload and "sub" in payload:
            user = db.query(User).filter(User.username == payload["sub"], User.is_active == True).first()
        return validate_request_key(db, raw_key, user, _client_ip(request))

class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/") or is_exempt(path):
            return await call_next(request)

        raw_key = request.headers.get(API_KEY_HEADER)
        result = await run_in_threadpool(_check, request, raw_key)
        if not result.ok:
            headers = {"WWW-Authenticate": "ApiKey"} if result.status_code == 401 else None
            return JSONResponse(
                status_code=result.status_code,
                content={
                    "success": False,
                    "error": result.code,
                    "message": result.message,
                    "detail": result.message,
                },
                headers=headers,
            )
        return await call_next(request)
