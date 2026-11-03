"""FastAPI entry point. Save as app/backend/src/main.py."""
from contextlib import asynccontextmanager
from pathlib import Path
import logging
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hrm import store
from hrm.auth import hr, router as auth_router
from hrm.api import router as hrm_router
from routers import kiosk, employees, ws, analytics
from services.face_service import face_service

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tao cac bang neu chua co; KHONG xoa tai khoan hay du lieu hien tai.
    # Loi CSDL phai duoc xu ly truoc khi cho phep server hoat dong.
    store.init()

    # HRM van hoat dong khi model khuon mat chua san sang.
    if os.environ.get("HRM_DISABLE_FACE") != "1":
        try:
            face_service.startup(db=None)
        except Exception:
            logger.exception("Chua the khoi tao face_service")
    yield


app = FastAPI(title="HRM Payroll API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dang ky API TRUOC khi mount StaticFiles tai '/'.
# auth_router da co prefix /api/hrm/auth; hrm_router da co /api/hrm.
app.include_router(auth_router)
app.include_router(hrm_router)

app.include_router(kiosk.router, prefix="/api/kiosk", tags=["kiosk"])
app.include_router(
    employees.router,
    prefix="/api/employees",
    tags=["employees"],
    dependencies=[Depends(hr)],
)
app.include_router(analytics.router, dependencies=[Depends(hr)])
app.include_router(ws.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


# app/backend/src/main.py -> app/frontend
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parents[1] / "frontend"

# Luon de mount '/' o cuoi, sau tat ca cac API routes.
if FRONTEND_DIR.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
else:
    logger.warning("Khong tim thay thu muc frontend tai: %s", FRONTEND_DIR)
