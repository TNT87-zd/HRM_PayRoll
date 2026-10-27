from datetime import datetime
from fastapi import APIRouter, UploadFile, Form, Depends
from sqlalchemy.orm import Session
from database import get_db
from schemas import RecognizeResponse

router = APIRouter()

@router.post("/recognize", response_model=RecognizeResponse)
def recognize(
    file: UploadFile,
    device_id: str = Form(...),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    # MOCK: sau này thay bằng imdecode -> face_service.recognize -> ghi attendance_events -> ws broadcast
    return RecognizeResponse(
        matched=True, employee_id="NV0002", full_name="Nhân viên mẫu",
        similarity=0.78, reason="accepted", bbox=[100, 80, 300, 320],
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )