import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import verify_token
from app.models.db import ProctoringLog, Session as ExamSession
from app.utils.integrity import update_integrity


router = APIRouter()


@router.websocket("/ws/proctoring/{session_id}")
async def proctoring_ws(websocket: WebSocket, session_id: str) -> None:
    token = websocket.query_params.get("token")
    try:
        if not token:
            await websocket.close(code=1008)
            return
        verify_token(token)
    except Exception:
        await websocket.close(code=1008)
        return
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ExamSession).where(ExamSession.id == session_uuid)
            )
            session = result.scalar_one_or_none()
            if not session:
                await websocket.close(code=1008)
                return
            while True:
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({"error": "invalid_json"})
                    continue
                if message.get("type") != "violation":
                    await websocket.send_json({"error": "unsupported_type"})
                    continue
                violation_type = message.get("violation_type")
                confidence = float(message.get("confidence", 0))
                if not violation_type:
                    await websocket.send_json({"error": "missing_violation_type"})
                    continue
                db.add(
                    ProctoringLog(
                        session_id=session.id,
                        violation_type=violation_type,
                        confidence=confidence,
                        payload=message,
                    )
                )
                session.integrity_score = update_integrity(
                    session.integrity_score or 100.0, violation_type, confidence
                )
                await db.commit()
                await db.refresh(session)
                await websocket.send_json(
                    {
                        "integrity_score": session.integrity_score,
                        "violation": violation_type,
                    }
                )
    except WebSocketDisconnect:
        return
