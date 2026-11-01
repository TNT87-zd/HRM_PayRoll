import csv
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from database import get_db
from schemas import RecognizeResponse
from services.face_service import face_service
from routers.ws import manager

router = APIRouter()

# Log lượt quét trực tiếp từ Kiosk. KHÔNG ghi vào data/clean/attendance_events.csv
# (file đó là dữ liệu gốc, khác schema). Pipeline chấm công sẽ gộp file này sau.
# kiosk.py nằm ở app/backend/src/routers/ -> parents[4] = thư mục gốc dự án
LIVE_LOG = Path(__file__).resolve().parents[4] / "data" / "live" / "scan_log.csv"
LIVE_LOG_HEADER = ["employee_id", "ts", "device_id", "scan_type",
                   "similarity", "distance_m", "status_msg"]


def evaluate_shift_status(scan_type: str, now: datetime) -> str:
    """
    Hàm xác định ca làm việc và trạng thái đi trễ / về sớm chuẩn xác cho cả IN và OUT.
    Các ca chuẩn:
    - CA_SANG: 06:30 - 14:30
    - CA_CHIEU: 14:30 - 22:30
    - HANH_CHINH: 07:30 - 16:30
    - PT_SANG: 06:30 - 10:30
    - PT_CHIEU: 14:30 - 18:30
    """
    time_min = now.hour * 60 + now.minute

    # Mốc giờ chuẩn (tính bằng phút từ 00:00)
    start_sang = 6 * 60 + 30      # 06:30 (390 min)
    end_sang = 14 * 60 + 30        # 14:30 (870 min)

    start_chieu = 14 * 60 + 30     # 14:30 (870 min)
    end_chieu = 22 * 60 + 30       # 22:30 (1350 min)

    if scan_type == "IN":
        if time_min < 11 * 60:
            shift_name = "CA_SANG (06:30 - 14:30)"
            target_start = start_sang
        else:
            shift_name = "CA_CHIEU (14:30 - 22:30)"
            target_start = start_chieu

        late_minutes = max(0, time_min - target_start)
        if late_minutes > 0:
            return f"VÀO {shift_name} - Đi trễ {late_minutes} phút"
        return f"VÀO {shift_name} - Đúng giờ"

    else:  # scan_type == "OUT"
        if time_min < 14 * 60 + 30:
            shift_name = "CA_SANG (06:30 - 14:30)"
            target_end = end_sang
        else:
            shift_name = "CA_CHIEU (14:30 - 22:30)"
            target_end = end_chieu

        early_minutes = max(0, target_end - time_min)
        if early_minutes > 0:
            return f"RA {shift_name} - Về sớm {early_minutes} phút"
        return f"RA {shift_name} - Đúng giờ"


def append_scan_log(row: list) -> None:
    """Ghi 1 dòng vào scan_log.csv, tự tạo thư mục và header lần đầu."""
    LIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LIVE_LOG.exists()
    with open(LIVE_LOG, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(LIVE_LOG_HEADER)
        writer.writerow(row)


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(
    file: UploadFile,
    device_id: str = Form(...),
    scan_type: str = Form("IN"),  # IN hoặc OUT, do Kiosk gửi lên
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    scan_type = scan_type.strip().upper()
    if scan_type not in ("IN", "OUT"):
        raise HTTPException(status_code=400, detail="scan_type phải là IN hoặc OUT")

    data = await file.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Ảnh không hợp lệ")

    # 1. Nhận diện khuôn mặt. Chạy trong threadpool để không chặn event loop
    result = await run_in_threadpool(
        face_service.recognize, img, device_id=device_id, lat=lat, lon=lon
    )
    now = datetime.now()

    # 2. Ghi nhận log khi hợp lệ
    if result.get("reason") == "accepted" and result.get("employee_id"):
        emp_id = result["employee_id"]
        sim = result.get("similarity", 0.0)

        status_msg = evaluate_shift_status(scan_type, now)
        result["status_msg"] = status_msg
        result["timestamp"] = now.isoformat(timespec="seconds")

        append_scan_log([
            emp_id,
            now.isoformat(timespec="seconds"),
            device_id,
            scan_type,
            f"{sim:.4f}",
            result.get("distance_m"),
            status_msg,
        ])

        # 3. Đẩy realtime tới trang Admin
        await manager.broadcast({
            "event": "attendance",
            "employee_id": emp_id,
            "full_name": result.get("full_name") or emp_id,
            "scan_type": scan_type,
            "status_msg": status_msg,
            "timestamp": now.isoformat(timespec="seconds"),
        })

    return RecognizeResponse(**result)