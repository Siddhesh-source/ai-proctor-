import random
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import AsyncSessionLocal, get_db
from app.models.db import Exam, Question, Response, Session as ExamSession, User
from app.models.grading import grade_session, run_code_piston
from app.schemas.exam import (
    ExamCreate,
    ExamCreateResponse,
    ExamResponse,
    FinishExamRequest,
    FinishExamResponse,
    QuestionResponse,
    StartExamResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)


router = APIRouter(prefix="/exams", tags=["exams"])

logger = logging.getLogger(__name__)


def _require_role(user: User, role: str) -> None:
    if user.role != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def grade_session_background(session_id: uuid.UUID) -> None:
    try:
        async with AsyncSessionLocal() as db:
            await grade_session(session_id, db)
        logger.info("Grading completed", extra={"session_id": str(session_id)})
    except Exception:
        logger.exception("Background grading failed for session %s", session_id)


@router.post("", response_model=ExamCreateResponse)
async def create_exam(
    payload: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExamCreateResponse:
    _require_role(current_user, "professor")
    start_time = payload.start_time
    end_time = payload.end_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    logger.info(
        "Create exam request",
        extra={
            "professor_id": str(current_user.id),
            "title": payload.title,
            "type": payload.type,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        },
    )
    exam = Exam(
        professor_id=current_user.id,
        title=payload.title,
        type=payload.type,
        duration_minutes=payload.duration_minutes,
        start_time=start_time,
        end_time=end_time,
        negative_marking=payload.negative_marking,
        randomize_questions=payload.randomize_questions,
    )
    db.add(exam)
    await db.flush()
    questions = [
        Question(
            exam_id=exam.id,
            text=item.text,
            type=item.type,
            options=item.options,
            correct_answer=item.correct_answer,
            keywords=item.keywords,
            marks=item.marks,
            order_index=item.order,
            code_language=item.code_language,
            test_cases=item.test_cases,
        )
        for item in payload.questions
    ]
    db.add_all(questions)
    await db.commit()
    logger.info(
        "Exam created",
        extra={
            "exam_id": str(exam.id),
            "professor_id": str(current_user.id),
            "question_count": len(questions),
        },
    )
    return ExamCreateResponse(exam_id=str(exam.id), question_count=len(questions))


@router.get("/available", response_model=list[ExamResponse])
async def list_available_exams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ExamResponse]:
    _require_role(current_user, "student")
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Exam).where(
            and_(
                Exam.is_active.is_(True),
                Exam.start_time <= now,
                Exam.end_time >= now,
            )
        )
    )
    exams = result.scalars().all()
    logger.info(
        "Available exams query",
        extra={
            "student_id": str(current_user.id),
            "now": now.isoformat(),
            "count": len(exams),
        },
    )
    active_result = await db.execute(select(Exam).where(Exam.is_active.is_(True)))
    active_exams = active_result.scalars().all()
    for exam in active_exams:
        logger.info(
            "Active exam window",
            extra={
                "exam_id": str(exam.id),
                "start_time": exam.start_time.isoformat(),
                "end_time": exam.end_time.isoformat(),
                "visible": exam in exams,
            },
        )
    return [
        ExamResponse(
            id=str(exam.id),
            professor_id=str(exam.professor_id),
            title=exam.title,
            type=exam.type,
            duration_minutes=exam.duration_minutes,
            start_time=exam.start_time,
            end_time=exam.end_time,
            negative_marking=exam.negative_marking,
            randomize_questions=exam.randomize_questions,
            is_active=exam.is_active,
        )
        for exam in exams
    ]


@router.get("/professor", response_model=list[ExamResponse])
async def list_professor_exams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ExamResponse]:
    _require_role(current_user, "professor")
    result = await db.execute(select(Exam).where(Exam.professor_id == current_user.id))
    exams = result.scalars().all()
    return [
        ExamResponse(
            id=str(exam.id),
            professor_id=str(exam.professor_id),
            title=exam.title,
            type=exam.type,
            duration_minutes=exam.duration_minutes,
            start_time=exam.start_time,
            end_time=exam.end_time,
            negative_marking=exam.negative_marking,
            randomize_questions=exam.randomize_questions,
            is_active=exam.is_active,
        )
        for exam in exams
    ]


@router.post("/{exam_id}/start", response_model=StartExamResponse)
async def start_exam(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StartExamResponse:
    _require_role(current_user, "student")
    try:
        exam_uuid = uuid.UUID(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid exam_id") from exc
    existing = await db.execute(
        select(ExamSession).where(
            and_(ExamSession.exam_id == exam_uuid, ExamSession.student_id == current_user.id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session already exists")
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_uuid))
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    session = ExamSession(
        student_id=current_user.id,
        exam_id=exam.id,
        status="active",
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return StartExamResponse(session_id=str(session.id), duration_minutes=exam.duration_minutes)


@router.get(
    "/{exam_id}/questions",
    response_model=list[QuestionResponse],
    response_model_exclude={"correct_answer"},
)
async def get_exam_questions(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[QuestionResponse]:
    logger.debug(
        "Fetching exam questions",
        extra={"exam_id": exam_id, "user_id": str(current_user.id)},
    )
    _require_role(current_user, "student")
    try:
        exam_uuid = uuid.UUID(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid exam_id") from exc
    session_result = await db.execute(
        select(ExamSession).where(
            and_(
                ExamSession.exam_id == exam_uuid,
                ExamSession.student_id == current_user.id,
                ExamSession.status == "active",
            )
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active session required")
    logger.debug(
        "Active session verified for exam questions",
        extra={"exam_id": exam_id, "session_id": str(session.id)},
    )
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_uuid))
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    question_result = await db.execute(
        select(Question).where(Question.exam_id == exam_uuid).order_by(Question.order_index.asc())
    )
    questions = question_result.scalars().all()
    logger.debug(
        "Questions fetched",
        extra={"exam_id": exam_id, "question_count": len(questions)},
    )
    if exam.randomize_questions:
        random.shuffle(questions)
    return [
        QuestionResponse(
            id=str(question.id),
            exam_id=str(question.exam_id),
            text=question.text,
            type=question.type,
            options=question.options,
            correct_answer=question.correct_answer,
            keywords=question.keywords,
            marks=question.marks,
            order=question.order_index,
            code_language=question.code_language,
            test_cases=question.test_cases,
        )
        for question in questions
    ]


@router.get("/{exam_id}/meta")
async def get_exam_meta(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_role(current_user, "student")
    try:
        exam_uuid = uuid.UUID(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid exam_id") from exc
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_uuid))
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    return {
        "exam_id": str(exam.id),
        "title": exam.title,
        "subject_name": exam.type,
        "start_time": exam.start_time.isoformat() if exam.start_time else None,
        "end_time": exam.end_time.isoformat() if exam.end_time else None,
        "duration_minutes": exam.duration_minutes,
    }


@router.post("/{exam_id}/submit-answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    exam_id: str,
    payload: SubmitAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubmitAnswerResponse:
    _require_role(current_user, "student")
    try:
        exam_uuid = uuid.UUID(exam_id)
        session_uuid = uuid.UUID(payload.session_id)
        question_uuid = uuid.UUID(payload.question_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id") from exc
    session_result = await db.execute(
        select(ExamSession).where(
            and_(
                ExamSession.id == session_uuid,
                ExamSession.exam_id == exam_uuid,
                ExamSession.student_id == current_user.id,
            )
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid session")
    response_result = await db.execute(
        select(Response).where(
            and_(Response.session_id == session_uuid, Response.question_id == question_uuid)
        )
    )
    response = response_result.scalar_one_or_none()
    
    current_time = datetime.now(timezone.utc)
    
    if response:
        # Update existing response
        if response.submitted_at:
            submitted = response.submitted_at
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone.utc)
            time_diff = int((current_time - submitted).total_seconds())
            response.time_spent_seconds = (response.time_spent_seconds or 0) + time_diff
        response.answer = payload.answer
        response.submitted_at = current_time
    else:
        # Create new response
        last_resp_query = await db.execute(
            select(Response)
            .where(Response.session_id == session_uuid)
            .order_by(Response.submitted_at.desc())
            .limit(1)
        )
        last_resp = last_resp_query.scalar_one_or_none()
        raw_start = last_resp.submitted_at if last_resp and last_resp.submitted_at else session.started_at
        if raw_start is not None and raw_start.tzinfo is None:
            raw_start = raw_start.replace(tzinfo=timezone.utc)
        start_time = raw_start or current_time

        db.add(
            Response(
                session_id=session_uuid,
                question_id=question_uuid,
                answer=payload.answer,
                started_at=start_time,
                submitted_at=current_time,
                time_spent_seconds=int((current_time - start_time).total_seconds())
            )
        )
    await db.commit()
    return SubmitAnswerResponse()


@router.post("/{exam_id}/finish", response_model=FinishExamResponse)
async def finish_exam(
    exam_id: str,
    payload: FinishExamRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FinishExamResponse:
    _require_role(current_user, "student")
    try:
        exam_uuid = uuid.UUID(exam_id)
        session_uuid = uuid.UUID(payload.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id") from exc
    session_result = await db.execute(
        select(ExamSession).where(
            and_(
                ExamSession.id == session_uuid,
                ExamSession.exam_id == exam_uuid,
                ExamSession.student_id == current_user.id,
            )
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid session")
    session.finished_at = datetime.now(timezone.utc)
    session.status = "completed"
    await db.commit()
    background_tasks.add_task(grade_session_background, session_uuid)
    return FinishExamResponse(status="grading")


@router.post("/run-code")
async def run_code(
    payload: dict,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Execute code via Piston API. Used by student for test runs during exam."""
    code = payload.get("code", "")
    language = payload.get("language", "")
    stdin = payload.get("stdin", "")
    if not code.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code required")
    if not language:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="language required")
    try:
        result = await run_code_piston(code, language, stdin)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Code execution failed") from exc
    return result
