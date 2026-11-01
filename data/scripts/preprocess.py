#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preprocess.py
=============
Làm sạch dữ liệu: data/raw/  ->  data/clean/

Các bước: bỏ BOM, cắt khoảng trắng, viết hoa mã nhân viên (raw có dòng viết thường), ép kiểu ngày/giờ,
xóa dòng trùng hoàn toàn. RIÊNG attendance_events KHÔNG xóa trùng: các lượt quét lặp (burst_duplicate)
là hành vi bất thường có nhãn để mô hình học.

Chạy riêng:  python data/scripts/preprocess.py
"""
from pathlib import Path

import pandas as pd

TABLES = ["branches", "devices", "shifts", "holidays", "weather_daily", "employees", "leave_requests",
          "attendance_events", "attendance_daily", "payroll", "branch_sales_hourly", "labels_anomaly"]
DATE_COLS = {
    "holidays": ["date"], "weather_daily": ["date"], "employees": ["hire_date", "termination_date"],
    "leave_requests": ["start_date", "end_date", "submitted_date"], "attendance_events": ["ts"],
    "attendance_daily": ["work_date", "planned_start", "planned_end", "check_in_ts", "check_out_ts"],
    "branch_sales_hourly": ["date"],
}
NO_DEDUP = {"attendance_events"}


def write_csv(df, path):
    # UTF-8 KHÔNG BOM để pandas ở backend đọc đúng tên cột đầu tiên (employee_id, event_id...)
    df.to_csv(path, index=False, encoding="utf-8")


def clean_all(root):
    raw, clean = Path(root) / "raw", Path(root) / "clean"
    clean.mkdir(parents=True, exist_ok=True)
    C, log = {}, []
    for name in TABLES:
        f = raw / f"{name}.csv"
        if not f.exists():
            print(f"  bỏ qua {name}: không có trong raw/")
            continue
        df = pd.read_csv(f, encoding="utf-8-sig")
        n0 = len(df)
        for c in df.select_dtypes(include=["object", "string"]).columns:
            df[c] = df[c].str.strip()
        if "employee_id" in df.columns:
            df["employee_id"] = df["employee_id"].str.upper()
        for c in DATE_COLS.get(name, []):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        if name not in NO_DEDUP:
            df = df.drop_duplicates()
        df = df.reset_index(drop=True)
        write_csv(df, clean / f"{name}.csv")
        C[name] = df
        log.append((name, n0, len(df), n0 - len(df)))
    print(f"[2] clean/: {len(C)} bảng")
    return C, pd.DataFrame(log, columns=["bảng", "dòng raw", "dòng sau làm sạch", "dòng bị loại"])


if __name__ == "__main__":
    clean_all(Path(__file__).resolve().parents[1])     # root = thư mục data/