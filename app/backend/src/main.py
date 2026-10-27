from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import kiosk, employees, ws

@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: với SessionLocal() as db: face_service.startup(db)
    yield

app = FastAPI(title="HRM Payroll API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])   # cho Tâm gọi từ frontend

app.include_router(kiosk.router, prefix="/api/kiosk", tags=["kiosk"])
app.include_router(employees.router, prefix="/api/employees", tags=["employees"])
app.include_router(ws.router)

@app.get("/api/health")
def health():
    return {"status": "ok"}