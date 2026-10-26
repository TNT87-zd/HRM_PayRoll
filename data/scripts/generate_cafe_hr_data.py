#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_cafe_hr_data.py
========================
Sinh bộ dữ liệu MÔ PHỎNG cho đồ án "Hệ thống quản lý nhân sự - tính lương - chấm công tự động"
theo mô hình một chuỗi cafe nhiều chi nhánh tại Đà Nẵng (chuỗi và tên người đều là GIẢ ĐỊNH).

Chạy:   python generate_cafe_hr_data.py --out ./cafe_hr_dataset
Tái lập: cùng seed trong CFG => cùng dữ liệu.

Luồng:  nhân sự (thay thế theo ô vị trí) -> lịch ca + nghỉ phép -> chấm công (lượt quét khuôn mặt/QR)
        -> bảng công ngày -> bảng lương tháng -> chèn bất thường CÓ NHÃN vào lượt quét
        -> bảng đặc trưng cho từng model (bất thường, nghỉ việc, nhu cầu nhân sự theo giờ).

Lưu ý quan trọng: mọi tham số lương/bảo hiểm/thuế ở CFG là GIẢ ĐỊNH để mô phỏng,
cần đối chiếu quy định hiện hành trước khi dùng cho mục đích khác.
"""
import argparse
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------------------------
# 1. CẤU HÌNH (đổi tham số ở đây, không cần sửa code bên dưới)
# ----------------------------------------------------------------------------------------------
CFG = {
    "seed": 42,
    "start": "2024-10-01",
    "end": "2026-09-30",
    "chain_name": "Cafe Biển Xanh (tên giả định)",
    "n_real_members": 5,
    "face": dict(genuine_mean=0.74, genuine_sd=0.06, accept_threshold=0.55, emp_shift_sd=0.03,
                 liveness_alpha=30, liveness_beta=3, qr_fallback_rate=0.08, reject_rate=0.025),
    "attendance": dict(grace_min=5, forgot_checkout_rate=0.010, absent_rate=0.004,
                       ft_ot_rate=0.22, pt_ot_rate=0.10, extra_shift_rate=0.06, std_days=26),
    "turnover": dict(base_pt=0.032, base_ft=0.016, vacancy_days=[7, 30]),
    "anomaly": dict(rate=0.009, risky_emp_share=0.08, risky_mult=6.0,
                    type_probs=dict(gps_mismatch=0.22, off_hours=0.12, spoof_attempt=0.15,
                                    low_similarity_manual=0.15, burst_duplicate=0.20, long_session=0.16)),
    "pay": dict(meal_per_day=30000, manager_allowance=500000, bonus_attendance=300000,
                bonus_sales_ft=200000, bonus_sales_pt=100000, bonus_sales_ratio=1.05,
                employee_ins_rate=0.105, employer_ins_rate=0.215,
                ot_weekday=1.5, ot_rest_day=2.0, ot_holiday=3.0,
                deduction_before_2026=11_000_000, deduction_from_2026=15_500_000,
                new_pit_from="2026-07"),
    "demand": dict(base_orders_per_hour=12, avg_order_value=48000, orders_per_staff_hour=6),
    "splits": dict(
        event_train_end="2025-12-31", event_val_end="2026-05-31",
        attr_train_last_snapshot="2025-10-31", attr_val_first="2025-12-31", attr_val_last="2026-02-28",
        attr_test_first="2026-04-30", horizon_days=60),
}

OFF_P = np.array([.20, .20, .20, .20, .10, .05, .05])       # xác suất chọn ngày nghỉ tuần (T2..CN) của FT
STUDENT_W = np.array([1, 1, 1, 1, 1.2, 2.2, 2.4])           # sinh viên PT thích làm cuối tuần
LEAVE_STATUS = {"phep_nam": "leave_annual", "om": "leave_sick", "viec_rieng_khong_luong": "leave_unpaid"}

SHIFTS = pd.DataFrame([
    ("CA_SANG", "Ca sáng", "FT", "06:30", "14:30", 8.0),
    ("CA_CHIEU", "Ca chiều", "FT", "14:30", "22:30", 8.0),
    ("HANH_CHINH", "Hành chính (quản lý)", "FT", "08:00", "17:00", 8.0),
    ("PT_SANG", "Bán thời gian - sáng", "PT", "06:30", "12:00", 5.5),
    ("PT_CHIEU", "Bán thời gian - chiều", "PT", "12:00", "17:30", 5.5),
    ("PT_TOI", "Bán thời gian - tối", "PT", "17:30", "22:30", 5.0),
], columns=["shift_id", "shift_name", "contract_type", "start_time", "end_time", "paid_hours"])
SHIFTS["start_min"] = SHIFTS.start_time.map(lambda s: int(s[:2]) * 60 + int(s[3:]))
SHIFTS["end_min"] = SHIFTS.end_time.map(lambda s: int(s[:2]) * 60 + int(s[3:]))
SH = SHIFTS.set_index("shift_id")
FT_SHIFTS, PT_SHIFTS = ["CA_SANG", "CA_CHIEU"], ["PT_SANG", "PT_CHIEU", "PT_TOI"]

BRANCHES = pd.DataFrame([
    ("CN01", "Chi nhánh Hải Châu", "Hải Châu", 16.0471, 108.2208, 1.00, 32),
    ("CN02", "Chi nhánh Thanh Khê", "Thanh Khê", 16.0680, 108.1900, 0.85, 28),
    ("CN03", "Chi nhánh Sơn Trà", "Sơn Trà", 16.0720, 108.2400, 1.20, 40),
    ("CN04", "Chi nhánh Ngũ Hành Sơn", "Ngũ Hành Sơn", 16.0050, 108.2600, 0.70, 24),
], columns=["branch_id", "branch_name", "district", "lat", "lon", "demand_factor", "seats"])
BRANCHES["open_time"], BRANCHES["close_time"] = "06:30", "22:30"

SLOT_TEMPLATE = [  # (role, contract, ca chính, số lượng) -> 13 vị trí / chi nhánh
    ("quan_ly", "FT", "HANH_CHINH", 1), ("pha_che", "FT", "CA_SANG", 2), ("pha_che", "FT", "CA_CHIEU", 1),
    ("thu_ngan", "FT", "CA_SANG", 1), ("thu_ngan", "FT", "CA_CHIEU", 1),
    ("phuc_vu", "PT", None, 4), ("pha_che", "PT", None, 2), ("thu_ngan", "PT", None, 1)]
REAL_SLOTS_CN01 = {0, 1, 4, 6, 10}   # 5 thành viên nhóm: quản lý, pha chế FT, thu ngân FT, phục vụ PT, pha chế PT

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
DEM_NAM = ["Văn", "Hữu", "Đức", "Minh", "Quốc", "Thanh", "Gia"]
DEM_NU = ["Thị", "Ngọc", "Thu", "Phương", "Khánh", "Bảo", "Mỹ"]
TEN_NAM = ["An", "Bình", "Cường", "Dũng", "Hải", "Hiếu", "Khoa", "Long", "Nam", "Phúc", "Quân", "Sơn", "Tâm", "Tuấn", "Việt"]
TEN_NU = ["Anh", "Chi", "Dung", "Giang", "Hà", "Hương", "Lan", "Linh", "My", "Ngân", "Nhi", "Thảo", "Trang", "Vy", "Yến"]


def tdelta(minutes):
    """phút (float) -> numpy timedelta64[ns]"""
    return (np.nan_to_num(np.asarray(minutes, dtype=float)) * 60e9).astype("int64").astype("timedelta64[ns]")


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2) - np.radians(lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


# ----------------------------------------------------------------------------------------------
# 2. LỊCH, NGÀY LỄ, THỜI TIẾT
# ----------------------------------------------------------------------------------------------
def make_holidays():
    rows = []

    def add(d, name, closed=False):
        rows.append((pd.Timestamp(d), name, closed))

    add("2025-01-01", "Tết Dương lịch")
    for d in pd.date_range("2025-01-28", "2025-02-01"):
        add(d, "Tết Nguyên đán 2025", True)
    add("2025-04-07", "Giỗ Tổ Hùng Vương 2025")
    add("2025-04-30", "Ngày Chiến thắng 30/4")
    add("2025-05-01", "Quốc tế Lao động 1/5")
    add("2025-09-01", "Quốc khánh 2/9 (ngày nghỉ liền kề)")
    add("2025-09-02", "Quốc khánh 2/9")
    add("2026-01-01", "Tết Dương lịch")
    for d in pd.date_range("2026-02-16", "2026-02-20"):
        add(d, "Tết Nguyên đán 2026 (Bính Ngọ)", True)
    add("2026-04-26", "Giỗ Tổ Hùng Vương 2026 (rơi vào Chủ nhật)")
    add("2026-04-27", "Nghỉ bù Giỗ Tổ 2026")
    add("2026-04-30", "Ngày Chiến thắng 30/4")
    add("2026-05-01", "Quốc tế Lao động 1/5")
    add("2026-09-01", "Quốc khánh 2/9 (ngày nghỉ liền kề, doanh nghiệp chọn 1/9)")
    add("2026-09-02", "Quốc khánh 2/9")
    df = pd.DataFrame(rows, columns=["date", "holiday_name", "is_closed_for_business"])
    df["note"] = "Ngày nghỉ lễ chính thức (mô phỏng); cần đối chiếu thông báo chính thức khi dùng thực tế"
    return df


def make_weather(rng, dates):
    p = {1: .20, 2: .20, 3: .10, 4: .10, 5: .12, 6: .10, 7: .08, 8: .10, 9: .30, 10: .38, 11: .40, 12: .32}
    pr = dates.month.map(p).values
    rain = (rng.random(len(dates)) < pr).astype(int)
    return pd.DataFrame({"date": dates, "is_rain": rain})


# ----------------------------------------------------------------------------------------------
# 3. NHÂN SỰ: thay thế người theo "ô vị trí" (slot) -> có nghỉ việc và tuyển mới
# ----------------------------------------------------------------------------------------------
def new_person(rng, slot, hire_off, real):
    ft = slot["contract_type"] == "FT"
    role = slot["role"]
    late_prone = bool(rng.random() < 0.15)
    is_student = bool(rng.random() < (0.03 if ft else 0.70))
    if ft:
        mean, sd = {"quan_ly": (12.5e6, 1.0e6), "pha_che": (8.2e6, 0.7e6),
                    "thu_ngan": (7.0e6, 0.5e6), "phuc_vu": (6.4e6, 0.4e6)}[role]
        base_salary = float(np.round(max(rng.normal(mean, sd), 6.0e6) / 1e5) * 1e5)
        hourly = np.nan
        primary = slot["primary_shift"]
    else:
        mean, sd = {"phuc_vu": (27e3, 1e3), "thu_ngan": (28.5e3, 1e3), "pha_che": (31e3, 1.5e3)}[role]
        hourly = float(np.round(max(rng.normal(mean, sd), 26e3) / 500) * 500)
        base_salary = np.nan
        pp = [.2, .35, .45] if is_student else [.4, .4, .2]
        primary = str(rng.choice(PT_SHIFTS, p=pp))
    return dict(
        slot_id=slot["slot_id"], branch_id=slot["branch_id"], role=role, contract_type=slot["contract_type"],
        primary_shift=primary, hire_off=int(hire_off), term_off=None, termination_reason=None,
        is_real=bool(real), is_student=is_student, late_prone=late_prone,
        high_ot=bool(rng.random() < (0.15 if ft else 0.08)),
        bias=float(rng.normal(4 if late_prone else -4.5, 4)),
        off_dow=int(rng.choice(7, p=OFF_P)) if ft else -1,
        risky=bool(rng.random() < CFG["anomaly"]["risky_emp_share"]),
        face_shift=float(rng.normal(0, CFG["face"]["emp_shift_sd"])),
        base_salary=base_salary, hourly_rate=hourly,
        birth_year=int(rng.integers(2002, 2008)) if is_student else int(rng.integers(1993, 2004)))


def hazard(e, d, month):
    t = CFG["turnover"]
    base = t["base_ft"] if e["contract_type"] == "FT" else t["base_pt"]
    tm = (d - e["hire_off"]) / 30.4
    z = 0.7 * e["late_prone"] + 0.5 * (tm < 6) - 0.3 * (tm > 24) + 0.5 * e["high_ot"]
    if e["is_student"] and month in (1, 5, 6, 12):
        z += 0.6                                  # sinh viên nghỉ nhiều mùa thi
    if month in (2, 3):
        z += 0.4                                  # nghỉ việc sau Tết
    m = min(base * math.exp(z), 0.5)
    return 1 - (1 - m) ** (1 / 30.4)


def simulate_staffing(rng, X):
    slots = []
    for b in BRANCHES.branch_id:
        i = 0
        for role, contract, shift, n in SLOT_TEMPLATE:
            for _ in range(n):
                slots.append(dict(slot_id=f"{b}-S{i:02d}", branch_id=b, role=role, contract_type=contract,
                                  primary_shift=shift, slot_idx=i))
                i += 1
    people = []
    N = X["N"]
    for s in slots:
        real = s["branch_id"] == "CN01" and s["slot_idx"] in REAL_SLOTS_CN01
        mean_ten = 20 if s["contract_type"] == "FT" else 9
        tenure = float(np.clip(rng.exponential(mean_ten), 2, 36))
        e = new_person(rng, s, -int(tenure * 30.4), real)
        d = 0
        while d < N:
            if (not e["is_real"]) and rng.random() < hazard(e, d, int(X["month"][d])):
                e["term_off"] = d
                e["termination_reason"] = str(rng.choice(["nghi_viec_tu_nguyen", "het_hop_dong", "cho_thoi_viec"],
                                                         p=[.86, .08, .06]))
                people.append(e)
                gap = int(rng.integers(CFG["turnover"]["vacancy_days"][0], CFG["turnover"]["vacancy_days"][1] + 1))
                h = d + gap
                if h >= N:
                    e = None
                    break
                e = new_person(rng, s, h, False)
                d = h
            d += 1
        if e is not None:
            people.append(e)
    # gán mã nhân viên: 5 thành viên thật trước, sau đó theo ngày vào làm
    people.sort(key=lambda p: (not p["is_real"], p["hire_off"], p["slot_id"]))
    k = 0
    for i, p in enumerate(people, 1):
        p["employee_id"] = f"NV{i:04d}"
        if p["is_real"]:
            k += 1
            p["full_name"] = f"Thành viên nhóm {k} (thay bằng tên thật)"
        else:
            nu = rng.random() < 0.5
            p["full_name"] = " ".join([str(rng.choice(HO)), str(rng.choice(DEM_NU if nu else DEM_NAM)),
                                       str(rng.choice(TEN_NU if nu else TEN_NAM))])
        p["ot_mult"] = 1.8 if p["high_ot"] else 1.0
    return people


# ----------------------------------------------------------------------------------------------
# 4. CHẤM CÔNG: lượt quét khuôn mặt / QR cho một nhân viên
# ----------------------------------------------------------------------------------------------
def scan_events(rng, e, br, ts, etype, manual):
    F = CFG["face"]
    m = len(ts)
    method = np.where(manual, "manual", np.where(rng.random(m) < F["qr_fallback_rate"], "qr", "face"))
    is_face = method == "face"
    mu = F["genuine_mean"] + e["face_shift"]
    sim = rng.normal(mu, F["genuine_sd"], m)
    bad = sim < F["accept_threshold"]
    sim[bad] = rng.normal(mu, F["genuine_sd"], int(bad.sum()))
    bad = sim < F["accept_threshold"]
    sim[bad] = rng.uniform(F["accept_threshold"], F["accept_threshold"] + 0.08, int(bad.sum()))
    sim = np.clip(sim, 0, 0.99)
    liv = np.clip(rng.beta(F["liveness_alpha"], F["liveness_beta"], m), 0.3, 0.999)
    sim = np.where(is_face, sim, np.nan)
    liv = np.where(is_face, liv, np.nan)
    jit = np.where(method == "face", 3e-5, np.where(method == "qr", 1.8e-4, 0.0))
    lat = br["lat"] + rng.normal(0, 1, m) * jit
    lon = br["lon"] + rng.normal(0, 1, m) * jit
    dev = np.where(method == "manual", "MANAGER_PORTAL", f"{e['branch_id']}-TB01")
    acc = pd.DataFrame(dict(employee_id=e["employee_id"], branch_id=e["branch_id"], device_id=dev, ts=ts,
                            event_type=etype, method=method, status="accepted", face_similarity=sim,
                            liveness_score=liv, lat=lat, lon=lon, is_manual=manual))
    # lần quét bị từ chối (FRR) ngay trước lần được chấp nhận
    rej_p = np.minimum(F["reject_rate"] * np.exp(-30 * e["face_shift"]), 0.25)
    rm = is_face & (rng.random(m) < rej_p)
    k = int(rm.sum())
    if k:
        rej = acc[rm].copy()
        rej["ts"] = rej["ts"] - tdelta(rng.uniform(8, 40, k) / 60.0)
        rej["status"] = "rejected"
        rej["face_similarity"] = rng.uniform(0.30, F["accept_threshold"] - 0.01, k)
        rej["liveness_score"] = np.clip(rng.beta(F["liveness_alpha"], F["liveness_beta"], k), 0.3, 0.999)
        acc = pd.concat([acc, rej], ignore_index=True)
    return acc


def simulate_employee(rng, e, X):
    A = CFG["attendance"]
    N = X["N"]
    a = max(e["hire_off"], 0)
    b = N - 1 if e["term_off"] is None else min(e["term_off"], N - 1)
    if a > b:
        return None
    off = np.arange(a, b + 1)
    n = len(off)
    dow = X["dow"][off]
    wk = off // 7
    ft = e["contract_type"] == "FT"
    # ---- lịch làm việc theo tuần
    sched = np.zeros(n, bool)
    extra = np.zeros(n, bool)
    if ft:
        w0 = int(wk.min())
        nw = int(wk.max()) - w0 + 1
        offd = np.full(nw, e["off_dow"])
        rd = rng.random(nw) < 0.10
        offd[rd] = rng.choice(7, int(rd.sum()), p=OFF_P)
        dayoff = offd[wk - w0]
        sched = dow != dayoff
        extra = (dow == dayoff) & (rng.random(n) < A["extra_shift_rate"])
        sched = sched | extra
    else:
        wdist = STUDENT_W if e["is_student"] else np.ones(7)
        kmin, kmax = (3, 5) if e["is_student"] else (4, 5)
        for w in np.unique(wk):
            ii = np.where(wk == w)[0]
            k = min(int(rng.integers(kmin, kmax + 1)), len(ii))
            p = wdist[dow[ii]]
            p = p / p.sum()
            sched[rng.choice(ii, size=k, replace=False, p=p)] = True
    closed = X["closed"][off]
    sched &= ~closed
    extra &= sched
    # ---- nghỉ phép
    leave_code = np.full(n, "", dtype=object)
    reqs = []
    cand = np.where(sched & ~extra)[0]
    nreq = int(rng.poisson((0.7 if ft else 0.5) * (1.3 if e["is_student"] else 1.0) * n / 30.4)) if len(cand) > 5 else 0
    for _ in range(nreq):
        i = int(rng.choice(cand))
        L = int(rng.choice([1, 2, 3], p=[.65, .25, .10]))
        if ft:
            lt = str(rng.choice(["phep_nam", "om", "viec_rieng_khong_luong"], p=[.55, .25, .20]))
        else:
            lt = str(rng.choice(["viec_rieng_khong_luong", "om"], p=[.7, .3]))
        sd_ = X["dates"][off[i]]
        sub = sd_ - pd.Timedelta(days=0 if lt == "om" else int(rng.integers(1, 8)))
        ok = rng.random() < 0.93
        reqs.append((e["employee_id"], e["branch_id"], lt, sd_, sd_ + pd.Timedelta(days=L - 1), L, sub,
                     "approved" if ok else "rejected"))
        if ok:
            mk = np.zeros(n, bool)
            mk[i:min(i + L, n)] = True
            mk &= sched & (leave_code == "")
            leave_code[mk] = lt
    on_leave = leave_code != ""
    p_abs = A["absent_rate"] * (3 if e["late_prone"] else 1)
    absent = sched & ~on_leave & (rng.random(n) < p_abs)
    pres = sched & ~on_leave & ~absent
    # ---- ca làm từng ngày
    prim = e["primary_shift"]
    shift_arr = np.full(n, prim, dtype=object)
    if prim != "HANH_CHINH":
        pool = FT_SHIFTS if ft else PT_SHIFTS
        other = [s for s in pool if s != prim]
        sw = rng.random(n) < (0.04 if ft else 0.15)
        shift_arr[sw] = rng.choice(other, int(sw.sum()))
    ps = SH["start_min"].reindex(shift_arr).values.astype(float)
    pe = SH["end_min"].reindex(shift_arr).values.astype(float)
    # ---- giờ vào/ra thực tế
    rain = X["rain"][off]
    exam = e["is_student"] & np.isin(X["month"][off], [1, 5, 6, 12])
    pbig = 0.06 if e["late_prone"] else 0.02
    off_in = (e["bias"] + rng.normal(0, 5, n) + (dow == 0) * 1.5 + rain * 3.0 + exam * 2.0
              + (rng.random(n) < pbig) * rng.exponential(25, n))
    in_min = ps + np.clip(off_in, -25, 90)
    peak = (dow >= 5) | X["hol"][off]
    p_ot = (A["ft_ot_rate"] if ft else A["pt_ot_rate"]) * e["ot_mult"] * np.where(peak, 1.3, 1.0)
    ot_flag = pres & (rng.random(n) < p_ot)
    out_off = np.where(ot_flag, rng.integers(20, 100, n).astype(float), np.clip(rng.normal(0.5, 4, n), -15, 15))
    forgot = pres & (rng.random(n) < A["forgot_checkout_rate"])
    out_min = np.minimum(np.where(forgot, pe, pe + out_off), 1439.0)
    reg = np.clip(np.minimum(out_min, pe) - np.maximum(in_min, ps), 0, None) / 60
    late = np.clip(in_min - ps, 0, None)
    early = np.clip(pe - out_min, 0, None)
    otm = np.clip(out_min - pe, 0, None)
    ot_h = np.where(otm >= 30, np.floor(otm / 30) * 0.5, 0.0)
    worked = (out_min - in_min) / 60
    daytype = np.where(X["hol"][off], "holiday", np.where(extra, "rest_extra", "normal"))
    base = X["dates"].values.astype("datetime64[ns]")[off]
    # ---- bảng công ngày (chỉ các ngày có lịch)
    st = np.full(n, "", dtype=object)
    st[pres] = "present"
    st[absent] = "absent_unapproved"
    for k_, v_ in LEAVE_STATUS.items():
        st[leave_code == k_] = v_
    ix = np.where(sched)[0]
    P = pres[ix]
    daily = pd.DataFrame(dict(
        employee_id=e["employee_id"], branch_id=e["branch_id"], work_date=base[ix], shift_id=shift_arr[ix],
        planned_start=base[ix] + tdelta(ps[ix]), planned_end=base[ix] + tdelta(pe[ix]), status=st[ix],
        check_in_ts=np.where(P, base[ix] + tdelta(in_min[ix]), np.datetime64("NaT")),
        check_out_ts=np.where(P, base[ix] + tdelta(out_min[ix]), np.datetime64("NaT")),
        late_minutes=np.where(P, np.round(late[ix]), 0).astype(int),
        early_leave_minutes=np.where(P, np.round(early[ix]), 0).astype(int),
        worked_hours=np.where(P, np.round(worked[ix], 2), np.nan),
        regular_hours=np.where(P, np.round(reg[ix], 2), 0.0),
        ot_hours=np.where(P, ot_h[ix], 0.0),
        day_type=daytype[ix], is_holiday=X["hol"][off][ix].astype(int), is_manual_fix=(forgot[ix]).astype(int)))
    # ---- lượt quét
    ip = np.where(pres)[0]
    br = BRANCHES.set_index("branch_id").loc[e["branch_id"]]
    ev_in = scan_events(rng, e, br, base[ip] + tdelta(in_min[ip]), "check_in", np.zeros(len(ip), bool))
    ev_out = scan_events(rng, e, br, base[ip] + tdelta(out_min[ip]), "check_out", forgot[ip])
    events = pd.concat([ev_in, ev_out], ignore_index=True)
    leaves = pd.DataFrame(reqs, columns=["employee_id", "branch_id", "leave_type", "start_date", "end_date",
                                         "days_requested", "submitted_date", "status"])
    return daily, events, leaves


# ----------------------------------------------------------------------------------------------
# 5. DOANH THU THEO GIỜ, SỐ NGƯỜI THEO GIỜ
# ----------------------------------------------------------------------------------------------
HOUR_PROFILE = {6: .5, 7: 1.4, 8: 1.8, 9: 1.4, 10: 1.0, 11: 1.2, 12: 1.4, 13: 1.0, 14: .8, 15: .9, 16: 1.1,
                17: 1.3, 18: 1.4, 19: 1.6, 20: 1.5, 21: 1.1, 22: .4}
SEASON = {1: .95, 2: .85, 3: .95, 4: 1.0, 5: 1.05, 6: 1.12, 7: 1.18, 8: 1.15, 9: 1.0, 10: .95, 11: .95, 12: 1.0}


def simulate_sales(rng, X):
    D = X["N"]
    hours = np.array(list(HOUR_PROFILE))
    w = np.array(list(HOUR_PROFILE.values()))
    dow_f = np.array([1, 1, 1, 1, 1.1, 1.25, 1.3])[X["dow"]]
    season = np.array([SEASON[m] for m in X["month"]])
    trend = 1 + 0.005 * (np.arange(D) / 30.4)
    since_closed = np.zeros(D)
    cnt = 99
    for i in range(D):
        cnt = 0 if X["closed"][i] else cnt + 1
        since_closed[i] = cnt
    reopen = np.where(since_closed <= 3, 0.85, 1.0)
    rows = []
    D_ = CFG["demand"]
    for _, br in BRANCHES.iterrows():
        noise = rng.lognormal(0, 0.08, D)
        day_mult = (dow_f * season * trend * (1 - 0.2 * X["rain"]) * np.where(X["hol"], 1.15, 1.0)
                    * reopen * noise * (~X["closed"]))
        mu = D_["base_orders_per_hour"] * br["demand_factor"] * day_mult[:, None] * w[None, :]
        orders = rng.poisson(mu)
        aov = np.clip(rng.normal(D_["avg_order_value"], 6000, mu.shape), 30000, 90000)
        rev = np.round(orders * aov / 1000) * 1000
        keep = ~X["closed"]
        di, hi = np.where(keep[:, None] & np.ones_like(mu, bool))
        rows.append(pd.DataFrame(dict(branch_id=br["branch_id"], date=X["dates"][di], hour=hours[hi],
                                      orders=orders[di, hi], revenue_vnd=rev[di, hi].astype("int64"))))
    return pd.concat(rows, ignore_index=True)


def staffing_hourly(daily, sales):
    def minutes(col, base):
        return ((col.values.astype("datetime64[ns]") - base) / np.timedelta64(1, "m")).astype(float)

    d = daily[daily.status.isin(["present", "absent_unapproved"]) | daily.status.str.startswith("leave_")].copy()
    base = d["work_date"].values.astype("datetime64[ns]")
    s0, s1 = minutes(d.planned_start, base), minutes(d.planned_end, base)
    is_p = (d.status == "present").to_numpy()
    a0 = np.where(is_p, minutes(d.check_in_ts, base), 0.0)
    a1 = np.where(is_p, minutes(d.check_out_ts, base), 0.0)
    parts = []
    for h in HOUR_PROFILE:
        lo, hi = h * 60, (h + 1) * 60
        sch = np.clip(np.minimum(s1, hi) - np.maximum(s0, lo), 0, 60) / 60
        pre = np.where(is_p, np.clip(np.minimum(a1, hi) - np.maximum(a0, lo), 0, 60) / 60, 0.0)
        parts.append(pd.DataFrame(dict(branch_id=d.branch_id.values, date=d.work_date.values, hour=h,
                                       scheduled_staff=sch, present_staff=pre)))
    g = pd.concat(parts).groupby(["branch_id", "date", "hour"], as_index=False).sum()
    out = sales.merge(g, on=["branch_id", "date", "hour"], how="left")
    out[["scheduled_staff", "present_staff"]] = out[["scheduled_staff", "present_staff"]].fillna(0).round(2)
    return out


# ----------------------------------------------------------------------------------------------
# 6. BẢNG LƯƠNG THÁNG
# ----------------------------------------------------------------------------------------------
def pit_amount(taxable, ym):
    old = [(5e6, .05), (10e6, .10), (18e6, .15), (32e6, .20), (52e6, .25), (80e6, .30), (np.inf, .35)]
    new = [(10e6, .05), (30e6, .10), (60e6, .20), (100e6, .30), (np.inf, .35)]
    br = new if ym >= CFG["pay"]["new_pit_from"] else old
    tax, prev = 0.0, 0.0
    for up, r in br:
        if taxable > prev:
            tax += (min(taxable, up) - prev) * r
        prev = up
    return tax


def build_payroll(daily, emps, holidays, sales):
    P = CFG["pay"]
    A = CFG["attendance"]
    d = daily.copy()
    d["month"] = d.work_date.dt.strftime("%Y-%m")
    pres = d.status == "present"
    norm = d.day_type == "normal"
    d["_late_ded"] = np.where(pres, np.clip(d.late_minutes - A["grace_min"], 0, None), 0)
    d["_late_cnt"] = (pres & (d.late_minutes > A["grace_min"])).astype(int)
    d["_pres"] = pres.astype(int)
    d["_pres_norm"] = (pres & norm).astype(int)
    d["_reg_norm"] = np.where(pres & norm, d.regular_hours, 0.0)
    d["_ot_norm"] = np.where(pres & norm, d.ot_hours, 0.0)
    d["_prem_hol"] = np.where(pres & (d.day_type == "holiday"), d.regular_hours + d.ot_hours, 0.0)
    d["_prem_rest"] = np.where(pres & (d.day_type == "rest_extra"), d.regular_hours + d.ot_hours, 0.0)
    for k, v in [("leave_annual", "_l_ann"), ("leave_unpaid", "_l_unp"), ("leave_sick", "_l_sick"),
                 ("absent_unapproved", "_abs")]:
        d[v] = (d.status == k).astype(int)
    agg = d.groupby(["employee_id", "month"], as_index=False).agg(
        days_scheduled=("status", "size"), days_worked=("_pres", "sum"), days_worked_normal=("_pres_norm", "sum"),
        days_leave_annual=("_l_ann", "sum"), days_leave_unpaid=("_l_unp", "sum"), days_leave_sick=("_l_sick", "sum"),
        days_absent_unapproved=("_abs", "sum"), regular_hours_normal=("_reg_norm", "sum"),
        ot_hours_normal=("_ot_norm", "sum"), premium_hours_holiday=("_prem_hol", "sum"),
        premium_hours_rest=("_prem_rest", "sum"), late_count=("_late_cnt", "sum"),
        late_minutes_deducted=("_late_ded", "sum"))
    # khung nhân viên x tháng đang làm việc
    e = emps.copy()
    rows = []
    for _, r in e.iterrows():
        lo = max(r.hire_date, pd.Timestamp(CFG["start"]))
        hi = min(r.termination_date if pd.notna(r.termination_date) else pd.Timestamp(CFG["end"]),
                 pd.Timestamp(CFG["end"]))
        for per in pd.period_range(lo, hi, freq="M"):
            rows.append((r.employee_id, str(per), per.start_time, per.end_time.normalize(), lo, hi))
    fr = pd.DataFrame(rows, columns=["employee_id", "month", "m_start", "m_end", "lo", "hi"])
    fr["a"] = fr[["m_start", "lo"]].max(axis=1)
    fr["b"] = fr[["m_end", "hi"]].min(axis=1)
    H = np.sort(holidays["date"].values.astype("datetime64[ns]"))
    fr["holiday_paid_days"] = (np.searchsorted(H, fr.b.values.astype("datetime64[ns]"), "right")
                               - np.searchsorted(H, fr.a.values.astype("datetime64[ns]"), "left"))
    pm = fr.merge(agg, on=["employee_id", "month"], how="left").merge(
        e[["employee_id", "branch_id", "role", "contract_type", "base_salary", "hourly_rate", "hire_date"]],
        on="employee_id")
    num = [c for c in agg.columns if c not in ("employee_id", "month")]
    pm[num] = pm[num].fillna(0)
    # doanh thu chi nhánh -> thưởng doanh số
    sm = sales.assign(month=sales.date.dt.strftime("%Y-%m")).groupby(["branch_id", "month"],
                                                                      as_index=False).revenue_vnd.sum()
    sm["target"] = sm.groupby("branch_id").revenue_vnd.transform("median") * P["bonus_sales_ratio"]
    sm["hit"] = (sm.revenue_vnd >= sm.target).astype(int)
    pm = pm.merge(sm[["branch_id", "month", "hit"]], on=["branch_id", "month"], how="left")
    pm["hit"] = pm.hit.fillna(0)
    ft = pm.contract_type == "FT"
    he = pm.base_salary / A["std_days"] / 8                     # đơn giá giờ quy đổi của FT
    paid_days = np.minimum(A["std_days"], pm.days_worked_normal + pm.days_leave_annual + pm.holiday_paid_days)
    rate = np.where(ft, he, pm.hourly_rate)
    base_pay = np.where(ft, pm.base_salary * paid_days / A["std_days"], pm.regular_hours_normal * pm.hourly_rate)
    ot_mult = np.where(ft, P["ot_weekday"], 1.0)
    ot_pay = (pm.ot_hours_normal * rate * ot_mult + pm.premium_hours_holiday * rate * P["ot_holiday"]
              + pm.premium_hours_rest * rate * P["ot_rest_day"])
    late_ded = np.where(ft, pm.late_minutes_deducted / 60 * he, 0.0)
    meal = np.where(ft, pm.days_worked * P["meal_per_day"], 0.0)
    other = np.where(ft & (pm.role == "quan_ly") & (pm.days_worked > 0), P["manager_allowance"], 0.0)
    b_att = np.where(ft & (pm.late_count <= 1) & (pm.days_absent_unapproved == 0) & (pm.days_worked_normal >= 20),
                     P["bonus_attendance"], 0.0)
    b_sales = np.where((pm.hit == 1) & (pm.days_worked >= 8), np.where(ft, P["bonus_sales_ft"], P["bonus_sales_pt"]), 0.0)
    gross = base_pay - late_ded + ot_pay + meal + other + b_att + b_sales
    ins_ok = ft & (pm.m_start > pm.hire_date + pd.Timedelta(days=30)) & (paid_days >= 14)
    emp_ins = np.where(ins_ok, pm.base_salary * P["employee_ins_rate"], 0.0)
    er_ins = np.where(ins_ok, pm.base_salary * P["employer_ins_rate"], 0.0)
    ded = np.where(pm.month < "2026-01", P["deduction_before_2026"], P["deduction_from_2026"])
    taxable = np.where(ft, np.clip(gross - emp_ins - ded, 0, None), 0.0)
    pit = np.array([pit_amount(t, m) for t, m in zip(taxable, pm.month)])
    net = gross - emp_ins - pit
    out = pm[["employee_id", "branch_id", "month", "contract_type", "days_scheduled", "days_worked",
              "days_leave_annual", "days_leave_unpaid", "days_leave_sick", "days_absent_unapproved",
              "holiday_paid_days", "regular_hours_normal", "ot_hours_normal", "premium_hours_holiday",
              "premium_hours_rest", "late_count", "late_minutes_deducted"]].copy()
    r3 = lambda x: np.round(np.asarray(x, dtype=float), -3)
    out["base_pay"], out["ot_pay"], out["late_deduction"] = r3(base_pay), r3(ot_pay), r3(late_ded)
    out["allowance_meal"], out["allowance_other"] = r3(meal), r3(other)
    out["bonus_attendance"], out["bonus_sales"], out["gross_pay"] = r3(b_att), r3(b_sales), r3(gross)
    out["employee_insurance"], out["employer_insurance"] = r3(emp_ins), r3(er_ins)
    out["taxable_income"], out["pit"], out["net_pay"] = r3(taxable), r3(pit), r3(net)
    for c in ["regular_hours_normal", "ot_hours_normal", "premium_hours_holiday", "premium_hours_rest"]:
        out[c] = out[c].round(2)
    out = out.sort_values(["month", "employee_id"]).reset_index(drop=True)
    out.insert(0, "payroll_id", [f"PR{i:06d}" for i in range(1, len(out) + 1)])
    return out


# ----------------------------------------------------------------------------------------------
# 7. CHÈN BẤT THƯỜNG CÓ NHÃN
# ----------------------------------------------------------------------------------------------
def inject_anomalies(rng, ev, emps):
    C = CFG["anomaly"]
    ev = ev.copy()
    ev["anomaly_type"] = ""
    risk = emps.set_index("employee_id")["_risky"]
    w_emp = 1 + (C["risky_mult"] - 1) * risk.astype(float)
    acc = ev.index[(ev.status == "accepted") & (~ev.is_manual)].to_numpy()
    n_total = int(len(acc) * C["rate"])
    types = list(C["type_probs"])
    counts = rng.multinomial(n_total, np.array(list(C["type_probs"].values())) / sum(C["type_probs"].values()))
    avail = pd.Series(True, index=acc)
    new_rows = []
    face_ok = ev.loc[acc, "method"].eq("face").to_numpy()
    out_ok = ev.loc[acc, "event_type"].eq("check_out").to_numpy()
    for t, c in zip(types, counts):
        if c == 0:
            continue
        elig = avail.to_numpy().copy()
        if t in ("spoof_attempt", "low_similarity_manual"):
            elig &= face_ok
        if t == "long_session":
            elig &= out_ok & face_ok
        w = (ev.loc[acc, "employee_id"].map(w_emp).to_numpy() * elig)
        pick = rng.choice(len(acc), size=int(min(c, elig.sum())), replace=False, p=w / w.sum())
        avail.iloc[pick] = False
        idx = acc[pick]
        k = len(idx)
        if t == "gps_mismatch":
            dist = rng.uniform(400, 8000, k)
            th = rng.uniform(0, 2 * np.pi, k)
            lat0 = ev.loc[idx, "lat"].to_numpy()
            ev.loc[idx, "method"] = "qr"
            ev.loc[idx, "lat"] = lat0 + dist * np.cos(th) / 111320
            ev.loc[idx, "lon"] = ev.loc[idx, "lon"].to_numpy() + dist * np.sin(th) / (111320 * np.cos(np.radians(lat0)))
            ev.loc[idx, "face_similarity"] = np.nan
            ev.loc[idx, "liveness_score"] = np.nan
            ev.loc[idx, "anomaly_type"] = t
        elif t == "spoof_attempt":
            ev.loc[idx, "face_similarity"] = np.clip(rng.normal(0.86, 0.04, k), 0.70, 0.99)
            ev.loc[idx, "liveness_score"] = rng.uniform(0.05, 0.45, k)
            ev.loc[idx, "anomaly_type"] = t
        elif t == "low_similarity_manual":
            ev.loc[idx, "face_similarity"] = rng.uniform(0.45, 0.58, k)
            ev.loc[idx, "is_manual"] = True
            ev.loc[idx, "anomaly_type"] = t
        elif t == "long_session":
            ev.loc[idx, "ts"] = (ev.loc[idx, "ts"].dt.normalize() + pd.Timedelta(days=1)
                                 + pd.to_timedelta(rng.uniform(6.5 * 60, 10 * 60, k), unit="m"))
            ev.loc[idx, "anomaly_type"] = t
        elif t == "burst_duplicate":
            for i in idx:
                nrep = int(rng.integers(2, 6))
                r = ev.loc[[i] * nrep].copy()
                r["ts"] = r["ts"] + pd.to_timedelta(np.cumsum(rng.uniform(1, 15, nrep)), unit="s")
                r["anomaly_type"] = t
                new_rows.append(r)
        elif t == "off_hours":
            r = ev.loc[idx].copy()
            r["ts"] = r["ts"].dt.normalize() + pd.to_timedelta(rng.uniform(60, 300, k), unit="m")
            r["event_type"] = rng.choice(["check_in", "check_out"], k)
            r["face_similarity"] = np.where(r.method == "face", rng.uniform(0.55, 0.78, k), np.nan)
            r["anomaly_type"] = t
            new_rows.append(r)
    if new_rows:
        ev = pd.concat([ev] + new_rows, ignore_index=True)
    ev = ev.sort_values("ts", kind="stable").reset_index(drop=True)
    ev.insert(0, "event_id", np.arange(1, len(ev) + 1))
    return ev


# ----------------------------------------------------------------------------------------------
# 8. BẢNG ĐẶC TRƯNG CHO MODEL
# ----------------------------------------------------------------------------------------------
def event_split(ts):
    S = CFG["splits"]
    return np.where(ts <= pd.Timestamp(S["event_train_end"]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1), "train",
                    np.where(ts <= pd.Timestamp(S["event_val_end"]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1),
                             "val", "test"))


def build_features_anomaly(ev, daily, emps, hol_dates):
    acc = ev[ev.status == "accepted"].copy()
    acc["work_date"] = acc.ts.dt.normalize()
    dd = daily[["employee_id", "work_date", "planned_start", "planned_end", "status"]].rename(
        columns={"status": "day_status"})
    acc = acc.merge(dd, on=["employee_id", "work_date"], how="left")
    acc = acc.merge(emps[["employee_id", "role", "contract_type", "hire_date"]], on="employee_id", how="left")
    acc["tenure_days"] = (acc.ts - acc.hire_date).dt.days
    acc["hour"] = acc.ts.dt.hour
    acc["dow"] = acc.ts.dt.dayofweek
    acc["is_weekend"] = (acc.dow >= 5).astype(int)
    acc["is_holiday"] = acc.work_date.isin(hol_dates).astype(int)
    acc["event_is_checkout"] = (acc.event_type == "check_out").astype(int)
    acc["method_qr"] = (acc.method == "qr").astype(int)
    acc["is_manual"] = acc.is_manual.astype(int)
    acc["has_face_score"] = acc.face_similarity.notna().astype(int)
    br = BRANCHES.set_index("branch_id")
    acc["gps_distance_m"] = haversine_m(acc.lat, acc.lon, acc.branch_id.map(br.lat), acc.branch_id.map(br.lon)).round(1)
    acc["scheduled_present"] = (acc.day_status == "present").astype(int)
    ref = np.where(acc.event_is_checkout == 1, acc.planned_end, acc.planned_start)
    acc["minutes_from_plan"] = ((acc.ts - pd.to_datetime(ref)).dt.total_seconds() / 60).round(1)
    acc = acc.sort_values("ts", kind="stable")
    acc["secs_since_prev_emp_event"] = acc.groupby("employee_id").ts.diff().dt.total_seconds()
    acc["secs_since_prev_device_event"] = acc.groupby("device_id").ts.diff().dt.total_seconds()
    acc["events_same_day_so_far"] = acc.groupby(["employee_id", "work_date"]).cumcount() + 1
    acc["min_of_day"] = acc.ts.dt.hour * 60 + acc.ts.dt.minute
    g = acc.groupby(["employee_id", "event_type"])
    mean30 = g["min_of_day"].transform(lambda s: s.shift(1).rolling(30, min_periods=5).mean())
    std30 = g["min_of_day"].transform(lambda s: s.shift(1).rolling(30, min_periods=5).std())
    acc["minute_dev_vs_own_30"] = (acc.min_of_day - mean30).round(1)
    acc["minute_z_vs_own_30"] = ((acc.min_of_day - mean30) / std30.clip(lower=3)).round(2)
    simm = g["face_similarity"].transform(lambda s: s.shift(1).rolling(30, min_periods=5).mean())
    acc["sim_dev_vs_own_30"] = (acc.face_similarity - simm).round(3)
    acc["is_anomaly"] = (acc.anomaly_type != "").astype(int)
    acc["split"] = event_split(acc.ts)
    cols = ["event_id", "ts", "employee_id", "branch_id", "role", "contract_type", "tenure_days", "hour", "dow",
            "is_weekend", "is_holiday", "event_is_checkout", "method_qr", "is_manual", "has_face_score",
            "face_similarity", "liveness_score", "gps_distance_m", "scheduled_present", "minutes_from_plan",
            "secs_since_prev_emp_event", "secs_since_prev_device_event", "events_same_day_so_far",
            "minute_dev_vs_own_30", "minute_z_vs_own_30", "sim_dev_vs_own_30", "is_anomaly", "anomaly_type", "split"]
    return acc[cols].reset_index(drop=True)


def build_features_attrition(daily, emps, payroll):
    S = CFG["splits"]
    snaps = pd.date_range("2024-12-01", "2026-07-31", freq="W-SUN")
    med = emps.assign(w=emps.base_salary.fillna(emps.hourly_rate)).groupby(["role", "contract_type"]).w.transform("median")
    emps = emps.assign(wage_ratio=(emps.base_salary.fillna(emps.hourly_rate) / med).round(3))
    d = daily.copy()
    d["late_flag"] = ((d.status == "present") & (d.late_minutes > CFG["attendance"]["grace_min"])).astype(int)
    d["pres"] = (d.status == "present").astype(int)
    d["leave_day"] = d.status.str.startswith("leave_").astype(int)
    d["abs_day"] = (d.status == "absent_unapproved").astype(int)
    rows = []
    for s in snaps:
        w0 = s - pd.Timedelta(days=89)
        act = emps[(emps.hire_date <= s) & (emps.termination_date.isna() | (emps.termination_date > s))]
        win = d[(d.work_date >= w0) & (d.work_date <= s)]
        g = win.groupby("employee_id").agg(
            sched_90d=("status", "size"), present_90d=("pres", "sum"), late_cnt_90d=("late_flag", "sum"),
            absent_90d=("abs_day", "sum"), leave_days_90d=("leave_day", "sum"), ot_hours_90d=("ot_hours", "sum"),
            clock_hours_90d=("worked_hours", "sum"), manual_fix_90d=("is_manual_fix", "sum"),
            late_min_sum=("late_minutes", "sum"))
        g30 = win[win.work_date > s - pd.Timedelta(days=30)].groupby("employee_id").agg(
            present_30d=("pres", "sum"), late_cnt_30d=("late_flag", "sum"))
        f = act[["employee_id", "branch_id", "role", "contract_type", "is_student", "wage_ratio", "hire_date",
                 "termination_date", "is_real_face"]].merge(g, on="employee_id", how="left").merge(
            g30, on="employee_id", how="left")
        numc = [c for c in list(g.columns) + list(g30.columns) if c in f.columns]
        f[numc] = f[numc].fillna(0)
        days_active = ((s - f.hire_date.clip(lower=w0)).dt.days + 1).clip(lower=1)
        f["snapshot_date"] = s
        f["tenure_days"] = (s - f.hire_date).dt.days
        f["late_rate_90d"] = (f.late_cnt_90d / f.present_90d.replace(0, np.nan)).fillna(0).round(3)
        f["late_rate_30d"] = (f.late_cnt_30d / f.present_30d.replace(0, np.nan)).fillna(0).round(3)
        f["avg_late_minutes_90d"] = (f.late_min_sum / f.present_90d.replace(0, np.nan)).fillna(0).round(2)
        f["avg_weekly_hours_90d"] = (f.clock_hours_90d / (days_active / 7)).round(2)
        f["ot_hours_90d"] = f.ot_hours_90d.round(2)
        f["month_of_year"] = s.month
        hc = len(act[act.branch_id.isin(act.branch_id)])
        left90 = emps[(emps.termination_date > s - pd.Timedelta(days=90)) & (emps.termination_date <= s)]
        tb = left90.groupby("branch_id").size()
        hcb = act.groupby("branch_id").size()
        f["branch_turnover_90d"] = (f.branch_id.map(tb).fillna(0) / f.branch_id.map(hcb)).round(3)
        f["left_next_60d"] = ((f.termination_date > s) & (f.termination_date <= s + pd.Timedelta(days=S["horizon_days"]))).astype(int)
        rows.append(f)
    out = pd.concat(rows, ignore_index=True)
    snap = out.snapshot_date
    out["split"] = np.select(
        [snap <= pd.Timestamp(S["attr_train_last_snapshot"]),
         (snap >= pd.Timestamp(S["attr_val_first"])) & (snap <= pd.Timestamp(S["attr_val_last"])),
         snap >= pd.Timestamp(S["attr_test_first"])], ["train", "val", "test"], "embargo")
    cols = ["snapshot_date", "employee_id", "branch_id", "role", "contract_type", "is_student", "tenure_days",
            "wage_ratio", "sched_90d", "present_90d", "late_rate_90d", "late_rate_30d", "avg_late_minutes_90d",
            "absent_90d", "leave_days_90d", "ot_hours_90d", "avg_weekly_hours_90d", "manual_fix_90d",
            "branch_turnover_90d", "month_of_year", "is_real_face", "left_next_60d", "split"]
    out["is_student"] = out.is_student.astype(int)
    out["is_real_face"] = out.is_real_face.astype(int)
    for c in ["sched_90d", "present_90d", "absent_90d", "leave_days_90d", "manual_fix_90d"]:
        out[c] = out[c].astype(int)
    return out[cols]


def build_features_staffing(sh, weather, hol_dates):
    f = sh.copy()
    f["dow"] = f.date.dt.dayofweek
    f["month"] = f.date.dt.month
    f["is_holiday"] = f.date.isin(hol_dates).astype(int)
    f = f.merge(weather, on="date", how="left")
    lag = f[["branch_id", "date", "hour", "orders"]].copy()
    lag["date"] = lag["date"] + pd.Timedelta(days=7)
    f = f.merge(lag.rename(columns={"orders": "orders_lag_7d"}), on=["branch_id", "date", "hour"], how="left")
    cap = CFG["demand"]["orders_per_staff_hour"]
    f["required_staff_est"] = np.maximum(2, np.ceil(f.orders / cap)).astype(int)
    f["orders_per_present_staff"] = (f.orders / f.present_staff.replace(0, np.nan)).round(2)
    f["split"] = event_split(f.date + pd.Timedelta(hours=12))
    cols = ["branch_id", "date", "hour", "dow", "month", "is_holiday", "is_rain", "orders_lag_7d", "scheduled_staff",
            "present_staff", "orders", "revenue_vnd", "required_staff_est", "orders_per_present_staff", "split"]
    return f[cols]


# ----------------------------------------------------------------------------------------------
# 9. CHẠY TOÀN BỘ
# ----------------------------------------------------------------------------------------------
def build_all(seed=None):
    rng = np.random.default_rng(CFG["seed"] if seed is None else seed)
    dates = pd.date_range(CFG["start"], CFG["end"], freq="D")
    holidays = make_holidays()
    closed_set = set(holidays.loc[holidays.is_closed_for_business, "date"])
    hol_set = set(holidays.date)
    weather = make_weather(rng, dates)
    X = dict(N=len(dates), dates=dates, dow=dates.dayofweek.to_numpy(), month=dates.month.to_numpy(),
             closed=np.array([d in closed_set for d in dates]), hol=np.array([d in hol_set for d in dates]),
             rain=weather.is_rain.to_numpy())
    people = simulate_staffing(rng, X)
    # ---- bảng nhân viên
    E = pd.DataFrame(people)
    start = pd.Timestamp(CFG["start"])
    E["hire_date"] = E.hire_off.map(lambda o: start + pd.Timedelta(days=int(o)))
    E["termination_date"] = E.term_off.map(lambda o: start + pd.Timedelta(days=int(o)) if pd.notna(o) else pd.NaT)
    E["is_real_face"] = E.is_real.astype(bool)
    E["data_source"] = np.where(E.is_real_face, "real_member_placeholder", "simulated")
    E = E.sort_values("employee_id").reset_index(drop=True)
    daily_parts, ev_parts, leave_parts = [], [], []
    for p in people:
        r = simulate_employee(rng, p, X)
        if r is None:
            continue
        daily_parts.append(r[0])
        ev_parts.append(r[1])
        leave_parts.append(r[2])
    daily = pd.concat(daily_parts, ignore_index=True).sort_values(["work_date", "employee_id"]).reset_index(drop=True)
    leaves = pd.concat(leave_parts, ignore_index=True).sort_values(["start_date", "employee_id"]).reset_index(drop=True)
    leaves.insert(0, "leave_id", [f"LV{i:05d}" for i in range(1, len(leaves) + 1)])
    ev_clean = pd.concat(ev_parts, ignore_index=True)
    sales = simulate_sales(rng, X)
    employees = E[["employee_id", "full_name", "branch_id", "role", "contract_type", "primary_shift", "hire_date",
                   "termination_date", "termination_reason", "is_student", "birth_year", "base_salary",
                   "hourly_rate", "is_real_face", "data_source"]].copy()
    employees["is_student"] = employees.is_student.astype(int)
    employees["is_real_face"] = employees.is_real_face.astype(int)
    payroll = build_payroll(daily, E.assign(is_real_face=E.is_real_face), holidays, sales)
    # ---- chèn bất thường vào lượt quét (bảng công/lương giữ nguyên = sự thật nền)
    ev = inject_anomalies(rng, ev_clean, E.assign(_risky=E.risky))
    br = BRANCHES.set_index("branch_id")
    ev["gps_distance_m"] = haversine_m(ev.lat, ev.lon, ev.branch_id.map(br.lat), ev.branch_id.map(br.lon)).round(1)
    labels = ev.loc[ev.anomaly_type != "", ["event_id", "anomaly_type"]].reset_index(drop=True)
    attendance_events = ev[["event_id", "employee_id", "branch_id", "device_id", "ts", "event_type", "method", "status",
                            "face_similarity", "liveness_score", "lat", "lon", "gps_distance_m", "is_manual"]].copy()
    attendance_events["is_manual"] = attendance_events.is_manual.astype(int)
    attendance_events["face_similarity"] = attendance_events.face_similarity.round(4)
    attendance_events["liveness_score"] = attendance_events.liveness_score.round(4)
    attendance_events["lat"] = attendance_events.lat.round(6)
    attendance_events["lon"] = attendance_events.lon.round(6)
    sh = staffing_hourly(daily, sales)
    hol_dates = set(holidays.date)
    f_anom = build_features_anomaly(ev, daily, E, hol_dates)
    f_attr = build_features_attrition(daily, E.assign(is_real_face=E.is_real_face), payroll)
    f_staff = build_features_staffing(sh, weather, hol_dates)
    latent = E[["employee_id", "slot_id", "late_prone", "high_ot", "risky", "bias", "face_shift", "off_dow"]].rename(
        columns={"risky": "risky_for_anomaly"})
    daily_out = daily.copy()
    daily_out["work_date"] = pd.to_datetime(daily_out.work_date)
    tables = dict(
        clean=dict(branches=BRANCHES, shifts=SHIFTS[["shift_id", "shift_name", "contract_type", "start_time",
                                                      "end_time", "paid_hours"]],
                   holidays=holidays, weather_daily=weather, employees=employees, leave_requests=leaves,
                   attendance_events=attendance_events, attendance_daily=daily_out, payroll=payroll,
                   branch_sales_hourly=sales, labels_anomaly=labels),
        features=dict(features_anomaly=f_anom, features_attrition=f_attr, features_staffing_hourly=f_staff),
        internal=dict(employee_latent_traits=latent))
    return tables
# ----------------------------------------------------------------------------------------------
# 10. TỪ ĐIỂN DỮ LIỆU
# ----------------------------------------------------------------------------------------------
TABLE_DESC = {
    "branches": "Danh mục 4 chi nhánh (giả định) tại Đà Nẵng",
    "shifts": "Danh mục ca làm việc (giờ bắt đầu/kết thúc, giờ công tính lương)",
    "holidays": "Ngày nghỉ lễ 2025-2026 (Tết, Giỗ Tổ, 30/4, 1/5, Quốc khánh) và cờ đóng cửa",
    "weather_daily": "Cờ có mưa theo ngày (mô phỏng theo mùa)",
    "employees": "Hồ sơ nhân viên (kể cả người đã nghỉ việc và người được tuyển thay thế)",
    "leave_requests": "Đơn xin nghỉ phép và kết quả duyệt",
    "attendance_events": "Lượt quét chấm công thô (khuôn mặt/QR/thủ công), gồm cả lượt bị từ chối và lượt bất thường",
    "attendance_daily": "Bảng công theo ngày (sự thật nền, không chứa bất thường chèn vào lượt quét)",
    "payroll": "Bảng lương tháng cho từng nhân viên",
    "branch_sales_hourly": "Đơn hàng và doanh thu theo giờ của từng chi nhánh",
    "labels_anomaly": "Nhãn bất thường theo event_id (chỉ chứa các lượt bất thường)",
    "features_anomaly": "Đặc trưng cho model phát hiện gian lận chấm công (1 dòng = 1 lượt quét được chấp nhận)",
    "features_attrition": "Đặc trưng cho model dự báo nghỉ việc trong 60 ngày (1 dòng = nhân viên x mốc cuối tháng)",
    "features_staffing_hourly": "Đặc trưng cho model dự báo nhu cầu nhân sự theo giờ",
    "employee_latent_traits": "Đặc điểm tiềm ẩn dùng để sinh dữ liệu (đáp án nền). KHÔNG dùng khi huấn luyện",
}

COL = {
    "branch_id": "Mã chi nhánh (CN01..CN04)", "branch_name": "Tên chi nhánh", "district": "Quận",
    "lat": "Vĩ độ (của chi nhánh hoặc của lượt quét)", "lon": "Kinh độ (của chi nhánh hoặc của lượt quét)",
    "demand_factor": "Hệ số nhu cầu tương đối của chi nhánh", "seats": "Số chỗ ngồi",
    "open_time": "Giờ mở cửa", "close_time": "Giờ đóng cửa",
    "shift_id": "Mã ca làm", "shift_name": "Tên ca làm", "contract_type": "Loại hợp đồng: FT = chính thức, PT = bán thời gian",
    "start_time": "Giờ bắt đầu ca", "end_time": "Giờ kết thúc ca", "paid_hours": "Số giờ công tính lương của ca",
    "date": "Ngày", "holiday_name": "Tên ngày lễ", "is_closed_for_business": "1 = cửa hàng đóng cửa cả ngày",
    "note": "Ghi chú", "is_rain": "1 = ngày có mưa",
    "employee_id": "Mã nhân viên", "full_name": "Họ tên (giả định)", "role": "Vai trò: quan_ly/pha_che/thu_ngan/phuc_vu",
    "primary_shift": "Ca làm chính", "hire_date": "Ngày vào làm", "termination_date": "Ngày nghỉ việc (rỗng = còn làm)",
    "termination_reason": "Lý do nghỉ việc", "is_student": "1 = sinh viên", "birth_year": "Năm sinh",
    "base_salary": "Lương cơ bản tháng (VND), chỉ FT", "hourly_rate": "Lương theo giờ (VND), chỉ PT",
    "is_real_face": "1 = ô vị trí dành cho thành viên nhóm (sẽ thay bằng dữ liệu khuôn mặt thật)",
    "data_source": "Nguồn dữ liệu: simulated / real_member_placeholder",
    "leave_id": "Mã đơn nghỉ", "leave_type": "Loại nghỉ: phep_nam/om/viec_rieng_khong_luong",
    "start_date": "Ngày bắt đầu nghỉ", "end_date": "Ngày kết thúc nghỉ", "days_requested": "Số ngày xin nghỉ",
    "submitted_date": "Ngày nộp đơn",
    "event_id": "Mã lượt quét", "device_id": "Mã thiết bị chấm công", "ts": "Thời điểm lượt quét",
    "event_type": "check_in / check_out", "method": "Phương thức: face / qr / manual",
    "face_similarity": "Độ giống khuôn mặt (0-1), rỗng nếu không quét mặt",
    "liveness_score": "Điểm chống giả mạo (0-1, cao = người thật)",
    "gps_distance_m": "Khoảng cách từ vị trí quét đến chi nhánh (mét)", "is_manual": "1 = quản lý chấm tay",
    "work_date": "Ngày làm việc", "planned_start": "Giờ bắt đầu theo lịch", "planned_end": "Giờ kết thúc theo lịch",
    "check_in_ts": "Giờ vào thực tế", "check_out_ts": "Giờ ra thực tế",
    "late_minutes": "Số phút đi trễ", "early_leave_minutes": "Số phút về sớm",
    "worked_hours": "Tổng giờ có mặt", "regular_hours": "Giờ trong ca", "ot_hours": "Giờ tăng ca (làm tròn 0,5 giờ, từ 30 phút)",
    "day_type": "normal / holiday / rest_extra (làm thêm ngày nghỉ tuần)", "is_holiday": "1 = ngày lễ",
    "is_manual_fix": "1 = quên chấm ra, quản lý sửa tay",
    "payroll_id": "Mã dòng lương", "month": "Kỳ lương YYYY-MM", "days_scheduled": "Số ngày có lịch",
    "days_worked": "Số ngày đi làm", "days_leave_annual": "Ngày phép năm", "days_leave_unpaid": "Ngày nghỉ không lương",
    "days_leave_sick": "Ngày nghỉ ốm", "days_absent_unapproved": "Ngày vắng không phép",
    "holiday_paid_days": "Số ngày lễ hưởng lương trong tháng", "regular_hours_normal": "Giờ trong ca ngày thường",
    "ot_hours_normal": "Giờ tăng ca ngày thường", "premium_hours_holiday": "Giờ làm ngày lễ (hệ số 300%)",
    "premium_hours_rest": "Giờ làm ngày nghỉ tuần (hệ số 200%)", "late_count": "Số lần trễ quá thời gian ân hạn",
    "late_minutes_deducted": "Số phút trễ bị trừ", "base_pay": "Lương theo công", "ot_pay": "Tiền tăng ca/làm ngày lễ",
    "late_deduction": "Trừ đi trễ", "allowance_meal": "Phụ cấp ăn", "allowance_other": "Phụ cấp khác (quản lý)",
    "bonus_attendance": "Thưởng chuyên cần", "bonus_sales": "Thưởng đạt doanh số chi nhánh", "gross_pay": "Tổng thu nhập",
    "employee_insurance": "Bảo hiểm người lao động đóng", "employer_insurance": "Bảo hiểm doanh nghiệp đóng",
    "taxable_income": "Thu nhập tính thuế (sau giảm trừ)", "pit": "Thuế thu nhập cá nhân", "net_pay": "Thực nhận",
    "hour": "Giờ trong ngày (0-23)", "orders": "Số đơn hàng", "revenue_vnd": "Doanh thu (VND)",
    "anomaly_type": "Loại bất thường (rỗng = bình thường). KHÔNG đưa vào đặc trưng, đây là nhãn",
    "tenure_days": "Số ngày đã làm việc", "dow": "Thứ trong tuần (0 = Thứ Hai)", "is_weekend": "1 = cuối tuần",
    "event_is_checkout": "1 = lượt check-out", "method_qr": "1 = quét QR", "has_face_score": "1 = có điểm khuôn mặt",
    "scheduled_present": "1 = hôm đó có lịch và đi làm", "minutes_from_plan": "Phút lệch so với giờ theo lịch",
    "secs_since_prev_emp_event": "Giây kể từ lượt quét trước của cùng nhân viên",
    "secs_since_prev_device_event": "Giây kể từ lượt quét trước trên cùng thiết bị",
    "events_same_day_so_far": "Số lượt quét trong ngày tính đến lúc này",
    "minute_dev_vs_own_30": "Lệch giờ quét so với trung bình 30 lượt gần nhất của chính nhân viên (phút)",
    "minute_z_vs_own_30": "Z-score của độ lệch trên", "sim_dev_vs_own_30": "Lệch độ giống khuôn mặt so với mức thường ngày",
    "is_anomaly": "Nhãn: 1 = bất thường", "split": "Tập dữ liệu: train / val / test (/ embargo)",
    "snapshot_date": "Mốc quan sát (cuối tháng)", "wage_ratio": "Lương / lương trung vị cùng vai trò và loại hợp đồng",
    "sched_90d": "Số ngày có lịch trong 90 ngày", "present_90d": "Số ngày đi làm trong 90 ngày",
    "late_rate_90d": "Tỷ lệ đi trễ 90 ngày", "late_rate_30d": "Tỷ lệ đi trễ 30 ngày",
    "avg_late_minutes_90d": "Số phút trễ trung bình 90 ngày", "absent_90d": "Số ngày vắng không phép 90 ngày",
    "leave_days_90d": "Số ngày nghỉ phép 90 ngày", "ot_hours_90d": "Giờ tăng ca 90 ngày",
    "avg_weekly_hours_90d": "Giờ làm trung bình mỗi tuần", "manual_fix_90d": "Số lần phải sửa công tay",
    "branch_turnover_90d": "Tỷ lệ nghỉ việc của chi nhánh trong 90 ngày", "month_of_year": "Tháng trong năm",
    "left_next_60d": "Nhãn: 1 = nghỉ việc trong 60 ngày sau mốc quan sát",
    "orders_lag_7d": "Số đơn cùng giờ cách 7 ngày", "scheduled_staff": "Số người theo lịch (quy đổi theo giờ)",
    "present_staff": "Số người có mặt thực tế (quy đổi theo giờ)", "required_staff_est": "Số người cần ước tính từ số đơn",
    "orders_per_present_staff": "Số đơn trên mỗi người có mặt",
    "slot_id": "Mã ô vị trí (mỗi ô có thể có nhiều người nối tiếp nhau)", "late_prone": "Hay đi trễ (đặc điểm ẩn)",
    "high_ot": "Hay tăng ca (đặc điểm ẩn)", "risky_for_anomaly": "Dễ phát sinh bất thường (đặc điểm ẩn)",
    "bias": "Độ lệch giờ vào quen thuộc (phút)", "face_shift": "Độ lệch điểm khuôn mặt riêng", "off_dow": "Ngày nghỉ tuần cố định",
}
COL_T = {  # cột trùng tên nhưng khác nghĩa theo bảng
    ("attendance_events", "status"): "accepted / rejected (lượt quét bị từ chối)",
    ("attendance_daily", "status"): "present / absent_unapproved / leave_annual / leave_sick / leave_unpaid",
    ("leave_requests", "status"): "approved / rejected",
    ("branch_sales_hourly", "date"): "Ngày bán hàng",
    ("features_anomaly", "hour"): "Giờ của lượt quét", ("features_staffing_hourly", "hour"): "Giờ bán hàng",
    ("features_staffing_hourly", "month"): "Tháng trong năm",
    ("features_anomaly", "ts"): "Thời điểm lượt quét",
}


def data_dictionary(T):
    rows = []
    for grp, tbs in T.items():
        for name, df in tbs.items():
            for c in df.columns:
                rows.append(dict(group=grp, table=name, column=c, dtype=str(df[c].dtype),
                                 description=COL_T.get((name, c)) or COL.get(c, "(chưa mô tả)"),
                                 n_missing=int(df[c].isna().sum())))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------
# 11. KIỂM TRA TOÀN VẸN
# ----------------------------------------------------------------------------------------------
def validate(T):
    C, F = T["clean"], T["features"]
    emp, d, ev, pay, lv = (C["employees"], C["attendance_daily"], C["attendance_events"],
                           C["payroll"], C["leave_requests"])
    res = []

    def chk(name, ok, detail=""):
        res.append(dict(check=name, passed=bool(ok), detail=str(detail)))

    # khóa chính / khóa ngoại
    chk("employee_id là duy nhất", emp.employee_id.is_unique)
    chk("event_id là duy nhất", ev.event_id.is_unique)
    chk("payroll: (employee_id, month) là duy nhất", not pay.duplicated(["employee_id", "month"]).any())
    chk("attendance_daily: (employee_id, work_date) là duy nhất", not d.duplicated(["employee_id", "work_date"]).any())
    for tn, df in [("attendance_daily", d), ("attendance_events", ev), ("payroll", pay), ("leave_requests", lv)]:
        chk(f"FK employee_id trong {tn}", df.employee_id.isin(emp.employee_id).all())
        chk(f"FK branch_id trong {tn}", df.branch_id.isin(C["branches"].branch_id).all())
    chk("FK shift_id trong attendance_daily", d.shift_id.isin(C["shifts"].shift_id).all())
    chk("labels_anomaly ⊂ attendance_events", C["labels_anomaly"].event_id.isin(ev.event_id).all())
    chk("số nhãn bất thường khớp features_anomaly",
        len(C["labels_anomaly"]) == int(F["features_anomaly"].is_anomaly.sum()),
        f'{len(C["labels_anomaly"])} vs {int(F["features_anomaly"].is_anomaly.sum())}')
    # bảng công
    p = d[d.status == "present"]
    chk("ngày present đều có giờ vào/ra", p.check_in_ts.notna().all() and p.check_out_ts.notna().all())
    chk("giờ ra > giờ vào", (p.check_out_ts > p.check_in_ts).all())
    chk("late/early/ot không âm", (d.late_minutes >= 0).all() and (d.early_leave_minutes >= 0).all()
        and (d.ot_hours >= 0).all())
    chk("giờ tăng ca là bội số của 0,5", ((d.ot_hours * 2) % 1 == 0).all())
    m = d.merge(emp[["employee_id", "hire_date", "termination_date"]], on="employee_id")
    ok = (m.work_date >= m.hire_date) & (m.termination_date.isna() | (m.work_date <= m.termination_date))
    chk("không có ngày công ngoài thời gian làm việc của nhân viên", ok.all(), f"vi phạm: {int((~ok).sum())}")
    closed = set(C["holidays"].loc[C["holidays"].is_closed_for_business, "date"])
    chk("không có ngày công vào ngày đóng cửa", not d.work_date.isin(closed).any())
    # bảng lương
    chk("gross_pay, net_pay >= 0", (pay.gross_pay >= 0).all() and (pay.net_pay >= 0).all(),
        f"net<0: {int((pay.net_pay < 0).sum())}")
    err = (pay.gross_pay - pay.employee_insurance - pay.pit - pay.net_pay).abs().max()
    chk("net = gross - bảo hiểm - thuế (sai số làm tròn <= 2.000đ)", err <= 2000, f"sai lệch lớn nhất {err:,.0f}")
    pt = pay[pay.contract_type == "PT"]
    chk("PT không có bảo hiểm và thuế", (pt.employee_insurance == 0).all() and (pt.pit == 0).all())
    ft = emp[emp.contract_type == "FT"]
    chk("FT có base_salary, PT có hourly_rate",
        ft.base_salary.notna().all() and emp[emp.contract_type == "PT"].hourly_rate.notna().all())
    # chia tập theo thời gian
    fe, fa = F["features_anomaly"], F["features_attrition"]
    mx = fe.groupby("split").ts.agg(["min", "max"])
    chk("features_anomaly: train < val < test theo thời gian",
        mx.loc["train", "max"] < mx.loc["val", "min"] and mx.loc["val", "max"] < mx.loc["test", "min"])
    sn = fa.groupby("split").snapshot_date.agg(["min", "max"])
    chk("features_attrition: train < val < test theo mốc",
        sn.loc["train", "max"] < sn.loc["val", "min"] and sn.loc["val", "max"] < sn.loc["test", "min"])
    pa = fe.groupby("split").is_anomaly.sum()
    chk("mỗi tập anomaly đều có mẫu dương", (pa > 0).all(), pa.to_dict())
    pn = fa.groupby("split").left_next_60d.sum()
    chk("mỗi tập attrition đều có mẫu dương", (pn.drop("embargo", errors="ignore") > 0).all(), pn.to_dict())
    rate = fe.is_anomaly.mean()
    chk("tỷ lệ bất thường trong khoảng 0,5%-3%", 0.005 <= rate <= 0.03, f"{rate:.4f}")
    return pd.DataFrame(res)


# ----------------------------------------------------------------------------------------------
# 12. XUẤT FILE
# ----------------------------------------------------------------------------------------------
def _flat_cfg(d, p=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _flat_cfg(v, p + k + ".")
        else:
            yield p + k, (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)


def _style(ws):
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    for i, col in enumerate(ws.columns, 1):
        w = max((len(str(c.value)) if c.value is not None else 0) for c in list(col)[:200])
        ws.column_dimensions[get_column_letter(i)].width = min(max(10, w + 2), 70)


def build_readme(T, val):
    L = [f"# Bộ dữ liệu mô phỏng: {CFG['chain_name']}", "",
         f"- Giai đoạn: {CFG['start']} → {CFG['end']} (seed = {CFG['seed']}, chạy lại cho kết quả giống hệt).",
         "- Đây là dữ liệu MÔ PHỎNG. Tên người, tên chuỗi và mọi tham số lương/bảo hiểm/thuế đều là giả định.",
         "- 5 nhân viên có is_real_face = 1 là ô vị trí dành cho thành viên nhóm, cần thay bằng dữ liệu thật.", "",
         "## Các bảng", ""]
    for grp, tbs in T.items():
        for n, df in tbs.items():
            L.append(f"- `{grp}/{n}` ({len(df):,} dòng x {df.shape[1]} cột): {TABLE_DESC.get(n, '')}")
    S = CFG["splits"]
    L += ["", "## Cách chia tập (theo thời gian, không xáo trộn)", "",
          f"- Anomaly và staffing: train đến {S['event_train_end']}, val đến {S['event_val_end']}, test phần còn lại.",
          f"- Attrition: train đến mốc {S['attr_train_last_snapshot']}, val {S['attr_val_first']} đến {S['attr_val_last']}, "
          f"test từ {S['attr_test_first']}, các mốc ở giữa gán 'embargo' (không dùng) vì nhãn nhìn trước {S['horizon_days']} ngày.", "",
          "## Lưu ý tránh rò rỉ nhãn", "",
          "- Không đưa `anomaly_type` và `is_anomaly` vào đặc trưng của model gian lận.",
          "- Không đưa `employee_latent_traits` vào huấn luyện, đây là tham số nền dùng để sinh dữ liệu.",
          "- `attendance_daily` và `payroll` là sự thật nền; bất thường chỉ chèn vào `attendance_events`.", "",
          "## Kết quả kiểm tra toàn vẹn", "",
          f"- Đạt {int(val.passed.sum())}/{len(val)} kiểm tra."]
    L += [f"- KHÔNG ĐẠT: {r.check} ({r.detail})" for r in val[~val.passed].itertuples()]
    return "\n".join(L)


def export_all(T, out, make_zip=True):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dd = data_dictionary(T)
    val = validate(T)
    readme = build_readme(T, val)
    # CSV (+ Parquet nếu có pyarrow)
    for grp, tbs in T.items():
        (out / grp).mkdir(exist_ok=True)
        for name, df in tbs.items():
            df.to_csv(out / grp / f"{name}.csv", index=False, encoding="utf-8-sig")
            try:
                df.to_parquet(out / grp / f"{name}.parquet", index=False)
            except Exception as ex:
                if name == "branches":
                    print("Bỏ qua Parquet:", type(ex).__name__)
    dd.to_csv(out / "data_dictionary.csv", index=False, encoding="utf-8-sig")
    val.to_csv(out / "validation_report.csv", index=False, encoding="utf-8-sig")
    (out / "README_dataset.md").write_text(readme, encoding="utf-8")
    # Excel tổng quan
    summary = pd.DataFrame([dict(group=g, table=n, rows=len(df), cols=df.shape[1], description=TABLE_DESC.get(n, ""))
                            for g, tbs in T.items() for n, df in tbs.items()])
    cfg = pd.DataFrame(list(_flat_cfg(CFG)), columns=["parameter", "value"])
    with pd.ExcelWriter(out / "cafe_hr_overview.xlsx", engine="openpyxl",
                        datetime_format="yyyy-mm-dd hh:mm", date_format="yyyy-mm-dd") as w:
        pd.DataFrame({"README": readme.splitlines()}).to_excel(w, sheet_name="README", index=False)
        summary.to_excel(w, sheet_name="summary", index=False)
        cfg.to_excel(w, sheet_name="config", index=False)
        T["clean"]["holidays"].to_excel(w, sheet_name="holidays", index=False)
        T["clean"]["branches"].to_excel(w, sheet_name="branches", index=False)
        T["clean"]["shifts"].to_excel(w, sheet_name="shifts", index=False)
        dd.to_excel(w, sheet_name="data_dictionary", index=False)
        val.to_excel(w, sheet_name="validation", index=False)
        for n in ["employees", "attendance_daily", "attendance_events", "payroll"]:
            T["clean"][n].head(300).to_excel(w, sheet_name=f"sample_{n}"[:31], index=False)
        for ws in w.book.worksheets:
            _style(ws)
    # Zip (loại thư mục internal để tránh lộ đáp án nền)
    if make_zip:
        zp = out.parent / f"{out.name}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in out.rglob("*"):
                if f.is_file() and "internal" not in f.relative_to(out).parts:
                    z.write(f, f.relative_to(out.parent))
        print("Zip:", zp)
    return dd, val


import argparse
from pathlib import Path
import pandas as pd

def main():
    # 1. Khởi tạo ArgumentParser với các tham số của bạn
    parser = argparse.ArgumentParser(description="Kiểm tra và xử lý dữ liệu")
    parser.add_argument('--out', type=str, default='output_folder', help='Thư mục đầu ra')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('--no-zip', action='store_true', help='Không nén file')

    # 2. Dùng parse_known_args() để Colab tự động bỏ qua các tham số kết nối Jupyter (-f ...)
    a, unknown = parser.parse_known_args()

    # --- GIẢ LẬP DỮ LIỆU ĐỂ CODE KHÔNG BỊ LỖI KHI CHẠY THỬ ---
    # (Bạn có thể thay thế bằng DataFrame thực tế của bạn)
    val = pd.DataFrame({
        'passed': [True, False, True],
        'check': ['', 'Check_Null', ''],
        'detail': ['', 'Cột bị thiếu giá trị', '']
    })
    
    dd = pd.DataFrame({
        'description': ['Mô tả 1', '(chưa mô tả)', 'Mô tả 3'],
        'column': ['col_A', 'col_B', 'col_C']
    })
    # --------------------------------------------------------

    # 3. Đoạn code gốc của bạn
    print(f"\nKiểm tra toàn vẹn: {int(val.passed.sum())}/{len(val)} đạt")
    for r in val[~val.passed].itertuples():
        print("  KHÔNG ĐẠT:", r.check, "|", r.detail)
        
    miss = dd[dd.description == "(chưa mô tả)"]
    if len(miss):
        print("Cột chưa có mô tả:", sorted(set(miss.column)))
        
    print("Đã xuất vào:", Path(a.out).resolve())

if __name__ == '__main__':
    main()