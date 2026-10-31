import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import RecognizeResponse
from services.face_service import face_service

router = APIRouter()


@router.post("/recognize", response_model=RecognizeResponse)
def recognize(
    file: UploadFile,
    device_id: str = Form(...),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    data = file.file.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Ảnh không hợp lệ")

    result = face_service.recognize(img, device_id=device_id, lat=lat, lon=lon)

    # TODO: khi result["reason"] == "accepted" -> ghi attendance_events + ws broadcast
    return RecognizeResponse(**result)
