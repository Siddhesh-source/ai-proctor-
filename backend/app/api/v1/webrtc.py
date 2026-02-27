import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import verify_token
from app.models.db import Session as ExamSession


router = APIRouter()
logger = logging.getLogger(__name__)

# session_id -> {"student": WebSocket, "professor": WebSocket}
CONNECTIONS: dict[str, dict[str, WebSocket]] = {}


async def _validate_session(session_id: str) -> bool:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        return False
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ExamSession).where(ExamSession.id == session_uuid))
        return result.scalar_one_or_none() is not None


def _get_role(token: str) -> str | None:
    payload = verify_token(token)
    return payload.get("role")


def _register(session_id: str, role: str, websocket: WebSocket) -> None:
    peers = CONNECTIONS.setdefault(session_id, {})
    peers[role] = websocket


def _unregister(session_id: str, role: str) -> None:
    peers = CONNECTIONS.get(session_id)
    if not peers:
        return
    peers.pop(role, None)
    if not peers:
        CONNECTIONS.pop(session_id, None)


@router.websocket("/ws/webrtc/{session_id}")
async def webrtc_ws(websocket: WebSocket, session_id: str) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return
    try:
        role = _get_role(token)
    except Exception:
        await websocket.close(code=1008)
        return
    if role not in {"student", "professor"}:
        await websocket.close(code=1008)
        return
    if not await _validate_session(session_id):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    _register(session_id, role, websocket)
    await websocket.send_json({"type": "registered", "role": role})

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "invalid_json"})
                continue
            message["from"] = role

            other_role = "professor" if role == "student" else "student"
            peer = CONNECTIONS.get(session_id, {}).get(other_role)
            if peer is None:
                await websocket.send_json({"type": "peer_missing"})
                continue
            await peer.send_json(message)
    except WebSocketDisconnect:
        _unregister(session_id, role)
        return
