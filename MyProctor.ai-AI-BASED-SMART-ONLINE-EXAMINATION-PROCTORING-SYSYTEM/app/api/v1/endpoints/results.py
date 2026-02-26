import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.db import Exam, ProctoringLog, Question, Response, Result, Session, User


router = APIRouter(prefix="/results", tags=["results"])


def _require_role(user: User, role: str) -> None:
    if user.role != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.get("/{session_id}")
async def get_session_results(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc
    session_result = await db.execute(select(Session).where(Session.id == session_uuid))
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if current_user.role == "student" and session.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result_row = await db.execute(select(Result).where(Result.session_id == session.id))
    result = result_row.scalar_one_or_none()

    violation_counts_result = await db.execute(
        select(ProctoringLog.violation_type, func.count(ProctoringLog.id))
        .where(ProctoringLog.session_id == session.id)
        .group_by(ProctoringLog.violation_type)
    )
    violation_summary = {
        row[0]: row[1] for row in violation_counts_result.all()
    }

    responses_result = await db.execute(
        select(Response, Question)
        .join(Question, Response.question_id == Question.id)
        .where(Response.session_id == session.id)
    )
    responses = [
        {
            "question_id": str(question.id),
            "answer": response.answer,
            "score": response.score,
            "marks": question.marks,
        }
        for response, question in responses_result.all()
    ]

    return {
        "session_id": str(session.id),
        "status": session.status,
        "total_score": result.total_score if result else None,
        "integrity_score": result.integrity_score if result else session.integrity_score,
        "violation_summary": violation_summary,
        "responses": responses,
    }


@router.get("/exam/{exam_id}")
async def get_exam_results(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    _require_role(current_user, "professor")
    try:
        exam_uuid = uuid.UUID(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid exam_id") from exc
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_uuid))
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

    results = await db.execute(
        select(Session, Result, User)
        .join(User, User.id == Session.student_id)
        .outerjoin(Result, Result.session_id == Session.id)
        .where(Session.exam_id == exam_uuid)
        .order_by(desc(Result.total_score))
    )
    rows = results.all()
    return [
        {
            "student_name": user.full_name,
            "total_score": result.total_score if result else None,
            "integrity_score": (
                result.integrity_score if result else session.integrity_score
            ),
            "status": session.status,
        }
        for session, result, user in rows
    ]
