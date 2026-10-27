from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]   # .../HRM_Payroll
DB_URL = f"sqlite:///{PROJECT_ROOT / 'hrm.db'}"

FACE_THRESHOLD = 0.55
FACE_MIN_MARGIN = 0.08
DUPLICATE_WINDOW_SEC = 60     # chống quét trùng
GEOFENCE_RADIUS_M = 50