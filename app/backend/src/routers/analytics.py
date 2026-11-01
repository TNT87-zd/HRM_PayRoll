from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, datetime
from pathlib import Path
import pandas as pd

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Trỏ đúng đường dẫn đến file CSV gốc của dự án
CSV_FILE = Path(__file__).resolve().parents[4] / "data" / "clean" / "attendance_events.csv"

def load_attendance_data():
    """Đọc dữ liệu chấm công thực tế từ CSV"""
    if not CSV_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(CSV_FILE)
        return df
    except Exception:
        return pd.DataFrame()

# 1. API Tổng quan (Summary)
@router.get("/summary")
async def get_summary():
    df = load_attendance_data()
    today_str = date.today().strftime("%Y-%m-%d")
    
    if df.empty:
        return {
            "date": today_str,
            "total_employees": 0,
            "present": 0,
            "late": 0,
            "absent": 0
        }
    
    # Lọc các lượt quét hôm nay
    df['date_only'] = df['timestamp'].str.slice(0, 10)
    today_df = df[df['date_only'] == today_str]
    
    present_ids = today_df['employee_id'].unique()
    present_count = len(present_ids)
    
    # Đếm số lượt bị trễ
    late_df = today_df[today_df['status_msg'].str.contains("Đi trễ|Trễ", na=False)]
    late_count = len(late_df['employee_id'].unique())
    
    return {
        "date": date.today().strftime("%d/%m/%Y"),
        "total_employees": max(present_count + 5, 10), # Giả định tổng NV
        "present": present_count,
        "late": late_count,
        "absent": max(10 - present_count, 0)
    }

# 2. API Biểu đồ tròn: Tỷ lệ trạng thái (Status Share)
@router.get("/status-share")
async def get_status_share():
    df = load_attendance_data()
    if df.empty:
        return {"labels": ["Đúng giờ", "Trễ 1-5p", "Trễ >15p", "Vắng"], "values": [0, 0, 0, 0]}
    
    on_time = len(df[df['status_msg'].str.contains("Đúng giờ", na=False)])
    late = len(df[df['status_msg'].str.contains("Đi trễ|Trễ", na=False)])
    
    return {
        "labels": ["Đúng giờ", "Trễ", "Vắng"],
        "values": [on_time, late, 0]
    }

# 3. API Biểu đồ đường: Lượt chấm công theo ngày
@router.get("/by-date")
async def get_by_date():
    df = load_attendance_data()
    if df.empty:
        return {"labels": [], "present": [], "late": []}
    
    df['date_only'] = df['timestamp'].str.slice(0, 10)
    grouped = df.groupby('date_only')
    
    labels = []
    present_list = []
    late_list = []
    
    for dt, group in grouped:
        labels.append(dt)
        present_list.append(len(group['employee_id'].unique()))
        late_list.append(len(group[group['status_msg'].str.contains("Đi trễ|Trễ", na=False)]))
        
    return {
        "labels": labels[-7:], # Lấy 7 ngày gần nhất
        "present": present_list[-7:],
        "late": late_list[-7:]
    }

# 4. API Biểu đồ cột ngang: Đi trễ theo chi nhánh
@router.get("/by-branch")
async def get_by_branch():
    return {
        "labels": ["CN Hải Châu", "CN Thanh Khê", "CN Sơn Trà"],
        "values": [12.5, 8.0, 15.0]
    }

# 5. API Top 10 nhân viên đi trễ
@router.get("/late-top")
async def get_late_top():
    df = load_attendance_data()
    if df.empty:
        return {"labels": [], "values": []}
        
    late_df = df[df['status_msg'].str.contains("Đi trễ|Trễ", na=False)]
    if late_df.empty:
        return {"labels": [], "values": []}
        
    top_late = late_df['employee_id'].value_counts().head(5)
    return {
        "labels": top_late.index.tolist(),
        "values": top_late.values.tolist()
    }

# 6. API Meta
@router.get("/meta")
async def get_meta():
    return {
        "branches": [
            {"id": "CN01", "name": "CN Hải Châu"},
            {"id": "CN02", "name": "CN Thanh Khê"}
        ],
        "min_date": "2026-01-01",
        "max_date": "2026-12-31"
    }

# 7. API Heatmap
@router.get("/heatmap")
async def get_heatmap(branch_id: Optional[str] = Query(None)):
    return {
        "dates": ["28/10", "29/10", "30/10", "31/10", "01/11"],
        "rows": [
            {"id": "NV0002", "name": "Nhân viên mẫu", "values": [0, 0, 0, 0, 15]}
        ]
    }

# 8. API Bảng chi tiết chấm công (Đọc dữ liệu thật từ CSV)
@router.get("/attendance")
async def get_attendance(
    branch_id: Optional[str] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    only_late: Optional[bool] = Query(False)
):
    df = load_attendance_data()
    if df.empty:
        return {"total": 0, "rows": []}
        
    rows = []
    for idx, row in df.iterrows():
        rows.append({
            "work_date": str(row.get('timestamp', ''))[:10],
            "employee_id": str(row.get('employee_id', '')),
            "full_name": f"Nhân viên ({row.get('employee_id', '')})",
            "branch_name": "CN Hải Châu",
            "shift_id": row.get('scan_type', 'IN'),
            "check_in_ts": str(row.get('timestamp', '')),
            "check_out_ts": "-",
            "late_minutes": 0,
            "worked_hours": 0,
            "ot_hours": 0,
            "status": str(row.get('status_msg', 'Hợp lệ'))
        })
        
    return {
        "total": len(rows),
        "rows": rows[::-1] # Hiện lượt mới nhất lên đầu
    }