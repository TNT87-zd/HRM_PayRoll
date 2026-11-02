"""Employee writes live in SQLite; the seed CSV is imported once."""
import csv
import hashlib
import json
import re
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from models import Counter, Employee, MigrationRecord
from schemas import ROLE_VN


def read_csv(path):
    if not Path(path).is_file():
        return []
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def reference_data(settings):
    return {
        "branches": read_csv(settings.data_dir / "clean/branches.csv"),
        "shifts": read_csv(settings.data_dir / "raw/shifts.csv"),
        "roles": [{"id": key, "name": value} for key, value in ROLE_VN.items()],
    }


def seed_employees(db, settings):
    if db.get(MigrationRecord, "employees-csv-v1"):
        return
    rows = read_csv(settings.data_dir / "clean/employees.csv")
    seen, duplicates, imported = set(), [], 0
    for row in rows:
        employee_id = row.get("employee_id", "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{1,32}", employee_id):
            continue
        if employee_id in seen:
            duplicates.append(employee_id)
            continue
        seen.add(employee_id)
        if db.get(Employee, employee_id):
            continue
        def amount(key):
            try:
                value = float(row.get(key) or 0)
                return value if 0 < value < float("inf") else None
            except ValueError:
                return None
        db.add(Employee(
            employee_id=employee_id, full_name=row.get("full_name") or employee_id,
            branch_id=row.get("branch_id", ""), role=row.get("role", ""),
            contract_type=row.get("contract_type", "FT"), primary_shift=row.get("primary_shift", ""),
            hire_date=row.get("hire_date", ""), base_salary=amount("base_salary"),
            hourly_rate=amount("hourly_rate"), is_real_face=False,
        ))
        imported += 1
    db.flush()
    ids = db.scalars(select(Employee.employee_id)).all()
    largest = max([int(x[2:]) for x in ids if re.fullmatch(r"NV\d+", x)] or [0])
    db.execute(insert(Counter).values(name="employee", value=largest).on_conflict_do_nothing())
    db.add(MigrationRecord(name="employees-csv-v1", detail=json.dumps({"imported": imported, "duplicates": duplicates})))
    db.commit()


def employee_or_404(db, employee_id):
    employee = db.get(Employee, employee_id.upper())
    if employee is None:
        raise HTTPException(404, "Không tìm thấy nhân viên")
    return employee


def validate_reference(payload, settings):
    refs = reference_data(settings)
    if payload.branch_id not in {r["branch_id"] for r in refs["branches"]}:
        raise HTTPException(422, "Chi nhánh không hợp lệ")
    shifts = {r["shift_id"]: r for r in refs["shifts"]}
    shift = shifts.get(payload.primary_shift)
    if not shift or shift.get("contract_type") != payload.contract_type:
        raise HTTPException(422, "Ca làm không phù hợp loại hợp đồng")


def employee_item(db, employee, face_service, include_pay=True):
    status = face_service.get_employee_face_status(employee.employee_id, db)
    fields = ("employee_id", "full_name", "branch_id", "role", "contract_type", "primary_shift", "hire_date", "employment_status")
    result = {key: getattr(employee, key) for key in fields}
    result.update(role_vn=ROLE_VN.get(employee.role, employee.role), has_face=status["ready"],
                  face_status=status["status"], photo_count=status["photo_count"], is_real_face=employee.is_real_face)
    if include_pay:
        result.update(base_salary=employee.base_salary, hourly_rate=employee.hourly_rate)
    return result


def create_employee(db, payload, settings, user_id, key):
    validate_reference(payload, settings)
    scope = f"employee:{user_id}:{key}"
    body = payload.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(Employee).where(Employee.create_key == scope))
    if existing:
        if existing.create_digest != digest:
            raise HTTPException(409, "Khóa gửi lặp đã dùng cho nội dung khác")
        return existing
    db.execute(insert(Counter).values(name="employee", value=0).on_conflict_do_nothing())
    sequence = db.scalar(update(Counter).where(Counter.name == "employee").values(value=Counter.value + 1).returning(Counter.value))
    employee = Employee(employee_id=f"NV{sequence:04d}", **body, create_key=scope, create_digest=digest)
    db.add(employee)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Employee).where(Employee.create_key == scope))
        if not existing or existing.create_digest != digest:
            raise HTTPException(409, "Hồ sơ bị trùng hoặc nội dung gửi lặp không khớp")
        return existing
    return employee
