"""Compatibility URLs for Portal; authentication is owned by routers.auth."""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from database import get_db
from hrm.store import audit, db, get, put, records
from models import User, UserEmployee, WorkflowRecord
from routers import auth
from schemas import Credentials

router=APIRouter(prefix="/api/hrm/auth",tags=["HRM auth"])
router.add_api_route('/login',auth.login,methods=['POST'])
router.add_api_route('/logout',auth.logout,methods=['POST'])

def user(account=Depends(auth.require_user), con=Depends(get_db)):
    link=con.get(UserEmployee,account.id)
    if account.role == 'employee' and not link:
        raise HTTPException(403,'Tài khoản chưa được liên kết với nhân viên')
    if account.role not in {'hr','manager','employee'}:
        raise HTTPException(403,'Tài khoản kiosk chỉ được sử dụng màn hình chấm công')
    return dict(username=account.username,role='hr' if account.role in {'hr','manager'} else account.role,
                employee_id=link.employee_id if link else None)

def hr(u=Depends(user)):
    if u['role']!='hr':
        raise HTTPException(403,'Cần quyền HR hoặc quản lý')
    return u

@router.get('/me')
def me(u=Depends(user)):
    return u


class EmployeeCredentials(Credentials):
    model_config = ConfigDict(extra='forbid')
    employee_id: str = Field(min_length=1, max_length=40)


class RegistrationDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    approved: bool


REGISTRATION_KIND = 'employee_registration'


def ensure_employee_unlinked(con, employee_id):
    query = select(UserEmployee.user_id).where(UserEmployee.employee_id == employee_id)
    if con.scalar(query) is not None:
        raise HTTPException(409, 'Nhân viên đã có tài khoản')


def ensure_username_available(con, username):
    if con.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(409, 'Tên đăng nhập đã được sử dụng')


def save_employee_account(con, employee_id, username, password_hash):
    ensure_username_available(con, username)
    ensure_employee_unlinked(con, employee_id)
    account = User(username=username, password_hash=password_hash, role='employee')
    con.add(account)
    con.flush()
    con.add(UserEmployee(user_id=account.id, employee_id=employee_id))
    return {'username': account.username, 'employee_id': employee_id, 'role': account.role}


@router.post('/employee-accounts', status_code=201)
def create_employee_account(body: EmployeeCredentials, actor=Depends(hr)):
    password_hash = auth.hash_password(body.password)
    with db(True) as con:
        employee = get(con, 'employees', body.employee_id)
        if not employee or not employee['active']:
            raise HTTPException(422, 'Chọn nhân viên đang làm việc để tạo tài khoản')
        result = save_employee_account(con, body.employee_id, body.username, password_hash)
        pending = con.get(WorkflowRecord, (REGISTRATION_KIND, body.employee_id))
        if pending:
            con.delete(pending)
        audit(con, actor['username'], 'employee_account_create', result)
        return result


@router.post('/employee-register', status_code=202)
def register_employee(body: EmployeeCredentials):
    with db(True) as con:
        employee = get(con, 'employees', body.employee_id)
        if not employee or not employee['active']:
            raise HTTPException(422, 'Kiểm tra lại mã nhân viên với quản lý')
        ensure_employee_unlinked(con, body.employee_id)
        ensure_username_available(con, body.username)
        if get(con, REGISTRATION_KIND, body.employee_id):
            raise HTTPException(409, 'Mã nhân viên này đã có yêu cầu chờ duyệt')
        request = dict(employee_id=body.employee_id, username=body.username, request_id=uuid4().hex,
                       requested_at=datetime.now(timezone.utc).isoformat())
        put(con, REGISTRATION_KIND, body.employee_id, {**request, 'password_hash': auth.hash_password(body.password)})
        return {'username': body.username, 'status': 'pending'}


@router.get('/employee-registrations')
def employee_registrations(actor=Depends(hr)):
    with db() as con:
        result = []
        for pending in records(con, REGISTRATION_KIND):
            row = {key: pending[key] for key in ('employee_id', 'username', 'request_id', 'requested_at')}
            employee = get(con, 'employees', row['employee_id'])
            row.update(full_name=employee['full_name'] if employee else '',
                       branch_id=employee['branch_id'] if employee else '')
            result.append(row)
        return result


@router.post('/employee-registrations/{employee_id}')
def resolve_employee_registration(employee_id: str, body: RegistrationDecision, actor=Depends(hr)):
    with db(True) as con:
        pending = get(con, REGISTRATION_KIND, employee_id)
        if not pending or pending['request_id'] != body.request_id:
            raise HTTPException(409, 'Yêu cầu đã thay đổi. Tải lại danh sách đăng ký.')
        if body.approved:
            employee = get(con, 'employees', employee_id)
            if not employee or not employee['active']:
                raise HTTPException(422, 'Chỉ duyệt tài khoản cho nhân viên đang làm việc')
            save_employee_account(con, employee_id, pending['username'], pending['password_hash'])
        result = {'employee_id': employee_id, 'username': pending['username'],
                  'status': 'approved' if body.approved else 'rejected'}
        con.delete(con.get(WorkflowRecord, (REGISTRATION_KIND, employee_id)))
        audit(con, actor['username'], 'employee_registration_decision', result)
        return result
