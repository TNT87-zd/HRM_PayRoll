#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preprocess.py
=============
Đọc dữ liệu thô từ data/raw/, thực hiện các bước làm sạch 
(chuẩn hóa định dạng, viết hoa mã nhân viên, xử lý thời gian, loại bỏ trùng lặp)
và xuất kết quả sang thư mục data/clean/.
"""
import os
import pandas as pd
from pathlib import Path

def clean_data():
    root = Path(__file__).resolve().parents[1] / "data"
    raw_dir = root / "raw"
    clean_dir = root / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)
    
    print("Đang tiến hành làm sạch dữ liệu từ thư mục raw/...")

    # 1. Làm sạch bảng nhân sự (employees.csv) - Khắc phục lỗi chữ hoa/thường ở raw
    emp_path = raw_dir / "employees.csv"
    if emp_path.exists():
        df_emp = pd.read_csv(emp_path)
        if "employee_id" in df_emp.columns:
            df_emp["employee_id"] = df_emp["employee_id"].astype(str).str.upper().str.strip()
        df_emp = df_emp.drop_duplicates()
        df_emp.to_csv(clean_dir / "employees.csv", index=False, encoding="utf-8-sig")

    # 2. Làm sạch bảng sự kiện chấm công (attendance_events.csv)
    att_path = raw_dir / "attendance_events.csv"
    if att_path.exists():
        df_att = pd.read_csv(att_path)
        if "employee_id" in df_att.columns:
            df_att["employee_id"] = df_att["employee_id"].astype(str).str.upper().str.strip()
        if "ts" in df_att.columns:
            df_att["ts"] = pd.to_datetime(df_att["ts"], errors="coerce")
        # Lưu ý: Theo nghiệp vụ, giữ lại các dòng trùng lặp loại burst_duplicate để model học bất thường (nếu có)
        df_att.to_csv(clean_dir / "attendance_events.csv", index=False, encoding="utf-8-sig")
        try:
            df_att.to_parquet(clean_dir / "attendance_events.parquet", index=False)
        except Exception:
            pass

    # 3. Làm sạch các bảng danh mục còn lại
    for file_name in ["branches.csv", "shifts.csv", "holidays.csv", "weather_daily.csv", "payroll.csv", "branch_sales_hourly.csv"]:
        f_path = raw_dir / file_name
        if f_path.exists():
            df = pd.read_csv(f_path)
            df = df.drop_duplicates()
            df.to_csv(clean_dir / file_name, index=False, encoding="utf-8-sig")

    print("Đã làm sạch và xuất dữ liệu sang data/clean/ thành công!")

if __name__ == "__main__":
    clean_data()