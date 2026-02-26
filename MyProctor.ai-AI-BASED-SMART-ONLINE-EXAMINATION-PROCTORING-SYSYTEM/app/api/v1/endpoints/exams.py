import random
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import AsyncSessionLocal, get_db
from app.models.db import Exam, Question, Response, Session as ExamSession, User
from app.models.grading import grade_session
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


def _require_role(user: User, role: str) -> None:
    if user.role != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def grade_session_background(session_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        await grade_session(session_id, db)


@router.post("", response_model=ExamCreateResponse)
async def create_exam(
    payload: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExamCreateResponse:
    _require_role(current_user, "professor")
    exam = Exam(
        professor_id=current_user.id,
        title=payload.title,
        type=payload.type,
        duration_minutes=payload.duration_minutes,
        start_time=payload.start_time,
        end_time=payload.end_time,
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
        )
        for item in payload.questions
    ]
    db.add_all(questions)
    await db.commit()
    return ExamCreateResponse(exam_id=str(exam.id), question_count=len(questions))


@router.get("/available", response_model=list[ExamResponse])
async def list_available_exams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ExamResponse]:
    _require_role(current_user, "student")
    now = datetime.utcnow()
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
        started_at=datetime.utcnow(),
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
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_uuid))
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    question_result = await db.execute(
        select(Question).where(Question.exam_id == exam_uuid).order_by(Question.order_index.asc())
    )
    questions = question_result.scalars().all()
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
        )
        for question in questions
    ]


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
    
    current_time = datetime.utcnow()
    
    if response:
        # Update existing response
        if response.submitted_at:
            time_diff = int((current_time - response.submitted_at).total_seconds())
            response.time_spent_seconds = (response.time_spent_seconds or 0) + time_diff
        response.answer = payload.answer
        response.submitted_at = current_time
    else:
        # Create new response
        # Find the last submitted response for this session to calculate start_time
        last_resp_query = await db.execute(
            select(Response)
            .where(Response.session_id == session_uuid)
            .order_by(Response.submitted_at.desc())
            .limit(1)
        )
        last_resp = last_resp_query.scalar_one_or_none()
        start_time = last_resp.submitted_at if last_resp and last_resp.submitted_at else session.started_at
        
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
    session.finished_at = datetime.utcnow()
    session.status = "completed"
    await db.commit()
    background_tasks.add_task(grade_session_background, session_uuid)
    return FinishExamResponse(status="grading")
