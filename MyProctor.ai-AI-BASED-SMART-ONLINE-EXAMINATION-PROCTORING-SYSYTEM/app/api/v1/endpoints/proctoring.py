import base64
import uuid
from io import BytesIO

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db import ProctoringLog, Session as ExamSession
from app.models.ml_models import yolo
from app.utils.integrity import update_integrity


router = APIRouter(prefix="/proctoring", tags=["proctoring"])


async def _get_session(session_id: str, db: AsyncSession) -> ExamSession:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc
    result = await db.execute(select(ExamSession).where(ExamSession.id == session_uuid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def _log_violation(
    db: AsyncSession,
    session: ExamSession,
    violation_type: str,
    confidence: float,
    payload: dict,
) -> float:
    db.add(
        ProctoringLog(
            session_id=session.id,
            violation_type=violation_type,
            confidence=confidence,
            payload=payload,
        )
    )
    session.integrity_score = update_integrity(
        session.integrity_score or 100.0, violation_type, confidence
    )
    await db.commit()
    await db.refresh(session)
    return session.integrity_score


@router.post("/frame")
async def process_frame(payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _get_session(payload.get("session_id", ""), db)
    frame_base64 = payload.get("frame_base64")
    if not frame_base64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="frame_base64 required")
    if "," in frame_base64:
        frame_base64 = frame_base64.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(frame_base64)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64") from exc
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    frame = np.array(image)
    results = yolo(frame)
    labels = []
    person_count = 0
    for result in results:
        names = result.names
        classes = result.boxes.cls.tolist() if result.boxes is not None else []
        for class_id in classes:
            name = names.get(int(class_id), "")
            labels.append(name)
            if name == "person":
                person_count += 1
    violations = []
    integrity_score = session.integrity_score or 100.0
    if "cell phone" in labels or "book" in labels:
        integrity_score = await _log_violation(
            db,
            session,
            "phone_detected",
            0.9,
            {"labels": labels},
        )
        violations.append("phone_detected")
    if person_count > 1:
        integrity_score = await _log_violation(
            db,
            session,
            "multiple_faces",
            0.85,
            {"person_count": person_count},
        )
        violations.append("multiple_faces")
    return {"violations": violations, "integrity_score": integrity_score}


@router.post("/audio")
async def process_audio(payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _get_session(payload.get("session_id", ""), db)
    voice_energy = float(payload.get("voice_energy", 0))
    keywords_detected = payload.get("keywords_detected", [])
    if voice_energy > 60:
        await _log_violation(
            db,
            session,
            "speech_detected",
            0.8,
            {"voice_energy": voice_energy, "keywords": keywords_detected},
        )
        return {"violation": True}
    return {"violation": False}


@router.post("/raf")
async def process_raf(payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _get_session(payload.get("session_id", ""), db)
    delta_ms = float(payload.get("delta_ms", 0))
    if delta_ms > 500:
        await _log_violation(
            db,
            session,
            "raf_tab_switch",
            0.95,
            {"delta_ms": delta_ms},
        )
        return {"violation": True}
    return {"violation": False}


@router.post("/violation")
async def process_violation(payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _get_session(payload.get("session_id", ""), db)
    violation_type = payload.get("violation_type")
    confidence = float(payload.get("confidence", 0))
    extra_payload = payload.get("payload", {})
    if not violation_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="violation_type required")
    integrity_score = await _log_violation(
        db, session, violation_type, confidence, extra_payload
    )
    return {"integrity_score": integrity_score}


@router.get("/{session_id}/integrity")
async def get_integrity(session_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    session = await _get_session(session_id, db)
    logs_result = await db.execute(
        select(ProctoringLog).where(ProctoringLog.session_id == session.id)
    )
    logs = logs_result.scalars().all()
    violations = [
        {
            "id": str(log.id),
            "session_id": str(log.session_id),
            "violation_type": log.violation_type,
            "confidence": log.confidence,
            "payload": log.payload,
            "created_at": log.created_at,
        }
        for log in logs
    ]
    return {"integrity_score": session.integrity_score or 100.0, "violations": violations}
