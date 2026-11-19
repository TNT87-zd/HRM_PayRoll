"""Effective calendar overlay; never mutates saved SQLite configurations."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path


def apply_calendar(configuration, month):
    cfg = deepcopy(configuration)
    year = int(month[:4])
    path = Path(__file__).with_name(f'holiday_calendar_{year}.json')
    if not path.is_file():
        raise ValueError(f'Chưa khai lịch lễ năm {year}; không tự dùng lịch năm cũ')
    calendar = json.loads(path.read_text(encoding='utf-8-sig'))
    if calendar['year'] != year or not isinstance(calendar['night_pay_enabled'], bool):
        raise ValueError('Lịch lễ sai năm hoặc cấu hình tiền đêm không hợp lệ')
    dates = [entry['date'] for entry in calendar['holidays']]
    if len(dates) != len(set(dates)) or any(date.fromisoformat(d).year != year for d in dates):
        raise ValueError('Ngày lễ trùng hoặc không thuộc năm cấu hình')
    policy = cfg['payroll_2026_policy']
    # This calendar is authoritative, including when a saved profile had an empty list.
    policy['holiday_dates'] = sorted(dates)
    policy['night_pay_enabled'] = calendar['night_pay_enabled']
    policy['holiday_calendar'] = calendar
    policy['version'] = policy['version'].split('|CALENDAR:')[0] + '|CALENDAR:' + calendar['version']
    return cfg
