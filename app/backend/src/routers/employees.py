from pathlib import Path
from typing import List, Optional
import pandas as pd
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas import EnrollResponse, EmployeeItem
from services.face_service import face_service, EMPLOYEES_CSV

router = APIRouter()

ROLE_VN = {
    "quan_ly": "Quản lý",
    "pha_che": "Pha chế",
    "thu_ngan": "Thu ngân",
    "phuc_vu": "Phục vụ",
    "bao_ve": "Bảo vệ",
    "tap_vu": "Tạp vụ",
}


@router.get("", response_model=List[EmployeeItem])
def list_employees():
    """Lấy danh sách tất cả nhân viên kèm trạng thái FaceID."""
    if not EMPLOYEES_CSV.is_file():
        return []

    try:
        df = pd.read_csv(EMPLOYEES_CSV)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không đọc được danh sách nhân viên: {exc}")

    result = []
    for _, row in df.iterrows():
        emp_id = str(row.get("employee_id", "")).strip().upper()
        if not emp_id:
            continue

        st = face_service.get_employee_face_status(emp_id)
        role = str(row.get("role", ""))
        full_name = str(row.get("full_name", "")) if "full_name" in row and pd.notna(row["full_name"]) else emp_id
        is_real = bool(row.get("is_real_face", False))

        result.append(
            EmployeeItem(
                employee_id=emp_id,
                full_name=full_name,
                branch_id=str(row.get("branch_id", "")),
                role=role,
                role_vn=ROLE_VN.get(role, role.replace("_", " ").title()),
                has_face=st["has_gallery"] or st["photo_count"] >= 3,
                photo_count=st["photo_count"],
                is_real_face=is_real,
            )
        )
    return result


@router.get("/{emp_id}", response_model=EmployeeItem)
def get_employee(emp_id: str):
    """Lấy thông tin một nhân viên cụ thể kèm trạng thái FaceID."""
    emp_id = emp_id.strip().upper()
    st = face_service.get_employee_face_status(emp_id)

    full_name = emp_id
    role = ""
    branch_id = ""
    is_real = False

    if EMPLOYEES_CSV.is_file():
        try:
            df = pd.read_csv(EMPLOYEES_CSV)
            row = df[df["employee_id"].astype(str).str.upper() == emp_id]
            if not row.empty:
                r = row.iloc[0]
                full_name = str(r.get("full_name", emp_id))
                role = str(r.get("role", ""))
                branch_id = str(r.get("branch_id", ""))
                is_real = bool(r.get("is_real_face", False))
        except Exception:
            pass

    return EmployeeItem(
        employee_id=emp_id,
        full_name=full_name,
        branch_id=branch_id,
        role=role,
        role_vn=ROLE_VN.get(role, role.replace("_", " ").title()),
        has_face=st["has_gallery"] or st["photo_count"] >= 3,
        photo_count=st["photo_count"],
        is_real_face=is_real,
    )


@router.post("/{emp_id}/face/enroll", response_model=EnrollResponse)
async def enroll(
    emp_id: str,
    files: List[UploadFile],
    full_name: Optional[str] = Form(None),
    consent: bool = Form(True),
    db: Session = Depends(get_db),
):
    """
    Đăng ký FaceID cho nhân viên:
    - Nhận 5 ảnh góc mặt (front, left, right, up, under).
    - Lưu file vào data/face/raw/<emp_id>/.
    - Trích xuất vector đặc trưng 512-d bằng ArcFace.
    - Nạp vector vào bộ nhớ FaceService Gallery để Kiosk nhận diện ngay lập tức.
    """
    emp_id = emp_id.strip().upper()
    if not emp_id:
        raise HTTPException(status_code=400, detail="Mã nhân viên không được để trống")

    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="Chưa có ảnh nào được gửi lên")

    if not consent:
        raise HTTPException(status_code=400, detail="Cần xác nhận đồng ý thu thập dữ liệu sinh trắc học theo quy định")

    # Đọc dữ liệu ảnh từ request
    files_data = []
    for f in files:
        content = await f.read()
        filename = f.filename or "photo.jpg"
        files_data.append((filename, content))

    res = face_service.enroll(emp_id, files_data, full_name=full_name, db=db)
    return EnrollResponse(**res)
