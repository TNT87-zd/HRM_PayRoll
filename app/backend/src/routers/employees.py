import json
import time
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from starlette.concurrency import run_in_threadpool
from config import CONSENT_VERSION, POSES
from database import get_db
from models import Employee, FaceSample
from repository import create_employee, employee_item, employee_or_404, reference_data, validate_reference
from routers.auth import require_hr
from schemas import EmployeeCreate, EmployeePatch, SessionCreate

router = APIRouter()


@router.get("/options")
def options(request: Request, user=Depends(require_hr)):
    return {**reference_data(request.app.state.settings), "poses": list(POSES), "samples_per_pose": 2,
            "consent_version": CONSENT_VERSION,
            "consent_text": "Tôi đồng ý thu nhận và lưu ảnh, vector khuôn mặt để đăng ký nhận diện và chấm công tại đơn vị. Tôi đã được thông báo về mục đích sử dụng và có thể liên hệ HR để yêu cầu xử lý dữ liệu của mình.",
            "preprocessing_policy": "baseline", "model_version": request.app.state.settings.model_version,
            "session_ttl": request.app.state.settings.session_ttl}


@router.post("", status_code=201)
def create(payload: EmployeeCreate, request: Request,
           idempotency_key: str = Header(min_length=8, max_length=80),
           user=Depends(require_hr), db=Depends(get_db)):
    employee = create_employee(db, payload, request.app.state.settings, user.id, idempotency_key)
    request.app.state.face.load_gallery(db)
    return employee_item(db, employee, request.app.state.face)


@router.get("")
def list_employees(request: Request, q: str = Query("", max_length=120), branch_id: str | None = None,
                   face_status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                   user=Depends(require_hr), db=Depends(get_db)):
    query = select(Employee)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(or_(Employee.full_name.ilike(f"%{escaped}%", escape="\\"), Employee.employee_id.ilike(f"%{escaped}%", escape="\\")))
    if branch_id:
        query = query.where(Employee.branch_id == branch_id)
    if face_status == "missing":
        query = query.where(Employee.active_template_id.is_(None))
    elif face_status == "registered":
        query = query.where(Employee.active_template_id.is_not(None))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    employees = db.scalars(query.order_by(Employee.employee_id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [employee_item(db, employee, request.app.state.face, include_pay=False) for employee in employees],
            "total": total, "page": page, "page_size": page_size}


@router.get("/{emp_id}")
def detail(emp_id: str, request: Request, user=Depends(require_hr), db=Depends(get_db)):
    return employee_item(db, employee_or_404(db, emp_id), request.app.state.face)


@router.patch("/{emp_id}")
def patch(emp_id: str, payload: EmployeePatch, request: Request, user=Depends(require_hr), db=Depends(get_db)):
    employee = employee_or_404(db, emp_id)
    keys = EmployeeCreate.model_fields
    merged = {key: getattr(employee, key) for key in keys}
    changes = payload.model_dump(mode="json", exclude_unset=True)
    merged.update({key: value for key, value in changes.items() if key in keys})
    try:
        valid = EmployeeCreate.model_validate(merged)
    except ValidationError:
        raise HTTPException(422, "Thông tin hồ sơ hoặc loại lương không hợp lệ")
    validate_reference(valid, request.app.state.settings)
    for key, value in valid.model_dump(mode="json").items():
        setattr(employee, key, value)
    if "employment_status" in changes:
        if changes["employment_status"] is None:
            raise HTTPException(422, "Trạng thái làm việc không được để trống")
        employee.employment_status = changes["employment_status"]
    employee.updated_at = time.time()
    db.commit()
    request.app.state.face.load_gallery(db)
    return employee_item(db, employee, request.app.state.face)


@router.post("/{emp_id}/face/sessions", status_code=201)
def start_session(emp_id: str, payload: SessionCreate, request: Request,
                  idempotency_key: str = Header(min_length=8, max_length=80),
                  user=Depends(require_hr), db=Depends(get_db)):
    service = request.app.state.enrollment
    session = service.create(db, emp_id.upper(), user.id, payload, idempotency_key)
    return service.view(db, session)


@router.get("/{emp_id}/face/sessions/{session_id}")
def session_status(emp_id: str, session_id: str, request: Request, user=Depends(require_hr), db=Depends(get_db)):
    service = request.app.state.enrollment
    session = service.get_session(db, emp_id.upper(), session_id, user.id, allow_committed=True)
    return service.view(db, session)


async def receive_samples(files, manifest, settings):
    try:
        metadata = json.loads(manifest)
    except (ValueError, TypeError):
        raise HTTPException(422, "Manifest ảnh không hợp lệ")
    if not isinstance(metadata, list) or not 1 <= len(files) <= 10 or len(metadata) != len(files) or any(not isinstance(item, dict) for item in metadata):
        raise HTTPException(422, "Gửi tối đa 10 ảnh cùng metadata tương ứng")
    uploads = []
    for meta, file in zip(metadata, files):
        data = await file.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            raise HTTPException(413, "Mỗi ảnh tối đa 5 MB")
        uploads.append((meta, data))
    return uploads


@router.post("/{emp_id}/face/sessions/{session_id}/samples")
async def upload_samples(emp_id: str, session_id: str, request: Request,
                         files: list[UploadFile] = File(...), manifest: str = Form(...),
                         user=Depends(require_hr), db=Depends(get_db)):
    service = request.app.state.enrollment
    session = service.get_session(db, emp_id.upper(), session_id, user.id)
    uploads = await receive_samples(files, manifest, request.app.state.settings)
    return await run_in_threadpool(service.add_samples, db, session, uploads)


@router.delete("/{emp_id}/face/sessions/{session_id}/samples/{sample_id}")
def delete_sample(emp_id: str, session_id: str, sample_id: str, request: Request,
                  user=Depends(require_hr), db=Depends(get_db)):
    service = request.app.state.enrollment
    session = service.get_session(db, emp_id.upper(), session_id, user.id)
    return service.remove_sample(db, session, sample_id)


@router.get("/{emp_id}/face/sessions/{session_id}/samples/{sample_id}/image")
def sample_image(emp_id: str, session_id: str, sample_id: str, request: Request,
                 user=Depends(require_hr), db=Depends(get_db)):
    service = request.app.state.enrollment
    service.get_session(db, emp_id.upper(), session_id, user.id, allow_committed=True)
    sample = db.get(FaceSample, sample_id)
    if not sample or sample.session_id != session_id:
        raise HTTPException(404, "Không tìm thấy ảnh")
    path = service.path(sample.path)
    if not path.is_file():
        raise HTTPException(404, "Ảnh không còn được lưu")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{emp_id}/face/sessions/{session_id}/commit")
def commit_session(emp_id: str, session_id: str, request: Request, user=Depends(require_hr), db=Depends(get_db)):
    service = request.app.state.enrollment
    session = service.get_session(db, emp_id.upper(), session_id, user.id, allow_committed=True)
    return service.commit(db, session)


@router.delete("/{emp_id}/face/sessions/{session_id}")
def cancel_session(emp_id: str, session_id: str, request: Request, user=Depends(require_hr), db=Depends(get_db)):
    service = request.app.state.enrollment
    session = service.get_session(db, emp_id.upper(), session_id, user.id)
    service.discard(db, session)
    return {"ok": True, "status": "cancelled"}


@router.post("/{emp_id}/face/verify-preview")
async def verify_preview(emp_id: str, request: Request, files: list[UploadFile] = File(...),
                         user=Depends(require_hr), db=Depends(get_db)):
    from routers.kiosk import recognize_group
    employee = employee_or_404(db, emp_id)
    request.app.state.face.load_gallery(db)
    images = await receive_recognition_images(files, request.app.state.settings)
    result = await run_in_threadpool(recognize_group, request.app.state.face, images)
    result["expected_employee_id"] = employee.employee_id
    result["verified_expected"] = result.get("matched", False) and result.get("employee_id") == employee.employee_id
    return result


async def receive_recognition_images(files, settings):
    from services.enrollment_service import decode_image
    if not 3 <= len(files) <= 5:
        raise HTTPException(422, "Cần 3–5 frame mới để kiểm tra ổn định")
    images = []
    for file in files:
        try:
            images.append(decode_image(await file.read(settings.max_image_bytes + 1), settings))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    return images


@router.post("/{emp_id}/face/enroll", deprecated=True)
async def legacy_enroll(emp_id: str, request: Request, files: list[UploadFile] = File(...),
                        session_id: str | None = Form(None), manifest: str | None = Form(None),
                        consent: bool = Form(False), user=Depends(require_hr), db=Depends(get_db)):
    if not consent:
        raise HTTPException(400, "Cần xác nhận đồng ý thu nhận khuôn mặt")
    if not session_id or not manifest:
        raise HTTPException(422, "Tạo phiên face/sessions và gửi manifest; cần đủ hai mẫu cho mỗi hướng")
    service = request.app.state.enrollment
    session = service.get_session(db, emp_id.upper(), session_id, user.id)
    uploads = await receive_samples(files, manifest, request.app.state.settings)
    result = await run_in_threadpool(service.add_samples, db, session, uploads)
    if result["status"] == "ready_to_commit":
        result = await run_in_threadpool(service.commit, db, session)
    return {**result, "ok": result.get("ready", False)}
