"""Run from project root: python -m hrm.manage --username admin --role hr (via --app-dir not supported)."""
import argparse
import getpass
from hrm.store import init,db,password_hash,get,audit

def main():
    p=argparse.ArgumentParser(description='Tạo tài khoản HRM; không lưu mật khẩu mặc định')
    p.add_argument('--username',required=True)
    p.add_argument('--role',choices=['hr','employee','kiosk'],required=True)
    p.add_argument('--employee-id')
    a=p.parse_args()
    init()
    password=getpass.getpass('Mật khẩu (ít nhất 12 ký tự): ')
    if len(password)<12 or password!=getpass.getpass('Nhập lại mật khẩu: '):
        p.error('Mật khẩu quá ngắn hoặc không khớp')
    with db(True) as con:
        if a.role=='employee' and (not a.employee_id or not get(con,'employees',a.employee_id)):
            p.error('Nhân viên cần --employee-id tồn tại')
        if con.execute('SELECT 1 FROM users WHERE username=?',(a.username,)).fetchone():
            p.error('Tài khoản đã tồn tại; không ghi đè')
        con.execute('INSERT INTO users VALUES(?,?,?,?)',(a.username,password_hash(password),a.role,a.employee_id))
        audit(con,'local-cli','create_user',{'username':a.username,'role':a.role})
    print('Đã tạo tài khoản:',a.username)

if __name__=='__main__':
    main()
