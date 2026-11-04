import hashlib
import time
import asyncio
from models import User, LoginSession
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        for ws in list(self.active):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(ws)

manager = ConnectionManager()

@router.websocket("/ws/events")
async def events(ws: WebSocket):
    def allowed():
        token=ws.cookies.get('hrm_session','')
        with ws.app.state.session_factory() as db:
            login=db.get(LoginSession,hashlib.sha256(token.encode()).hexdigest()) if token else None
            user=db.get(User,login.user_id) if login and login.expires_at>time.time() else None
            return bool(user and user.enabled and user.role in {'hr','manager'})
    if not allowed():
        await ws.close(code=1008)
        return
    await manager.connect(ws)
    try:
        while True:
            if not allowed():
                await ws.close(code=1008)
                break
            try:
                await asyncio.wait_for(ws.receive_text(),timeout=30)
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
