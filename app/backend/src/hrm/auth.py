import hashlib
import hmac
import os
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from hrm.store import db, password_hash, audit

router = APIRouter(prefix='/api/hrm/auth', tags=['HRM auth'])
COOKIE = 'hrm_session'

def session_user(token):
    if not token:
        return None
    with db() as con:
        row = con.execute('SELECT u.username,u.role,u.employee_id FROM sessions s JOIN users u ON s.username=u.username WHERE s.token=? AND s.expires>?',
                          (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return dict(row) if row else None

def user(request: Request):
    u = session_user(request.cookies.get(COOKIE))
    if not u:
        raise HTTPException(401,'Vui lòng đăng nhập tại /portal.html')
    return u

def hr(u=Depends(user)):
    if u['role'] != 'hr':
        raise HTTPException(403,'Chỉ HR được thực hiện thao tác này')
    return u

def operator(u=Depends(user)):
    if u['role'] not in ('hr','kiosk'):
        raise HTTPException(403,'Cần tài khoản vận hành Kiosk')
    return u

class Login(BaseModel):
    username: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=1,max_length=256)

@router.post('/login')
def login(body: Login, response: Response):
    with db(True) as con:
        # Persisted per-user rate limit; no password is logged.
        failures = con.execute("SELECT COUNT(*) FROM audit WHERE actor=? AND action='login_failed' AND ts>datetime('now','-5 minutes')",(body.username,)).fetchone()[0]
        if failures >= 10:
            raise HTTPException(429,'Thử lại sau 5 phút')
        row = con.execute('SELECT * FROM users WHERE username=?',(body.username,)).fetchone()
        valid = row and hmac.compare_digest(password_hash(body.password,row['password'].split(':')[0]),row['password'])
        if not valid:
            audit(con,body.username,'login_failed',{})
        else:
            token = secrets.token_urlsafe(32)
            con.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            con.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),body.username,time.time()+8*3600))
            audit(con,body.username,'login',{})
    if not valid:
        raise HTTPException(401,'Sai tài khoản hoặc mật khẩu')
    response.set_cookie(COOKIE,token,httponly=True,samesite='strict',secure=os.environ.get('HRM_HTTPS')=='1',max_age=8*3600)
    return dict(username=row['username'],role=row['role'],employee_id=row['employee_id'])

@router.get('/me')
def me(u=Depends(user)):
    return u

@router.post('/logout')
def logout(request: Request,response: Response):
    token=request.cookies.get(COOKIE,'')
    with db(True) as con:
        con.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE)
    return {'ok':True}
