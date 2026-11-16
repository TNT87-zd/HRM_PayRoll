"""Explicit review/import of reusable configurations. No scans, shifts or payroll are changed."""
import argparse
import copy
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from config import Settings
from hrm import store
from hrm.payroll_configuration import resolve,save_profile,month_value


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    draft=sub.add_parser('draft')
    draft.add_argument('--from-month',required=True)
    draft.add_argument('--valid-from',required=True)
    draft.add_argument('--valid-until',required=True)
    draft.add_argument('--profile-id',required=True)
    draft.add_argument('--out',required=True)
    imp=sub.add_parser('import')
    imp.add_argument('--file',required=True)
    imp.add_argument('--reviewed-by',required=True)
    imp.add_argument('--confirm-contracts',action='store_true')
    check=sub.add_parser('check');check.add_argument('--month',required=True)
    args=parser.parse_args();settings=Settings();url=make_url(settings.database_url)
    if url.get_backend_name()!='sqlite' or not url.database or url.database==':memory:':
        raise ValueError('Cần SQLite trên đĩa')
    dbpath=Path(url.database).resolve(strict=True)
    print('SQLite:',dbpath)
    # rw refuses to create missing databases; ro is used for draft/check.
    mode='rw' if args.command=='import' else 'ro'
    engine=create_engine('sqlite://',creator=lambda:sqlite3.connect(dbpath.as_uri()+'?mode='+mode,uri=True,timeout=30))
    try:
        if args.command=='import':
            if not args.confirm_contracts: raise ValueError('Cần rà soát hợp đồng rồi thêm --confirm-contracts')
            profile=json.loads(Path(args.file).read_text(encoding='utf-8-sig'))
            if profile.get('reviewed') is not True: raise ValueError('Sau khi rà soát, sửa reviewed thành true trong JSON')
            backup=settings.data_dir/'backups'/('payroll_config_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.sqlite3')
            backup.parent.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(backup) as target:
                source.backup(target)
            print('Backup:',backup)
            with engine.connect() as connection:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
                with Session(bind=connection) as con:
                    value=save_profile(con,profile,args.reviewed_by)
                    con.flush()
                connection.commit()
            print('Đã lưu cấu hình:',value['profile_id'],value['valid_from'],'->',value['valid_until'])
        else:
            with engine.connect() as connection:
                connection.exec_driver_sql('BEGIN')
                with Session(bind=connection) as con:
                    if args.command=='draft':
                        for m in (args.from_month,args.valid_from,args.valid_until):month_value(m)
                        if args.valid_from>args.valid_until:raise ValueError('Khoảng hiệu lực bị đảo ngược')
                        cfg=copy.deepcopy(store.get(con,'payroll_config',args.from_month))
                        if not cfg: raise ValueError('Không có payroll_config cho tháng nguồn')
                        original=copy.deepcopy(cfg)
                        for c in cfg['contracts'].values():
                            c['valid_from']=args.valid_from;c['valid_until']=args.valid_until
                        value=dict(profile_id=args.profile_id,valid_from=args.valid_from,valid_until=args.valid_until,
                            reviewed=False,configuration=cfg,origin_month=args.from_month,
                            origin_source=original.get('source'),
                            review_note='BẢN NHÁP: ngày hiệu lực mới là đề xuất, không phải tự gia hạn hợp đồng. Kiểm tra từng hợp đồng, giờ PT, phụ thuộc, khoản phụ cấp và chính sách. Nguồn giả định tháng 10 được giữ lại.',
                            original_configuration=original)
                        out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
                        with out.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
                        print('Đã tạo bản nháp, CHƯA ghi CSDL:',out)
                    else:
                        cfg=resolve(con,args.month)
                        policy=cfg['payroll_2026_policy']
                        month_value(args.month)
                        if not policy['supported_from']<=args.month<=policy['supported_until']:
                            raise ValueError('Chính sách chưa hỗ trợ kỳ này')
                        print('Nguồn:',cfg.get('source'),'| Số hợp đồng:',len(cfg['contracts']))
                        bad=[eid for eid,c in cfg['contracts'].items() if not c.get('valid_from','9999')<=args.month<=c.get('valid_until','0000')]
                        if bad:raise ValueError('Hợp đồng hết/chưa hiệu lực: '+', '.join(bad))
                        print('Hiệu lực cấu hình hợp lệ. Công, lịch ca và dữ liệu nhân viên vẫn được kiểm tra khi bấm Tính lương.')
                connection.rollback()
    finally:engine.dispose()

if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError,FileExistsError) as exc:raise SystemExit(str(exc))
