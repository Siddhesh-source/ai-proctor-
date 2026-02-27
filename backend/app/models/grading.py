import asyncio
import http.client
import json
import logging
import os
import uuid
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

# Judge0 CE language IDs: https://ce.judge0.com/languages/
JUDGE0_LANGUAGE_IDS = {
    "python":     71,  # Python 3
    "python3":    71,
    "javascript": 63,  # Node.js
    "js":         63,
    "typescript": 74,
    "java":       62,
    "c":          50,  # C (GCC)
    "c++":        54,  # C++ (GCC)
    "cpp":        54,
    "go":         60,
    "rust":       73,
    "ruby":       72,
    "kotlin":     78,
    "swift":      83,
    "r":          80,
    "php":        68,
    "csharp":     51,
    "c#":         51,
}

def _judge0_host() -> str:
    return os.getenv("JUDGE0_API_HOST", "judge0-ce.p.rapidapi.com")

def _judge0_key() -> str:
    return os.getenv("JUDGE0_API_KEY", "")


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


def _resolve_judge0_language(language: str) -> int:
    key = str(language).strip().lower()
    if key in JUDGE0_LANGUAGE_IDS:
        return JUDGE0_LANGUAGE_IDS[key]
    raise ValueError(f"Unsupported language: {language}")


async def run_code_judge0(code: str, language: str, stdin: str = "") -> dict:
    """Run code via Judge0 RapidAPI. Returns {stdout, stderr, exit_code}."""
    import base64

    key  = _judge0_key()
    host = _judge0_host()

    if not key:
        return {"stdout": "", "stderr": "JUDGE0_API_KEY not set in .env", "exit_code": -1}

    lang_id = _resolve_judge0_language(language)
    payload = json.dumps({
        "source_code": base64.b64encode(code.encode()).decode(),
        "language_id": lang_id,
        "stdin": base64.b64encode(stdin.encode()).decode() if stdin else "",
    })
    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": host,
        "Content-Type": "application/json",
    }

    def _send() -> dict:
        conn = http.client.HTTPSConnection(host, timeout=30)
        conn.request("POST", "/submissions?base64_encoded=true&wait=true&fields=*", payload, headers)
        res = conn.getresponse()
        return json.loads(res.read().decode("utf-8"))

    result = await asyncio.to_thread(_send)

    def _decode(val: str | None) -> str:
        if not val:
            return ""
        try:
            return base64.b64decode(val).decode("utf-8", errors="replace")
        except Exception:
            return val

    stdout = _decode(result.get("stdout"))
    stderr = _decode(result.get("stderr")) or _decode(result.get("compile_output"))
    exit_code = result.get("exit_code") or 0
    status = result.get("status", {})
    # status_id: 3=Accepted, 4=Wrong Answer — anything else is an error
    if status.get("id", 3) not in (3, 4):
        stderr = stderr or status.get("description", "Runtime error")

    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}


# Alias used by the /run-code endpoint
run_code_piston = run_code_judge0


async def grade_code(student_code: str, language: str, test_cases: list[dict], marks: float) -> dict:
    """Grade code against test cases using Judge0. Returns {score, passed, total, results}."""
    if not test_cases or not student_code.strip():
        return {"score": 0.0, "passed": 0, "total": len(test_cases), "results": []}

    total = len(test_cases)
    passed = 0
    results = []

    for case in test_cases:
        stdin = str(case.get("input") or case.get("stdin") or "")
        expected = str(case.get("expected_output") or "").strip()
        run = await run_code_judge0(student_code, language, stdin)
        stdout = run["stdout"].strip()
        ok = stdout == expected
        if ok:
            passed += 1
        results.append({
            "input": stdin,
            "expected": expected,
            "got": stdout,
            "passed": ok,
            "stderr": run["stderr"][:200] if run["stderr"] else "",
        })

    score = round((passed / total) * marks, 2) if total else 0.0
    return {"score": score, "passed": passed, "total": total, "results": results}


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
            language = question.code_language or ""
            test_cases = question.test_cases or []
            if language and test_cases:
                result = await grade_code(response.answer or "", language, test_cases, question.marks)
                score = float(result["score"])
                if not response.manually_graded:
                    response.grading_breakdown = {
                        "passed": result["passed"],
                        "total": result["total"],
                        "results": result["results"],
                    }
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
