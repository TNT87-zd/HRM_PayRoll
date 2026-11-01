#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_cafe_hr_data.py
========================
Sinh bộ dữ liệu MÔ PHỎNG cho đồ án HRM_Payroll (chấm công khuôn mặt + tính lương) của chuỗi cafe Đà Nẵng.

Điểm quan trọng: MỌI bảng đều sinh từ MỘT mô phỏng duy nhất nên khớp nhau
  nhân viên -> lịch ca -> lượt quét mặt (events) -> bảng công ngày (daily) -> bảng lương (payroll)
  và khớp với hệ thống: mã thiết bị CNxx-TB01, ngưỡng mặt 0.55, liveness 0.85, geofence 50 m, grace 5 phút.

Dùng qua build_data_folder.py:  python data/scripts/build_data_folder.py
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ CẤU HÌNH
CFG = dict(
    seed=42, start="2024-10-01", months=24, chain_name="Cafe 5TN", n_real_members=5,
    face=dict(mean=0.72, sd=0.08, emp_shift_sd=0.04, threshold=0.55,        # độ giống khuôn mặt
              live_mean=0.93, live_sd=0.04, live_threshold=0.85,            # liveness
              qr_fallback_rate=0.01, geofence_m=50.0),
    att=dict(grace_min=5, forgot_checkout_rate=0.015, absent_base=0.008, std_days=26),
    anomaly=dict(day_rate=0.07, risky_day_rate=0.35, risky_emp_share=0.08),
    turnover=dict(monthly_pt=0.045, monthly_ft=0.018),
    pay=dict(meal_per_day=30000, meal_tax_exempt=730000, manager_allowance=500000,
             bonus_ft=300000, bonus_pt=150000, late_per_min=1000,
             ot_mult=dict(normal=1.5, dayoff=2.0, holiday=3.0),
             ins_rate=0.105, er_ins_rate=0.215, personal_deduction=11_000_000, dependent_deduction=4_400_000),
)
# Thuế TNCN lũy tiến từng phần 7 bậc (giả định theo plan.md): (trần bậc, thuế suất)
PIT_BRACKETS = [(5e6, .05), (10e6, .10), (18e6, .15), (32e6, .20), (52e6, .25), (80e6, .30), (float("inf"), .35)]

BRANCHES = pd.DataFrame([
    ("CN01", "Chi nhánh Hải Châu", "Hải Châu", 16.0471, 108.2208, 1.00, 32),
    ("CN02", "Chi nhánh Thanh Khê", "Thanh Khê", 16.0680, 108.1900, 0.85, 28),
    ("CN03", "Chi nhánh Sơn Trà", "Sơn Trà", 16.0720, 108.2400, 1.20, 40),
    ("CN04", "Chi nhánh Ngũ Hành Sơn", "Ngũ Hành Sơn", 16.0050, 108.2600, 0.70, 24),
], columns=["branch_id", "branch_name", "district", "lat", "lon", "demand_factor", "seats"])

DEVICES = pd.DataFrame([(f"{b}-TB01", b, f"Máy chấm công cửa chính {b}", f"192.168.{i + 1}.10")
                        for i, b in enumerate(BRANCHES.branch_id)],
                       columns=["device_id", "branch_id", "device_name", "ip_address"])

SHIFTS = pd.DataFrame([
    ("CA_SANG", "Ca sáng", "FT", "06:30", "14:30", 8.0),
    ("CA_CHIEU", "Ca chiều", "FT", "14:30", "22:30", 8.0),
    ("HANH_CHINH", "Hành chính", "FT", "08:00", "17:00", 8.0),   # nghỉ trưa 1h không tính lương
    ("PT_SANG", "PT sáng", "PT", "06:30", "12:00", 5.5),
    ("PT_CHIEU", "PT chiều", "PT", "12:00", "17:30", 5.5),
    ("PT_TOI", "PT tối", "PT", "17:30", "22:30", 5.0),
], columns=["shift_id", "shift_name", "contract_type", "start_time", "end_time", "paid_hours"])
_SH = {r.shift_id: (r.start_time, r.end_time, float(r.paid_hours)) for r in SHIFTS.itertuples()}

# 7 vị trí mỗi chi nhánh (role, hợp đồng, ca chính). NV0001..NV0005 = 5 thành viên nhóm (khuôn mặt thật, ở CN01)
SLOTS = [("quan_ly", "FT", "HANH_CHINH"), ("pha_che", "FT", "CA_SANG"), ("pha_che", "FT", "CA_CHIEU"),
         ("thu_ngan", "FT", "CA_CHIEU"), ("phuc_vu", "PT", "PT_SANG"), ("phuc_vu", "PT", "PT_CHIEU"),
         ("phuc_vu", "PT", "PT_TOI")]
ROLE_WAGE = {"quan_ly": 13_500_000, "pha_che": 9_500_000, "thu_ngan": 8_300_000}
PT_RATE = 29_000
# TODO: sửa lại thành họ tên thật của 5 thành viên (NV0001..NV0005)
REAL_NAMES = ["Nguyễn Văn Nhẫn", "Trương Nhật Trường", "Mai Nam Quốc", "Nguyễn Hữu Tâm", "Mai Văn Chung"]
HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ"]
DEM = ["Văn", "Hữu", "Minh", "Quốc", "Thị", "Ngọc", "Thu", "Phương", "Khánh", "Bảo"]
TEN = ["An", "Anh", "Bình", "Chi", "Dung", "Giang", "Hà", "Hải", "Hiếu", "Hoa", "Hùng", "Khoa", "Lan", "Linh",
       "Long", "My", "Nga", "Phát", "Quân", "Sơn", "Thảo", "Trang", "Vy", "Yến"]
REASONS = ["Chuyển việc khác", "Nghỉ để đi học", "Chuyển nơi ở", "Lương chưa phù hợp", "Lý do cá nhân"]

# Ngày lễ mô phỏng gần theo lịch Việt Nam (có thể chỉnh)
HOLIDAYS = [
    ("2025-01-01", "Tết Dương lịch"), ("2025-01-28", "Tết Nguyên đán"), ("2025-01-29", "Tết Nguyên đán"),
    ("2025-01-30", "Tết Nguyên đán"), ("2025-01-31", "Tết Nguyên đán"), ("2025-02-01", "Tết Nguyên đán"),
    ("2025-04-07", "Giỗ Tổ Hùng Vương"), ("2025-04-30", "Giải phóng miền Nam"), ("2025-05-01", "Quốc tế Lao động"),
    ("2025-09-01", "Quốc khánh"), ("2025-09-02", "Quốc khánh"),
    ("2026-01-01", "Tết Dương lịch"), ("2026-02-16", "Tết Nguyên đán"), ("2026-02-17", "Tết Nguyên đán"),
    ("2026-02-18", "Tết Nguyên đán"), ("2026-02-19", "Tết Nguyên đán"), ("2026-02-20", "Tết Nguyên đán"),
    ("2026-04-27", "Giỗ Tổ Hùng Vương"), ("2026-04-30", "Giải phóng miền Nam"), ("2026-05-01", "Quốc tế Lao động"),
    ("2026-09-01", "Quốc khánh"), ("2026-09-02", "Quốc khánh"),
]
RAIN_BASE = {1: .15, 2: .10, 3: .08, 4: .10, 5: .18, 6: .14, 7: .12, 8: .16, 9: .35, 10: .55, 11: .50, 12: .28}
HOUR_W = {7: .9, 8: 1.3, 9: 1.1, 10: .8, 11: .8, 12: 1.0, 13: .9, 14: .8, 15: .9, 16: 1.0, 17: 1.1, 18: 1.3,
          19: 1.2, 20: .9, 21: .6}
RISK_BASE = dict(gps_mismatch=.90, low_sim_borderline=.55, burst_duplicate=.60, spoof_suspect=.95, off_hours=.80)


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def pit_tax(taxable):
    tax, lo = 0.0, 0.0
    for hi, rate in PIT_BRACKETS:
        if taxable > lo:
            tax += (min(taxable, hi) - lo) * rate
        lo = hi
    return tax


# ------------------------------------------------------------------ LỊCH, THỜI TIẾT
def make_dates(cfg):
    s = pd.Timestamp(cfg["start"])
    return pd.date_range(s, s + pd.DateOffset(months=cfg["months"]) - pd.Timedelta(days=1), freq="D")


def make_weather(rng, dates):
    out, prev = [], 0
    for d in dates:
        prev = int(rng.random() < min(0.9, RAIN_BASE[d.month] * (0.7 + 0.6 * prev)))
        out.append(prev)
    return pd.DataFrame({"date": dates, "is_rain": out})


def make_holidays(dates):
    h = pd.DataFrame(HOLIDAYS, columns=["date", "holiday_name"])
    h["date"] = pd.to_datetime(h["date"])
    h = h[(h.date >= dates[0]) & (h.date <= dates[-1])].reset_index(drop=True)
    h["is_closed_for_business"] = False
    return h


# ------------------------------------------------------------------ NHÂN SỰ (có luân chuyển nhân sự)
def _new_person(rng, idx, slot, branch, hire, real, used):
    role, ctype, shift = slot
    ft = ctype == "FT"
    wf = 1.0 if real else float(np.clip(rng.normal(1, 0.08), 0.8, 1.25))
    if real:
        name = REAL_NAMES[idx - 1]
    else:
        while True:
            name = f"{rng.choice(HO)} {rng.choice(DEM)} {rng.choice(TEN)}"
            if name not in used:
                break
    used.add(name)
    return dict(
        employee_id=f"NV{idx:04d}", full_name=name, branch_id=branch, role=role, contract_type=ctype,
        primary_shift=shift, base_salary=float(round(ROLE_WAGE[role] * wf, -3)) if ft else 0.0,
        hourly_rate=0.0 if ft else float(round(PT_RATE * wf, -2)), hire_date=hire, termination_date=None,
        termination_reason=None, is_real_face=real, is_student=(not ft) and bool(rng.random() < 0.7),
        dependents=int(rng.choice([0, 0, 1, 2])) if ft else 0,
        # đặc tính ẩn (không đưa vào bảng employees, chỉ lưu _internal)
        unrest=0.0 if real else float(rng.normal(0, 1)), wage_f=wf,
        face_shift=float(rng.normal(0, CFG["face"]["emp_shift_sd"])),
        risky=(not real) and bool(rng.random() < CFG["anomaly"]["risky_emp_share"]),
        weekly_off=int(rng.integers(0, 7)), pt_days=sorted(rng.choice(7, 4, replace=False).tolist()),
    )


def simulate_people(rng, dates):
    start, end = dates[0], dates[-1]
    people, cur, used, idx = [], {}, set(), 0
    for b in BRANCHES.branch_id:
        for si, slot in enumerate(SLOTS):
            idx += 1
            p = _new_person(rng, idx, slot, b, start - pd.Timedelta(days=int(rng.integers(40, 700))),
                            idx <= CFG["n_real_members"], used)
            p["slot"] = (b, si)
            people.append(p)
            cur[(b, si)] = p
    for m in pd.period_range(start, end, freq="M"):
        ms, me = m.start_time, min(m.end_time.normalize(), end)
        for key, p in list(cur.items()):
            if p["is_real_face"] or p["termination_date"] is not None or p["hire_date"] > me - pd.Timedelta(days=30):
                continue
            ft = p["contract_type"] == "FT"
            hz = CFG["turnover"]["monthly_ft" if ft else "monthly_pt"] * math.exp(0.7 * p["unrest"]) \
                * math.exp(-1.5 * (p["wage_f"] - 1)) * (1.8 if (ms - p["hire_date"]).days < 90 else 1.0)
            if rng.random() < hz:
                lo = max(ms, p["hire_date"] + pd.Timedelta(days=30))
                term = lo + pd.Timedelta(days=int(rng.integers(0, max(1, (me - lo).days + 1))))
                p["termination_date"], p["termination_reason"] = term, str(rng.choice(REASONS))
                nh = term + pd.Timedelta(days=int(rng.integers(5, 21)))
                if nh <= end:
                    idx += 1
                    q = _new_person(rng, idx, SLOTS[key[1]], key[0], nh, False, used)
                    q["slot"] = key
                    people.append(q)
                    cur[key] = q
    return people


def make_leaves(rng, people, dates):
    rows, leave_map = [], {}
    for p in people:
        a, z = max(p["hire_date"], dates[0]), min(p["termination_date"] or dates[-1], dates[-1])
        if a > z:
            continue
        ft = p["contract_type"] == "FT"
        for m in pd.period_range(a, z, freq="M"):
            if rng.random() >= (0.35 if ft else 0.12):
                continue
            lt = str(rng.choice(["annual", "sick", "unpaid"], p=[.6, .3, .1] if ft else [0, .2, .8]))
            lo, hi = max(a, m.start_time), min(z, m.end_time.normalize())
            s = lo + pd.Timedelta(days=int(rng.integers(0, (hi - lo).days + 1)))
            e = min(s + pd.Timedelta(days=int(rng.integers(0, 3 if lt != "sick" else 2))), z)
            sub = s if lt == "sick" else s - pd.Timedelta(days=int(rng.integers(3, 15)))
            ok = rng.random() < 0.88
            rows.append(dict(employee_id=p["employee_id"], branch_id=p["branch_id"], leave_type=lt, start_date=s,
                             end_date=e, days_requested=(e - s).days + 1, submitted_date=sub,
                             status="approved" if ok else "rejected"))
            if ok:
                for d in pd.date_range(s, e):
                    leave_map[(p["employee_id"], d)] = "leave_" + lt
    df = pd.DataFrame(rows).sort_values("start_date").reset_index(drop=True)
    df.insert(0, "leave_id", [f"LV{i + 1:05d}" for i in range(len(df))])
    return df, leave_map


# ------------------------------------------------------------------ RULE: 1 ngày công
def calc_day(ps, pe, ci, co, paid_h, day_type):
    """Quy tắc tính công (attendance_engine nên cho kết quả giống hàm này)."""
    g = CFG["att"]["grace_min"]
    m_late = (ci - ps).total_seconds() / 60
    late = int(m_late) if m_late > g else 0
    m_early = (pe - co).total_seconds() / 60
    early = int(m_early) if m_early > g else 0
    brk = max(0.0, (pe - ps).total_seconds() / 3600 - paid_h)          # nghỉ trưa không tính
    worked = max(0.0, (co - max(ci, ps)).total_seconds() / 3600 - brk)
    if day_type == "normal":
        over = (co - pe).total_seconds() / 60
        ot = math.floor(over / 30) * 0.5 if over >= 30 else 0.0          # OT làm tròn xuống mỗi 30 phút
        regular = max(0.0, worked - ot)
    else:                                                                # ngày nghỉ / lễ: toàn bộ giờ làm tính hệ số cao
        ot, regular = worked, 0.0
    return late, early, round(worked, 2), round(regular, 2), round(ot, 2)


# ------------------------------------------------------------------ SỰ KIỆN QUÉT MẶT
def _gps(rng, b, offset_m=None):
    if offset_m is None:
        lat, lon = b.lat + rng.normal(0, 4e-5), b.lon + rng.normal(0, 4e-5)
    else:
        ang = rng.uniform(0, 2 * math.pi)
        lat = b.lat + offset_m * math.cos(ang) / 111320
        lon = b.lon + offset_m * math.sin(ang) / (111320 * math.cos(math.radians(b.lat)))
    return round(lat, 6), round(lon, 6), round(haversine_m(lat, lon, b.lat, b.lon), 1)


def _ev(rng, p, b, ts, etype, method, sim, live, status, atype="normal", offset_m=None):
    lat, lon, dist = _gps(rng, b, offset_m)
    return dict(employee_id=p["employee_id"], branch_id=b.branch_id, device_id=f"{b.branch_id}-TB01", ts=ts,
                event_type=etype, method=method, similarity=sim, liveness_score=live, gps_lat=lat, gps_lon=lon,
                distance_m=dist, status_code=status, _atype=atype)


def _sample_face(rng, p):
    f = CFG["face"]
    sim = float(np.clip(rng.normal(f["mean"] + p["face_shift"], f["sd"]), .30, .99))
    live = float(np.clip(rng.normal(f["live_mean"], f["live_sd"]), .50, .999))
    return round(sim, 3), round(live, 3)


def scan(rng, out, p, b, ts, etype):
    """Sinh các lần quét lỗi (sim thấp 401 / liveness thấp 422) rồi 1 lần thành công; trả về dòng thành công."""
    f, fails = CFG["face"], []
    if rng.random() >= f["qr_fallback_rate"]:
        for k in range(3):
            sim, live = _sample_face(rng, p)
            if sim >= f["threshold"] and live >= f["live_threshold"]:
                for j, row in enumerate(fails):
                    row["ts"] = ts - pd.Timedelta(seconds=12 * (len(fails) - j) + int(rng.integers(0, 5)))
                out.extend(fails)
                ok = _ev(rng, p, b, ts, etype, "FACE", sim, live, 200)
                out.append(ok)
                return ok
            fails.append(_ev(rng, p, b, ts, etype, "FACE", sim, live, 401 if sim < f["threshold"] else 422))
    for j, row in enumerate(fails):                                      # 3 lần lỗi hoặc camera hỏng -> QR
        row["ts"] = ts - pd.Timedelta(seconds=12 * (len(fails) - j) + int(rng.integers(0, 5)))
    out.extend(fails)
    ok = _ev(rng, p, b, ts, etype, "QR", np.nan, np.nan, 200)
    out.append(ok)
    return ok


def inject_anomaly(rng, out, p, b, ok_in, ok_out, d):
    """Gắn 1 bất thường vào ngày công (không làm sai bảng công)."""
    kind = str(rng.choice(list(RISK_BASE), p=[.25, .25, .20, .15, .15]))
    if kind == "gps_mismatch":          # quét xa chi nhánh -> bị geofence từ chối (403)
        s, l = _sample_face(rng, p)
        out.append(_ev(rng, p, b, ok_in["ts"] - pd.Timedelta(seconds=int(rng.integers(20, 90))), "IN", "FACE",
                       s, l, 403, kind, offset_m=float(rng.uniform(80, 350))))
    elif kind == "spoof_suspect":       # ảnh/video giả: giống mặt nhưng liveness thấp -> bị chặn (422)
        out.append(_ev(rng, p, b, ok_in["ts"] - pd.Timedelta(seconds=int(rng.integers(20, 90))), "IN", "FACE",
                       round(float(rng.uniform(.62, .90)), 3), round(float(rng.uniform(.15, .60)), 3), 422, kind))
    elif kind == "low_sim_borderline" and ok_in["method"] == "FACE":   # nghi chấm hộ: giống sát ngưỡng
        ok_in["similarity"], ok_in["_atype"] = round(float(rng.uniform(.55, .61)), 3), kind
    elif kind == "burst_duplicate":     # quét lặp liên tiếp trong vài giây
        base = ok_in if rng.random() < .5 or ok_out is None else ok_out
        s, l = _sample_face(rng, p)
        out.append(_ev(rng, p, b, base["ts"] + pd.Timedelta(seconds=int(rng.integers(3, 45))), base["event_type"],
                       "FACE", s, l, 200, kind))
    elif kind == "off_hours":           # quét lúc nửa đêm / rạng sáng
        s, l = _sample_face(rng, p)
        t = d + pd.Timedelta(minutes=int(rng.integers(30, 270)))
        out.append(_ev(rng, p, b, t, "IN", "FACE", round(float(rng.uniform(.56, .70)), 3), l, 200, kind))


# ------------------------------------------------------------------ MÔ PHỎNG CHẤM CÔNG
def simulate_attendance(rng, people, dates, hol, leave_map):
    bmap = {r.branch_id: r for r in BRANCHES.itertuples()}
    A, E = [], []
    cfg_a, cfg_n = CFG["att"], CFG["anomaly"]
    for p in people:
        a, z = max(p["hire_date"], dates[0]), min(p["termination_date"] or dates[-1], dates[-1])
        if a > z:
            continue
        ft, b = p["contract_type"] == "FT", bmap[p["branch_id"]]
        s_t, e_t, paid_h = _SH[p["primary_shift"]]
        p_late = 1 / (1 + math.exp(2.6 - 0.5 * p["unrest"]))
        p_abs = cfg_a["absent_base"] + 0.012 * max(0.0, p["unrest"])
        p_anom = cfg_n["risky_day_rate"] if p["risky"] else cfg_n["day_rate"]
        for d in pd.date_range(a, z):
            wd, is_hol = d.weekday(), d in hol
            sched = (wd != p["weekly_off"]) if ft else (wd in p["pt_days"])
            status, work, dtype = None, False, "normal"
            if is_hol:
                if sched:
                    if rng.random() < 0.5:
                        work, dtype = True, "holiday"
                    elif ft:
                        status = "holiday"
            elif sched:
                lv = leave_map.get((p["employee_id"], d))
                if lv:
                    status = lv
                elif rng.random() < p_abs:
                    status = "absent"
                else:
                    work = True
            elif ft and rng.random() < 0.04 and (p["employee_id"], d) not in leave_map:
                work, dtype = True, "dayoff"
            if not work and status is None:
                continue
            ds = f"{d:%Y-%m-%d}"
            ps, pe = pd.Timestamp(f"{ds} {s_t}"), pd.Timestamp(f"{ds} {e_t}")
            row = dict(employee_id=p["employee_id"], branch_id=p["branch_id"], work_date=d, shift_id=p["primary_shift"],
                       planned_start=ps, planned_end=pe, status=status or "present", check_in_ts=pd.NaT,
                       check_out_ts=pd.NaT, late_minutes=0, early_leave_minutes=0, worked_hours=0.0,
                       regular_hours=0.0, ot_hours=0.0, day_type=dtype, is_holiday=int(is_hol), is_manual_fix=0)
            if work:
                if rng.random() < p_late:
                    off_in = 6 + min(80, rng.exponential(7))
                elif rng.random() < 0.15:
                    off_in = rng.uniform(0, 5)                           # trong thời gian ân hạn
                else:
                    off_in = -rng.uniform(0, 18)
                u = rng.random()
                off_out = (rng.uniform(30, 150) if u < 0.10 else -(6 + rng.exponential(8)) if u < 0.14
                           else rng.uniform(-4, 8))
                ci = ps + pd.Timedelta(seconds=int(off_in * 60))
                co = pe + pd.Timedelta(seconds=int(off_out * 60))
                okin = scan(rng, E, p, b, ci, "IN")
                if rng.random() < cfg_a["forgot_checkout_rate"]:         # quên chấm ra -> quản lý bổ sung
                    co, row["is_manual_fix"] = pe, 1
                    okout = _ev(rng, p, b, co, "OUT", "MANUAL", np.nan, np.nan, 200)
                    okout.update(gps_lat=np.nan, gps_lon=np.nan, distance_m=np.nan)
                    E.append(okout)
                else:
                    okout = scan(rng, E, p, b, co, "OUT")
                late, early, wk, rg, ot = calc_day(ps, pe, ci, co, paid_h, dtype)
                row.update(check_in_ts=ci, check_out_ts=co, late_minutes=late, early_leave_minutes=early,
                           worked_hours=wk, regular_hours=rg, ot_hours=ot)
                if rng.random() < p_anom:
                    inject_anomaly(rng, E, p, b, okin, okout, d)
            A.append(row)
    return pd.DataFrame(A), pd.DataFrame(E)


# ------------------------------------------------------------------ BẢNG LƯƠNG (đáp án đối soát cho payroll_engine)
def compute_payroll(p, month, day):
    P, std = CFG["pay"], CFG["att"]["std_days"]
    ft = p["contract_type"] == "FT"
    pres = day[day.status == "present"]
    npres = pres[pres.day_type == "normal"]
    paid_leave = int(day.status.isin(["leave_annual", "leave_sick"]).sum())
    hol_days, unpaid = int((day.status == "holiday").sum()), int((day.status == "leave_unpaid").sum())
    absent = int((day.status == "absent").sum())
    paid_days = min(std, len(npres) + paid_leave + hol_days)
    mult = pres.day_type.map(P["ot_mult"]).fillna(1.5)
    ot_normal, ot_off, ot_hol = (float(pres.loc[pres.day_type == k, "ot_hours"].sum()) for k in ("normal", "dayoff", "holiday"))
    hourly_eq = p["base_salary"] / (std * 8) if ft else p["hourly_rate"]
    base_pay = p["base_salary"] / std * paid_days if ft else p["hourly_rate"] * float(pres.regular_hours.sum())
    ot_pay = hourly_eq * float((pres.ot_hours * mult).sum())
    meal = P["meal_per_day"] * len(pres)
    other = P["manager_allowance"] * min(1.0, paid_days / std) if p["role"] == "quan_ly" else 0.0
    late_days = int((day.late_minutes > 0).sum())
    clean = late_days == 0 and absent == 0 and unpaid == 0
    bonus = (P["bonus_ft"] if (ft and len(day) >= 20 and clean) else P["bonus_pt"] if (not ft and len(day) >= 8 and clean) else 0)
    late_ded = P["late_per_min"] * int(day.late_minutes.sum())
    gross = base_pay + ot_pay + meal + other + bonus - late_ded
    ins = P["ins_rate"] * p["base_salary"] if (ft and paid_days + len(pres[pres.day_type != "normal"]) >= 14) else 0.0
    taxable = max(0.0, gross - min(meal, P["meal_tax_exempt"]) - ins - P["personal_deduction"]
                  - p["dependents"] * P["dependent_deduction"])
    pit = pit_tax(taxable)
    r = lambda x: int(round(x))
    return dict(
        payroll_id=f"PR-{p['employee_id']}-{month.replace('-', '')}", employee_id=p["employee_id"], month=month,
        branch_id=p["branch_id"], contract_type=p["contract_type"], base_salary_vnd=r(p["base_salary"]),
        hourly_rate_vnd=r(p["hourly_rate"]), std_days=std, work_days=len(pres), paid_leave_days=paid_leave,
        holiday_days=hol_days, unpaid_leave_days=unpaid, absent_days=absent, late_days=late_days,
        actual_work_hours=round(float(pres.worked_hours.sum()), 2), regular_hours=round(float(pres.regular_hours.sum()), 2),
        ot_hours_normal=round(ot_normal, 2), ot_hours_dayoff=round(ot_off, 2), ot_hours_holiday=round(ot_hol, 2),
        base_pay_vnd=r(base_pay), ot_pay_vnd=r(ot_pay), allowance_meal_vnd=r(meal), allowance_other_vnd=r(other),
        bonus_attendance_vnd=r(bonus), late_deduction_vnd=r(late_ded), gross_income_vnd=r(gross),
        employee_insurance_vnd=r(ins), dependents=p["dependents"], taxable_income_vnd=r(taxable), pit_vnd=r(pit),
        net_pay_vnd=r(gross) - r(ins) - r(pit), employer_insurance_vnd=r(P["er_ins_rate"] * p["base_salary"]) if ins > 0 else 0)


# ------------------------------------------------------------------ DOANH THU THEO GIỜ
def simulate_sales(rng, daily, dates, weather, hol):
    rain = dict(zip(weather.date, weather.is_rain))
    pres = daily[daily.status == "present"]
    staff = {}
    for r in pres.itertuples():                                           # số người thực có mặt từng giờ (lấy từ chấm công)
        for h in range(7, 22):
            mid = r.work_date + pd.Timedelta(hours=h, minutes=30)
            if r.check_in_ts <= mid <= r.check_out_ts:
                k = (r.branch_id, r.work_date, h)
                staff[k] = staff.get(k, 0) + 1
    rows = []
    for b in BRANCHES.itertuples():
        for d in dates:
            dow = 1.25 if d.weekday() >= 5 else 1.0
            for h in range(7, 22):
                lam = 17 * b.demand_factor * HOUR_W[h] * dow * (1.15 if d in hol else 1) * (0.9 if rain[d] else 1)
                o = int(rng.poisson(lam * float(rng.lognormal(0, 0.12))))
                rows.append(dict(branch_id=b.branch_id, date=d, hour=h, orders=o,
                                 revenue_vnd=int(round(o * rng.normal(55000, 8000), -3)),
                                 present_staff=staff.get((b.branch_id, d, h), 0), is_rain=int(rain[d])))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ TỔNG HỢP
def build_all(seed=None, months=None):
    """Trả về dict: tables (đã đúng chuẩn, dùng làm 'sự thật'), internal (đặc tính ẩn)."""
    if seed is not None:
        CFG["seed"] = seed
    if months is not None:
        CFG["months"] = months
    rng = np.random.default_rng(CFG["seed"])
    dates = make_dates(CFG)
    weather, holidays = make_weather(rng, dates), make_holidays(dates)
    hol = set(holidays.date)
    people = simulate_people(rng, dates)
    leaves, leave_map = make_leaves(rng, people, dates)
    daily, ev = simulate_attendance(rng, people, dates, hol, leave_map)
    daily = daily.sort_values(["work_date", "employee_id"]).reset_index(drop=True)

    ev = ev.sort_values(["ts", "employee_id"]).reset_index(drop=True)
    ev.insert(0, "event_id", [f"EV{i + 1:06d}" for i in range(len(ev))])
    is_a = ev._atype != "normal"
    labels = pd.DataFrame({
        "event_id": ev.event_id, "is_anomaly": is_a.astype(int), "anomaly_type": ev._atype,
        "risk_score": np.where(is_a, ev._atype.map(RISK_BASE).fillna(0) + rng.normal(0, 0.04, len(ev)),
                               rng.uniform(0.01, 0.12, len(ev))).clip(0, 1).round(2)})
    ev = ev.drop(columns=["_atype", "branch_id"])

    emp_cols = ["employee_id", "full_name", "branch_id", "role", "contract_type", "primary_shift", "base_salary",
                "hourly_rate", "hire_date", "termination_date", "termination_reason", "is_real_face", "is_student",
                "dependents"]
    emps = pd.DataFrame(people)[emp_cols].sort_values("employee_id").reset_index(drop=True)
    emps["is_real_face"] = emps.is_real_face.astype(bool)
    internal = pd.DataFrame(people)[["employee_id", "unrest", "wage_f", "face_shift", "risky", "weekly_off"]]

    daily["_m"] = daily.work_date.dt.strftime("%Y-%m")
    pmap = {p["employee_id"]: p for p in people}
    pay = [compute_payroll(pmap[e], m, g.drop(columns="_m")) for (e, m), g in daily.groupby(["employee_id", "_m"])]
    daily = daily.drop(columns="_m")
    payroll = pd.DataFrame(pay).sort_values(["month", "employee_id"]).reset_index(drop=True)
    sales = simulate_sales(rng, daily, dates, weather, hol)

    tables = dict(branches=BRANCHES, devices=DEVICES, shifts=SHIFTS, holidays=holidays, weather_daily=weather,
                  employees=emps, leave_requests=leaves, attendance_events=ev, attendance_daily=daily,
                  payroll=payroll, branch_sales_hourly=sales, labels_anomaly=labels)
    return dict(tables=tables, internal=dict(employee_latent_traits=internal))


if __name__ == "__main__":
    T = build_all()
    for k, v in T["tables"].items():
        print(f"{k:22s} {len(v):>7,} dòng")