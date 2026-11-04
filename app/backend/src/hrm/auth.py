"""Compatibility URLs for Portal; authentication is owned by routers.auth."""
from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from models import UserEmployee
from routers import auth

router=APIRouter(prefix="/api/hrm/auth",tags=["HRM auth"])
router.add_api_route('/login',auth.login,methods=['POST'])
router.add_api_route('/logout',auth.logout,methods=['POST'])

def user(account=Depends(auth.require_user), con=Depends(get_db)):
    link=con.get(UserEmployee,account.id)
    if account.role == 'employee' and not link:
        raise HTTPException(403,'Tài khoản chưa được liên kết với nhân viên')
    if account.role not in {'hr','manager','employee'}:
        raise HTTPException(403,'Tài khoản kiosk chỉ được sử dụng màn hình chấm công')
    return dict(username=account.username,role='hr' if account.role in {'hr','manager'} else account.role,
                employee_id=link.employee_id if link else None)

def hr(u=Depends(user)):
    if u['role']!='hr':
        raise HTTPException(403,'Cần quyền HR hoặc quản lý')
    return u

@router.get('/me')
def me(u=Depends(user)):
    return u
