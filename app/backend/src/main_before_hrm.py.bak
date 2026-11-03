from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Nạp các routers (đã bao gồm router analytics mới)
from routers import kiosk, employees, ws, analytics
from services.face_service import face_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo mô hình AI / Gallery khi ứng dụng bắt đầu chạy
    try:
        face_service.startup(db=None)  # Tạm thời truyền None trong lúc chờ DB của Quốc
    except Exception as e:
        print(f"[WARNING] Chưa thể khởi tạo face_service: {e}")
    yield

app = FastAPI(title="HRM Payroll API", lifespan=lifespan)

# Cấu hình CORS cho phép Frontend truy cập tự do
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Nạp các API Routers
app.include_router(kiosk.router, prefix="/api/kiosk", tags=["kiosk"])
app.include_router(employees.router, prefix="/api/employees", tags=["employees"])
app.include_router(analytics.router)
app.include_router(ws.router)

@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}

# Phục vụ giao diện web (Static Files)
# Đường dẫn chuẩn trỏ từ src/main.py lên thư mục frontend gốc: app/backend/src -> app/frontend
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parents[1] / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    print(f"[WARNING] Không tìm thấy thư mục frontend tại: {FRONTEND_DIR}")