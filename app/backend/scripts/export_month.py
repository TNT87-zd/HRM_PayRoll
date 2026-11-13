"""Read a consistent SQLite snapshot and export one month. No database writes."""
import argparse
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from config import Settings
from hrm.data_snapshot import export_snapshot, month_bounds


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--month',required=True,help='YYYY-MM')
    args=parser.parse_args()
    month_bounds(args.month)
    settings=Settings()
    url=make_url(settings.database_url)
    if url.get_backend_name()!='sqlite' or not url.database or url.database==':memory:':
        raise SystemExit('Lenh nay chi ho tro SQLite luu tren dia.')
    path=Path(url.database).resolve(strict=True)
    print('SQLite:',path)
    engine=create_engine('sqlite://', creator=lambda:sqlite3.connect(path.as_uri()+'?mode=ro',uri=True))
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql('BEGIN')
            with Session(bind=connection) as con:
                folders, manifest=export_snapshot(con,settings.data_dir,args.month)
            connection.rollback()
        for folder in folders: print('Da xuat:',folder.resolve())
        print('Luot quet:',manifest['scan_count'],'| Ca:',manifest['shift_count'],'| Chua gan ca:',manifest['unassigned_count'])
        print('Bang luong:',manifest['payroll_status'])
    finally:
        engine.dispose()

if __name__=='__main__': main()
