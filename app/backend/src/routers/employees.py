import os
import shutil
import tempfile
from pathlib import Path
import numpy as np
from fastapi import APIRouter, UploadFile, HTTPException
from schemas import EnrollResponse
from services.face_service import face_service, FACE_RAW_DIR
from hrm.store import db
from hrm.api import employee_exists

router=APIRouter()

@router.post('/{emp_id}/face/enroll',response_model=EnrollResponse)
def enroll(emp_id: str,files: list[UploadFile]):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',emp_id):
        raise HTTPException(422,'Mã nhân viên không hợp lệ')
    with db() as con:
        employee_exists(con,emp_id)
    if face_service.engine is None:
        raise HTTPException(503,'Model khuôn mặt chưa sẵn sàng')
    angles={'front','left','right','under','up'}
    names=[Path(f.filename or '').stem.lower() for f in files]
    if len(files)!=5 or set(names)!=angles:
        raise HTTPException(422,'Cần đúng 5 ảnh front, left, right, under, up')
    import cv2
    with tempfile.TemporaryDirectory() as tmp:
        for i,file in enumerate(files):
            data=file.file.read(5*1024*1024+1)
            if len(data)>5*1024*1024:
                raise HTTPException(413,'Mỗi ảnh tối đa 5 MB')
            image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
            if image is None:
                raise HTTPException(422,'Ảnh không hợp lệ')
            cv2.imwrite(str(Path(tmp)/f'{names[i]}.jpg'),image)
        r=face_service.engine.enroll_from_images(Path(tmp),employee_id=emp_id,min_valid_images=5)
        if not r.success or len(r.embeddings)!=5:
            raise HTTPException(422,r.message)
        target=FACE_RAW_DIR/emp_id
        target.mkdir(parents=True,exist_ok=True)
        backup=FACE_RAW_DIR.parent/'backups'/emp_id/str(__import__('time').time_ns())
        if any(target.iterdir()):
            shutil.copytree(target,backup)
        for p in target.iterdir():
            if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.bmp','.webp'}:
                p.unlink()
        for p in Path(tmp).glob('*.jpg'):
            shutil.copy2(p,target/p.name)
        face_service.gallery[emp_id]=np.vstack([r.centroid_embedding]+r.embeddings).astype(np.float32)
    return EnrollResponse(ok=True,employee_id=emp_id,num_valid=len(r.embeddings),
                          mean_intra_similarity=float(r.mean_intra_similarity),message='Đã đăng ký khuôn mặt thật')
