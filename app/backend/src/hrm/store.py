import csv
import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

def database_path():
    return Path(os.environ.get('HRM_DB', str(ROOT / 'data/live/hrm.sqlite3')))

@contextmanager
def db(write=False):
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA foreign_keys=ON')
        if write:
            con.execute('BEGIN IMMEDIATE')
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def records(con, kind):
    return [json.loads(r[0]) for r in con.execute('SELECT payload FROM records WHERE kind=? ORDER BY id', (kind,))]

def get(con, kind, key):
    row = con.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, key)).fetchone()
    return json.loads(row[0]) if row else None

def put(con, kind, key, value):
    con.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload',
                (kind, key, json.dumps(value, ensure_ascii=False, allow_nan=False)))

def audit(con, actor, action, data):
    con.execute('INSERT INTO audit(actor,action,payload) VALUES(?,?,?)',
                (actor, action, json.dumps(data, ensure_ascii=False, allow_nan=False)))

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'{salt}:{digest}'

def init():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,password TEXT NOT NULL,role TEXT NOT NULL,employee_id TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,username TEXT NOT NULL REFERENCES users(username),expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,ts TEXT DEFAULT CURRENT_TIMESTAMP,actor TEXT,action TEXT,payload TEXT);
        ''')
    with db(True) as con:
        if not get(con, 'meta', 'imported'):
            p = ROOT / 'data/clean/employees.csv'
            if p.exists():
                with p.open(encoding='utf-8-sig', newline='') as f:
                    for r in csv.DictReader(f):
                        e = dict(employee_id=r['employee_id'], full_name=r.get('full_name') or r['employee_id'],
                                 branch_id=r['branch_id'], contract_type=r['contract_type'],
                                 base_salary=int(float(r.get('base_salary') or 0)), hourly_rate=int(float(r.get('hourly_rate') or 0)), active=True)
                        put(con, 'employees', e['employee_id'], e)
            put(con, 'meta', 'imported', {'done': True})
