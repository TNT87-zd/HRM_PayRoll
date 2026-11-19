"""Preview or consolidate the local operational data into Hải Châu (CN01)."""
import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sqlalchemy.engine import make_url
from config import PROJECT_ROOT, Settings
from hrm.admin_overview import BRANCH_ID
from hrm.payroll_reports import csv_bytes, workbook_bytes


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def normalize(value):
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: BRANCH_ID if key == 'branch_id' and item else normalize(item)
                for key, item in value.items()}
    return value


def file_changes(data_dir, used_devices):
    changed = {}
    for collection in ('clean', 'raw', 'attendance', 'live'):
        for path in (data_dir / collection).rglob('*.csv'):
            raw = path.read_bytes()
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
            if not reader.fieldnames or 'branch_id' not in reader.fieldnames:
                continue
            rows = list(reader)
            if path == data_dir / 'clean' / 'branches.csv':
                updated = [row for row in rows if row['branch_id'] == BRANCH_ID]
                if len(updated) != 1:
                    raise ValueError(f'Cần đúng một dòng {BRANCH_ID} trong {path.name}')
            elif path == data_dir / 'clean' / 'devices.csv':
                updated = [normalize(row) for row in rows
                           if row['branch_id'] == BRANCH_ID or row['device_id'] in used_devices]
            else:
                updated = normalize(rows)
            if updated != rows:
                out = io.StringIO(newline='')
                writer = csv.DictWriter(out, reader.fieldnames)
                writer.writeheader()
                writer.writerows(updated)
                changed[path] = out.getvalue().encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8')

    for manifest in data_dir.glob('*/operational/*/*/manifest.json'):
        original = json.loads(manifest.read_text(encoding='utf-8-sig'))
        updated = normalize(original)
        for member in updated.get('sha256', {}):
            collection, filename = member.replace('\\', '/').split('/')
            if collection not in ('clean', 'raw') or filename != Path(filename).name:
                raise ValueError(f'Đường dẫn trong manifest không hợp lệ: {member}')
            counterpart = data_dir / collection / 'operational' / manifest.parent.parent.name / manifest.parent.name / filename
            if counterpart in changed:
                updated['sha256'][member] = hashlib.sha256(changed[counterpart]).hexdigest()
        if updated != original:
            changed[manifest] = json_bytes(updated)

    for path in (data_dir / 'reports' / 'payroll').glob('*/*/*/payroll.json'):
        original = json.loads(path.read_text(encoding='utf-8-sig'))
        updated = normalize(original)
        if updated == original:
            continue
        files = {'payroll.json': json_bytes(updated), 'payroll.xlsx': workbook_bytes(updated),
                 'attendance.csv': csv_bytes(updated.get('attendance', []))}
        checksums = {name: hashlib.sha256(contents).hexdigest() for name, contents in files.items()}
        files['checksums.json'] = json_bytes(checksums)
        changed.update({path.with_name(name): contents for name, contents in files.items()})
    return changed


def replace_file(path, contents):
    temporary = path.with_name('.' + path.name + '.cn01.tmp')
    temporary.write_bytes(contents)
    os.replace(temporary, path)


def consolidate(db_path, data_dir, apply):
    uri = db_path.as_uri() + '?mode=' + ('rw' if apply else 'ro')
    with sqlite3.connect(uri, uri=True, timeout=30) as con:
        con.execute('PRAGMA foreign_keys=ON')
        if apply:
            con.execute('BEGIN IMMEDIATE')
        employees = con.execute('SELECT COUNT(*) FROM employees WHERE branch_id<>?', (BRANCH_ID,)).fetchone()[0]
        devices = {row[0] for row in con.execute('SELECT DISTINCT device_id FROM attendance_records')}
        changes = []
        for kind, key, payload in con.execute('SELECT kind,key,payload FROM hrm_records'):
            original = json.loads(payload)
            updated = normalize(original)
            if updated != original:
                changes.append((json_bytes(updated).decode('utf-8'), kind, key))
        files = file_changes(data_dir, devices)
        print(f'{BRANCH_ID}: {employees} hồ sơ nhân viên, {len(changes)} bản ghi nghiệp vụ, {len(files)} tệp cần cập nhật.')
        if not apply or not (employees or changes or files):
            return

        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = data_dir / 'backups' / f'before-cn01-{stamp}'
        backup.mkdir(parents=True)
        with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as source:
            with sqlite3.connect(backup / db_path.name) as destination:
                source.backup(destination)
        for path in files:
            original = backup / 'files' / path.relative_to(data_dir)
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, original)
        restored = []
        try:
            con.execute('UPDATE employees SET branch_id=? WHERE branch_id<>?', (BRANCH_ID, BRANCH_ID))
            con.executemany('UPDATE hrm_records SET payload=? WHERE kind=? AND key=?', changes)
            con.execute('INSERT INTO hrm_audit(ts,actor,action,payload) VALUES(?,?,?,?)', (
                datetime.now(timezone.utc).timestamp(), 'local_migration', 'branch_consolidation',
                json.dumps({'branch_id': BRANCH_ID, 'employee_count': employees, 'records_changed': len(changes)}),
            ))
            if con.execute('PRAGMA foreign_key_check').fetchone() or con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Kiểm tra tính toàn vẹn SQLite thất bại')
            for path, contents in files.items():
                replace_file(path, contents)
                restored.append(path)
            con.commit()
        except Exception:
            con.rollback()
            for path in reversed(restored):
                replace_file(path, (backup / 'files' / path.relative_to(data_dir)).read_bytes())
            raise
        print(f'Đã cập nhật. Sao lưu tại {backup}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Áp dụng sau khi sao lưu. Mặc định chỉ xem trước.')
    args = parser.parse_args()
    settings = Settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != 'sqlite' or not url.database:
        parser.error('Cấu hình cần trỏ tới file SQLite của dự án')
    db_path = Path(url.database).resolve()
    data_dir = settings.data_dir.resolve()
    if not db_path.is_relative_to(PROJECT_ROOT) or not data_dir.is_relative_to(PROJECT_ROOT):
        parser.error('Chỉ cập nhật dữ liệu trong workspace của dự án')
    consolidate(db_path, data_dir, args.apply)
