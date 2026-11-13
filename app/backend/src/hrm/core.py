"""Cafe5TN payroll 2026. Vietnamese resident employees."""
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
        if start.date() != end.date() or end <= start:
            raise ValueError('Chỉ hỗ trợ ca kết thúc trong cùng ngày')
        unsupported_shift = (start.strftime('%H:%M:%S'), end.strftime('%H:%M:%S')) not in SHIFT_WINDOWS
        if s['break_minutes'] < 0 or s['approved_ot_minutes'] < 0:
            raise ValueError('Phút nghỉ và OT phải không âm')
        relevant = [e for e in events if e['shift_id'] == s['shift_id']]
        ins = sorted(dt(e['ts']) for e in relevant if e['scan_type'] == 'IN')
        outs = sorted(dt(e['ts']) for e in relevant if e['scan_type'] == 'OUT')
        ci = ins[0] if ins else None
        co = max((o for o in outs if ci and o > ci), default=None)
        if ci and co and (ci.date() != start.date() or co > end + timedelta(days=1)):
            raise ValueError('Lượt quét ngoài phạm vi ca; kiểm tra IN/OUT và mã ca')
        day = start.date().isoformat()
        leave = next((l for l in leaves if l['employee_id'] == s['employee_id'] and l['status'] == 'approved'
                      and l['start_date'] <= day <= l['end_date']), None)
        planned = (end-start).total_seconds()/60 - s['break_minutes']
        if planned < 0:
            raise ValueError('Giờ nghỉ vượt độ dài ca')
        flags = []
        if unsupported_shift:
            flags.append('unsupported_shift_window')
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
            allowed = min(s['approved_ot_minutes'], 90)
            overtime = max(0, (min(co, end + timedelta(minutes=allowed))-max(end,ci)).total_seconds()/60)
            if s['approved_ot_minutes'] > 90:
                flags.append('ot_approval_capped_at_90_minutes')
            late_raw = max(0, (ci-start).total_seconds()/60)
            early_raw = max(0, (end-co).total_seconds()/60)
            late = int(late_raw) if late_raw > 5 else 0
            early = int(early_raw) if early_raw > 5 else 0
            if co > end + timedelta(minutes=allowed):
                flags.append('unapproved_overtime_excluded')
        rows.append(dict(shift_id=s['shift_id'],employee_id=s['employee_id'],branch_id=s['branch_id'],
                         work_date=day,status=status,check_in=ci.isoformat() if ci else None,
                         check_out=co.isoformat() if co else None,regular_hours=round(regular/60,4),
                         paid_leave_hours=round(paid_leave/60,4),ot_hours=round(overtime/60,4),
                         ot_multiplier=s['ot_multiplier'],late_minutes=late,early_minutes=early,flags=flags,
                         scheduled_start=start.isoformat(),scheduled_end=end.isoformat(),
                         source=','.join(sorted({e.get('source','UNSPECIFIED') for e in relevant})) or s.get('source','SCHEDULE'),
                         break_minutes=s['break_minutes'],approved_ot_minutes=s['approved_ot_minutes']))
    return rows

import json
from pathlib import Path

SHIFT_WINDOWS = {('07:00:00','15:00:00'),('15:00:00','23:00:00'),('07:00:00','12:00:00'),('12:00:00','18:00:00'),('18:00:00','23:00:00')}
HOUR_FIELDS = ('regular_hours','paid_leave_hours','regular_night_hours','ot_normal_hours','ot_rest_hours','ot_holiday_hours','ot_normal_night_hours','ot_normal_night_after_day_ot_hours','ot_rest_night_hours','ot_holiday_night_hours')


def dec(value, name='Giá trị'):
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError(name+' phải là số') from exc
    if not number.is_finite() or number < 0:
        raise ValueError(name+' phải hữu hạn, không âm')
    return number


def integer(value, name):
    v = dec(value,name)
    if v != int(v):
        raise ValueError(name+' phải là số nguyên')
    return int(v)


def load_policy():
    return json.loads(Path(__file__).with_name('payroll_2026_policy.json').read_text(encoding='utf-8-sig'))


def progressive_tax(taxable, brackets):
    amount, prev, result = dec(taxable), Decimal(0), Decimal(0)
    if not brackets or brackets[-1][0] is not None:
        raise ValueError('Biểu thuế cần bậc cuối không giới hạn')
    for i,(limit,percent) in enumerate(brackets):
        rate = dec(percent)
        if rate>1: raise ValueError('Thuế suất không hợp lệ')
        if limit is None:
            if i != len(brackets)-1: raise ValueError('Bậc không giới hạn phải ở cuối')
            result += max(Decimal(0), amount-prev)*rate
        else:
            ceiling=dec(limit)
            if ceiling<=prev: raise ValueError('Ngưỡng thuế phải tăng dần')
            result += max(Decimal(0),min(amount,ceiling)-prev)*rate
            prev=ceiling
    return money(result)


def calculate_employee(employee, metrics, contract, period, config=None, adjustments=None):
    """Monthly payroll from verified aggregate hours. One payment per month.

    PT eligibility/base uses agreed contractual monthly pay, not OT or bonuses.
    Separate trial contract is excluded; probation embedded in labor contract is not.
    Supports VN resident workers with one employer, no pension/special exemptions.
    Returns only scalar fields so the existing generic XLSX exporter works.
    """
    cfg=config or load_policy()
    try: datetime.strptime(period,'%Y-%m')
    except (ValueError,TypeError) as exc: raise ValueError('Kỳ phải có dạng YYYY-MM') from exc
    if not cfg['supported_from'] <= period <= cfg['supported_until']:
        raise ValueError('Bản này kiểm chứng chính sách cho kỳ 07-12/2026; không tự áp dụng sai sang kỳ khác')
    if not contract: raise ValueError('Thiếu cấu hình hợp đồng nhân viên')
    if contract.get('resident') is not True or contract.get('nationality') != 'VN':
        raise ValueError('Bản này hỗ trợ lao động Việt Nam là cá nhân cư trú')
    if contract.get('special_insurance_case',False):
        raise ValueError('Trường hợp BH đặc biệt cần xử lý riêng trước khi tính')
    if contract.get('valid_from','9999-99')>period or contract.get('valid_until','0000-00')<period:
        raise ValueError('Hợp đồng chưa được xác nhận cho kỳ tính này')
    # Không suy luận hợp đồng pháp lý từ nhãn FT/PT.
    document=contract.get('document_type')
    if document not in ('labor','trial','none'): raise ValueError('document_type: labor, trial hoặc none')
    duration=integer(contract.get('duration_months',0),'Thời hạn hợp đồng')
    indefinite=contract.get('indefinite',False)
    if not isinstance(indefinite,bool): raise ValueError('indefinite phải là boolean')
    if document!='labor' and indefinite: raise ValueError('Chỉ hợp đồng lao động được khai không xác định thời hạn')
    commitment=contract.get('tax_commitment',False)
    if not isinstance(commitment,bool): raise ValueError('tax_commitment phải là boolean')
    if commitment and not contract.get('tax_commitment_verified',False):
        raise ValueError('Cam kết thuế cần được kiểm tra điều kiện và hồ sơ')
    if integer(metrics.get('unpaid_workdays',0),'Ngày không hưởng lương')>=14:
        raise ValueError('Có từ 14 ngày không hưởng lương: cần xác định BH riêng; cần đối chiếu hồ sơ riêng')
    if integer(metrics.get('incomplete_count',0),'Công thiếu'):
        raise ValueError('Còn công thiếu, ca ngoài khung giờ hoặc xung đột nghỉ phép; xử lý trước khi tính')
    if integer(metrics.get('worked_days',0),'Ngày đi làm')>31: raise ValueError('Ngày đi làm vượt 31')
    h={k:dec(metrics.get(k,0),k) for k in HOUR_FIELDS}
    if sum(v for k,v in h.items() if k!='regular_night_hours')>744: raise ValueError('Tổng giờ không hợp lệ')
    if h['regular_night_hours']>h['regular_hours']: raise ValueError('Giờ đêm trong ca vượt giờ thường')
    a=adjustments or {}
    for key in ('insurance','tax'):
        if dec(a.get(key,0)):
            raise ValueError('Bảo hiểm và thuế tự tính; đặt ô '+key+' ở form cũ về 0')
    typ=employee['contract_type']
    if typ not in ('FT','PT'): raise ValueError('Loại nhân viên phải FT hoặc PT')
    wage=dec(employee.get('base_salary',0))
    day_hours=dec(cfg['hours_per_day']); standard_days=dec(cfg['standard_days'])
    if day_hours<=0 or standard_days<=0: raise ValueError('Ngày và giờ chuẩn phải dương')
    rate=wage/(day_hours*standard_days) if typ=='FT' else dec(employee.get('hourly_rate',0))
    if document=='labor':
        if typ=='FT' and wage<dec(cfg['region_min_month']): raise ValueError('Lương FT hợp đồng thấp hơn tối thiểu vùng II')
        if typ=='PT' and rate<dec(cfg['region_min_hour']): raise ValueError('Lương giờ PT thấp hơn 22.700 đồng')
    paid_hours=h['regular_hours']+h['paid_leave_hours']
    base=money(rate*paid_hours)
    multipliers={'ot_normal_hours':'1.5','ot_rest_hours':'2','ot_holiday_hours':'3',
        'ot_normal_night_hours':'2','ot_normal_night_after_day_ot_hours':'2.1',
        'ot_rest_night_hours':'2.7','ot_holiday_night_hours':'3.9'}
    ot_parts={k:money(rate*h[k]*Decimal(v)) for k,v in multipliers.items()}
    ot=sum(ot_parts.values())
    night_extra=money(rate*h['regular_night_hours']*Decimal('.3'))
    meal=money(dec(contract.get('meal_per_day',cfg['meal_per_day']))*integer(metrics.get('worked_days',0),'Ngày làm'))
    fixed_allowance=money(dec(contract.get('fixed_allowance',0)))
    bonus_ok=not integer(metrics.get('late_minutes',0),'Phút trễ') and not integer(metrics.get('unpaid_workdays',0),'Ngày vắng') and metrics.get('worked_days',0)>0
    attendance_bonus=money(dec(contract.get('attendance_bonus',cfg['attendance_bonus']))) if bonus_ok else 0
    allowance=meal+fixed_allowance+money(dec(a.get('allowance',0)))
    bonus=attendance_bonus+money(dec(a.get('bonus',0)))
    gross=base+ot+night_extra+allowance+bonus
    # Căn cứ BH được xác nhận từ hợp đồng, không lấy tổng thu nhập.
    regular_supplements=dec(contract.get('insurance_fixed_supplements',0))
    if typ=='FT':
        agreed_base=wage+regular_supplements
    else:
        if 'agreed_monthly_hours' not in contract: raise ValueError('PT cần agreed_monthly_hours theo hợp đồng')
        agreed_base=rate*dec(contract['agreed_monthly_hours'])+regular_supplements
    eligible=document=='labor' and (indefinite or duration>=1)
    if typ=='PT': eligible=eligible and agreed_base>=dec(cfg['pt_ins_min_pay'])
    reference=dec(cfg['reference_salary'])
    if dec(cfg['pt_ins_min_pay'])!=reference: raise ValueError('Ngưỡng PT phải bằng mức tham chiếu trong chính sách này')
    si_base=min(agreed_base,reference*20) if eligible else Decimal(0)
    ui_base=min(agreed_base,dec(cfg['region_min_month'])*20) if eligible else Decimal(0)
    emp_parts={}; company_parts={}
    for key in ('bhxh','bhyt','bhtn'):
        b=ui_base if key=='bhtn' else si_base
        emp_parts[key]=money(b*dec(cfg['employee_rates'][key]))
        company_parts[key]=money(b*dec(cfg['employer_rates'][key]))
    insurance=sum(emp_parts.values()); employer=sum(company_parts.values())
    meal_exempt=min(meal,money(dec(cfg['meal_exempt_limit'])))
    # Tiền lương đêm toàn phần: phần cơ bản của giờ đêm + khoản thêm 30%.
    night_exempt=min(base,money(rate*h['regular_night_hours']))+night_extra
    exempt=ot+night_exempt+meal_exempt
    taxable_pay=max(0,gross-exempt)
    dependents=integer(contract.get('dependents',0),'Số người phụ thuộc')
    deduction=money(dec(cfg['personal_deduction'])+dependents*dec(cfg['dependent_deduction']))
    long_contract=document=='labor' and (indefinite or duration>=3)
    taxable=max(0,taxable_pay-insurance-deduction) if long_contract else 0
    if long_contract:
        tax=progressive_tax(taxable,cfg['tax_brackets']); tax_method='progressive_2026'
    elif commitment:
        tax=0; tax_method='verified_commitment'
    else:
        # Scope: one monthly payment, threshold checked against taxable payment before deductions.
        tax=money(Decimal(taxable_pay)*dec(cfg['short_contract_rate'])) if taxable_pay>=dec(cfg['short_contract_threshold']) else 0
        tax_method='withholding_10pct_per_payment'
    other=money(dec(a.get('other_deduction',0)))
    net=gross-insurance-tax-other
    if net<0: raise ValueError('Khấu trừ vượt thu nhập; kiểm tra lại công và hồ sơ BH')
    result=dict(employee_id=employee['employee_id'],full_name=employee['full_name'],contract_type=typ,period=period,
        regular_paid_hours=float(paid_hours),regular_night_hours=float(h['regular_night_hours']),
        paid_days=float(paid_hours/day_hours),worked_days=int(metrics.get('worked_days',0)),hourly_rate=float(rate),
        base_pay=base,ot_pay=ot,night_extra_pay=night_extra,ot_hours=float(sum(h[k] for k in multipliers)),
        allowance=allowance,meal_allowance=meal,fixed_allowance=fixed_allowance,bonus=bonus,attendance_bonus=attendance_bonus,
        gross=gross,insurance=insurance,employer_insurance=employer,employer_total_cost=gross+employer,
        insurance_eligible=eligible,insurance_contract_base=money(agreed_base),insurance_si_base=money(si_base),insurance_ui_base=money(ui_base),
        pt_ins_min_pay=cfg['pt_ins_min_pay'],meal_tax_exempt=meal_exempt,ot_tax_exempt=ot,night_tax_exempt=night_exempt,
        taxable_pay=taxable_pay,personal_deduction=cfg['personal_deduction'],dependent_count=dependents,
        taxable_income=taxable,tax=tax,tax_method=tax_method,tax_commitment=commitment,
        other_deduction=other,net=net,late_minutes=int(metrics.get('late_minutes',0)),
        policy_version=cfg['version'],policy_snapshot=json.dumps(cfg,ensure_ascii=False,sort_keys=True),
        contract_snapshot=json.dumps(contract,ensure_ascii=False,sort_keys=True))
    for key in emp_parts:
        result['employee_'+key]=emp_parts[key]; result['employer_'+key]=company_parts[key]
    for key in multipliers:
        result[key]=float(h[key]); result[key.replace('_hours','_pay')]=ot_parts[key]
    return result


def _interval_hours(left, right, night=False):
    if right <= left:
        return Decimal(0)
    if not night:
        return Decimal(str((right-left).total_seconds())) / 3600
    # Night windows 22:00--06:00, including the preceding day's window.
    anchor = left.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    total = Decimal(0)
    while anchor < right:
        begin = anchor + timedelta(hours=22)
        finish = anchor + timedelta(days=1, hours=6)
        lo, hi = max(left, begin), min(right, finish)
        if hi > lo:
            total += Decimal(str((hi-lo).total_seconds())) / 3600
        anchor += timedelta(days=1)
    return total


def metrics_from_rows(employee_id, rows, cfg):
    m={k:Decimal(0) for k in HOUR_FIELDS}
    days=set(); unpaid=set(); late=0; bad=0
    def day_type(value):
        day=value.date().isoformat()
        return 'holiday' if day in cfg['holiday_dates'] else ('rest' if value.weekday() in cfg['weekly_rest_days'].get(employee_id,[]) else 'normal')
    # Collect OT day/night by calendar day before selecting night multipliers.
    buckets={}
    for r in rows:
        if r['employee_id']!=employee_id: continue
        day=r['work_date']; status=r['status']; flags=r.get('flags',[])
        bad += int(status=='incomplete' or 'leave_and_work_conflict' in flags or 'unsupported_shift_window' in flags)
        late += int(r.get('late_minutes',0))
        if status in ('absent','unpaid_leave'): unpaid.add(day)
        if status=='paid_leave': m['paid_leave_hours']+=dec(r['paid_leave_hours']); continue
        if status!='present': continue
        if 'scheduled_start' not in r: raise ValueError('Cần tính lại bảng công bằng core.py mới')
        ci,co,start,end=[dt(r[k]) for k in ('check_in','check_out','scheduled_start','scheduled_end')]
        if start.date()!=end.date() or end<=start or ci.date()!=start.date() or co>end+timedelta(days=1):
            raise ValueError('Thời điểm ca/IN/OUT không hợp lệ')
        if dec(r['break_minutes']) and end.hour>=22:
            raise ValueError('Ca có giờ đêm và giờ nghỉ: cần biết thời điểm nghỉ; cần khai thời điểm nghỉ cụ thể cho ca B/3')
        left,right=max(ci,start),min(co,end)
        regular=max(Decimal(0),_interval_hours(left,right)-dec(r['break_minutes'])/60)
        regular_night=min(regular,_interval_hours(left,right,True))
        typ=day_type(start)
        if typ=='normal':
            m['regular_hours']+=regular; m['regular_night_hours']+=regular_night
        else:
            m['ot_'+typ+'_hours']+=regular-regular_night
            m['ot_'+typ+'_night_hours']+=regular_night
        allowed=min(dec(r['approved_ot_minutes']),Decimal(90))
        ot_left=max(ci,end); ot_right=min(co,end+timedelta(minutes=float(allowed)))
        if regular+_interval_hours(ot_left,ot_right): days.add(day)
        while ot_left < ot_right:
            midnight=ot_left.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
            finish=min(midnight,ot_right)
            key=(ot_left.date().isoformat(),day_type(ot_left))
            entry=buckets.setdefault(key,[Decimal(0),Decimal(0)])
            night=_interval_hours(ot_left,finish,True)
            entry[0]+=_interval_hours(ot_left,finish)-night; entry[1]+=night
            ot_left=finish
    for (_,typ),(daytime,night) in buckets.items():
        m['ot_'+typ+'_hours']+=daytime
        key='ot_normal_night_after_day_ot_hours' if typ=='normal' and daytime else 'ot_'+typ+'_night_hours'
        m[key]+=night
    m.update(worked_days=len(days),unpaid_workdays=len(unpaid),late_minutes=late,incomplete_count=bad)
    return m


def payroll(employees, rows, policy, adjustments):
    cfg=policy.get('payroll_2026_policy') or load_policy()
    if dec(policy.get('standard_hours',208))!=dec(cfg['standard_days'])*dec(cfg['hours_per_day']):
        raise ValueError('Giờ chuẩn FT của chính sách này là 208 (26 × 8)')
    contracts=policy.get('contracts')
    if contracts is None:
        path=Path(__file__).with_name('payroll_contracts.json')
        if not path.is_file(): raise ValueError('Thiếu payroll_contracts.json; khai hợp đồng trước khi tính')
        contracts=json.loads(path.read_text(encoding='utf-8-sig'))
    periods={r['work_date'][:7] for r in rows}
    if len(periods)!=1: raise ValueError('Chỉ tính một kỳ có dữ liệu trong mỗi lần')
    period=next(iter(periods)); results=[]
    for e in employees:
        if not any(r['employee_id']==e['employee_id'] for r in rows): continue
        contract=contracts.get(e['employee_id'])
        if not contract: raise ValueError('Thiếu hợp đồng cho '+e['employee_id']+' trong payroll_contracts.json')
        results.append(calculate_employee(e,metrics_from_rows(e['employee_id'],rows,cfg),contract,period,cfg,adjustments.get(e['employee_id'],{})))
    return results
