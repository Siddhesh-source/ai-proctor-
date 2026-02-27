import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.db import Exam, ProctoringLog, Question, Response, Result, Session, User
from app.models.grading import grade_session
from app.utils.analytics import calculate_comparative_analytics, calculate_time_analytics, calculate_question_analytics
from app.utils.pdf_generator import generate_student_report, generate_professor_report


router = APIRouter(prefix="/results", tags=["results"])
logger = logging.getLogger(__name__)


def _require_role(user: User, role: str) -> None:
    if user.role != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.get("/me")
async def get_my_results(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    _require_role(current_user, "student")
    rows = await db.execute(
        select(Session, Result, Exam)
        .join(Exam, Exam.id == Session.exam_id)
        .outerjoin(Result, Result.session_id == Session.id)
        .where(Session.student_id == current_user.id)
        .where(Session.status == "completed")
        .order_by(desc(Session.finished_at))
    )
    return [
        {
            "session_id": str(session.id),
            "exam_id": str(exam.id),
            "exam_title": exam.title,
            "total_score": result.total_score if result else None,
            "integrity_score": result.integrity_score if result else session.integrity_score,
            "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        }
        for session, result, exam in rows.all()
    ]


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

    # If session is completed but no Result row exists, grading failed silently — run it now
    if not result and session.status == "completed":
        try:
            await grade_session(session.id, db)
            result_row = await db.execute(select(Result).where(Result.session_id == session.id))
            result = result_row.scalar_one_or_none()
        except Exception:
            logger.exception("On-demand grading failed for session %s", session_id)

    violation_counts_result = await db.execute(
        select(ProctoringLog.violation_type, func.count(ProctoringLog.id))
        .where(ProctoringLog.session_id == session.id)
        .group_by(ProctoringLog.violation_type)
    )
    violation_summary = {
        row[0]: row[1] for row in violation_counts_result.all()
    }

    exam_result = await db.execute(select(Exam).where(Exam.id == session.exam_id))
    exam = exam_result.scalar_one_or_none()

    responses_result = await db.execute(
        select(Response, Question)
        .join(Question, Response.question_id == Question.id)
        .where(Response.session_id == session.id)
    )
    responses = [
        {
            "question_id": str(question.id),
            "question_text": question.text,
            "correct_answer": question.correct_answer,
            "answer": response.answer,
            "score": response.score,
            "marks": question.marks,
            "question_type": question.type,
            "grading_breakdown": response.grading_breakdown,
            "needs_review": (
                response.grading_breakdown.get("needs_review", False)
                if response.grading_breakdown else False
            ),
            "manually_graded": response.manually_graded,
            "override_note": response.override_note,
        }
        for response, question in responses_result.all()
    ]

    total_marks = None
    if exam:
        total_marks_result = await db.execute(
            select(func.sum(Question.marks)).where(Question.exam_id == exam.id)
        )
        total_marks = total_marks_result.scalar() or 0

    return {
        "session_id": str(session.id),
        "exam_title": exam.title if exam else None,
        "status": session.status,
        "total_score": result.total_score if result else None,
        "total_marks": total_marks,
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
    total_marks_result = await db.execute(
        select(func.sum(Question.marks)).where(Question.exam_id == exam_uuid)
    )
    total_marks = total_marks_result.scalar() or 0
    logger.info(
        "Exam results fetched",
        extra={"exam_id": str(exam_uuid), "session_count": len(rows)},
    )
    session_ids = [session.id for session, _, _ in rows]
    violation_counts: dict[uuid.UUID, int] = {}
    if session_ids:
        violation_result = await db.execute(
            select(ProctoringLog.session_id, func.count(ProctoringLog.id))
            .where(ProctoringLog.session_id.in_(session_ids))
            .group_by(ProctoringLog.session_id)
        )
        violation_counts = {row[0]: row[1] for row in violation_result.all()}

    return [
        {
            "session_id": str(session.id),
            "student_name": user.full_name,
            "student_email": user.email,
            "total_score": result.total_score if result else None,
            "total_marks": total_marks,
            "integrity_score": (
                result.integrity_score if result else session.integrity_score
            ),
            "status": session.status,
            "violation_count": violation_counts.get(session.id, 0),
        }
        for session, result, user in rows
    ]



@router.get("/{session_id}/pdf")
async def get_session_results_pdf(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Generate and download PDF report for a session"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc
    
    # Get session
    session_result = await db.execute(select(Session).where(Session.id == session_uuid))
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    
    # Check permissions
    if current_user.role == "student" and session.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    
    # Get exam
    exam_result = await db.execute(select(Exam).where(Exam.id == session.exam_id))
    exam = exam_result.scalar_one_or_none()
    
    # Get student
    student_result = await db.execute(select(User).where(User.id == session.student_id))
    student = student_result.scalar_one_or_none()
    
    # Get result
    result_row = await db.execute(select(Result).where(Result.session_id == session.id))
    result = result_row.scalar_one_or_none()
    
    # Get responses
    responses_result = await db.execute(
        select(Response, Question)
        .join(Question, Response.question_id == Question.id)
        .where(Response.session_id == session.id)
    )
    responses = [
        {
            "question_id": str(question.id),
            "question_text": question.text,
            "question_type": question.type,
            "answer": response.answer,
            "score": response.score,
            "marks": question.marks,
            "time_spent_seconds": response.time_spent_seconds,
            "keywords": question.keywords or [],
        }
        for response, question in responses_result.all()
    ]
    
    # Get violations
    violations_result = await db.execute(
        select(ProctoringLog).where(ProctoringLog.session_id == session.id)
    )
    violations = [
        {
            "violation_type": log.violation_type,
            "confidence": log.confidence,
            "created_at": log.created_at.isoformat(),
        }
        for log in violations_result.scalars().all()
    ]
    
    total_marks = None
    if exam:
        total_marks_result = await db.execute(
            select(func.sum(Question.marks)).where(Question.exam_id == exam.id)
        )
        total_marks = total_marks_result.scalar() or 0

    time_analytics = calculate_time_analytics(responses)

    topic_map: dict[str, dict] = {}
    for item in responses:
        keywords = item.get("keywords") or []
        topic = (keywords[0] if keywords else None) or "General"
        entry = topic_map.setdefault(topic, {"scored": 0.0, "possible": 0.0, "attempts": 0})
        entry["scored"] += float(item.get("score") or 0)
        entry["possible"] += float(item.get("marks") or 0)
        if item.get("answer"):
            entry["attempts"] += 1

    topic_analytics = [
        {
            "topic": topic,
            "accuracy_pct": round((values["scored"] / values["possible"]) * 100, 1)
            if values["possible"] > 0
            else 0.0,
            "scored": round(values["scored"], 2),
            "possible": round(values["possible"], 2),
            "attempts": values["attempts"],
        }
        for topic, values in topic_map.items()
    ]

    question_rows_result = await db.execute(
        select(Response, Question)
        .join(Question, Response.question_id == Question.id)
        .join(Session, Response.session_id == Session.id)
        .where(Session.exam_id == session.exam_id)
    )
    question_map: dict[str, list[dict]] = {}
    for resp, q in question_rows_result.all():
        question_map.setdefault(str(q.id), []).append(
            {
                "score": resp.score,
                "marks": q.marks,
                "time_spent_seconds": resp.time_spent_seconds,
            }
        )

    question_analytics = []
    for item in responses:
        analytics = calculate_question_analytics(question_map.get(item["question_id"], []))
        question_analytics.append({
            **analytics,
            "question_id": item["question_id"],
            "question_text": item.get("question_text"),
            "student_score": item.get("score") or 0,
            "student_time_seconds": item.get("time_spent_seconds") or 0,
            "max_marks": item.get("marks") or 0,
        })

    sessions_result = await db.execute(
        select(Session, Result)
        .outerjoin(Result, Result.session_id == Session.id)
        .where(Session.exam_id == session.exam_id)
    )
    sessions_rows = sessions_result.all()
    all_scores = [row[1].total_score for row in sessions_rows if row[1] and row[1].total_score is not None]

    time_totals_result = await db.execute(
        select(Response.session_id, func.sum(Response.time_spent_seconds))
        .join(Session, Response.session_id == Session.id)
        .where(Session.exam_id == session.exam_id)
        .group_by(Response.session_id)
    )
    time_totals = {row[0]: int(row[1] or 0) for row in time_totals_result.all()}
    all_times = list(time_totals.values())
    student_time = int(time_analytics.get("total_time_seconds") or 0)
    comparative = calculate_comparative_analytics(
        student_score=float(result.total_score if result else 0),
        all_scores=all_scores,
        student_time=student_time,
        all_times=all_times,
    )

    # Prepare session data
    session_data = {
        "session_id": str(session.id),
        "status": session.status,
        "total_score": result.total_score if result else None,
        "total_marks": total_marks,
        "integrity_score": result.integrity_score if result else session.integrity_score,
        "violation_summary": result.violation_summary if result else {},
        "comparative": comparative,
        "time_analytics": time_analytics,
    }
    
    # Generate PDF
    pdf_buffer = generate_student_report(
        student_name=student.full_name if student else "Unknown",
        exam_title=exam.title if exam else "Unknown Exam",
        session_data=session_data,
        responses=responses,
        violations=violations,
        topic_analytics=topic_analytics,
        question_analytics=question_analytics,
        comparative_analytics=comparative,
        time_analytics=time_analytics,
    )
    
    # Return as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=exam_report_{session_id[:8]}.pdf"
        }
    )


@router.get("/exam/{exam_id}/pdf")
async def get_exam_results_pdf(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Generate and download PDF report for entire exam (professor only)"""
    _require_role(current_user, "professor")
    
    try:
        exam_uuid = uuid.UUID(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid exam_id") from exc
    
    # Get exam
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_uuid))
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    
    # Get all sessions with results
    results = await db.execute(
        select(Session, Result, User)
        .join(User, User.id == Session.student_id)
        .outerjoin(Result, Result.session_id == Session.id)
        .where(Session.exam_id == exam_uuid)
        .order_by(desc(Result.total_score))
    )
    
    sessions = [
        {
            "student_name": user.full_name,
            "total_score": result.total_score if result else 0,
            "integrity_score": result.integrity_score if result else session.integrity_score,
            "status": session.status,
        }
        for session, result, user in results.all()
    ]
    
    # Generate PDF
    pdf_buffer = generate_professor_report(
        exam_title=exam.title,
        sessions=sessions,
        exam_data={}
    )
    
    # Return as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=exam_analysis_{exam_id[:8]}.pdf"
        }
    )



@router.post("/{session_id}/email")
async def email_session_results(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Email PDF report to student"""
    from app.utils.email import send_email_with_attachment, generate_student_email_body
    
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc
    
    # Get session
    session_result = await db.execute(select(Session).where(Session.id == session_uuid))
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    
    # Check permissions
    if current_user.role == "student" and session.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    
    # Get data for email and PDF
    exam_result = await db.execute(select(Exam).where(Exam.id == session.exam_id))
    exam = exam_result.scalar_one_or_none()
    
    student_result = await db.execute(select(User).where(User.id == session.student_id))
    student = student_result.scalar_one_or_none()
    
    result_row = await db.execute(select(Result).where(Result.session_id == session.id))
    result = result_row.scalar_one_or_none()
    
    # Get responses
    responses_result = await db.execute(
        select(Response, Question)
        .join(Question, Response.question_id == Question.id)
        .where(Response.session_id == session.id)
    )
    responses = [
        {
            "question_id": str(question.id),
            "question_text": question.text,
            "question_type": question.type,
            "answer": response.answer,
            "score": response.score,
            "marks": question.marks,
            "time_spent_seconds": response.time_spent_seconds,
            "keywords": question.keywords or [],
        }
        for response, question in responses_result.all()
    ]
    
    # Get violations
    violations_result = await db.execute(
        select(ProctoringLog).where(ProctoringLog.session_id == session.id)
    )
    violations = [
        {
            "violation_type": log.violation_type,
            "confidence": log.confidence,
            "created_at": log.created_at.isoformat(),
        }
        for log in violations_result.scalars().all()
    ]
    
    total_marks = None
    if exam:
        total_marks_result = await db.execute(
            select(func.sum(Question.marks)).where(Question.exam_id == exam.id)
        )
        total_marks = total_marks_result.scalar() or 0

    time_analytics = calculate_time_analytics(responses)

    topic_map: dict[str, dict] = {}
    for item in responses:
        keywords = item.get("keywords") or []
        topic = (keywords[0] if keywords else None) or "General"
        entry = topic_map.setdefault(topic, {"scored": 0.0, "possible": 0.0, "attempts": 0})
        entry["scored"] += float(item.get("score") or 0)
        entry["possible"] += float(item.get("marks") or 0)
        if item.get("answer"):
            entry["attempts"] += 1

    topic_analytics = [
        {
            "topic": topic,
            "accuracy_pct": round((values["scored"] / values["possible"]) * 100, 1)
            if values["possible"] > 0
            else 0.0,
            "scored": round(values["scored"], 2),
            "possible": round(values["possible"], 2),
            "attempts": values["attempts"],
        }
        for topic, values in topic_map.items()
    ]

    question_rows_result = await db.execute(
        select(Response, Question)
        .join(Question, Response.question_id == Question.id)
        .join(Session, Response.session_id == Session.id)
        .where(Session.exam_id == session.exam_id)
    )
    question_map: dict[str, list[dict]] = {}
    for resp, q in question_rows_result.all():
        question_map.setdefault(str(q.id), []).append(
            {
                "score": resp.score,
                "marks": q.marks,
                "time_spent_seconds": resp.time_spent_seconds,
            }
        )

    question_analytics = []
    for item in responses:
        analytics = calculate_question_analytics(question_map.get(item["question_id"], []))
        question_analytics.append({
            **analytics,
            "question_id": item["question_id"],
            "question_text": item.get("question_text"),
            "student_score": item.get("score") or 0,
            "student_time_seconds": item.get("time_spent_seconds") or 0,
            "max_marks": item.get("marks") or 0,
        })

    sessions_result = await db.execute(
        select(Session, Result)
        .outerjoin(Result, Result.session_id == Session.id)
        .where(Session.exam_id == session.exam_id)
    )
    sessions_rows = sessions_result.all()
    all_scores = [row[1].total_score for row in sessions_rows if row[1] and row[1].total_score is not None]

    time_totals_result = await db.execute(
        select(Response.session_id, func.sum(Response.time_spent_seconds))
        .join(Session, Response.session_id == Session.id)
        .where(Session.exam_id == session.exam_id)
        .group_by(Response.session_id)
    )
    time_totals = {row[0]: int(row[1] or 0) for row in time_totals_result.all()}
    all_times = list(time_totals.values())
    student_time = int(time_analytics.get("total_time_seconds") or 0)
    comparative = calculate_comparative_analytics(
        student_score=float(result.total_score if result else 0),
        all_scores=all_scores,
        student_time=student_time,
        all_times=all_times,
    )

    # Prepare session data
    session_data = {
        "session_id": str(session.id),
        "status": session.status,
        "total_score": result.total_score if result else 0,
        "total_marks": total_marks,
        "integrity_score": result.integrity_score if result else session.integrity_score,
        "violation_summary": result.violation_summary if result else {},
        "comparative": comparative,
        "time_analytics": time_analytics,
    }
    
    # Generate PDF
    pdf_buffer = generate_student_report(
        student_name=student.full_name if student else "Unknown",
        exam_title=exam.title if exam else "Unknown Exam",
        session_data=session_data,
        responses=responses,
        violations=violations,
        topic_analytics=topic_analytics,
        question_analytics=question_analytics,
        comparative_analytics=comparative,
        time_analytics=time_analytics,
    )
    
    # Generate email body
    max_score = total_marks if total_marks is not None else (sum(r['marks'] for r in responses) if responses else 0)
    email_body = generate_student_email_body(
        student_name=student.full_name if student else "Student",
        exam_title=exam.title if exam else "Exam",
        total_score=session_data['total_score'],
        max_score=max_score,
        integrity_score=session_data['integrity_score']
    )
    
    # Send to the logged-in user's email (from their registration profile)
    recipient_email = current_user.email
    
    success = await send_email_with_attachment(
        to_email=recipient_email,
        subject=f"Exam Results: {exam.title if exam else 'Your Exam'}",
        body_html=email_body,
        attachment_data=pdf_buffer,
        attachment_filename=f"exam_report_{session_id[:8]}.pdf"
    )
    
    if success:
        return {"message": "Email sent successfully", "sent_to": recipient_email}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send email. Check SMTP configuration."
        )


@router.get("/{session_id}/analytics")
async def get_session_analytics(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get comprehensive analytics for a session including comparative analysis"""
    from app.utils.analytics import (
        calculate_comparative_analytics,
        calculate_time_analytics
    )
    
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc
    
    # Get session
    session_result = await db.execute(select(Session).where(Session.id == session_uuid))
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    
    # Check permissions
    if current_user.role == "student" and session.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    
    # Get result
    result_row = await db.execute(select(Result).where(Result.session_id == session.id))
    result = result_row.scalar_one_or_none()
    
    # Get all sessions for this exam (for comparative analysis)
    all_sessions_result = await db.execute(
        select(Session, Result)
        .outerjoin(Result, Result.session_id == Session.id)
        .where(Session.exam_id == session.exam_id)
    )
    all_sessions = all_sessions_result.all()
    
    all_scores = [r.total_score for s, r in all_sessions if r and r.total_score is not None]
    
    # Get responses with time data
    responses_result = await db.execute(
        select(Response).where(Response.session_id == session.id)
    )
    responses = responses_result.scalars().all()
    
    all_times = [r.time_spent_seconds for r in responses if r.time_spent_seconds]
    student_total_time = sum(all_times) if all_times else 0
    
    # Get all times for comparison
    all_session_times_result = await db.execute(
        select(Response.time_spent_seconds)
        .join(Session, Response.session_id == Session.id)
        .where(Session.exam_id == session.exam_id)
        .where(Response.time_spent_seconds.isnot(None))
    )
    all_session_times = [t[0] for t in all_session_times_result.all() if t[0]]
    
    # Calculate analytics
    comparative = calculate_comparative_analytics(
        student_score=result.total_score if result else 0,
        all_scores=all_scores,
        student_time=student_total_time,
        all_times=all_session_times
    )
    
    time_analytics = calculate_time_analytics([
        {
            "time_spent_seconds": r.time_spent_seconds,
            "question_id": str(r.question_id)
        }
        for r in responses
    ])
    
    return {
        "session_id": str(session.id),
        "comparative_analytics": comparative,
        "time_analytics": time_analytics,
        "total_score": result.total_score if result else 0,
        "integrity_score": result.integrity_score if result else session.integrity_score
    }


class OverrideScoreRequest(BaseModel):
    score: float
    note: str | None = None


@router.patch("/{session_id}/responses/{question_id}/override")
async def override_response_score(
    session_id: str,
    question_id: str,
    payload: OverrideScoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_role(current_user, "professor")
    try:
        session_uuid = uuid.UUID(session_id)
        question_uuid = uuid.UUID(question_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id") from exc

    session_result = await db.execute(select(Session).where(Session.id == session_uuid))
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Verify the professor owns the exam
    exam_result = await db.execute(select(Exam).where(Exam.id == session.exam_id))
    exam = exam_result.scalar_one_or_none()
    if not exam or exam.professor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    response_result = await db.execute(
        select(Response).where(
            Response.session_id == session_uuid,
            Response.question_id == question_uuid,
        )
    )
    response = response_result.scalar_one_or_none()
    if not response:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Response not found")

    question_result = await db.execute(select(Question).where(Question.id == question_uuid))
    question = question_result.scalar_one_or_none()
    if question and payload.score > question.marks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Score cannot exceed question marks ({question.marks})",
        )

    old_score = response.score or 0.0
    response.score = payload.score
    response.manually_graded = True
    response.override_note = payload.note
    if response.grading_breakdown:
        response.grading_breakdown = {**response.grading_breakdown, "needs_review": False}

    # Recompute result total
    result_row = await db.execute(select(Result).where(Result.session_id == session_uuid))
    result = result_row.scalar_one_or_none()
    if result:
        result.total_score = round((result.total_score or 0.0) - old_score + payload.score, 2)

    await db.commit()
    return {
        "session_id": session_id,
        "question_id": question_id,
        "new_score": payload.score,
        "total_score": result.total_score if result else None,
        "manually_graded": True,
    }
