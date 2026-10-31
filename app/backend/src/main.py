from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles          # MỚI
from routers import kiosk, employees, ws, analytics  # MỚI: thêm analytics
from services.face_service import face_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    face_service.startup()
    yield

app = FastAPI(title="HRM Payroll API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])   # cho Tâm gọi từ frontend

app.include_router(kiosk.router, prefix="/api/kiosk", tags=["kiosk"])
app.include_router(employees.router, prefix="/api/employees", tags=["employees"])
app.include_router(ws.router)
app.include_router(analytics.router)                  # MỚI

@app.get("/api/health")
def health():
    return {"status": "ok"}

# MỚI: phục vụ giao diện web. PHẢI nằm cuối file, sau tất cả router
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
