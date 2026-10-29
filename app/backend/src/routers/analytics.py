from pathlib import Path
import pandas as pd
from fastapi import APIRouter

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
DATA = Path(__file__).resolve().parents[4] / "data" / "clean"


def _load():
    daily = pd.read_csv(DATA / "attendance_daily.csv", parse_dates=["work_date"])
    events = pd.read_csv(DATA / "attendance_events.csv", parse_dates=["ts"])
    branches = pd.read_csv(DATA / "branches.csv")
    return daily, events, branches


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
