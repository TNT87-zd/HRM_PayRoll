"""Pure business calculations. Demo policy, not a statutory payroll implementation."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

VN = timezone(timedelta(hours=7))

def dt(value):
    d = datetime.fromisoformat(value)
    return d.replace(tzinfo=VN) if d.tzinfo is None else d.astimezone(VN)

def money(value):
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def timesheet(shifts, events, leaves):
    rows = []
    for s in sorted(shifts, key=lambda s: s['start']):
        start, end = dt(s['start']), dt(s['end'])
        relevant = [e for e in events if e['shift_id'] == s['shift_id']]
        ins = sorted(dt(e['ts']) for e in relevant if e['scan_type'] == 'IN')
        outs = sorted(dt(e['ts']) for e in relevant if e['scan_type'] == 'OUT')
        ci = ins[0] if ins else None
        co = max((o for o in outs if ci and o > ci), default=None)
        day = start.date().isoformat()
        leave = next((l for l in leaves if l['employee_id'] == s['employee_id'] and l['status'] == 'approved'
                      and l['start_date'] <= day <= l['end_date']), None)
        planned = (end-start).total_seconds()/60 - s['break_minutes']
        flags = []
        regular = overtime = late = early = paid_leave = 0
        if not relevant and leave:
            status = 'paid_leave' if leave['leave_type'] == 'PAID' else 'unpaid_leave'
            paid_leave = planned if status == 'paid_leave' else 0
        elif not relevant:
            status = 'absent'
        elif not ci or not co:
            status = 'incomplete'
            flags.append('missing_in_or_out')
        else:
            status = 'present'
            if leave:
                flags.append('leave_and_work_conflict')
            # Break deduction applies once; no negative hours for short attendance.
            regular = max(0, (min(co,end)-max(ci,start)).total_seconds()/60 - s['break_minutes'])
            overtime = min(max(0, (co-max(end,ci)).total_seconds()/60), s['approved_ot_minutes'])
            late_raw = max(0, (ci-start).total_seconds()/60)
            early_raw = max(0, (end-co).total_seconds()/60)
            late = int(late_raw) if late_raw > 5 else 0
            early = int(early_raw) if early_raw > 5 else 0
            if (co-end).total_seconds()/60 > s['approved_ot_minutes'] + 1:
                flags.append('unapproved_overtime_excluded')
        rows.append(dict(shift_id=s['shift_id'],employee_id=s['employee_id'],branch_id=s['branch_id'],
                         work_date=day,status=status,check_in=ci.isoformat() if ci else None,
                         check_out=co.isoformat() if co else None,regular_hours=round(regular/60,4),
                         paid_leave_hours=round(paid_leave/60,4),ot_hours=round(overtime/60,4),
                         ot_multiplier=s['ot_multiplier'],late_minutes=late,early_minutes=early,flags=flags))
    return rows

def payroll(employees, rows, policy, adjustments):
    result = []
    for e in employees:
        days = [r for r in rows if r['employee_id']==e['employee_id']]
        if not days:
            continue
        rate = Decimal(str(e['base_salary']))/Decimal(str(policy['standard_hours'])) if e['contract_type']=='FT' else Decimal(str(e['hourly_rate']))
        hours = sum(Decimal(str(r['regular_hours']))+Decimal(str(r['paid_leave_hours'])) for r in days)
        base = money(rate*hours)
        ot = money(sum(rate*Decimal(str(r['ot_hours']))*Decimal(str(r['ot_multiplier'])) for r in days))
        a = adjustments.get(e['employee_id'], {})
        allowance, bonus = a.get('allowance',0), a.get('bonus',0)
        insurance, tax, other = a.get('insurance',0), a.get('tax',0), a.get('other_deduction',0)
        gross = base+ot+allowance+bonus
        net = gross-insurance-tax-other
        if net < 0:
            raise ValueError(f"Khoản khấu trừ vượt thu nhập: {e['employee_id']}")
        result.append(dict(employee_id=e['employee_id'],full_name=e['full_name'],contract_type=e['contract_type'],
                           regular_paid_hours=float(hours),ot_hours=round(sum(r['ot_hours'] for r in days),4),
                           base_pay=base,ot_pay=ot,allowance=allowance,bonus=bonus,gross=gross,
                           insurance=insurance,tax=tax,other_deduction=other,net=net))
    return result
