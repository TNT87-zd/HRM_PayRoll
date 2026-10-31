import io
from pathlib import Path

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
DATA = Path(__file__).resolve().parents[4] / "data" / "clean"

COLS = ["work_date", "employee_id", "full_name", "branch_name", "shift_id", "status",
        "check_in_ts", "check_out_ts", "late_minutes", "early_leave_minutes",
        "worked_hours", "ot_hours"]
VN = {"work_date": "Ngày", "employee_id": "Mã NV", "full_name": "Họ tên",
      "branch_name": "Chi nhánh", "shift_id": "Ca", "status": "Trạng thái",
      "check_in_ts": "Giờ vào", "check_out_ts": "Giờ ra", "late_minutes": "Phút trễ",
      "early_leave_minutes": "Phút về sớm", "worked_hours": "Giờ làm", "ot_hours": "Giờ OT"}


def _load():
    daily = pd.read_csv(DATA / "attendance_daily.csv", parse_dates=["work_date"])
    events = pd.read_csv(DATA / "attendance_events.csv", parse_dates=["ts"])
    branches = pd.read_csv(DATA / "branches.csv")
    return daily, events, branches


def _names():
    try:
        e = pd.read_csv(DATA / "employees.csv")
        col = next((c for c in ("full_name", "name", "ho_ten") if c in e.columns), None)
        if col:
            return dict(zip(e["employee_id"], e[col]))
    except Exception:
        pass
    return {}


def _filtered(branch_id=None, start=None, end=None, only_late=False):
    d, _, b = _load()
    if branch_id:
        d = d[d["branch_id"] == branch_id]
    if start:
        d = d[d["work_date"] >= pd.to_datetime(start)]
    if end:
        d = d[d["work_date"] <= pd.to_datetime(end)]
    if only_late:
        d = d[d["late_minutes"] > 0]
    d = d.merge(b[["branch_id", "branch_name"]], on="branch_id", how="left")
    d["full_name"] = d["employee_id"].map(_names()).fillna("")
    return d.sort_values(["work_date", "employee_id"], ascending=[False, True])


@router.get("/meta")
def meta():
    d, _, b = _load()
    return {
        "branches": [{"id": r.branch_id, "name": r.branch_name} for r in b.itertuples()],
        "min_date": str(d["work_date"].min().date()),
        "max_date": str(d["work_date"].max().date()),
    }


@router.get("/summary")
def summary():
    d, _, _ = _load()
    last = d["work_date"].max()
    day = d[d["work_date"] == last]
    return {
        "date": str(last.date()),
        "total_employees": int(d["employee_id"].nunique()),
        "present": int((day["status"] == "present").sum()),
        "late": int((day["late_minutes"] > 0).sum()),
        "absent": int((day["status"] == "absent").sum()),
    }


@router.get("/status-share")
def status_share():
    d, _, _ = _load()
    present = d["status"] == "present"
    late = d["late_minutes"] > 0
    rest = d[~present & ~late]["status"].value_counts()
    return {
        "labels": ["Đúng giờ", "Đi trễ"] + rest.index.tolist(),
        "values": [int((present & ~late).sum()), int(late.sum())] + rest.tolist(),
    }


@router.get("/late-top")
def late_top():
    d, _, _ = _load()
    s = d.groupby("employee_id")["late_minutes"].sum().nlargest(10)
    return {"labels": s.index.tolist(), "values": s.tolist()}


@router.get("/by-branch")
def by_branch():
    d, _, b = _load()
    g = d.groupby("branch_id")["late_minutes"].mean().round(1).reset_index()
    g = g.merge(b[["branch_id", "branch_name"]], on="branch_id")
    return {"labels": g["branch_name"].tolist(), "values": g["late_minutes"].tolist()}


@router.get("/by-hour")
def by_hour():
    _, e, _ = _load()
    s = e["ts"].dt.hour.value_counts().sort_index()
    return {"labels": [f"{h}h" for h in s.index], "values": s.tolist()}


@router.get("/by-date")
def by_date():
    d, _, _ = _load()
    g = d.groupby("work_date").agg(
        present=("status", lambda s: int((s == "present").sum())),
        late=("late_minutes", lambda s: int((s > 0).sum())),
    )
    return {
        "labels": [x.strftime("%d/%m") for x in g.index],
        "present": g["present"].tolist(),
        "late": g["late"].tolist(),
    }


@router.get("/heatmap")
def heatmap(branch_id: str | None = None):
    d, _, _ = _load()
    if branch_id:
        d = d[d["branch_id"] == branch_id]
    d = d.assign(v=d["late_minutes"].where(d["status"] == "present", -1))
    p = d.pivot_table(index="employee_id", columns="work_date", values="v", aggfunc="max")
    names = _names()
    rows = [
        {"id": emp, "name": names.get(emp, ""),
         "values": [None if pd.isna(x) else float(x) for x in r.tolist()]}
        for emp, r in p.iterrows()
    ]
    return {"dates": [x.strftime("%d/%m") for x in p.columns], "rows": rows}


@router.get("/attendance")
def attendance(branch_id: str | None = None, start: str | None = None,
               end: str | None = None, only_late: bool = False, limit: int = 300):
    df = _filtered(branch_id, start, end, only_late)
    out = df[COLS].head(limit).copy()
    out["work_date"] = out["work_date"].dt.strftime("%Y-%m-%d")
    out = out.astype(object).where(out.notna(), None)
    return {"total": int(len(df)), "rows": out.to_dict("records")}


@router.get("/export")
def export(branch_id: str | None = None, start: str | None = None,
           end: str | None = None, only_late: bool = False):
    df = _filtered(branch_id, start, end, only_late)[COLS].copy()
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
