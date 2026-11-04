"""Workflow adapter: shares SQLAlchemy sessions, employees and attendance with main."""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from sqlalchemy import select, text
from config import PROJECT_ROOT
from models import Employee, AttendanceRecord, AttendanceAssignment, WorkflowRecord, WorkflowAudit
from hrm.core import VN, dt

ROOT = PROJECT_ROOT
context = ContextVar("hrm_context")

def settings():
    return context.get()[1]

@contextmanager
def db(write=False):
    factory, _ = context.get()
    with factory() as session:
        try:
            if write:
                session.execute(text("BEGIN IMMEDIATE"))
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

def employee_dict(e):
    return dict(employee_id=e.employee_id, full_name=e.full_name, branch_id=e.branch_id,
                contract_type=e.contract_type, base_salary=e.base_salary or 0,
                hourly_rate=e.hourly_rate or 0, active=e.employment_status == "active")

def event_dict(a, e):
    return dict(event_id=a.event_id, employee_id=e.employee_id, shift_id=a.shift_id,
                scan_type=e.scan_type, ts=datetime.fromtimestamp(e.timestamp,VN).isoformat(),
                source=a.source, reason=a.reason)

def records(con, kind):
    if kind == "employees":
        return [employee_dict(e) for e in con.scalars(select(Employee).order_by(Employee.employee_id))]
    if kind == "events":
        return [event_dict(a,e) for a,e in con.execute(select(AttendanceAssignment,AttendanceRecord)
            .join(AttendanceRecord,AttendanceRecord.id==AttendanceAssignment.attendance_id)
            .order_by(AttendanceAssignment.event_id))]
    return [json.loads(r.payload) for r in con.scalars(select(WorkflowRecord)
        .where(WorkflowRecord.kind==kind).order_by(WorkflowRecord.key))]

def get(con, kind, key):
    if kind == "employees":
        e=con.get(Employee,key)
        return employee_dict(e) if e else None
    if kind == "events":
        a=con.get(AttendanceAssignment,key)
        return event_dict(a,con.get(AttendanceRecord,a.attendance_id)) if a else None
    row=con.get(WorkflowRecord,(kind,key))
    return json.loads(row.payload) if row else None

def put(con, kind, key, value):
    if kind == "employees":
        raise ValueError("Use the shared employee API")
    if kind == "events":
        e=AttendanceRecord(employee_id=value['employee_id'], device_id=value.get('device_id') or 'HR',
            scan_type=value['scan_type'], timestamp=dt(value['ts']).timestamp(),similarity=value.get('similarity',0))
        con.add(e); con.flush()
        con.add(AttendanceAssignment(event_id=key,attendance_id=e.id,shift_id=value['shift_id'],
            source=value['source'],reason=value.get('reason','')))
    else:
        row=con.get(WorkflowRecord,(kind,key))
        if row is None:
            row=WorkflowRecord(kind=kind,key=key); con.add(row)
        row.payload=json.dumps(value,ensure_ascii=False,allow_nan=False)
    con.flush()

def audit(con, actor, action, data):
    con.add(WorkflowAudit(actor=actor,action=action,payload=json.dumps(data,ensure_ascii=False,allow_nan=False)))
    con.flush()
