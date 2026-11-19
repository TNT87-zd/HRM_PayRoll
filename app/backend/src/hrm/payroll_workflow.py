from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import groupby

from hrm import core
from hrm.store import get, records

ADVANCE_KIND = 'payroll_advance'
ADVANCE_RATE = Decimal('0.90')


def advance_key(month, employee_id):
    return f'{month}:{employee_id}'


def month_advances(con, month):
    return {
        record['employee_id']: record
        for record in records(con, ADVANCE_KIND) if record['month'] == month
    }


def historical_estimates(con, month, employees):
    first = date.fromisoformat(month + '-01')
    months = []
    for _ in range(2):
        first = (first - timedelta(days=1)).replace(day=1)
        months.append(first.isoformat()[:7])
    history = {}
    for previous in months:
        snapshot = get(con, 'payroll', previous)
        if snapshot and snapshot['status'] == 'finalized':
            for row in snapshot['rows']:
                if row['contract_type'] == 'FT' and row.get('base_pay') is not None:
                    history.setdefault(row['employee_id'], []).append((previous, row['base_pay']))
    estimates = {}
    for employee in employees:
        if employee['contract_type'] != 'FT':
            continue
        samples = history.get(employee['employee_id'], [])
        if samples:
            estimates[employee['employee_id']] = {
                'amount': min(amount for _, amount in samples),
                'months': [previous for previous, _ in samples],
            }
    return estimates


def attendance_rows(data, *, cutoff=None, employee_id=None, events_until=None):
    types = {e['employee_id']: e['contract_type'] for e in data['employees']}
    events = {}
    events_until = events_until or cutoff
    for event in data['events']:
        if events_until is None or core.dt(event['ts']) <= events_until:
            events.setdefault(event['shift_id'], []).append(event)
    rows = []
    for shift in sorted(data['shifts'], key=lambda shift: shift['start']):
        if employee_id is not None and shift['employee_id'] != employee_id:
            continue
        try:
            if cutoff is not None and core.dt(shift['end']) > cutoff:
                continue
            row, = core.timesheet([shift], events.get(shift['shift_id'], []), data['leaves'])
        except ValueError as ex:
            row = dict(shift_id=shift['shift_id'], employee_id=shift['employee_id'],
                       branch_id=shift['branch_id'], work_date=shift['start'][:10],
                       status='invalid', flags=[str(ex)])
        rows.append({'contract_type': types.get(row['employee_id']), **row})
    return rows


def employee_pay(employee, rows, month, parameters, advance):
    employee_id = employee['employee_id']
    cfg = parameters['payroll_2026_policy']
    pending = [row for row in rows if row['status'] == 'incomplete']
    if any(row['status'] == 'invalid' for row in rows):
        raise ValueError('Có ca chấm công không hợp lệ. Kiểm tra chi tiết ở bảng công.')
    if employee['contract_type'] == 'PT':
        rows = [row for row in rows if row['status'] != 'incomplete']
        if pending and not any(row['status'] in ('present', 'paid_leave') for row in rows):
            raise ValueError('Chưa có ca đủ lượt vào/ra hoặc phép có lương để tính.')
    metrics = core.metrics_from_rows(employee_id, rows, cfg)
    row = core.calculate_employee(employee, metrics, parameters['contracts'].get(employee_id),
                                  month, cfg, parameters['adjustments'].get(employee_id))
    already_paid = advance.get('paid_amount', 0)
    row.update(pending_shift_count=len(pending), advance_paid=already_paid,
               balance_due=row['net']-already_paid)
    return row


def daily_earnings(employee_id, rows, cfg, rate, now):
    """Estimate earned gross pay by shift start date using the monthly pay rules."""
    eligible = [
        row for row in rows if row['work_date'] <= now.date().isoformat()
        and (not row.get('scheduled_end') or core.dt(row['scheduled_end']) <= now)
    ]
    daily = []
    for day, shifts in groupby(sorted(eligible, key=lambda row: row['work_date']), key=lambda row: row['work_date']):
        payable, pending = [], 0
        for row in shifts:
            if row['status'] in ('invalid', 'incomplete', 'absent') or {
                'leave_and_work_conflict', 'unsupported_shift_window'
            }.intersection(row['flags']):
                pending += 1
                continue
            try:
                core.metrics_from_rows(employee_id, [row], cfg)
            except ValueError:
                pending += 1
                continue
            payable.append(row)
        metrics = core.metrics_from_rows(employee_id, payable, cfg)
        base, ot, hours, _ = core.work_pay(metrics, rate)
        night = core.money(rate * metrics['regular_night_hours'] * Decimal('.3'))
        daily.append(dict(work_date=day, regular_paid_hours=float(hours), base_pay=base, ot_pay=ot,
                          night_extra_pay=night, amount=base+ot+night if payable else None,
                          pending_shift_count=pending))
    return daily


def advance_preview(employee, rows, month, cfg, contract, cutoff):
    employee_id = employee['employee_id']
    if employee['contract_type'] != 'FT':
        raise ValueError('Tạm ứng ngày 15 chỉ áp dụng cho nhân viên full-time')
    core.validate_pay_period(contract, month, cfg)
    pending = 0
    verified = []
    for row in rows:
        if row['status'] in ('invalid', 'incomplete') or {'leave_and_work_conflict', 'unsupported_shift_window'}.intersection(row['flags']):
            pending += 1
        elif row['status'] == 'present':
            verified.append({**row, 'check_out': min(core.dt(row['check_out']), cutoff).isoformat()})
    if not verified:
        raise ValueError('Chưa có công hợp lệ đến ngày 15 để tính tạm ứng')
    metrics = core.metrics_from_rows(employee_id, verified, cfg)
    rate = core.hourly_wage(employee, cfg, contract)
    base, overtime, paid_hours, _ = core.work_pay(metrics, rate)
    accrued = base + overtime
    if not accrued:
        raise ValueError('Chưa phát sinh lương công hoặc OT đến ngày 15')
    return dict(month=month, employee_id=employee_id, through_date=month+'-15',
                base_pay=base, ot_pay=overtime, accrued=accrued,
                paid_days=float(paid_hours / core.dec(cfg['hours_per_day'])),
                suggested_amount=core.money(Decimal(accrued)*ADVANCE_RATE),
                pending_shift_count=pending, paid_amount=0,
                calculated_at=datetime.now(core.VN).isoformat())
