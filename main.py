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

from app.routes import router
from app.routes_auth import router as auth_router
from app.routes_dashboard import router as dashboard_router
from app.deps import templates

app = FastAPI(title="Market Research Platform", version="3.0")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request, "404.html", {}, status_code=404
        )
    # Default handling for other HTTP errors
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
