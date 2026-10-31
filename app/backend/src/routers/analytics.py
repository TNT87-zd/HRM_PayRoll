import io
import os
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Định vị thư mục data/clean an toàn (hỗ trợ cả chạy qua app hoặc standalone)
try:
    from config import PROJECT_ROOT
    DATA = PROJECT_ROOT / "data" / "clean"
except Exception:
    DATA = Path(__file__).resolve().parents[4] / "data" / "clean"

COLS = [
    "work_date", "employee_id", "full_name", "branch_name", "shift_id", "status",
    "check_in_ts", "check_out_ts", "late_minutes", "early_leave_minutes",
    "worked_hours", "ot_hours"
]

VN = {
    "work_date": "Ngày", "employee_id": "Mã NV", "full_name": "Họ tên",
    "branch_name": "Chi nhánh", "shift_id": "Ca", "status": "Trạng thái",
    "check_in_ts": "Giờ vào", "check_out_ts": "Giờ ra", "late_minutes": "Phút trễ",
    "early_leave_minutes": "Phút về sớm", "worked_hours": "Giờ làm", "ot_hours": "Giờ OT"
}

STATUS_VN = {
    "present": "Có mặt",
    "absent": "Vắng",
    "leave": "Nghỉ phép",
    "on_leave": "Nghỉ phép",
    "holiday": "Nghỉ lễ",
}

ROLE_VN = {
    "quan_ly": "Quản lý",
    "pha_che": "Pha chế",
    "thu_ngan": "Thu ngân",
    "phuc_vu": "Phục vụ",
    "bao_ve": "Bảo vệ",
    "tap_vu": "Tạp vụ",
}

# Bộ đệm dữ liệu thông minh: tự động reload khi file CSV bị thay đổi mtime
_CACHE: Dict[str, Dict[str, Any]] = {}


def _get_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _load_daily() -> pd.DataFrame:
    p = DATA / "attendance_daily.csv"
    mtime = _get_mtime(p)
    if "daily" in _CACHE and _CACHE["daily"]["mtime"] == mtime:
        return _CACHE["daily"]["data"].copy()
    if not p.is_file():
        return pd.DataFrame()
    df = pd.read_csv(p, parse_dates=["work_date"])
    _CACHE["daily"] = {"mtime": mtime, "data": df}
    return df.copy()


def _load_branches() -> pd.DataFrame:
    p = DATA / "branches.csv"
    mtime = _get_mtime(p)
    if "branches" in _CACHE and _CACHE["branches"]["mtime"] == mtime:
        return _CACHE["branches"]["data"].copy()
    if not p.is_file():
        return pd.DataFrame()
    df = pd.read_csv(p)
    _CACHE["branches"] = {"mtime": mtime, "data": df}
    return df.copy()


def _load_events() -> pd.DataFrame:
    p = DATA / "attendance_events.csv"
    mtime = _get_mtime(p)
    if "events" in _CACHE and _CACHE["events"]["mtime"] == mtime:
        return _CACHE["events"]["data"].copy()
    if not p.is_file():
        return pd.DataFrame()
    df = pd.read_csv(p, parse_dates=["ts"])
    _CACHE["events"] = {"mtime": mtime, "data": df}
    return df.copy()


def _names() -> Dict[str, str]:
    p = DATA / "employees.csv"
    mtime = _get_mtime(p)
    if "names" in _CACHE and _CACHE["names"]["mtime"] == mtime:
        return _CACHE["names"]["data"]
    if not p.is_file():
        return {}
    try:
        e = pd.read_csv(p)
        col = next((c for c in ("full_name", "name", "ho_ten") if c in e.columns), None)
        if col and "employee_id" in e.columns:
            d = dict(zip(e["employee_id"], e[col].fillna("")))
        elif "role" in e.columns and "employee_id" in e.columns:
            role_title = e["role"].map(ROLE_VN).fillna(e["role"])
            d = dict(zip(e["employee_id"], role_title))
        else:
            d = {}
        _CACHE["names"] = {"mtime": mtime, "data": d}
        return d
    except Exception:
        pass
    return {}


def _filtered(branch_id: str | None = None, start: str | None = None,
              end: str | None = None, only_late: bool = False) -> pd.DataFrame:
    d = _load_daily()
    b = _load_branches()
    if d.empty:
        return pd.DataFrame(columns=COLS)

    if branch_id:
        d = d[d["branch_id"] == branch_id]

    if start:
        try:
            start_dt = pd.to_datetime(start)
            d = d[d["work_date"] >= start_dt]
        except (ValueError, TypeError):
            pass

    if end:
        try:
            end_dt = pd.to_datetime(end)
            d = d[d["work_date"] <= end_dt]
        except (ValueError, TypeError):
            pass

    if only_late:
        d = d[d["late_minutes"] > 0]

    if not b.empty and "branch_name" in b.columns:
        d = d.merge(b[["branch_id", "branch_name"]], on="branch_id", how="left")
    elif "branch_id" in d.columns:
        d["branch_name"] = d["branch_id"]
    else:
        d["branch_name"] = ""

    names = _names()
    d["full_name"] = d["employee_id"].map(names).fillna(d["employee_id"])

    for c in COLS:
        if c not in d.columns:
            d[c] = None

    return d.sort_values(["work_date", "employee_id"], ascending=[False, True])


@router.get("/meta")
def meta():
    d = _load_daily()
    b = _load_branches()

    branches = []
    if not b.empty and "branch_id" in b.columns and "branch_name" in b.columns:
        branches = [{"id": r.branch_id, "name": r.branch_name} for r in b.itertuples()]

    min_date = ""
    max_date = ""
    if not d.empty and "work_date" in d.columns:
        min_val = d["work_date"].min()
        max_val = d["work_date"].max()
        if pd.notna(min_val):
            min_date = str(min_val.date())
        if pd.notna(max_val):
            max_date = str(max_val.date())

    return {
        "branches": branches,
        "min_date": min_date,
        "max_date": max_date,
    }


@router.get("/summary")
def summary():
    d = _load_daily()
    if d.empty:
        return {
            "date": "",
            "total_employees": 0,
            "present": 0,
            "late": 0,
            "absent": 0,
        }

    last = d["work_date"].max()
    day = d[d["work_date"] == last]
    names = _names()
    total_employees = len(names) if names else int(d["employee_id"].nunique())

    return {
        "date": str(last.date()) if pd.notna(last) else "",
        "total_employees": total_employees,
        "present": int((day["status"] == "present").sum()),
        "late": int((day["late_minutes"] > 0).sum()),
        "absent": int((day["status"] == "absent").sum()),
    }


@router.get("/status-share")
def status_share():
    d = _load_daily()
    if d.empty:
        return {"labels": ["Đúng giờ", "Đi trễ"], "values": [0, 0]}

    present = d["status"] == "present"
    late = d["late_minutes"] > 0
    on_time_count = int((present & ~late).sum())
    late_count = int(late.sum())

    labels = ["Đúng giờ", "Đi trễ"]
    values = [on_time_count, late_count]

    # Các trạng thái còn lại (Vắng, Nghỉ phép...) được Việt hóa
    rest = d[~present & ~late]["status"].value_counts()
    for st, count in rest.items():
        st_vn = STATUS_VN.get(str(st).lower(), str(st))
        labels.append(st_vn)
        values.append(int(count))

    return {"labels": labels, "values": values}


@router.get("/late-top")
def late_top():
    d = _load_daily()
    if d.empty:
        return {"labels": [], "values": []}

    # Chỉ xếp hạng những nhân viên có số phút đi trễ > 0
    late_records = d[d["late_minutes"] > 0]
    if late_records.empty:
        return {"labels": [], "values": []}

    s = late_records.groupby("employee_id")["late_minutes"].sum().nlargest(10)
    names = _names()
    labels = []
    for emp in s.index:
        emp_str = str(emp)
        name = names.get(emp_str, "")
        labels.append(f"{emp_str} · {name}" if name else emp_str)
    return {"labels": labels, "values": s.astype(int).tolist()}


@router.get("/by-branch")
def by_branch():
    d = _load_daily()
    b = _load_branches()
    if d.empty:
        return {"labels": [], "values": []}

    g = d.groupby("branch_id")["late_minutes"].mean().round(1).reset_index()
    if not b.empty and "branch_id" in b.columns and "branch_name" in b.columns:
        # Dùng merge right để không bỏ sót chi nhánh chưa có dữ liệu chấm công
        g = b[["branch_id", "branch_name"]].merge(g, on="branch_id", how="left")
        g["late_minutes"] = g["late_minutes"].fillna(0.0)
    else:
        g["branch_name"] = g["branch_id"]

    return {"labels": g["branch_name"].tolist(), "values": g["late_minutes"].tolist()}


@router.get("/by-hour")
def by_hour():
    e = _load_events()
    if e.empty or "ts" not in e.columns:
        return {"labels": [], "values": []}
    s = e["ts"].dt.hour.value_counts().sort_index()
    return {"labels": [f"{h}h" for h in s.index], "values": s.astype(int).tolist()}


@router.get("/by-date")
def by_date():
    d = _load_daily()
    if d.empty or "work_date" not in d.columns:
        return {"labels": [], "present": [], "late": []}

    g = d.groupby("work_date").agg(
        present=("status", lambda s: int((s == "present").sum())),
        late=("late_minutes", lambda s: int((s > 0).sum())),
    )
    labels = pd.to_datetime(g.index).strftime("%d/%m").tolist()
    return {
        "labels": labels,
        "present": g["present"].tolist(),
        "late": g["late"].tolist(),
    }


@router.get("/heatmap")
def heatmap(branch_id: str | None = None):
    d = _load_daily()
    if d.empty:
        return {"dates": [], "rows": []}

    if branch_id:
        d = d[d["branch_id"] == branch_id]

    if d.empty:
        return {"dates": [], "rows": []}

    d = d.assign(v=d["late_minutes"].where(d["status"] == "present", -1))
    p = d.pivot_table(index="employee_id", columns="work_date", values="v", aggfunc="max")
    names = _names()
    rows = [
        {"id": str(emp), "name": names.get(str(emp), ""),
         "values": [None if pd.isna(x) else float(x) for x in r.tolist()]}
        for emp, r in p.iterrows()
    ]
    dates = pd.to_datetime(p.columns).strftime("%d/%m").tolist()
    return {"dates": dates, "rows": rows}


@router.get("/attendance")
def attendance(branch_id: str | None = None, start: str | None = None,
               end: str | None = None, only_late: bool = False, limit: int = 300):
    df = _filtered(branch_id, start, end, only_late)
    if df.empty:
        return {"total": 0, "rows": []}

    out = df[COLS].head(limit).copy()
    if "work_date" in out.columns and pd.api.types.is_datetime64_any_dtype(out["work_date"]):
        out["work_date"] = out["work_date"].dt.strftime("%Y-%m-%d")
    raw_rows = out.to_dict("records")
    rows = [
        {k: (None if pd.isna(v) else v) for k, v in r.items()}
        for r in raw_rows
    ]
    return {"total": int(len(df)), "rows": rows}


@router.get("/export")
def export(branch_id: str | None = None, start: str | None = None,
           end: str | None = None, only_late: bool = False):
    df = _filtered(branch_id, start, end, only_late)[COLS].copy()
    if not df.empty and "work_date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["work_date"]):
        df["work_date"] = df["work_date"].dt.strftime("%Y-%m-%d")
    df = df.rename(columns=VN)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Chấm công")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="cham_cong.xlsx"'},
    )
