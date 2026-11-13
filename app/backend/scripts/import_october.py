"""Run with the application stopped. Uses HRM_DB_URL / HRM_DATA_DIR normally."""
import sys
import sqlite3
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqlalchemy.engine import make_url
from config import Settings
from database import open_database
from hrm import store
from hrm.october_import import import_october

def main():
    cfg=Settings(); url=make_url(cfg.database_url)
    if url.get_backend_name()!='sqlite' or not url.database or url.database==':memory:':
        raise SystemExit('Trình nhập này chỉ hỗ trợ SQLite có file, đúng cấu hình dự án.')
    source=Path(url.database).resolve()
    if not source.is_file(): raise SystemExit('Không thấy CSDL. Khởi động ứng dụng một lần trước khi nhập.')
    folder=cfg.data_dir/'backups'; folder.mkdir(parents=True,exist_ok=True)
    backup=folder/('before_october_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.sqlite3')
    with sqlite3.connect(str(source)) as src,sqlite3.connect(str(backup)) as dest: src.backup(dest)
    engine,factory=open_database(cfg.database_url); token=store.context.set((factory,cfg))
    try:
        result=import_october()
        print('Backup:',backup)
        print(result)
        print('Mo portal.html?month=2026-10#attendance; sau do #salary de tinh luong.')
    finally:
        store.context.reset(token); engine.dispose()

if __name__=='__main__': main()
