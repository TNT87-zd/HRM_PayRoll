"""Explicit, idempotent test-data import into the existing workflow database."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from sqlalchemy import select
from models import Employee, AttendanceRecord
from hrm import core
from hrm.store import db, records, get, put, audit, employee_dict, settings
from hrm.payroll_reports import csv_bytes

MONTH='2026-10'
BATCH='OCT2026-ROSTER-V1'
SOURCE='GENERATED_TEST'
WINDOWS=[('07:00','15:00'),('15:00','23:00'),('07:00','12:00'),('12:00','18:00'),('18:00','23:00')]

def generate(employees, policy, existing_contracts=None):
    """Use roster wages; never replace an employee or claim these are real scans."""
    shifts=[]; events=[]; contracts={}; existing_contracts=existing_contracts or {}
    days=[date(2026,10,d) for d in range(1,31) if date(2026,10,d).weekday()!=6]
    for index,e in enumerate(employees):
        eid=e['employee_id']; ft=e['contract_type']=='FT'
        chosen=days if ft else days[:(18,22,26)[index%3]]
        window=WINDOWS[index%2] if ft else WINDOWS[2+index%3]
        agreed_hours=len(chosen)*(int(window[1][:2])-int(window[0][:2]))
        contract=existing_contracts.get(eid)
        if contract and contract.get('valid_from','9999')<=MONTH<=contract.get('valid_until','0000'):
            contracts[eid]=contract
        else:
            contracts[eid]=dict(nationality='VN',resident=True,document_type='labor',duration_months=12,
                indefinite=False,valid_from=MONTH,valid_until=MONTH,dependents=0,
                tax_commitment=False,tax_commitment_verified=False,insurance_fixed_supplements=0,
                fixed_allowance=0,meal_per_day=30000 if ft else 0,attendance_bonus=300000 if ft else 0,
                agreed_monthly_hours=agreed_hours,source=SOURCE,
                assumption='Hợp đồng giả định cho kiểm thử tháng 10; cần xác nhận trước sử dụng thực tế')
        for n,day in enumerate(chosen):
            start=core.dt(day.isoformat()+'T'+window[0]+':00')
            end=core.dt(day.isoformat()+'T'+window[1]+':00')
            # Approved overtime after shift end, including next-day OUT for B.
            ot=(60 if n%2==0 else 90) if ft and n in (5,12,19,25) else 0
            sid=f'O26-{eid}-{day:%Y%m%d}'
            shifts.append(dict(shift_id=sid,employee_id=eid,branch_id=e['branch_id'],
                start=start.isoformat(),end=end.isoformat(),break_minutes=0,
                approved_ot_minutes=ot,ot_multiplier=1.5,source=SOURCE,batch_id=BATCH))
            for scan,stamp in [('IN',start),('OUT',end+timedelta(minutes=ot))]:
                events.append(dict(event_id=sid+'-'+scan,employee_id=eid,shift_id=sid,scan_type=scan,
                    ts=stamp.isoformat(),source=SOURCE,reason=BATCH+'; generated for project verification',
                    device_id='IMPORT-OCT2026'))
    policy=json.loads(json.dumps(policy))
    policy['weekly_rest_days']={**policy.get('weekly_rest_days',{}),
        **{e['employee_id']:[6] for e in employees if e['employee_id'] not in policy.get('weekly_rest_days',{})}}
    config=dict(payroll_2026_policy=policy,contracts=contracts,source=SOURCE,batch_id=BATCH)
    rows=core.timesheet(shifts,events,[])
    pays=core.payroll(employees,rows,dict(standard_hours=208,**config),{})
    return dict(employees=employees,shifts=shifts,events=events,leaves=[],configuration=config,
                attendance=rows,expected_payroll=pays)

def import_october():
    with db(True) as con:
        if get(con,'import_batches',BATCH):
            return {'already_imported':True,**get(con,'import_batches',BATCH)}
        if any(s['start'].startswith(MONTH) for s in records(con,'shifts')) or get(con,'payroll',MONTH) or get(con,'payroll_config',MONTH):
            raise ValueError('Tháng 10 đã có lịch/cấu hình/lương. Không ghi đè; cần đối chiếu dữ liệu hiện có.')
        left=core.dt('2026-10-01T00:00:00').timestamp(); right=core.dt('2026-11-01T00:00:00').timestamp()
        if con.scalar(select(AttendanceRecord.id).where(AttendanceRecord.timestamp>=left,AttendanceRecord.timestamp<right).limit(1)):
            raise ValueError('Đã có lượt chấm công tháng 10; không trộn dữ liệu tạo mới vào lượt quét thật.')
        if any(l['start_date'][:7]<=MONTH<=l['end_date'][:7] for l in records(con,'leaves')):
            raise ValueError('Đã có đơn nghỉ trong tháng 10; cần đối chiếu trước khi nhập.')
        roster=[employee_dict(e) for e in con.scalars(select(Employee).order_by(Employee.employee_id))
                if e.employment_status=='active' and e.hire_date<='2026-10-01' and not e.employee_id.startswith('DEMO')]
        if not roster:
            raise ValueError('CSDL chưa có nhân viên hoạt động vào đầu tháng 10. Khởi động ứng dụng để nạp danh sách trước.')
        path=Path(core.__file__).with_name('payroll_contracts.json')
        existing=json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
        package=generate(roster,core.load_policy(),existing)
        folder=settings().data_dir/'attendance'/MONTH/BATCH
        folder.mkdir(parents=True,exist_ok=True)
        for name in ('employees','shifts','events','attendance'):
            (folder/(name+'.csv')).write_bytes(csv_bytes(package[name]))
        (folder/'configuration.json').write_text(json.dumps(package['configuration'],ensure_ascii=False,indent=2),encoding='utf-8')
        for s in package['shifts']: put(con,'shifts',s['shift_id'],s)
        for e in package['events']: put(con,'events',e['event_id'],e)
        put(con,'payroll_config',MONTH,package['configuration'])
        summary=dict(batch_id=BATCH,month=MONTH,source=SOURCE,employees=len(roster),
            shifts=len(package['shifts']),events=len(package['events']),
            imported_at=datetime.now(core.VN).isoformat(),input_folder=str(folder.resolve()))
        (folder/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        put(con,'import_batches',BATCH,summary)
        audit(con,'october-import','attendance_import',summary)
        return summary
