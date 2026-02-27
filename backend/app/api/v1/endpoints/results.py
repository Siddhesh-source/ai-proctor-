import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.db import Exam, ProctoringLog, Question, Response, Result, Session, User
from app.utils.pdf_generator import generate_student_report, generate_professor_report


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
            "answer": response.answer,
            "score": response.score,
            "marks": question.marks,
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
    
    # Prepare session data
    session_data = {
        "session_id": str(session.id),
        "status": session.status,
        "total_score": result.total_score if result else None,
        "integrity_score": result.integrity_score if result else session.integrity_score,
        "violation_summary": result.violation_summary if result else {},
    }
    
    # Generate PDF
    pdf_buffer = generate_student_report(
        student_name=student.full_name if student else "Unknown",
        exam_title=exam.title if exam else "Unknown Exam",
        session_data=session_data,
        responses=responses,
        violations=violations
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
    db: AsyncSession = Depends(get_current_user),
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
            "answer": response.answer,
            "score": response.score,
            "marks": question.marks,
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
    
    # Prepare session data
    session_data = {
        "session_id": str(session.id),
        "status": session.status,
        "total_score": result.total_score if result else 0,
        "integrity_score": result.integrity_score if result else session.integrity_score,
        "violation_summary": result.violation_summary if result else {},
    }
    
    # Generate PDF
    pdf_buffer = generate_student_report(
        student_name=student.full_name if student else "Unknown",
        exam_title=exam.title if exam else "Unknown Exam",
        session_data=session_data,
        responses=responses,
        violations=violations
    )
    
    # Generate email body
    max_score = sum(r['marks'] for r in responses) if responses else 100
    email_body = generate_student_email_body(
        student_name=student.full_name if student else "Student",
        exam_title=exam.title if exam else "Exam",
        total_score=session_data['total_score'],
        max_score=max_score,
        integrity_score=session_data['integrity_score']
    )
    
    # Send email
    success = await send_email_with_attachment(
        to_email=student.email if student else "",
        subject=f"Exam Results: {exam.title if exam else 'Your Exam'}",
        body_html=email_body,
        attachment_data=pdf_buffer,
        attachment_filename=f"exam_report_{session_id[:8]}.pdf"
    )
    
    if success:
        return {"message": "Email sent successfully", "sent_to": student.email if student else ""}
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
