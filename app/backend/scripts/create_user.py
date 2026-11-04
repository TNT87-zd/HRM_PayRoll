"""Create a local account in main's database. Never overwrite an existing account."""
import argparse
import getpass
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqlalchemy import select
from config import Settings
from database import Base, open_database
from models import User, UserEmployee, Employee
from routers.auth import hash_password


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--username',required=True)
    p.add_argument('--role',choices=['hr','manager','employee','kiosk'],required=True)
    p.add_argument('--employee-id')
    a=p.parse_args()
    if a.role=='employee' and not a.employee_id:
        p.error('Nhân viên cần --employee-id')
    password=getpass.getpass('Mật khẩu (12–128 ký tự): ')
    if not 12<=len(password)<=128 or password!=getpass.getpass('Nhập lại mật khẩu: '):
        p.error('Mật khẩu không hợp lệ hoặc không khớp')
    from schemas import Credentials
    Credentials(username=a.username,password=password)
    settings=Settings();settings.storage_dir.mkdir(parents=True,exist_ok=True)
    engine,factory=open_database(settings.database_url)
    Base.metadata.create_all(engine)
    with factory.begin() as db:
        if db.scalar(select(User).where(User.username==a.username)):
            p.error('Tên tài khoản đã tồn tại; không ghi đè')
        if a.employee_id and not db.get(Employee,a.employee_id):
            p.error('Mã nhân viên chưa tồn tại; tạo hồ sơ trước')
        if a.employee_id and db.scalar(select(UserEmployee).where(UserEmployee.employee_id==a.employee_id)):
            p.error('Nhân viên đã có tài khoản liên kết')
        user=User(username=a.username,password_hash=hash_password(password),role=a.role)
        db.add(user);db.flush()
        if a.employee_id: db.add(UserEmployee(user_id=user.id,employee_id=a.employee_id))
    engine.dispose()
    print('Đã tạo tài khoản:',a.username)

if __name__=='__main__': main()
