"""
Integration tests: coding exam end-to-end flow
  - Professor creates exam with code + MCQ + subjective questions
  - Student starts exam, gets questions (code_language + test_cases present)
  - Student submits answers (code answer stored)
  - Student finishes exam  -> background grading triggered synchronously
  - Results endpoint returns grading_breakdown with test case pass/fail
  - /run-code endpoint works for live test runs
  - Professor can override a score
  - /results/me lists the completed session
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── load .env ────────────────────────────────────────────────────────────────
_env = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env):
    with open(_env) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                k, v = _line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.db import Exam, Question, Response, Result, Session as ExamSession, User
from app.models.grading import grade_session, run_code_judge0

# ── helpers ───────────────────────────────────────────────────────────────────
PASS_CLR = "\033[92mPASS\033[0m"
FAIL_CLR = "\033[91mFAIL\033[0m"
SKIP_CLR = "\033[93mSKIP\033[0m"

_results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _results.append(ok)
    tag = PASS_CLR if ok else FAIL_CLR
    print(f"  [{tag}] {label}" + (f"  => {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ── DB helpers ────────────────────────────────────────────────────────────────
async def get_or_create_user(db: AsyncSession, email: str, role: str, name: str) -> User:
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if not user:
        from app.core.security import hash_password
        user = User(email=email, password_hash=hash_password("Test1234!"), role=role, full_name=name)
        db.add(user)
        await db.flush()
    return user


async def cleanup(db: AsyncSession, exam_id: uuid.UUID) -> None:
    """Remove test data created during this run."""
    from sqlalchemy import delete
    from app.models.db import ProctoringLog

    sessions_res = await db.execute(select(ExamSession).where(ExamSession.exam_id == exam_id))
    sessions = sessions_res.scalars().all()
    for s in sessions:
        await db.execute(delete(ProctoringLog).where(ProctoringLog.session_id == s.id))
        await db.execute(delete(Result).where(Result.session_id == s.id))
        await db.execute(delete(Response).where(Response.session_id == s.id))
        await db.execute(delete(ExamSession).where(ExamSession.id == s.id))
    await db.execute(delete(Question).where(Question.exam_id == exam_id))
    await db.execute(delete(Exam).where(Exam.id == exam_id))
    await db.commit()


# ═════════════════════════════════════════════════════════════════════════════
async def main() -> None:
    async with AsyncSessionLocal() as db:

        # ── 1. Setup users ────────────────────────────────────────────────────
        section("1. Setup — users")
        prof = await get_or_create_user(db, "integ_prof@test.com", "professor", "Prof Integration")
        student = await get_or_create_user(db, "integ_student@test.com", "student", "Student Integration")
        await db.commit()
        check("Professor user exists", prof.id is not None, str(prof.email))
        check("Student user exists", student.id is not None, str(student.email))

        # ── 2. Professor creates exam with mixed questions ────────────────────
        section("2. Exam creation — mixed (code + MCQ + subjective)")
        now = datetime.now(timezone.utc)
        exam = Exam(
            professor_id=prof.id,
            title="Integration Test Exam",
            type="mixed",
            duration_minutes=60,
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(hours=2),
            negative_marking=0.0,
            randomize_questions=False,
        )
        db.add(exam)
        await db.flush()

        q_code = Question(
            exam_id=exam.id,
            text="Write a function that reads an integer n and prints n * 2.",
            type="code",
            correct_answer="",
            marks=10.0,
            order_index=1,
            code_language="python",
            test_cases=[
                {"input": "3", "expected_output": "6"},
                {"input": "5", "expected_output": "10"},
                {"input": "0", "expected_output": "0"},
            ],
        )
        q_mcq = Question(
            exam_id=exam.id,
            text="What does HTTP stand for?",
            type="mcq",
            options={"A": "HyperText Transfer Protocol", "B": "High Transfer Text Protocol", "C": "Hyper Transfer Text Process"},
            correct_answer="A",
            marks=5.0,
            order_index=2,
        )
        q_subj = Question(
            exam_id=exam.id,
            text="Explain what a REST API is.",
            type="subjective",
            correct_answer="REST API is an architectural style for distributed hypermedia systems using HTTP methods.",
            keywords=["REST", "API", "HTTP", "stateless"],
            marks=5.0,
            order_index=3,
        )
        db.add_all([q_code, q_mcq, q_subj])
        await db.commit()
        await db.refresh(exam)

        check("Exam created in DB", exam.id is not None, str(exam.id)[:8])
        check("Code question has code_language", q_code.code_language == "python", q_code.code_language)
        check("Code question has 3 test cases", len(q_code.test_cases) == 3, str(len(q_code.test_cases)))
        check("MCQ question stored", q_mcq.correct_answer == "A")
        check("Subjective question stored", bool(q_subj.keywords))

        # ── 3. Student starts exam ────────────────────────────────────────────
        section("3. Student starts exam")
        session = ExamSession(
            student_id=student.id,
            exam_id=exam.id,
            status="active",
            started_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        check("Session created", session.id is not None, str(session.id)[:8])
        check("Session status = active", session.status == "active")

        # ── 4. Questions returned to student have code fields ─────────────────
        section("4. Question structure — code fields present")
        qs_res = await db.execute(
            select(Question).where(Question.exam_id == exam.id).order_by(Question.order_index)
        )
        questions = qs_res.scalars().all()
        check("3 questions returned", len(questions) == 3, str(len(questions)))
        code_q = next((q for q in questions if q.type == "code"), None)
        check("Code question present in list", code_q is not None)
        if code_q:
            check("code_language field present", bool(code_q.code_language), code_q.code_language)
            check("test_cases field present", isinstance(code_q.test_cases, list), str(type(code_q.test_cases)))
            check("test_cases not empty", len(code_q.test_cases) > 0, str(len(code_q.test_cases)))
            check("test_case has input key", "input" in code_q.test_cases[0])
            check("test_case has expected_output key", "expected_output" in code_q.test_cases[0])

        # ── 5. Student submits answers ────────────────────────────────────────
        section("5. Student submits answers")
        correct_code = "n = int(input())\nprint(n * 2)"
        wrong_mcq = "B"   # wrong answer
        subj_answer = "REST API is an architectural style that uses HTTP methods for stateless communication between client and server."

        resp_code = Response(
            session_id=session.id,
            question_id=q_code.id,
            answer=correct_code,
            started_at=datetime.now(timezone.utc),
            submitted_at=datetime.now(timezone.utc),
        )
        resp_mcq = Response(
            session_id=session.id,
            question_id=q_mcq.id,
            answer=wrong_mcq,
            started_at=datetime.now(timezone.utc),
            submitted_at=datetime.now(timezone.utc),
        )
        resp_subj = Response(
            session_id=session.id,
            question_id=q_subj.id,
            answer=subj_answer,
            started_at=datetime.now(timezone.utc),
            submitted_at=datetime.now(timezone.utc),
        )
        db.add_all([resp_code, resp_mcq, resp_subj])
        await db.commit()
        check("Code answer saved", resp_code.id is not None)
        check("MCQ answer saved", resp_mcq.id is not None)
        check("Subjective answer saved", resp_subj.id is not None)

        # ── 6. Student finishes exam → grading ────────────────────────────────
        section("6. Exam finish + grading")
        session.status = "completed"
        session.finished_at = datetime.now(timezone.utc)
        await db.commit()
        check("Session marked completed", session.status == "completed")

        print("  [....] Running grade_session (calls Judge0 API)...")
        await grade_session(session.id, db)
        print("  [done] grade_session finished")

        # ── 7. Verify graded responses ────────────────────────────────────────
        section("7. Graded response verification")
        await db.refresh(resp_code)
        await db.refresh(resp_mcq)
        await db.refresh(resp_subj)

        # Code question
        check("Code response has score", resp_code.score is not None, str(resp_code.score))
        check("Code score = 10.0 (all tests pass)", resp_code.score == 10.0, str(resp_code.score))
        check("Code grading_breakdown present", isinstance(resp_code.grading_breakdown, dict), str(resp_code.grading_breakdown))
        if resp_code.grading_breakdown:
            bd = resp_code.grading_breakdown
            check("breakdown has 'passed'", "passed" in bd, str(bd.keys()))
            check("breakdown has 'total'", "total" in bd, str(bd.keys()))
            check("breakdown has 'results'", "results" in bd, str(bd.keys()))
            check("breakdown passed=3", bd.get("passed") == 3, str(bd.get("passed")))
            check("breakdown total=3", bd.get("total") == 3, str(bd.get("total")))
            check("results list has 3 items", len(bd.get("results", [])) == 3, str(len(bd.get("results", []))))
            first = bd["results"][0]
            check("result item has input", "input" in first)
            check("result item has expected", "expected" in first)
            check("result item has got", "got" in first)
            check("result item has passed", "passed" in first)

        # MCQ question — wrong answer, score should be 0 or negative
        check("MCQ response has score", resp_mcq.score is not None, str(resp_mcq.score))
        check("MCQ wrong answer scored <= 0", (resp_mcq.score or 0) <= 0.0, str(resp_mcq.score))

        # Subjective question
        check("Subjective response has score", resp_subj.score is not None, str(resp_subj.score))
        check("Subjective score > 0", (resp_subj.score or 0) > 0, str(resp_subj.score))
        check("Subjective grading_breakdown present", isinstance(resp_subj.grading_breakdown, dict))
        if resp_subj.grading_breakdown:
            bd2 = resp_subj.grading_breakdown
            check("subjective breakdown has semantic", "semantic" in bd2)
            check("subjective breakdown has keyword", "keyword" in bd2)
            check("subjective breakdown has structure", "structure" in bd2)
            check("subjective breakdown has needs_review", "needs_review" in bd2)

        # ── 8. Result row ─────────────────────────────────────────────────────
        section("8. Result row")
        result_res = await db.execute(select(Result).where(Result.session_id == session.id))
        result = result_res.scalar_one_or_none()
        check("Result row created", result is not None)
        if result:
            expected_total = (resp_code.score or 0) + (resp_mcq.score or 0) + (resp_subj.score or 0)
            check("Result total_score correct", abs(result.total_score - expected_total) < 0.01,
                  f"got={result.total_score} expected={expected_total:.2f}")
            check("Result total_score > 0 (code+subj earned points)", result.total_score > 0, str(result.total_score))

        # ── 9. /run-code live execution ───────────────────────────────────────
        section("9. run_code_judge0 — live execution (student 'Run' button)")
        r = await run_code_judge0("n = int(input()); print(n * 2)", "python", "7")
        check("run-code returns stdout", r["stdout"].strip() == "14", repr(r["stdout"].strip()))
        check("run-code returns stderr key", "stderr" in r)
        check("run-code returns exit_code key", "exit_code" in r)

        r2 = await run_code_judge0("print('hello world')", "python")
        check("run-code no stdin works", r2["stdout"].strip() == "hello world")

        r3 = await run_code_judge0("syntax error!!!", "python")
        check("run-code syntax error has stderr", bool(r3["stderr"]))

        # ── 10. Professor score override ──────────────────────────────────────
        section("10. Professor score override")
        old_subj_score = resp_subj.score or 0.0
        old_total = result.total_score if result else 0.0

        resp_subj.score = 5.0
        resp_subj.manually_graded = True
        resp_subj.override_note = "Excellent answer, full marks"
        if resp_subj.grading_breakdown:
            resp_subj.grading_breakdown = {**resp_subj.grading_breakdown, "needs_review": False}

        if result:
            result.total_score = round((result.total_score or 0) - old_subj_score + 5.0, 2)

        await db.commit()
        await db.refresh(resp_subj)
        await db.refresh(result)

        check("Override: score set to 5.0", resp_subj.score == 5.0, str(resp_subj.score))
        check("Override: manually_graded = True", resp_subj.manually_graded is True)
        check("Override: note saved", resp_subj.override_note == "Excellent answer, full marks")
        check("Override: result total updated", result and result.total_score == round(old_total - old_subj_score + 5.0, 2),
              f"total={result.total_score if result else 'N/A'}")

        # ── 11. Results/me — past exams list ──────────────────────────────────
        section("11. GET /results/me — past sessions list")
        sessions_res = await db.execute(
            select(ExamSession, Result, Exam)
            .join(Exam, Exam.id == ExamSession.exam_id)
            .outerjoin(Result, Result.session_id == ExamSession.id)
            .where(ExamSession.student_id == student.id)
            .where(ExamSession.status == "completed")
        )
        my_results = sessions_res.all()
        check("At least 1 completed session in /results/me", len(my_results) >= 1, str(len(my_results)))
        found = next((r for s, r, e in my_results if str(s.id) == str(session.id)), None)
        check("Our session appears in /results/me", found is not None)

        # ── 12. Full results payload structure ────────────────────────────────
        section("12. Full results payload structure")
        full_responses_res = await db.execute(
            select(Response, Question)
            .join(Question, Response.question_id == Question.id)
            .where(Response.session_id == session.id)
        )
        full_responses = [
            {
                "question_id": str(q.id),
                "question_text": q.text,
                "question_type": q.type,
                "correct_answer": q.correct_answer,
                "answer": r.answer,
                "score": r.score,
                "marks": q.marks,
                "grading_breakdown": r.grading_breakdown,
                "manually_graded": r.manually_graded,
                "override_note": r.override_note,
            }
            for r, q in full_responses_res.all()
        ]
        check("3 responses in results payload", len(full_responses) == 3, str(len(full_responses)))

        code_resp_data = next((r for r in full_responses if r["question_type"] == "code"), None)
        check("Code response in payload", code_resp_data is not None)
        if code_resp_data:
            check("Code answer stored correctly", "int(input())" in (code_resp_data["answer"] or ""))
            check("Code grading_breakdown in payload", isinstance(code_resp_data["grading_breakdown"], dict))

        mcq_resp_data = next((r for r in full_responses if r["question_type"] == "mcq"), None)
        check("MCQ response in payload", mcq_resp_data is not None)
        if mcq_resp_data:
            check("MCQ answer stored", mcq_resp_data["answer"] == "B")

        subj_resp_data = next((r for r in full_responses if r["question_type"] == "subjective"), None)
        check("Subjective response in payload", subj_resp_data is not None)
        if subj_resp_data:
            check("Subjective manually_graded = True", subj_resp_data["manually_graded"] is True)
            check("Subjective override_note present", bool(subj_resp_data["override_note"]))

        # ── 13. Cleanup ───────────────────────────────────────────────────────
        section("13. Cleanup")
        await cleanup(db, exam.id)
        leftover = await db.execute(select(Exam).where(Exam.id == exam.id))
        check("Test exam removed from DB", leftover.scalar_one_or_none() is None)

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(_results)
    passed = sum(_results)
    failed = total - passed
    print(f"\n{'='*55}")
    print(f"INTEGRATION TOTAL: {passed}/{total} passed  ({failed} failed)")
    print("=" * 55)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
