"""Read-only operational totals for the branch shown on the admin dashboard."""
from collections import Counter
from datetime import datetime, time, timedelta

from hrm import core, store
from hrm.auth import REGISTRATION_KIND
from hrm.payroll_workflow import attendance_rows
from repository import read_csv

BRANCH_ID = 'CN01'


def operational(source):
    return not any(value.strip().startswith(('TEST', 'GENERATED', 'DEMO')) for value in (source or '').upper().split(','))


def branch_payroll(con, month, employees):
    snapshot = store.get(con, 'payroll', month)
    if not snapshot:
        return {'status': 'unavailable'}
    if not operational(snapshot.get('source')):
        return {'status': 'test_data'}
    attendance = snapshot.get('attendance', [])
    branch_ids = {row['employee_id'] for row in attendance if row['branch_id'] == BRANCH_ID}
    known_ids = {row['employee_id'] for row in attendance}
    test_ids = {row['employee_id'] for row in attendance if not operational(row.get('source'))}
    candidates = branch_ids | (employees.keys() - known_ids)
    branch_rows = [row for row in snapshot['rows'] if row['employee_id'] in candidates]
    rows = [row for row in branch_rows if row['employee_id'] not in test_ids]
    if not rows:
        return {'status': 'test_data' if branch_rows else 'unavailable'}
    return {
        'status': snapshot['status'], 'employee_count': len(rows),
        'cost': sum(row['gross'] + row.get('employer_insurance', 0) for row in rows),
        'net': sum(row['net'] for row in rows),
    }


def branch_dashboard(con, day, days, now):
    first = day - timedelta(days=days - 1)
    start = datetime.combine(first, time.min, core.VN)
    end = datetime.combine(day + timedelta(days=1), time.min, core.VN)
    branch = next((row for row in read_csv(store.settings().data_dir / 'clean/branches.csv')
                   if row['branch_id'] == BRANCH_ID), {})
    employees = {row['employee_id']: row for row in store.records(con, 'employees') if row['branch_id'] == BRANCH_ID}
    shifts = {row['shift_id']: row for row in store.records(con, 'shifts')
              if row['branch_id'] == BRANCH_ID and operational(row.get('source'))}
    selected = [shift for shift in shifts.values() if start <= core.dt(shift['start']) < end]
    shift_ids = {row['shift_id'] for row in selected}
    events, journal = [], []
    bars = Counter()
    latest = None
    for event in store.records(con, 'events'):
        if event['shift_id'] not in shifts or not operational(event.get('source')):
            continue
        stamp = core.dt(event['ts'])
        if stamp > now:
            continue
        latest = max(latest, stamp.date()) if latest else stamp.date()
        if event['shift_id'] in shift_ids:
            events.append(event)
        if start <= stamp < end:
            if event['scan_type'] == 'IN':
                bars[stamp.hour if days == 1 else stamp.date()] += 1
            journal.append({key: event[key] for key in ('employee_id', 'ts', 'scan_type', 'source')})

    leaves = [row for row in store.records(con, 'leaves')
              if row['status'] == 'approved' and row['start_date'] <= day.isoformat() and row['end_date'] >= first.isoformat()]
    rows = attendance_rows({'employees': list(employees.values()), 'shifts': selected, 'events': events, 'leaves': leaves})
    for row in rows:
        row['full_name'] = employees.get(row['employee_id'], {}).get('full_name', row['employee_id'])
        if row.get('scheduled_end') and core.dt(row['scheduled_end']) > now:
            if row['status'] == 'absent':
                row['status'] = 'scheduled'
            elif row['status'] == 'incomplete' and row.get('check_in'):
                row['status'] = 'in_progress'

    anchor_rows = [row for row in rows if row['work_date'] == day.isoformat()]
    chart = [{'label': f'{hour:02d}:00', 'count': bars[hour]} for hour in range(24)] if days == 1 else [
        {'label': current.isoformat(), 'count': bars[current]}
        for current in (first + timedelta(days=index) for index in range(days))
    ]
    journal.sort(key=lambda event: event['ts'], reverse=True)
    for event in journal[:12]:
        event['full_name'] = employees.get(event['employee_id'], {}).get('full_name', event['employee_id'])
    return {
        'branch': {'id': BRANCH_ID, 'name': branch.get('branch_name') or BRANCH_ID},
        'date': day.isoformat(), 'start_date': first.isoformat(), 'today': now.date().isoformat(),
        'latest_date': latest.isoformat() if latest else None,
        'days': days, 'active_employees': sum(row['active'] for row in employees.values()),
        'scheduled_employees': len({row['employee_id'] for row in anchor_rows}),
        'checked_in_employees': len({row['employee_id'] for row in anchor_rows if row.get('check_in')}),
        'ot_hours': round(sum(row.get('ot_hours', 0) for row in rows), 2),
        'issues': sum(row['status'] in {'absent', 'incomplete', 'invalid'}
                      or 'leave_and_work_conflict' in row['flags'] for row in rows),
        'checkins': sum(bars.values()), 'chart': chart, 'attendance': rows, 'events': journal[:12],
        'payroll': branch_payroll(con, day.strftime('%Y-%m'), employees),
        'pending_accounts': sum(row['employee_id'] in employees for row in store.records(con, REGISTRATION_KIND)),
        'pending_leaves': sum(row['employee_id'] in employees and row['status'] == 'pending'
                              for row in store.records(con, 'leaves')),
    }
