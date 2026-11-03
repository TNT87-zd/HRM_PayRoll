import sys
from pathlib import Path

# Thêm đường dẫn tới thư mục src (nơi chứa package hrm)
ROOT_DIR = Path(__file__).resolve().parents[1] / "app" / "backend" / "src"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from hrm.manage import main

if __name__ == "__main__":
    main()