from fastapi import APIRouter, Query
from typing import Optional
from datetime import date

# Khởi tạo router
router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# 1. API Tổng quan (Summary)
@router.get("/summary")
async def get_summary():
    # TODO: Truy vấn COUNT từ database dựa trên ngày hôm nay
    return {
        "date": "01/11/2026",
        "total_employees": 120,
        "present": 95,
        "late": 15,
        "absent": 10
    }

# 2. API Biểu đồ tròn: Tỷ lệ trạng thái (Status Share)
@router.get("/status-share")
async def get_status_share():
    # Màu sắc Frontend đã fix: Đúng giờ, Trễ, Vắng, Khác...
    return {
        "labels": ["Đúng giờ", "Trễ 1-5p", "Trễ >15p", "Vắng"],
        "values": [70, 15, 10, 10]
    }

# 3. API Biểu đồ đường: Lượt chấm công theo ngày (By Date)
@router.get("/by-date")
async def get_by_date():
    return {
        "labels": ["25/10", "26/10", "27/10", "28/10", "29/10", "30/10", "31/10"],
        "present": [110, 112, 115, 111, 109, 114, 95],
        "late": [10, 8, 5, 9, 11, 6, 15]
    }

# 4. API Biểu đồ cột ngang: Đi trễ theo chi nhánh
@router.get("/by-branch")
async def get_by_branch():
    return {
        "labels": ["CN Hải Châu", "CN Thanh Khê", "CN Sơn Trà", "CN Cẩm Lệ"],
        "values": [15.5, 12.0, 22.5, 8.0] # Phút đi trễ trung bình
    }

# 5. API Top 10 nhân viên đi trễ
@router.get("/late-top")
async def get_late_top():
    return {
        "labels": ["NV012", "NV045", "NV003", "NV089", "NV102"],
        "values": [120, 95, 80, 75, 60] # Tổng số phút trễ
    }

# 6. API Meta: Dữ liệu bộ lọc (Lấy danh sách chi nhánh và giới hạn ngày)
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

# 7. API Heatmap: Bản đồ nhiệt chuyên cần
@router.get("/heatmap")
async def get_heatmap(
    branch_id: Optional[str] = Query(None)
):
    # Trả về ma trận: mỗi row là 1 nhân viên, mảng values tương ứng với mảng dates
    # value = 0 (Đúng giờ), value > 0 (Số phút trễ), value < 0 (Vắng)
    return {
        "dates": ["28/10", "29/10", "30/10", "31/10", "01/11"],
        "rows": [
            {"id": "NV01", "name": "Nguyễn Văn Nhẫn", "values": [0, 5, 0, -1, 20]},
            {"id": "NV02", "name": "Trương Nhật Trường", "values": [0, 0, 0, 0, 0]},
            {"id": "NV03", "name": "Nguyễn Hữu Tâm", "values": [15, 30, -1, 0, 5]},
        ]
    }

# 8. API Bảng chi tiết chấm công (có phân trang/lọc)
@router.get("/attendance")
async def get_attendance(
    branch_id: Optional[str] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    only_late: Optional[bool] = Query(False)
):
    # Trả về danh sách chi tiết để vẽ bảng html
    return {
        "total": 2, # Tổng số record thỏa mãn bộ lọc (để phân trang nếu cần)
        "rows": [
            {
                "work_date": "01/11/2026",
                "employee_id": "NV01",
                "full_name": "Nguyễn Văn Nhẫn",
                "branch_name": "CN Hải Châu",
                "shift_id": "Ca Sáng",
                "check_in_ts": "2026-11-01T07:15:00",
                "check_out_ts": "2026-11-01T12:05:00",
                "late_minutes": 15,
                "worked_hours": 4.5,
                "ot_hours": 0,
                "status": "Trễ"
            },
            {
                "work_date": "01/11/2026",
                "employee_id": "NV02",
                "full_name": "Trương Nhật Trường",
                "branch_name": "CN Hải Châu",
                "shift_id": "Ca Sáng",
                "check_in_ts": "2026-11-01T06:55:00",
                "check_out_ts": "2026-11-01T12:10:00",
                "late_minutes": 0,
                "worked_hours": 5.0,
                "ot_hours": 0.1,
                "status": "Đúng giờ"
            }
        ]
    }