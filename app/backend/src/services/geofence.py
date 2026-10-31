import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

GEOFENCE_RADIUS_M = 50.0  # theo plan: lệch quá 50m là cảnh báo
_BRANCHES_CSV = Path(__file__).resolve().parents[4] / "data" / "clean" / "branches.csv"


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Khoảng cách (mét) giữa 2 toạ độ GPS."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _branch_coords() -> dict[str, tuple[float, float]]:
    df = pd.read_csv(_BRANCHES_CSV)
    return {str(r.branch_id): (float(r.lat), float(r.lon)) for r in df.itertuples()}


def branch_from_device(device_id: str) -> str:
    """'CN01-TB01' -> 'CN01'"""
    return device_id.split("-")[0]


def distance_to_branch(device_id: str, lat, lon):
    """Khoảng cách từ thiết bị đến chi nhánh; None nếu thiếu GPS hoặc không biết chi nhánh."""
    if lat is None or lon is None:
        return None
    coords = _branch_coords().get(branch_from_device(device_id))
    if coords is None:
        return None
    return haversine_m(lat, lon, coords[0], coords[1])
