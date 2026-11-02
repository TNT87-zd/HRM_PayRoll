"""A capture group produces at most one durable attendance event."""
import csv
from datetime import datetime, timezone
from pathlib import Path
import time
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from config import PROJECT_ROOT
from database import get_db
from models import AttendanceRecord
from routers.auth import same_origin
from routers.ws import manager
from schemas import RecognizeResponse

router = APIRouter()

LIVE_LOG = PROJECT_ROOT / "data" / "live" / "scan_log.csv"
LIVE_LOG_HEADER = [
    "employee_id",
    "ts",
    "device_id",
    "scan_type",
    "similarity",
    "distance_m",
    "status_msg",
]


def evaluate_shift_status(scan_type: str, now: datetime) -> str:
    """
    Xác định ca làm việc và trạng thái đi trễ / về sớm chuẩn xác cho cả IN và OUT.
    Các ca chuẩn:
    - CA_SANG: 06:30 - 14:30
    - CA_CHIEU: 14:30 - 22:30
    """
    time_min = now.hour * 60 + now.minute

    start_sang = 6 * 60 + 30       # 06:30
    end_sang = 14 * 60 + 30        # 14:30

    start_chieu = 14 * 60 + 30      # 14:30
    end_chieu = 22 * 60 + 30       # 22:30

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
    else:
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


def recognize_group(face, images, device_id="", lat=None, lon=None):
    results = [face.recognize(image, device_id, lat, lon) for image in images]
    failed = next((result for result in results if not result["matched"]), None)
    if failed:
        return failed
    if len({result["employee_id"] for result in results}) != 1:
        return {**results[-1], "matched": False, "employee_id": None, "full_name": None, "reason": "unstable_identity"}
    return {**results[-1], "similarity": min(result["similarity"] for result in results)}


def record_attendance(db, face, result, device_id, scan_type):
    if not result["matched"]:
        return result
    with face.lock:
        now = time.time()
        last = db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == result["employee_id"],
                AttendanceRecord.scan_type == scan_type,
                AttendanceRecord.timestamp > now - 60,
            ).limit(1)
        )
        if last:
            return {**result, "reason": "duplicate", "recorded": False}

        now_dt = datetime.now()
        status_msg = evaluate_shift_status(scan_type, now_dt)
        db.add(
            AttendanceRecord(
                employee_id=result["employee_id"],
                device_id=device_id,
                scan_type=scan_type,
                timestamp=now,
                similarity=result["similarity"],
            )
        )
        db.commit()

        append_scan_log([
            result["employee_id"],
            now_dt.isoformat(timespec="seconds"),
            device_id,
            scan_type,
            f"{result['similarity']:.4f}",
            result.get("distance_m"),
            status_msg,
        ])

        return {
            **result,
            "recorded": True,
            "reason": "accepted",
            "status_msg": status_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(
    request: Request,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
    device_id: str = Form(..., min_length=1, max_length=80),
    scan_type: str = Form(...),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db=Depends(get_db),
):
    from routers.employees import receive_recognition_images

    same_origin(request)
    scan_type = scan_type.strip().upper()
    if scan_type not in {"IN", "OUT"}:
        raise HTTPException(422, "scan_type phải là IN hoặc OUT")
    if (lat is None) != (lon is None) or (lat is not None and (not -90 <= lat <= 90 or not -180 <= lon <= 180)):
        raise HTTPException(422, "Tọa độ không hợp lệ")

    upload_list = files or ([file] if file is not None else [])
    if not upload_list:
        raise HTTPException(422, "Chưa gửi ảnh nhận diện")

    face = request.app.state.face
    face.load_gallery(db)
    images = await receive_recognition_images(upload_list, request.app.state.settings)
    result = await run_in_threadpool(recognize_group, face, images, device_id, lat, lon)
    result = await run_in_threadpool(record_attendance, db, face, result, device_id, scan_type)
    if result.get("recorded"):
        await manager.broadcast({
            "event": "attendance",
            "employee_id": result["employee_id"],
            "full_name": result["full_name"],
            "scan_type": scan_type,
            "status_msg": result.get("status_msg"),
            "timestamp": result["timestamp"],
        })
    return result
