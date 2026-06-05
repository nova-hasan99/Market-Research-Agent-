"""
Market Research Platform - entry point.
Run:  python main.py
      uvicorn main:app --reload

Note: python-multipart is required for form parsing (included in requirements.txt).
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import router
from app.routes_auth import router as auth_router
from app.routes_dashboard import router as dashboard_router

app = FastAPI(title="Market Research Platform", version="3.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.head("/")
async def health_head():
    return
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
