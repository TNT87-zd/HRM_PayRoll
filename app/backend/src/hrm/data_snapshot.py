"""Monthly read-only exports from the operational database; never seed attendance."""
import csv
import hashlib
import json
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from models import AttendanceRecord, AttendanceAssignment
from hrm import core, store

EVENT_FIELDS = ['attendance_id','event_id','employee_id','device_id','scan_type','ts','timestamp','similarity','shift_id','source','reason','calendar_month','work_month']
DAILY_FIELDS = ['shift_id','employee_id','branch_id','work_date','status','check_in','check_out','regular_hours','paid_leave_hours','ot_hours','ot_multiplier','late_minutes','early_minutes','flags','scheduled_start','scheduled_end','source','break_minutes','approved_ot_minutes']
SHIFT_FIELDS = ['shift_id','employee_id','branch_id','start','end','break_minutes','approved_ot_minutes','ot_multiplier']
PAY_FIELDS = ['employee_id','contract_type','gross','insurance','employer_insurance','tax','net']


def month_bounds(month):
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('Ky phai co dang YYYY-MM')
    start = datetime.strptime(month, '%Y-%m').replace(tzinfo=core.VN)
    end = start.replace(year=start.year+1, month=1) if start.month == 12 else start.replace(month=start.month+1)
    return start, end


def daily_rows(con, month=None):
    shifts = store.records(con, 'shifts')
    if month is not None:
        month_bounds(month)
        shifts = [s for s in shifts if core.dt(s['start']).strftime('%Y-%m') == month]
    ids = {s['shift_id'] for s in shifts}
    events = [e for e in store.records(con, 'events') if e['shift_id'] in ids]
    return core.timesheet(shifts, events, store.records(con, 'leaves'))


def snapshot(con, month):
    start, end = month_bounds(month)
    all_shifts = store.records(con, 'shifts')
    shift_map = {s['shift_id']: s for s in all_shifts}
    shifts = [s for s in all_shifts if core.dt(s['start']).strftime('%Y-%m') == month]
    ids = {s['shift_id'] for s in shifts}
    events = []
    # Include every scan in the calendar month, AND next-month OUT linked to this month's shifts.
    query = select(AttendanceRecord, AttendanceAssignment).outerjoin(
        AttendanceAssignment, AttendanceAssignment.attendance_id == AttendanceRecord.id
    ).where((AttendanceRecord.timestamp >= start.timestamp()) & (AttendanceRecord.timestamp < end.timestamp()) |
            AttendanceAssignment.shift_id.in_(ids)).order_by(AttendanceRecord.timestamp, AttendanceRecord.id)
    for r, a in con.execute(query):
        s = shift_map.get(a.shift_id) if a else None
        ts = datetime.fromtimestamp(r.timestamp, core.VN)
        events.append(dict(attendance_id=r.id, event_id=a.event_id if a else '', employee_id=r.employee_id,
            device_id=r.device_id, scan_type=r.scan_type, ts=ts.isoformat(), timestamp=r.timestamp,
            similarity=r.similarity, shift_id=a.shift_id if a else '', source=a.source if a else 'UNASSIGNED',
            reason=a.reason if a else '', calendar_month=ts.strftime('%Y-%m'),
            work_month=core.dt(s['start']).strftime('%Y-%m') if s else ''))
    leaves = [l for l in store.records(con, 'leaves') if l['start_date'][:7] <= month <= l['end_date'][:7]]
    run = store.get(con, 'payroll', month)
    return dict(month=month, employees=store.records(con,'employees'), shifts=shifts, events=events,
                leaves=leaves, attendance=daily_rows(con,month), payroll=run)


def write_csv(path, rows, fields):
    keys = list(dict.fromkeys(fields + [k for row in rows for k in row]))
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, keys)
        writer.writeheader()
        for row in rows:
            values = {}
            for k,v in row.items():
                if isinstance(v,(dict,list)): v=json.dumps(v,ensure_ascii=False)
                # CSVs are intended for Excel review, not round-trip database imports.
                if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')): v="'"+v
                values[k]=v
            writer.writerow(values)


def export_snapshot(con, data_dir, month):
    data = snapshot(con,month)
    root = Path(data_dir)
    run_id = datetime.now(core.VN).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    destinations = [root/'raw'/'operational'/month/run_id, root/'clean'/'operational'/month/run_id]
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.snapshot_',dir=root))
    published = []
    try:
        raw, clean = stage/'raw', stage/'clean'
        raw.mkdir(); clean.mkdir()
        write_csv(raw/'attendance_events.csv',data['events'],EVENT_FIELDS)
        assignments = [{k:r[k] for k in ['event_id','attendance_id','shift_id','source','reason']} for r in data['events'] if r['event_id']]
        write_csv(raw/'attendance_assignments.csv',assignments,['event_id','attendance_id','shift_id','source','reason'])
        write_csv(raw/'shifts.csv',data['shifts'],SHIFT_FIELDS)
        write_csv(raw/'employees.csv',data['employees'],['employee_id','full_name','branch_id','contract_type','base_salary','hourly_rate','active'])
        write_csv(raw/'leaves.csv',data['leaves'],['leave_id','employee_id','start_date','end_date','leave_type','status'])
        write_csv(clean/'attendance_daily.csv',data['attendance'],DAILY_FIELDS)
        unassigned = [r for r in data['events'] if not r['work_month']]
        write_csv(clean/'unassigned_events.csv',unassigned,EVENT_FIELDS)
        payroll = data['payroll']
        write_csv(clean/'payroll.csv',payroll.get('rows',[]) if payroll else [],PAY_FIELDS)
        if payroll:
            (clean/'payroll_saved.json').write_text(json.dumps(payroll,ensure_ascii=False,indent=2),encoding='utf-8')
        manifest=dict(schema_version=1, month=month,snapshot_id=run_id, timezone='Asia/Ho_Chi_Minh',
            source='SQLITE_SNAPSHOT', created_at=datetime.now(core.VN).isoformat(),
            scan_count=len(data['events']),shift_count=len(data['shifts']),daily_count=len(data['attendance']),
            unassigned_count=len(unassigned),event_sources=sorted({e['source'] for e in data['events']}),
            payroll_status=payroll.get('status') if payroll else 'NOT_CALCULATED',
            payroll_run_id=payroll.get('run_id') if payroll else None,
            note='Payroll is the last saved run; attendance is current at export time. Compare input_hash before finalizing. Events include month-boundary scans linked to selected shifts; raw CSV is Excel-safe, not an import format.')
        manifest['sha256']={str(f.relative_to(stage)):hashlib.sha256(f.read_bytes()).hexdigest() for f in stage.rglob('*') if f.is_file()}
        for folder in (raw,clean):
            (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        for folder,dest in zip((raw,clean),destinations):
            dest.parent.mkdir(parents=True,exist_ok=True)
            folder.rename(dest); published.append(dest)
        return destinations, manifest
    except Exception:
        for folder in published: shutil.rmtree(folder)
        raise
    finally:
        shutil.rmtree(stage,ignore_errors=True)
