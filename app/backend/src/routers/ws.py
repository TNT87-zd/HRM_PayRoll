from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from database import get_db
from schemas import EnrollResponse

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
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()    # giữ kết nối
    except WebSocketDisconnect:
        manager.disconnect(ws)