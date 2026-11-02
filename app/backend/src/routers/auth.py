"""Local first-run setup and revocable HttpOnly login sessions."""
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert
from database import get_db
from models import Counter, LoginSession, User
from schemas import Credentials

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE = "hrm_session"


def client_address(request):
    return request.client.host if request.client else "unknown"


def local_setup_allowed(request):
    return client_address(request) in {"127.0.0.1", "::1"} and request.url.hostname in {"127.0.0.1", "::1", "localhost"}


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password, encoded):
    try:
        _, salt, _ = encoded.split("$")
        return hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def same_origin(request: Request):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.url.netloc:
            raise HTTPException(403, "Nguồn gửi yêu cầu không hợp lệ")


def require_hr(request: Request, db=Depends(get_db)):
    same_origin(request)
    token = request.cookies.get(COOKIE, "")
    login = db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
    user = db.get(User, login.user_id) if login and login.expires_at > time.time() else None
    if user is None or not user.enabled:
        raise HTTPException(401, "Vui lòng đăng nhập HR/quản lý")
    if user.role not in {"hr", "manager"}:
        raise HTTPException(403, "Cần quyền HR hoặc quản lý")
    return user


def set_login(request, response, db, user):
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                        expires_at=time.time() + request.app.state.settings.auth_ttl))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=request.app.state.settings.auth_ttl,
                        httponly=True, samesite="strict", secure=request.app.state.settings.secure_cookie)
    return {"username": user.username, "role": user.role}


@router.get("/status")
def status(request: Request, db=Depends(get_db)):
    return {"setup_required": db.scalar(select(User.id).limit(1)) is None,
            "local_setup_allowed": local_setup_allowed(request)}


@router.post("/setup")
def setup(payload: Credentials, request: Request, response: Response, db=Depends(get_db)):
    same_origin(request)
    if not local_setup_allowed(request):
        raise HTTPException(403, "Thiết lập tài khoản đầu tiên từ localhost")
    db.execute(insert(Counter).values(name="auth_setup", value=0).on_conflict_do_nothing())
    db.execute(update(Counter).where(Counter.name == "auth_setup").values(value=Counter.value + 1))
    if db.scalar(select(User.id).limit(1)) is not None:
        db.rollback()
        raise HTTPException(409, "Tài khoản quản trị đã được thiết lập")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role="manager")
    db.add(user)
    db.flush()
    return set_login(request, response, db, user)


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response, db=Depends(get_db)):
    same_origin(request)
    address, now = client_address(request), time.monotonic()
    attempts = request.app.state.login_attempts
    attempts[address] = [t for t in attempts.get(address, []) if now - t < 300]
    if len(attempts[address]) >= 10:
        raise HTTPException(429, "Thử lại sau 5 phút")
    user = db.scalar(select(User).where(User.username == payload.username))
    encoded = user.password_hash if user else request.app.state.dummy_password_hash
    valid = verify_password(payload.password, encoded)
    if not user or not user.enabled or not valid:
        attempts[address].append(now)
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng")
    attempts.pop(address, None)
    db.execute(delete(LoginSession).where(LoginSession.expires_at < time.time()))
    return set_login(request, response, db, user)


@router.get("/me")
def me(user=Depends(require_hr)):
    return {"username": user.username, "role": user.role}


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    same_origin(request)
    token = request.cookies.get(COOKIE, "")
    db.execute(delete(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    db.commit()
    response.delete_cookie(COOKIE)
    return {"ok": True}
