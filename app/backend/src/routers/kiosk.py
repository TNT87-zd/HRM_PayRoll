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
from routers.auth import same_origin, require_operator
from routers.ws import manager
from schemas import RecognizeResponse

router = APIRouter()

def recognize_group(face, images, device_id="", lat=None, lon=None):
    results = [face.recognize(image, device_id, lat, lon) for image in images]
    failed = next((result for result in results if not result["matched"]), None)
    if failed:
        return failed
    if len({result["employee_id"] for result in results}) != 1:
        return {**results[-1], "matched": False, "employee_id": None, "full_name": None, "reason": "unstable_identity"}
    return {**results[-1], "similarity": min(result["similarity"] for result in results)}


def record_attendance(db, face, result, device_id, scan_type, actor="kiosk"):
    """Serialize duplicate checks and persist one canonical attendance record + assignment."""
    if not result["matched"]:
        return result
    from sqlalchemy import text
    from hrm.api import record_event
    from hrm.core import VN
    from hrm.store import get
    from models import AttendanceAssignment
    # Recognition only read the gallery; end that transaction before acquiring the write lock.
    db.rollback()
    with face.lock:
        db.execute(text("BEGIN IMMEDIATE"))
        try:
            now_dt = datetime.now(VN)
            # Detect duplicates across all scheduled events, not just this request.
            previous = db.scalar(select(AttendanceRecord).where(
                AttendanceRecord.employee_id==result['employee_id'],
                AttendanceRecord.scan_type==scan_type,
                AttendanceRecord.timestamp > now_dt.timestamp()-60).order_by(AttendanceRecord.id.desc()))
            if previous:
                db.rollback()
                return {**result,"reason":"duplicate","recorded":False}
            event=record_event(db,result['employee_id'],scan_type,now_dt.isoformat(),actor,'FACE',
                               device_id=device_id,similarity=result['similarity'])
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {**result,"recorded":True,"reason":"accepted",
            "status_msg":f"Đã ghi {scan_type} · ca {event['shift_id']}","timestamp":event['ts']}


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
    account=Depends(require_operator),
):
    from routers.employees import receive_recognition_images

    same_origin(request)
    scan_type = scan_type.strip().upper()
    if scan_type not in {"IN", "OUT"}:
        raise HTTPException(422, "scan_type phải là IN hoặc OUT")
    if (lat is None) != (lon is None) or (lat is not None and (not -90 <= lat <= 90 or not -180 <= lon <= 180)):
        raise HTTPException(422, "Tọa độ không hợp lệ")

    # Use the configured dataset; never infer a registered device from its name.
    import math
    from repository import read_csv
    from services.geofence import haversine_m, GEOFENCE_RADIUS_M
    if lat is None or lon is None or not math.isfinite(lat) or not math.isfinite(lon):
        raise HTTPException(422,"Cần tọa độ GPS hợp lệ; cho phép trình duyệt truy cập vị trí")
    settings=request.app.state.settings
    device=next((d for d in read_csv(settings.data_dir/'clean/devices.csv') if d['device_id']==device_id),None)
    branch=next((b for b in read_csv(settings.data_dir/'clean/branches.csv') if device and b['branch_id']==device['branch_id']),None)
    if not branch:
        raise HTTPException(422,"Thiết bị hoặc chi nhánh chưa được đăng ký")
    try:
        distance=haversine_m(lat,lon,float(branch['lat']),float(branch['lon']))
    except (KeyError,ValueError):
        raise HTTPException(422,"Chi nhánh chưa có tọa độ hợp lệ")
    if not math.isfinite(distance) or distance>GEOFENCE_RADIUS_M:
        raise HTTPException(403,"Ngoài vùng chấm công của chi nhánh")

    upload_list = files or ([file] if file is not None else [])
    if not upload_list:
        raise HTTPException(422, "Chưa gửi ảnh nhận diện")

    face = request.app.state.face
    face.load_gallery(db)
    if face.engine is None:
        raise HTTPException(503,"Model nhận diện chưa sẵn sàng; kiểm tra /api/health")
    images = await receive_recognition_images(upload_list, request.app.state.settings)
    result = await run_in_threadpool(recognize_group, face, images, device_id, lat, lon)
    result = await run_in_threadpool(record_attendance, db, face, result, device_id, scan_type, account.username)
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
