import asyncio
import json
import logging
import os
import uuid
import urllib.request
from datetime import datetime, timezone
from typing import Any

os.environ.setdefault("TRANSFORMERS_NO_CODECARBON", "1")

from sentence_transformers import SentenceTransformer, util
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Exam, Question, Response, Result, Session as ExamSession

logger = logging.getLogger(__name__)


try:
    nlp_model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("SentenceTransformer loaded")
except Exception as exc:
    logger.exception("SentenceTransformer load failed")
    raise

LANGUAGE_CHOICES = {
    "c": "11",
    "c#": "27",
    "c++": "1",
    "go": "114",
    "java": "10",
    "kotlin": "47",
    "node.js": "56",
    "objective-c": "43",
    "php": "29",
    "perl-6": "54",
    "python 3x": "116",
    "r": "117",
    "ruby": "17",
    "rust": "93",
    "sqlite-queries": "52",
    "sqlite-schema": "40",
    "scala": "39",
    "swift": "85",
    "typescript": "57",
}


def grade_mcq(
    student_answer: str,
    correct_answer: str,
    marks: float,
    negative_marking: float,
) -> float:
    if not student_answer:
        return 0.0
    if student_answer.strip().lower() == correct_answer.strip().lower():
        return float(marks)
    return -(float(marks) * float(negative_marking))


def grade_subjective(
    student_answer: str,
    correct_answer: str,
    keywords: list[str],
    marks: float,
) -> dict:
    semantic = util.cos_sim(
        nlp_model.encode(student_answer),
        nlp_model.encode(correct_answer),
    ).item()
    kw_score = (
        sum(1 for k in keywords if k.lower() in student_answer.lower())
        / max(len(keywords), 1)
    )
    word_diff = abs(len(student_answer.split()) - len(correct_answer.split()))
    struct_score = max(0.0, 1 - word_diff / 100)
    final = (semantic * 0.6 + kw_score * 0.25 + struct_score * 0.15) * marks
    return {
        "score": round(final, 2),
        "semantic": round(semantic, 3),
        "keyword": round(kw_score, 3),
        "structure": round(struct_score, 3),
    }


def _resolve_language_id(language: str | int) -> str:
    if isinstance(language, int):
        return str(language)
    lang = str(language).strip()
    if lang.isdigit():
        return lang
    lang_key = lang.lower()
    if lang_key in LANGUAGE_CHOICES:
        return LANGUAGE_CHOICES[lang_key]
    raise ValueError("Unsupported language")


async def _post_json(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")

    def _send() -> dict:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    return await asyncio.to_thread(_send)


async def grade_code(student_code: str, language: str | int, test_cases: list[dict]) -> dict:
    if not test_cases:
        return {"score": 0.0, "passed": 0, "total": 0}
    api_key = os.getenv("JUDGE0_API_KEY")
    if not api_key:
        raise RuntimeError("JUDGE0_API_KEY is not configured")
    host = os.getenv("JUDGE0_API_HOST", "judge0-ce.p.rapidapi.com")
    language_id = _resolve_language_id(language)
    total = len(test_cases)
    passed = 0
    marks = float(test_cases[0].get("marks", 0.0)) if test_cases else 0.0
    for case in test_cases:
        stdin = case.get("stdin") or case.get("input") or ""
        expected = (case.get("expected_output") or "").strip()
        payload = {
            "language_id": language_id,
            "source_code": student_code or "",
            "stdin": stdin,
        }
        response = await _post_json(
            f"https://{host}/submissions?base64_encoded=false&wait=true",
            payload,
            {
                "Content-Type": "application/json",
                "X-RapidAPI-Key": api_key,
                "X-RapidAPI-Host": host,
            },
        )
        stdout = (response.get("stdout") or "").strip()
        if stdout == expected:
            passed += 1
    score = (passed / total) * marks if total else 0.0
    return {"score": score, "passed": passed, "total": total}


async def grade_session(session_id: uuid.UUID, db: AsyncSession) -> None:
    session_result = await db.execute(select(ExamSession).where(ExamSession.id == session_id))
    session = session_result.scalar_one_or_none()
    if not session:
        return
    exam_result = await db.execute(select(Exam).where(Exam.id == session.exam_id))
    exam = exam_result.scalar_one_or_none()
    if not exam:
        return
    response_result = await db.execute(
        select(Response, Question)
        .join(Question, Response.question_id == Question.id)
        .where(Response.session_id == session_id)
    )
    rows = response_result.all()
    total_score = 0.0
    for response, question in rows:
        score = 0.0
        if question.type == "mcq":
            score = grade_mcq(
                response.answer or "",
                question.correct_answer or "",
                question.marks,
                exam.negative_marking or 0.0,
            )
        elif question.type == "subjective":
            result = grade_subjective(
                response.answer or "",
                question.correct_answer or "",
                question.keywords or [],
                question.marks,
            )
            score = float(result["score"])
            if not response.manually_graded:
                response.grading_breakdown = {
                    "semantic": result["semantic"],
                    "keyword": result["keyword"],
                    "structure": result["structure"],
                    "needs_review": result["semantic"] < 0.45,
                }
        elif question.type == "code":
            options: dict[str, Any] = question.options or {}
            language = options.get("language") or options.get("language_id") or options.get("lang")
            test_cases = options.get("test_cases", []) if isinstance(options, dict) else []
            for case in test_cases:
                if isinstance(case, dict) and "marks" not in case:
                    case["marks"] = question.marks
            if language and test_cases:
                result = await grade_code(response.answer or "", language, test_cases)
                score = float(result["score"])
        response.score = score
        response.graded_at = datetime.now(timezone.utc)
        total_score += score
    await db.flush()
    result_row = await db.execute(select(Result).where(Result.session_id == session_id))
    existing = result_row.scalar_one_or_none()
    if existing:
        existing.total_score = total_score
        existing.integrity_score = session.integrity_score
        existing.violation_summary = existing.violation_summary or {}
        existing.generated_at = datetime.now(timezone.utc)
    else:
        db.add(
            Result(
                session_id=session_id,
                total_score=total_score,
                integrity_score=session.integrity_score,
                violation_summary={},
            )
        )
    await db.commit()
