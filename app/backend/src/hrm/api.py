import csv
import hashlib
import io
import json
import math
import uuid
from datetime import date, datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from models import WorkflowAudit
from hrm.store import settings
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from hrm import core, payroll_reports as reports
from hrm.auth import hr, user
from hrm.store import db, records, get, put, audit, ROOT

router = APIRouter(prefix='/api/hrm',tags=['HRM workflow'])

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)

class Employee(Model):
    employee_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    full_name: str = Field(min_length=1,max_length=120)
    branch_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    contract_type: Literal['FT','PT']
    base_salary: int = Field(default=0,ge=0,le=10000000000)
    hourly_rate: int = Field(default=0,ge=0,le=100000000)
    active: bool = True

class Shift(Model):
    shift_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    employee_id: str
    branch_id: str
    start: datetime
    end: datetime
    break_minutes: int = Field(default=0,ge=0,le=240)
    approved_ot_minutes: int = Field(default=0,ge=0,le=90)
    ot_multiplier: float = Field(default=1.5,ge=1,le=5)

class ManualEvent(Model):
    employee_id: str
    shift_id: str
    scan_type: Literal['IN','OUT']
    ts: datetime
    reason: str = Field(min_length=5,max_length=300)

class Leave(Model):
    employee_id: str
    start_date: date
    end_date: date
    leave_type: Literal['PAID','UNPAID']
    reason: str = Field(min_length=3,max_length=300)

class Decision(Model):
    status: Literal['approved','rejected']

class Adjustment(Model):
    allowance: int = Field(default=0,ge=0,le=10000000000)
    bonus: int = Field(default=0,ge=0,le=10000000000)
    insurance: int = Field(default=0,ge=0,le=10000000000)
    tax: int = Field(default=0,ge=0,le=10000000000)
    other_deduction: int = Field(default=0,ge=0,le=10000000000)

class Run(Model):
    standard_hours: float = Field(default=208,gt=0,le=744)
    adjustments: dict[str,Adjustment] = Field(default_factory=dict)
    note: str = Field(min_length=5,max_length=500)

class Close(Model):
    reviewed: Literal[True]
    input_hash: str


def month_check(month):
    try:
        d=date.fromisoformat(month+'-01')
        if d.strftime('%Y-%m')!=month:
            raise ValueError()
    except ValueError:
        raise HTTPException(422,'Kỳ lương phải có dạng YYYY-MM')

def unlocked(con, month):
    p=get(con,'payroll',month)
    if p and p['status']=='finalized':
        raise HTTPException(409,f'Kỳ {month} đã chốt; không được đổi công hoặc lịch ca')

def employee_exists(con,eid):
    e=get(con,'employees',eid)
    if not e or not e['active']:
        raise HTTPException(422,'Nhân viên không tồn tại hoặc đã ngừng hoạt động')
    return e

def scope(u,rows):
    return rows if u['role']=='hr' else [r for r in rows if r.get('employee_id')==u['employee_id']]

@router.get('/employees')
def employees(u=Depends(user)):
    with db() as con:
        return scope(u,records(con,'employees'))

# Employee creation and updates use /api/employees, the shared registration API.

@router.get('/shifts')
def shifts(month: str,u=Depends(user)):
    month_check(month)
    with db() as con:
        return scope(u,[s for s in records(con,'shifts') if s['start'][:7]==month])

@router.put('/shifts')
def save_shift(body: Shift,u=Depends(hr)):
    s=body.model_dump(mode='json')
    start,end=core.dt(s['start']),core.dt(s['end'])
    s['start'],s['end']=start.isoformat(),end.isoformat()
    if start.date()!=end.date() or (start.strftime('%H:%M:%S'),end.strftime('%H:%M:%S')) not in core.SHIFT_WINDOWS:
        raise HTTPException(422,'Chọn ca A 07–15, B 15–23, 1 07–12, 2 12–18 hoặc 3 18–23 trong cùng ngày')
    hours=(end-start).total_seconds()/3600
    if not 0<hours<=16 or body.break_minutes>=hours*60:
        raise HTTPException(422,'Ca phải dài 0–16 giờ, giờ nghỉ nhỏ hơn độ dài ca')
    with db(True) as con:
        e=employee_exists(con,body.employee_id)
        if e['branch_id']!=body.branch_id:
            raise HTTPException(422,'Chi nhánh ca khác chi nhánh nhân viên')
        unlocked(con,s['start'][:7])
        old=get(con,'shifts',body.shift_id)
        if old:
            unlocked(con,old['start'][:7])
            if any(x['shift_id']==body.shift_id for x in records(con,'events')):
                raise HTTPException(409,'Ca đã có log; không được sửa lịch sau chấm công')
        for other in records(con,'shifts'):
            if other['employee_id']==body.employee_id and other['shift_id']!=body.shift_id:
                if start<core.dt(other['end']) and end>core.dt(other['start']):
                    raise HTTPException(409,'Ca bị chồng thời gian')
        put(con,'shifts',body.shift_id,s)
        audit(con,u['username'],'shift_update',{'before':old,'after':s})
    return s

def record_event(con,eid,kind,ts,actor,source,reason='',shift_id=None,event_id=None,device_id=None,similarity=0):
    employee=employee_exists(con,eid)
    stamp=core.dt(ts)
    candidates=[s for s in records(con,'shifts') if s['employee_id']==eid and s['branch_id']==employee['branch_id']
                and core.dt(s['start'])-timedelta(hours=2)<=stamp<=core.dt(s['end'])+timedelta(hours=4)
                and (kind=='OUT' or stamp<core.dt(s['end']))]
    if shift_id:
        candidates=[s for s in candidates if s['shift_id']==shift_id]
    if device_id:
        p=settings().data_dir/'clean/devices.csv'
        if not p.is_file():
            raise HTTPException(422,'Thiếu danh sách thiết bị data/clean/devices.csv')
        with p.open(encoding='utf-8-sig') as f:
            device=next((r for r in csv.DictReader(f) if r['device_id']==device_id),None)
        if not device:
            raise HTTPException(422,'Thiết bị không được đăng ký')
        candidates=[s for s in candidates if s['branch_id']==device['branch_id']]
    if not candidates:
        raise HTTPException(409,'no_shift: Chưa có lịch ca phù hợp với nhân viên, chi nhánh và thời điểm chấm công')
    if len(candidates)>1:
        raise HTTPException(409,'ambiguous_shift: Có nhiều ca phù hợp; HR cần kiểm tra lịch ca')
    s=candidates[0]
    unlocked(con,s['start'][:7])
    key=event_id or uuid.uuid4().hex
    previous=get(con,'events',key)
    if previous:
        return previous
    for e in records(con,'events'):
        if e['shift_id']==s['shift_id'] and e['scan_type']==kind and abs((core.dt(e['ts'])-stamp).total_seconds())<60:
            return e
    e=dict(event_id=key,employee_id=eid,shift_id=s['shift_id'],scan_type=kind,ts=stamp.isoformat(),source=source,reason=reason,device_id=device_id,similarity=similarity)
    put(con,'events',key,e)
    audit(con,actor,'attendance_event',e)
    return e

@router.post('/events/manual')
def manual(body: ManualEvent,u=Depends(hr)):
    with db(True) as con:
        return record_event(con,body.employee_id,body.scan_type,body.ts.isoformat(),u['username'],'MANUAL',body.reason,body.shift_id)

@router.get('/events')
def events(month: str,u=Depends(user)):
    month_check(month)
    with db() as con:
        ids={s['shift_id'] for s in records(con,'shifts') if s['start'][:7]==month}
        return scope(u,[e for e in records(con,'events') if e['shift_id'] in ids])

@router.post('/events/import-live')
def import_live(u=Depends(hr)):
    p=settings().data_dir/'live/scan_log.csv'
    if not p.exists():
        return {'imported':0,'errors':[]}
    errors=[]
    imported=0
    with p.open(encoding='utf-8-sig') as f:
        for i,r in enumerate(csv.DictReader(f),2):
            key='legacy-'+hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
            try:
                with db(True) as con:
                    if get(con,'events',key):
                        continue
                    kind=r['scan_type'].upper()
                    if kind not in ('IN','OUT'):
                        raise ValueError('scan_type không hợp lệ')
                    before=len(records(con,'events'))
                    record_event(con,r['employee_id'],kind,r['ts'],u['username'],'LEGACY_FACE',event_id=key,device_id=r['device_id'])
                    imported+=len(records(con,'events'))-before
            except (HTTPException,ValueError,KeyError) as ex:
                errors.append({'line':i,'error':str(getattr(ex,'detail',ex))})
    return {'imported':imported,'errors':errors}

@router.post('/leaves')
def request_leave(body: Leave,u=Depends(user)):
    if u['role']!='hr' and body.employee_id!=u['employee_id']:
        raise HTTPException(403,'Chỉ được gửi đơn cho chính mình')
    if body.end_date<body.start_date or (body.end_date-body.start_date).days>366:
        raise HTTPException(422,'Khoảng nghỉ không hợp lệ')
    item=body.model_dump(mode='json') | {'leave_id':uuid.uuid4().hex,'status':'pending'}
    with db(True) as con:
        employee_exists(con,body.employee_id)
        put(con,'leaves',item['leave_id'],item)
        audit(con,u['username'],'leave_request',item)
    return item

@router.get('/leaves')
def leaves(u=Depends(user)):
    with db() as con:
        return scope(u,records(con,'leaves'))

@router.post('/leaves/{key}/decision')
def approve_leave(key: str,body: Decision,u=Depends(hr)):
    with db(True) as con:
        l=get(con,'leaves',key)
        if not l:
            raise HTTPException(404,'Không tìm thấy đơn')
        if l['status']!='pending':
            raise HTTPException(409,'Đơn đã được xử lý')
        for p in records(con,'payroll'):
            if p['status']=='finalized' and l['start_date'][:7]<=p['month']<=l['end_date'][:7]:
                raise HTTPException(409,'Đơn thuộc kỳ lương đã chốt')
        if body.status=='approved':
            for other in records(con,'leaves'):
                if other['employee_id']==l['employee_id'] and other['status']=='approved' and l['start_date']<=other['end_date'] and l['end_date']>=other['start_date']:
                    raise HTTPException(409,'Trùng khoảng nghỉ đã duyệt')
        l['status']=body.status
        l['reviewed_by']=u['username']
        put(con,'leaves',key,l)
        audit(con,u['username'],'leave_decision',l)
    return l

def inputs(con,month):
    shifts=[s for s in records(con,'shifts') if s['start'][:7]==month]
    ids={s['shift_id'] for s in shifts}
    return {'shifts':shifts,'events':[e for e in records(con,'events') if e['shift_id'] in ids],
            'leaves':[l for l in records(con,'leaves') if l['status']=='approved' and l['start_date'][:7]<=month<=l['end_date'][:7]],
            'employees':records(con,'employees')}

def fingerprint(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

@router.get('/attendance')
def attendance(month: str,u=Depends(user)):
    month_check(month)
    with db() as con:
        data=inputs(con,month)
        try:
            return scope(u,core.timesheet(data['shifts'],data['events'],data['leaves']))
        except ValueError as ex:
            raise HTTPException(422,str(ex))

@router.post('/payroll/{month}/calculate')
def calculate(month: str,body: Run,u=Depends(hr)):
    month_check(month)
    with db(True) as con:
        unlocked(con,month)
        data=inputs(con,month)
        try:
            rows=core.timesheet(data['shifts'],data['events'],data['leaves'])
        except ValueError as ex:
            raise HTTPException(422,str(ex))
        if not rows:
            raise HTTPException(422,'Chưa có lịch ca trong kỳ')
        if set(body.adjustments)-{e['employee_id'] for e in data['employees']}:
            raise HTTPException(422,'Mã nhân viên điều chỉnh không tồn tại')
        params=body.model_dump()
        try:
            params.update(reports.configuration(con,month))
            pays=core.payroll(data['employees'],rows,params,params['adjustments'])
        except ValueError as ex:
            raise HTTPException(422,str(ex))
        result=dict(month=month,status='draft',policy=params['payroll_2026_policy']['version'],parameters=params,
                    run_id=uuid.uuid4().hex,source=params.get('source','WORKFLOW'),
                    input_hash=fingerprint({"data":data,"parameters":params}),attendance=rows,rows=pays,
                    calculated_at=datetime.now(core.VN).isoformat(),calculated_by=u['username'])
        try:
            reports.archive(result)
        except OSError as ex:
            raise HTTPException(503,'Không lưu được báo cáo; kiểm tra dung lượng/quyền ghi thư mục data/reports') from ex
        put(con,'payroll_runs',result['run_id'],result)
        put(con,'payroll',month,result)
        audit(con,u['username'],'payroll_calculate',{'month':month,'input_hash':result['input_hash']})
    return result

@router.post('/payroll/{month}/finalize')
def finalize(month: str,body: Close,u=Depends(hr)):
    month_check(month)
    with db(True) as con:
        unlocked(con,month)
        p=get(con,'payroll',month)
        if not p:
            raise HTTPException(404,'Chưa tính bảng lương')
        try:
            current_params={**p['parameters'],**reports.configuration(con,month)}
        except ValueError as ex:
            raise HTTPException(422,str(ex))
        if current_params!=p['parameters']:
            raise HTTPException(409,'Cấu hình hợp đồng/chính sách đã đổi; hãy tính lại')
        if p['input_hash']!=body.input_hash or p['input_hash']!=fingerprint({'data':inputs(con,month),'parameters':p['parameters']}):
            raise HTTPException(409,'Dữ liệu đã thay đổi; cần tính và kiểm tra lại')
        if any(r['status']=='incomplete' or 'leave_and_work_conflict' in r['flags'] for r in p['attendance']):
            raise HTTPException(409,'Còn thiếu giờ vào/ra hoặc nghỉ phép trùng ngày làm')
        if any(core.dt(s['end'])>datetime.now(core.VN) for s in inputs(con,month)['shifts']):
            raise HTTPException(409,'Ca làm việc chưa kết thúc')
        if any(r.get('check_out') and core.dt(r['check_out'])>datetime.now(core.VN) for r in p['attendance']):
            raise HTTPException(409,'Có giờ ra nằm trong tương lai; kiểm tra lại dữ liệu')
        p.update(status='finalized',finalized_by=u['username'],finalized_at=datetime.now(core.VN).isoformat())
        if not p.get('run_id'):
            raise HTTPException(409,'Bảng lương cũ chưa có mã lần tính; hãy tính lại trước khi chốt')
        try:
            reports.archive(p)
        except OSError as ex:
            raise HTTPException(503,'Không lưu được báo cáo chốt lương') from ex
        put(con,'payroll_runs',p['run_id'],p)
        put(con,'payroll',month,p)
        audit(con,u['username'],'payroll_finalize',{'month':month,'input_hash':p['input_hash']})
    return p

@router.get('/payroll/{month}')
def view_payroll(month: str,u=Depends(user)):
    month_check(month)
    with db() as con:
        p=get(con,'payroll',month)
        if not p or (u['role']!='hr' and p['status']!='finalized'):
            raise HTTPException(404,'Chưa có bảng lương được phép xem')
        if u['role']!='hr':
            return {'month':month,'status':p['status'],'policy':p['policy'],'rows':scope(u,p['rows'])}
        return p

def download(content, filename, media):
    return StreamingResponse(io.BytesIO(content),media_type=media,
                             headers={'Content-Disposition':f'attachment; filename="{filename}"'})

@router.get('/payroll/{month}/export')
def export(month: str,u=Depends(user)):
    p=view_payroll(month,u)
    return download(reports.workbook_bytes(p),f'payroll_{month}.xlsx',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@router.get('/attendance/export')
def export_attendance(month: str,u=Depends(user)):
    return download(reports.csv_bytes(attendance(month,u)),f'attendance_{month}.csv','text/csv; charset=utf-8')

@router.get('/payroll/{month}/json')
def export_json(month: str,u=Depends(hr)):
    p=view_payroll(month,u)
    return download(json.dumps(p,ensure_ascii=False,indent=2).encode('utf-8'),f'payroll_{month}.json','application/json')

@router.get('/payroll/{month}/history')
def history(month: str,u=Depends(hr)):
    month_check(month)
    with db() as con:
        return [dict(run_id=p['run_id'],status=p['status'],calculated_at=p['calculated_at'],
                     total_net=sum(r['net'] for r in p['rows']))
                for p in records(con,'payroll_runs') if p['month']==month]

@router.get('/payroll/{month}/history/{run_id}/export')
def export_history(month: str,run_id: str,u=Depends(hr)):
    month_check(month)
    with db() as con:
        p=get(con,'payroll_runs',run_id)
        if not p or p['month']!=month:
            raise HTTPException(404,'Không tìm thấy lần tính')
    return download(reports.workbook_bytes(p),f'payroll_{month}_{p["run_id"]}.xlsx',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@router.get('/audit')
def audit_log(u=Depends(hr)):
    with db() as con:
        return [dict(id=r.id,ts=datetime.fromtimestamp(r.ts,core.VN).isoformat(),actor=r.actor,action=r.action,payload=json.loads(r.payload)) for r in con.scalars(select(WorkflowAudit).order_by(WorkflowAudit.id.desc()).limit(200))]


@router.get('/events/unassigned')
def unassigned(u=Depends(hr)):
    from models import AttendanceRecord, AttendanceAssignment
    with db() as con:
        rows=con.scalars(select(AttendanceRecord).where(~AttendanceRecord.id.in_(select(AttendanceAssignment.attendance_id))).order_by(AttendanceRecord.timestamp.desc()).limit(200))
        return [dict(attendance_id=e.id,employee_id=e.employee_id,scan_type=e.scan_type,
                     ts=datetime.fromtimestamp(e.timestamp,core.VN).isoformat(),device_id=e.device_id) for e in rows]

class Assign(Model):
    shift_id: str
    reason: str = Field(min_length=5,max_length=300)

@router.post('/events/{attendance_id}/assign')
def assign(attendance_id: int, body: Assign, u=Depends(hr)):
    from models import AttendanceRecord, AttendanceAssignment
    with db(True) as con:
        old=con.get(AttendanceRecord,attendance_id)
        if not old:
            raise HTTPException(404,'Không tìm thấy lượt chấm công')
        if con.scalar(select(AttendanceAssignment).where(AttendanceAssignment.attendance_id==attendance_id)):
            raise HTTPException(409,'Lượt chấm công đã được gắn ca')
        s=get(con,'shifts',body.shift_id)
        if not s or s['employee_id']!=old.employee_id:
            raise HTTPException(422,'Ca không thuộc nhân viên này')
        unlocked(con,s['start'][:7])
        stamp=datetime.fromtimestamp(old.timestamp,core.VN)
        if not core.dt(s['start'])-timedelta(hours=2)<=stamp<=core.dt(s['end'])+timedelta(hours=4):
            raise HTTPException(422,'Thời điểm quét nằm ngoài khoảng ca')
        if old.scan_type=='IN' and stamp>=core.dt(s['end']):
            raise HTTPException(422,'Giờ vào phải trước kết thúc ca')
        # For old device scans, preserve the branch check too.
        from repository import read_csv
        device=next((d for d in read_csv(settings().data_dir/'clean/devices.csv') if d['device_id']==old.device_id),None)
        if not device or device['branch_id']!=s['branch_id']:
            raise HTTPException(422,'Thiết bị không thuộc chi nhánh ca')
        con.add(AttendanceAssignment(event_id='assigned-'+str(old.id),attendance_id=old.id,
             shift_id=body.shift_id,source='RECONCILED',reason=body.reason))
        audit(con,u['username'],'attendance_assign',{'attendance_id':old.id,'shift_id':body.shift_id,'reason':body.reason})
    return {'ok':True}
