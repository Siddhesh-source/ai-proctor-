import base64
import logging
import uuid
from io import BytesIO
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.sarvam import analyse_speech
from app.models.db import Exam, ProctoringLog, Session as ExamSession, User
from app.models.ml_models import yolo
from app.utils.integrity import update_integrity


router = APIRouter(prefix="/proctoring", tags=["proctoring"])
logger = logging.getLogger(__name__)
LAST_FRAMES: dict[str, str] = {}

VIOLATION_EXPLANATIONS = {
    "phone_detected": "Mobile device detected in the camera frame.",
    "gaze_away": "Student gaze away from screen beyond threshold.",
    "raf_tab_switch": "Browser tab or window switch detected.",
    "speech_detected": "Sustained voice energy detected by microphone.",
    "multiple_faces": "More than one person detected in frame.",
    "no_mouse": "No mouse activity detected for extended period.",
    "screenshot_attempt": "Screenshot key/visibility change detected.",
}


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
    logger.info(
        "Violation logged",
        extra={
            "session_id": str(session.id),
            "violation_type": violation_type,
            "confidence": confidence,
        },
    )
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
    LAST_FRAMES[str(session.id)] = f"data:image/jpeg;base64,{frame_base64}"
    logger.debug(
        "Frame received",
        extra={"session_id": str(session.id), "size": len(frame_base64)},
    )
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
    logger.debug(
        "Frame processed",
        extra={"session_id": str(session.id), "violations": violations},
    )
    return {"violations": violations, "integrity_score": integrity_score}


@router.get("/session/{session_id}/frame")
async def get_session_frame(session_id: str) -> dict:
    frame = LAST_FRAMES.get(session_id)
    if not frame:
        logger.debug("Frame not found", extra={"session_id": session_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")
    logger.debug("Frame served", extra={"session_id": session_id})
    return {"frame_base64": frame}


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
        logger.info(
            "Speech violation",
            extra={"session_id": str(session.id), "voice_energy": voice_energy},
        )
        return {"violation": True}
    return {"violation": False}


@router.post("/audio/stt")
async def process_audio_stt(payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Energy-gated Sarvam STT endpoint.
    Receives a base64-encoded audio clip recorded when mic energy exceeded threshold.
    Transcribes via Sarvam API, checks for cheating keywords, logs violation if found.
    Returns { transcript, language_code, violation, keywords, tier, integrity_score }.
    If SARVAM_API_KEY is not configured, returns { skipped: true }.
    """
    if not settings.SARVAM_API_KEY or settings.SARVAM_API_KEY == "your_sarvam_api_key_here":
        return {"skipped": True, "reason": "SARVAM_API_KEY not configured"}

    session = await _get_session(payload.get("session_id", ""), db)
    audio_b64 = payload.get("audio_base64", "")
    mime_type = payload.get("mime_type", "audio/webm")

    if not audio_b64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio_base64 required")

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 audio") from exc

    # Must be at least 0.5KB to be meaningful audio
    if len(audio_bytes) < 512:
        return {"skipped": True, "reason": "audio clip too short"}

    try:
        result = await analyse_speech(audio_bytes, mime_type, settings.SARVAM_API_KEY)
    except Exception as exc:
        logger.warning("Sarvam STT failed: %s", exc)
        return {"skipped": True, "reason": "stt_error", "detail": str(exc)}

    integrity_score = session.integrity_score or 100.0

    if result["violation"]:
        integrity_score = await _log_violation(
            db,
            session,
            "speech_cheating",
            result["confidence"],
            {
                "transcript": result["transcript"],
                "language_code": result["language_code"],
                "tier": result["tier"],
                "keywords": result["keywords"],
            },
        )
        logger.info(
            "Speech cheating detected",
            extra={
                "session_id": str(session.id),
                "tier": result["tier"],
                "transcript": result["transcript"],
            },
        )
    else:
        # No violation — log transcript silently in a non-penalising proctoring log
        # so professors can still review what was said
        if result["transcript"]:
            db.add(ProctoringLog(
                session_id=session.id,
                violation_type="speech_transcript",
                confidence=0.0,
                payload={
                    "transcript": result["transcript"],
                    "language_code": result["language_code"],
                },
            ))
            await db.commit()

    return {
        "transcript": result["transcript"],
        "language_code": result["language_code"],
        "tier": result["tier"],
        "keywords": result["keywords"],
        "violation": result["violation"],
        "integrity_score": integrity_score,
    }


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
        logger.info(
            "Tab switch violation",
            extra={"session_id": str(session.id), "delta_ms": delta_ms},
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
    logger.info(
        "Manual violation",
        extra={"session_id": str(session.id), "violation_type": violation_type},
    )
    return {"integrity_score": integrity_score}


@router.get("/exam/{exam_id}/live")
async def get_live_sessions(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Live monitoring data: active sessions sorted by integrity (worst first)."""
    if current_user.role != "professor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    try:
        exam_uuid = uuid.UUID(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid exam_id") from exc
    from sqlalchemy import func as sqlfunc
    sessions_result = await db.execute(
        select(ExamSession, User)
        .join(User, User.id == ExamSession.student_id)
        .where(ExamSession.exam_id == exam_uuid)
    )
    rows = sessions_result.all()
    session_ids = [s.id for s, _ in rows]

    violation_counts: dict[uuid.UUID, int] = {}
    recent_violations: dict[uuid.UUID, list] = {}
    if session_ids:
        vc = await db.execute(
            select(ProctoringLog.session_id, sqlfunc.count(ProctoringLog.id))
            .where(ProctoringLog.session_id.in_(session_ids))
            .group_by(ProctoringLog.session_id)
        )
        violation_counts = {r[0]: r[1] for r in vc.all()}

        recent = await db.execute(
            select(ProctoringLog)
            .where(ProctoringLog.session_id.in_(session_ids))
            .order_by(ProctoringLog.created_at.desc())
            .limit(50)
        )
        for log in recent.scalars().all():
            recent_violations.setdefault(log.session_id, []).append({
                "type": log.violation_type,
                "confidence": log.confidence,
                "time": log.created_at.isoformat() if log.created_at else None,
            })

    students = []
    for session, user in rows:
        sid = str(session.id)
        integrity = session.integrity_score if session.integrity_score is not None else 100.0
        students.append({
            "session_id": sid,
            "student_name": user.full_name,
            "student_email": user.email,
            "status": session.status,
            "integrity_score": integrity,
            "violation_count": violation_counts.get(session.id, 0),
            "recent_violations": recent_violations.get(session.id, [])[:5],
            "has_frame": sid in LAST_FRAMES,
            "started_at": session.started_at.isoformat() if session.started_at else None,
        })

    students.sort(key=lambda s: s["integrity_score"])
    active_count = sum(1 for s in students if s["status"] == "active")
    return {"students": students, "active_count": active_count, "total_count": len(students)}


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


@router.get("/exam/{exam_id}/logs")
async def get_exam_logs(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if current_user.role != "professor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    logger.info(
        "Exam logs requested",
        extra={"exam_id": exam_id, "professor_id": str(current_user.id)},
    )
    try:
        exam_uuid = uuid.UUID(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid exam_id") from exc
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_uuid))
    exam = exam_result.scalar_one_or_none()
    if not exam or exam.professor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

    sessions_result = await db.execute(select(ExamSession).where(ExamSession.exam_id == exam_uuid))
    sessions = sessions_result.scalars().all()
    session_ids = [session.id for session in sessions]

    logger.info(
        "Exam log sessions resolved",
        extra={"exam_id": exam_id, "session_count": len(sessions)},
    )

    logs: list[dict[str, Any]] = []

    for session in sessions:
        logs.append(
            {
                "event_type": "session_started",
                "message": "Session started",
                "explanation": "Student started the exam session.",
                "session_id": str(session.id),
                "student_id": str(session.student_id),
                "created_at": session.started_at,
            }
        )
        if session.finished_at:
            logs.append(
                {
                    "event_type": "session_finished",
                    "message": "Session finished",
                    "explanation": "Student submitted or finished the exam.",
                    "session_id": str(session.id),
                    "student_id": str(session.student_id),
                    "created_at": session.finished_at,
                }
            )

    if session_ids:
        logs_result = await db.execute(
            select(ProctoringLog)
            .where(ProctoringLog.session_id.in_(session_ids))
            .order_by(ProctoringLog.created_at.asc())
        )
        violation_logs = logs_result.scalars().all()
        logger.info(
            "Exam log violations loaded",
            extra={"exam_id": exam_id, "violation_count": len(violation_logs)},
        )
        for log in violation_logs:
            logs.append(
                {
                    "event_type": log.violation_type,
                    "message": f"Violation: {log.violation_type.replace('_', ' ')}",
                    "explanation": VIOLATION_EXPLANATIONS.get(log.violation_type, "Proctoring violation detected."),
                    "session_id": str(log.session_id),
                    "student_id": str(log.session.student_id) if log.session else None,
                    "created_at": log.created_at,
                }
            )

    logs.sort(key=lambda item: item.get("created_at") or 0)
    logger.info(
        "Exam logs response",
        extra={"exam_id": exam_id, "log_count": len(logs)},
    )
    return logs
