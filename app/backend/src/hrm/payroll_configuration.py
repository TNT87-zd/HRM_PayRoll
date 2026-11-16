"""Reusable, explicitly reviewed payroll configurations with effective month ranges."""
import copy
import json
import re
from datetime import datetime
from pathlib import Path
from hrm import core, store

KIND = 'payroll_config_profiles'

def month_value(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}',value):
        raise ValueError('Kỳ phải có dạng YYYY-MM')
    datetime.strptime(value,'%Y-%m')
    return value

def validate_profile(profile, employees):
    if not isinstance(profile,dict): raise ValueError('Cấu hình phải là object JSON')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',profile.get('profile_id','')):
        raise ValueError('profile_id chỉ gồm chữ, số, gạch ngang/gạch dưới; tối đa 80 ký tự')
    start,end=month_value(profile.get('valid_from')),month_value(profile.get('valid_until'))
    if start>end: raise ValueError('Khoảng hiệu lực bị đảo ngược')
    cfg=profile.get('configuration',{})
    policy=cfg.get('payroll_2026_policy',{})
    if not month_value(policy.get('supported_from'))<=start<=end<=month_value(policy.get('supported_until')):
        raise ValueError('Chính sách chưa hỗ trợ toàn bộ khoảng hiệu lực. Không tự kéo dài chính sách sang năm khác.')
    contracts=cfg.get('contracts')
    if not isinstance(contracts,dict) or not contracts: raise ValueError('Chưa khai contracts')
    roster={e['employee_id']:e for e in employees}
    for eid,c in contracts.items():
        if eid not in roster: raise ValueError('Mã nhân viên không tồn tại: '+eid)
        if not month_value(c.get('valid_from'))<=start<=end<=month_value(c.get('valid_until')):
            raise ValueError('Hợp đồng '+eid+' không phủ khoảng hiệu lực của cấu hình')
        # Exercise engine validation with a full-period probe, never stored as attendance or payroll.
        metrics=dict(regular_hours=float(policy['standard_days'])*float(policy['hours_per_day']),paid_leave_hours=0,worked_days=int(policy['standard_days']),late_minutes=0,unpaid_workdays=0,incomplete_count=0)
        for period in {start,end}:
            core.calculate_employee(roster[eid],metrics,c,period,policy,{})
    return profile

def resolve(con,month):
    month_value(month)
    saved=store.get(con,'payroll_config',month)
    if saved:
        return saved  # Preserve existing period overrides and old payroll fingerprints.
    matches=[p for p in store.records(con,KIND) if p.get('reviewed') is True
             and p['valid_from']<=month<=p['valid_until']]
    if len(matches)>1: raise ValueError('Có nhiều cấu hình hợp đồng cùng hiệu lực; cần xử lý trùng trước khi tính')
    if matches:
        p=matches[0]
        cfg=copy.deepcopy(p['configuration'])
        cfg.update(source='REVIEWED_PROFILE',configuration_profile=p['profile_id'],
                   configuration_revision=p.get('revision',1))
        return cfg
    path=Path(core.__file__).with_name('payroll_contracts.json')
    if path.is_file():
        return dict(payroll_2026_policy=core.load_policy(),contracts=json.loads(path.read_text(encoding='utf-8-sig')),source='CONTRACT_FILE')
    raise ValueError('Chưa có hợp đồng còn hiệu lực cho kỳ '+month+'. Khai cấu hình dùng chung bằng scripts/manage_payroll_config.py; không cần tạo cấu hình riêng mỗi tháng.')

def save_profile(con,profile,actor):
    validate_profile(profile,store.records(con,'employees'))
    key=profile['profile_id']
    if store.get(con,KIND,key): raise ValueError('profile_id đã tồn tại; không ghi đè cấu hình đã duyệt')
    for other in store.records(con,KIND):
        if other.get('reviewed') and max(profile['valid_from'],other['valid_from'])<=min(profile['valid_until'],other['valid_until']):
            raise ValueError('Khoảng hiệu lực trùng cấu hình '+other['profile_id'])
    value=copy.deepcopy(profile)
    value.update(reviewed=True,reviewed_by=actor,reviewed_at=datetime.now(core.VN).isoformat(),revision=1)
    store.put(con,KIND,key,value)
    store.audit(con,actor,'payroll_config_profile_create',dict(profile_id=key,valid_from=value['valid_from'],valid_until=value['valid_until']))
    return value
