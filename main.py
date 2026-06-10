"""
Market Research Platform - entry point.
Run:  python main.py
      uvicorn main:app --reload

Note: python-multipart is required for form parsing (included in requirements.txt).
"""
import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.routes import router
from app.routes_auth import router as auth_router
from app.routes_dashboard import router as dashboard_router
from app.deps import templates
from app.config import IS_PRODUCTION

# ── Disable interactive API docs in production ────────────────────────────────
app = FastAPI(
    title="Market Research Platform",
    version="3.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Security headers middleware ───────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        h.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: blob: https:; "
            "font-src 'self' https:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none';",
        )
        # HSTS only over HTTPS — never set in development
        if IS_PRODUCTION:
            h.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request, "404.html", {}, status_code=404
        )
    return HTMLResponse(
        content=f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>",
        status_code=exc.status_code,
    )


@app.head("/")
async def health_head():
    return
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
