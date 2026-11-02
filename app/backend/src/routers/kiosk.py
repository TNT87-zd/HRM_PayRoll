"""A capture group produces at most one durable attendance event."""
from datetime import datetime, timezone
import time
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from database import get_db
from models import AttendanceRecord
from routers.auth import same_origin
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


def record_attendance(db, face, result, device_id, scan_type):
    if not result["matched"]:
        return result
    with face.lock:
        now = time.time()
        last = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == result["employee_id"],
            AttendanceRecord.scan_type == scan_type, AttendanceRecord.timestamp > now - 60).limit(1))
        if last:
            return {**result, "reason": "duplicate", "recorded": False}
        db.add(AttendanceRecord(employee_id=result["employee_id"], device_id=device_id,
                               scan_type=scan_type, timestamp=now, similarity=result["similarity"]))
        db.commit()
        return {**result, "recorded": True, "reason": "accepted", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(request: Request, files: list[UploadFile] = File(...),
                    device_id: str = Form(..., min_length=1, max_length=80),
                    scan_type: str = Form(...), lat: float | None = Form(None), lon: float | None = Form(None),
                    db=Depends(get_db)):
    from routers.employees import receive_recognition_images
    same_origin(request)
    if scan_type not in {"IN", "OUT"}:
        raise HTTPException(422, "scan_type phải là IN hoặc OUT")
    if (lat is None) != (lon is None) or (lat is not None and (not -90 <= lat <= 90 or not -180 <= lon <= 180)):
        raise HTTPException(422, "Tọa độ không hợp lệ")
    face = request.app.state.face
    face.load_gallery(db)
    images = await receive_recognition_images(files, request.app.state.settings)
    result = await run_in_threadpool(recognize_group, face, images, device_id, lat, lon)
    result = await run_in_threadpool(record_attendance, db, face, result, device_id, scan_type)
    if result.get("recorded"):
        await manager.broadcast({"event": "attendance", "employee_id": result["employee_id"],
            "full_name": result["full_name"], "scan_type": scan_type, "timestamp": result["timestamp"]})
    return result
