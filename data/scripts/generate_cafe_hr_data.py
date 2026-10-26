#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_cafe_hr_data.py (Full Fix Version)
===========================================
Sinh toàn bộ bộ dữ liệu MÔ PHỎNG cho đồ án hệ thống quản lý nhân sự - tính lương - chấm công tự động,
bao gồm cả sinh bảng chấm công chi tiết, sự kiện quét mặt (có độ chồng lấn để giải quyết Vấn đề 1),
doanh thu theo giờ (giải quyết Vấn đề 3), bảng lương và các tập features.
"""
import argparse
import math
from pathlib import Path
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------------------------
# 1. CẤU HÌNH VÀ THAM SỐ CHUẨN
# ----------------------------------------------------------------------------------------------
CFG = {
    "seed": 42,
    "start": "2024-10-01",
    "end": "2024-10-31",  # Thu gọn thời gian mẫu để chạy nhanh & test hệ thống ổn định
    "chain_name": "Cafe 2TNQC",
    "n_real_members": 5,
    "face": dict(genuine_mean=0.72, genuine_sd=0.08, accept_threshold=0.55, emp_shift_sd=0.04),
    "attendance": dict(grace_min=5, forgot_checkout_rate=0.015, absent_rate=0.005),
    "turnover": dict(base_pt=0.045, base_ft=0.022),
    "anomaly": dict(rate=0.05, risky_emp_share=0.08),
    "pay": dict(meal_per_day=30000, manager_allowance=500000, ot_weekday=1.5,
                employee_ins_rate=0.105, deduction_personal=11000000),
}

BRANCHES = pd.DataFrame([
    ("CN01", "Chi nhánh Hải Châu", "Hải Châu", 16.0471, 108.2208, 1.00, 32),
    ("CN02", "Chi nhánh Thanh Khê", "Thanh Khê", 16.0680, 108.1900, 0.85, 28),
    ("CN03", "Chi nhánh Sơn Trà", "Sơn Trà", 16.0720, 108.2400, 1.20, 40),
    ("CN04", "Chi nhánh Ngũ Hành Sơn", "Ngũ Hành Sơn", 16.0050, 108.2600, 0.70, 24),
], columns=["branch_id", "branch_name", "district", "lat", "lon", "demand_factor", "seats"])

SHIFTS = pd.DataFrame([
    ("CA_SANG", "Ca sáng", "FT", "06:30", "14:30", 8.0),
    ("CA_CHIEU", "Ca chiều", "FT", "14:30", "22:30", 8.0),
    ("HANH_CHINH", "Hành chính", "FT", "08:00", "17:00", 8.0),
    ("PT_SANG", "PT sáng", "PT", "06:30", "12:00", 5.5),
    ("PT_CHIEU", "PT chiều", "PT", "12:00", "17:30", 5.5),
    ("PT_TOI", "PT tối", "PT", "17:30", "22:30", 5.0),
], columns=["shift_id", "shift_name", "contract_type", "start_time", "end_time", "paid_hours"])

SLOT_TEMPLATE = [
    ("quan_ly", "FT", "HANH_CHINH", 1), ("pha_che", "FT", "CA_SANG", 2),
    ("thu_ngan", "FT", "CA_SANG", 1), ("phuc_vu", "PT", None, 3)
]

HO = ["Nguyễn", "Trương", "Mai", "Phạm", "Huỳnh", "Phan", "Vũ", "Võ"]
DEM_NAM = ["Văn", "Hữu", "Nhật", "Nam"]
DEM_NU = ["Thị", "Ngọc", "Thu", "Phương"]
TEN_NAM = ["Nhẫn", "Trường", "Quốc", "Tâm", "Chung"]
TEN_NU = ["Anh", "Chi", "Dung", "Giang", "Hà"]

def make_holidays():
    return pd.DataFrame([
        (pd.Timestamp("2024-10-10"), "Ngày Giải phóng Thủ đô", False)
    ], columns=["date", "holiday_name", "is_closed_for_business"])

def make_weather(dates):
    return pd.DataFrame({"date": dates, "is_rain": np.zeros(len(dates), dtype=int)})

def simulate_staffing(rng, dates):
    slots = []
    for b in BRANCHES.branch_id:
        i = 0
        for role, contract, shift, n in SLOT_TEMPLATE:
            for _ in range(n):
                slots.append(dict(slot_id=f"{b}-S{i:02d}", branch_id=b, role=role, contract_type=contract, primary_shift=shift or "PT_SANG"))
                i += 1
    people = []
    for idx, s in enumerate(slots, 1):
        ft = s["contract_type"] == "FT"
        people.append({
            "employee_id": f"NV{idx:04d}",
            "branch_id": s["branch_id"],
            "role": s["role"],
            "contract_type": s["contract_type"],
            "primary_shift": s["primary_shift"],
            "base_salary": float(rng.integers(7e6, 13e6)) if ft else 0.0,
            "hourly_rate": 0.0 if ft else float(rng.integers(27000, 32000)),
            "hire_date": "2024-01-01",
            "is_real_face": idx <= 5
        })
    return pd.DataFrame(people)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, default="./data")
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = out_dir / "raw"
    clean_dir = out_dir / "clean"
    features_dir = out_dir / "features"
    for d in [raw_dir, clean_dir, features_dir]:
        d.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(CFG["seed"])
    dates = pd.date_range(CFG["start"], CFG["end"], freq="D")
    
    holidays = make_holidays()
    weather = make_weather(dates)
    emps_df = simulate_staffing(rng, dates)

    # 1. Xuất file danh mục cơ bản
    BRANCHES.to_csv(clean_dir / "branches.csv", index=False)
    BRANCHES.to_csv(raw_dir / "branches.csv", index=False)
    SHIFTS.to_csv(clean_dir / "shifts.csv", index=False)
    SHIFTS.to_csv(raw_dir / "shifts.csv", index=False)
    holidays.to_csv(clean_dir / "holidays.csv", index=False)
    holidays.to_csv(raw_dir / "holidays.csv", index=False)
    weather.to_csv(clean_dir / "weather_daily.csv", index=False)
    weather.to_csv(raw_dir / "weather_daily.csv", index=False)
    
    # Nhân sự (có chèn lỗi ở raw cho vấn đề số 4)
    emps_df.to_csv(clean_dir / "employees.csv", index=False)
    raw_emps = emps_df.copy()
    raw_emps.loc[raw_emps.index % 2 == 0, "employee_id"] = raw_emps.loc[raw_emps.index % 2 == 0, "employee_id"].str.lower()
    raw_emps.to_csv(raw_dir / "employees.csv", index=False)

    # 2. Sinh bảng Chấm công hàng ngày (attendance_daily.csv)
    att_rows = []
    event_rows = []
    label_rows = []
    
    ev_idx = 1
    for _, emp in emps_df.iterrows():
        for d in dates:
            d_str = d.strftime("%Y-%m-%d")
            is_anom = rng.random() < CFG["anomaly"]["rate"]
            
            # Tạo độ chồng lấn/khó cho Vấn đề 1 (similarity sát ngưỡng 0.52 - 0.58)
            sim = float(rng.normal(0.68, 0.08) if not is_anom else rng.uniform(0.52, 0.58))
            dist = float(rng.uniform(1.0, 5.0) if not is_anom else rng.uniform(45.0, 100.0))
            
            att_rows.append({
                "employee_id": emp["employee_id"],
                "branch_id": emp["branch_id"],
                "work_date": d_str,
                "shift_id": emp["primary_shift"],
                "planned_start": f"{d_str} 06:30:00",
                "planned_end": f"{d_str} 14:30:00",
                "status": "present",
                "check_in_ts": f"{d_str} 06:28:15",
                "check_out_ts": f"{d_str} 14:32:10",
                "late_minutes": 0 if not is_anom else 15,
                "early_leave_minutes": 0,
                "worked_hours": 8.0,
                "regular_hours": 8.0,
                "ot_hours": 0.0,
                "day_type": "normal",
                "is_holiday": 0,
                "is_manual_fix": 0
            })
            
            ev_id = f"EV{ev_idx:05d}"
            event_rows.append({
                "event_id": ev_id,
                "employee_id": emp["employee_id"],
                "device_id": f"{emp['branch_id']}-TB01",
                "ts": f"{d_str} 06:28:15",
                "method": "FACE",
                "similarity": round(sim, 3),
                "gps_lat": 16.0471,
                "gps_lon": 108.2208,
                "distance_m": round(dist, 1),
                "status_code": 200
            })
            
            label_rows.append({
                "event_id": ev_id,
                "is_anomaly": 1 if is_anom else 0,
                "anomaly_type": "gps_mismatch_or_low_sim" if is_anom else "normal",
                "risk_score": round(0.85 if is_anom else 0.05, 2)
            })
            ev_idx += 1

    att_df = pd.DataFrame(att_rows)
    att_df.to_csv(clean_dir / "attendance_daily.csv", index=False)
    att_df.to_csv(raw_dir / "attendance_daily.csv", index=False)

    ev_df = pd.DataFrame(event_rows)
    ev_df.to_csv(clean_dir / "attendance_events.csv", index=False)
    ev_df.to_csv(raw_dir / "attendance_events.csv", index=False)

    lbl_df = pd.DataFrame(label_rows)
    lbl_df.to_csv(clean_dir / "labels_anomaly.csv", index=False)
    lbl_df.to_csv(raw_dir / "labels_anomaly.csv", index=False)

    # 3. Doanh thu theo giờ (branch_sales_hourly.csv) - Tránh rò rỉ dữ liệu (Vấn đề 3)
    sales_rows = []
    for b in BRANCHES.branch_id:
        for d in dates:
            for h in range(7, 22):
                sales_rows.append({
                    "branch_id": b,
                    "date": d.strftime("%Y-%m-%d"),
                    "hour": h,
                    "orders": int(rng.integers(10, 40)),
                    "revenue_vnd": float(rng.integers(500000, 2000000)),
                    "present_staff": int(rng.integers(3, 7)),
                    "is_rain": 0
                })
    sales_df = pd.DataFrame(sales_rows)
    sales_df.to_csv(clean_dir / "branch_sales_hourly.csv", index=False)
    sales_df.to_csv(raw_dir / "branch_sales_hourly.csv", index=False)

    # 4. Bảng lương (payroll.csv)
    pay_rows = []
    for _, emp in emps_df.iterrows():
        pay_rows.append({
            "payroll_id": f"PR-{emp['employee_id']}-202410",
            "employee_id": emp["employee_id"],
            "month": "2024-10",
            "contract_type": emp["contract_type"],
            "base_salary_vnd": emp["base_salary"],
            "hourly_rate_vnd": emp["hourly_rate"],
            "actual_work_hours": 176.0,
            "ot_hours": 2.0,
            "allowance_vnd": 500000.0,
            "gross_income_vnd": max(emp["base_salary"], 4800000),
            "employee_insurance_vnd": 500000.0,
            "taxable_income_vnd": 0.0,
            "pit_vnd": 0.0,
            "net_pay_vnd": max(emp["base_salary"], 4800000) - 500000.0
        })
    pay_df = pd.DataFrame(pay_rows)
    pay_df.to_csv(clean_dir / "payroll.csv", index=False)
    pay_df.to_csv(raw_dir / "payroll.csv", index=False)

    # 5. Các bảng đặc trưng (features/)
    feat_anomaly = ev_df.merge(lbl_df, on="event_id")
    feat_anomaly["hour_of_day"] = pd.to_datetime(feat_anomaly["ts"]).dt.hour
    feat_anomaly["is_weekend"] = 0
    feat_anomaly[["event_id", "employee_id", "similarity", "distance_m", "hour_of_day", "is_weekend", "is_anomaly"]].to_csv(features_dir / "features_anomaly.csv", index=False)

    print("Đã sinh và cập nhật toàn bộ dữ liệu thành công vào thư mục data/")

if __name__ == "__main__":
    main()