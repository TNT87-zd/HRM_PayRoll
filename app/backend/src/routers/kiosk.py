from datetime import datetime
import math
import numpy as np
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from schemas import RecognizeResponse
from services.face_service import face_service
from services.geofence import distance_to_branch, GEOFENCE_RADIUS_M
from routers.ws import manager
from hrm.auth import operator
from hrm.store import db
from hrm.api import record_event
from hrm.core import VN

router=APIRouter()

@router.post('/recognize',response_model=RecognizeResponse)
async def recognize(file: UploadFile,device_id: str=Form(...),scan_type: str=Form('IN'),
                    lat: float|None=Form(None),lon: float|None=Form(None),u=Depends(operator)):
    scan_type=scan_type.upper().strip()
    if scan_type not in ('IN','OUT'):
        raise HTTPException(422,'scan_type phải là IN hoặc OUT')
    if lat is None or lon is None or not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
        raise HTTPException(422,'Cần tọa độ GPS hợp lệ')
    distance=distance_to_branch(device_id,lat,lon)
    if distance is None or distance>GEOFENCE_RADIUS_M:
        raise HTTPException(403,'Thiết bị chưa đăng ký hoặc ở ngoài vùng chấm công')
    if face_service.engine is None:
        raise HTTPException(503,'Model khuôn mặt chưa sẵn sàng; xem hướng dẫn cài CV')
    import cv2
    data=await file.read(5*1024*1024+1)
    if len(data)>5*1024*1024:
        raise HTTPException(413,'Ảnh tối đa 5 MB')
    image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(422,'Ảnh không hợp lệ')
    result=await run_in_threadpool(face_service.recognize,image,device_id=device_id,lat=lat,lon=lon,scan_type=scan_type)
    now=datetime.now(VN)
    if result.get('reason')=='accepted' and result.get('employee_id'):
        try:
            with db(True) as con:
                e=record_event(con,result['employee_id'],scan_type,now.isoformat(),u['username'],'FACE',device_id=device_id)
        except HTTPException:
            face_service._last_seen.pop((result['employee_id'],scan_type),None)
            raise
        result['status_msg']=f"Đã ghi {scan_type} · ca {e['shift_id']} · chưa kiểm tra liveness"
        result['timestamp']=now.isoformat(timespec='seconds')
        await manager.broadcast(dict(event='attendance',employee_id=result['employee_id'],
                                     full_name=result.get('full_name'),scan_type=scan_type,
                                     status_msg=result['status_msg'],timestamp=result['timestamp']))
    return RecognizeResponse(**result)
