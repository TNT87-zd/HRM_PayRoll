import csv
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np

from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import RecognizeResponse
from services.face_service import face_service
from routers.ws import manager
router = APIRouter()

# Xác định đường dẫn file CSV thực tế lưu Data của bạn
CSV_FILE = Path(__file__).resolve().parents[3] / "data" / "clean" / "attendance_events.csv"

def evaluate_shift_status(scan_type: str, now: datetime) -> str:
    """
    Hàm mô phỏng logic chia ca (Ca 1, Ca 2, Ca 3) dựa trên giờ hiện tại.
    """
    hour = now.hour
    minute = now.minute

    if scan_type == "IN":
        # Xác định đang Check-in cho Ca nào
        if 6 <= hour < 12:
            shift_name = "Ca 1 (7h-12h)"
            late_minutes = max(0, (hour - 7) * 60 + minute)
        elif 12 <= hour < 17:
            shift_name = "Ca 2 (12h-18h)"
            late_minutes = max(0, (hour - 12) * 60 + minute)
        else:
            shift_name = "Ca 3 (18h-23h)"
            late_minutes = max(0, (hour - 18) * 60 + minute)

        if late_minutes > 0:
            return f"VÀO {shift_name} - Đi trễ {late_minutes} phút"
        return f"VÀO {shift_name} - Đúng giờ"

    else: # scan_type == "OUT"
        # Xác định đang Check-out cho Ca nào
        if 10 <= hour < 15:
            shift_name = "Ca 1 (7h-12h)"
            early_minutes = max(0, (12 - hour) * 60 - minute)
        elif 15 <= hour < 20:
            shift_name = "Ca 2 (12h-18h)"
            early_minutes = max(0, (18 - hour) * 60 - minute)
        else:
            shift_name = "Ca 3 (18h-23h)"
            early_minutes = max(0, (23 - hour) * 60 - minute)

        if early_minutes > 0:
            return f"RA {shift_name} - Về sớm {early_minutes} phút"
        return f"RA {shift_name} - Hợp lệ"


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(
    file: UploadFile,
    device_id: str = Form(...),
    scan_type: str = Form(...),  # Nhận trạng thái IN/OUT từ giao diện
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    data = file.file.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    
    if img is None:
        raise HTTPException(status_code=400, detail="Ảnh không hợp lệ")

    # 1. Gọi Engine nhận diện khuôn mặt
    result = face_service.recognize(img, device_id=device_id, lat=lat, lon=lon)

    # 2. Xử lý Logic nếu nhận ra khuôn mặt
    if result.get("matched"):
        emp_id = result.get("employee_id")
        sim = result.get("similarity")
        now = datetime.now()

        # Tính toán kết quả đi làm
        status_msg = evaluate_shift_status(scan_type, now)
        
        # Ghi đè vào biến reason để đẩy thẳng câu thông báo này lên màn hình Kiosk
        result["reason"] = status_msg  
        result["timestamp"] = now.isoformat()

        # 3. Mở file CSV và ghi log lại quá trình
        # Tự động tạo thư mục nếu chưa có
        CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_exists = CSV_FILE.exists()

        with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                # Ghi tiêu đề (Header) lần đầu
                writer.writerow(["employee_id", "timestamp", "device_id", "scan_type", "similarity", "status"])
            
            # Ghi dòng dữ liệu mới
            writer.writerow([emp_id, now.isoformat(), device_id, scan_type, f"{sim:.4f}", status_msg])

        # TODO: Phát sự kiện realtime qua WebSocket (ws manager) tới trang Admin ở đây
        # Kiểm tra nếu nhận diện thành công (matched = True)
        if result.get("matched"):
            await manager.broadcast({
            "event": "attendance",
            "employee_id": result.get("employee_id"),
            "full_name": result.get("full_name", "Nhân viên"),
            "scan_type": scan_type,
            "timestamp": now.isoformat()
        })

    return RecognizeResponse(**result)