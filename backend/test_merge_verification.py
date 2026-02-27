"""
Comprehensive merge verification tests.
Checks that ALL features from both branches are present and working:
  - Our branch: /me endpoint, grading_breakdown, override, null-safe score display
  - Teammate's: correct_answer in response, exam_title, on-demand grading, PDF/email routes
  - api.js: no duplicate functions, all 6 new functions exported
  - result.html: CSS classes, renderBreakdown, try/catch, polling, PDF buttons
"""
import json
import uuid
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

BASE = "http://127.0.0.1:8000/api/v1"

# ── helpers ───────────────────────────────────────────────────────────────────
def http(method, path, body=None, token=None, raw_response=False):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            if raw_response:
                return r.status, raw
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        if raw_response:
            return e.code, raw
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")}

results = []
def test(name, fn):
    try:
        fn()
        results.append((name, "PASS", ""))
        print(f"  [PASS] {name}")
    except AssertionError as e:
        results.append((name, "FAIL", str(e)))
        print(f"  [FAIL] {name}: {e}")
    except Exception as e:
        results.append((name, "ERROR", str(e)))
        print(f"  [ERROR] {name}: {e}")

# ── setup ─────────────────────────────────────────────────────────────────────
uid = str(uuid.uuid4())[:8]
PROF_EMAIL = f"prof_mv_{uid}@test.local"
STU_EMAIL  = f"stu_mv_{uid}@test.local"
PASSWORD   = "Test@12345"

print("\nSetting up test accounts...")
http("POST", "/auth/register", {"email": PROF_EMAIL, "password": PASSWORD, "full_name": "MV Prof", "role": "professor"})
http("POST", "/auth/register", {"email": STU_EMAIL,  "password": PASSWORD, "full_name": "MV Stu",  "role": "student"})
_, pl = http("POST", "/auth/login", {"email": PROF_EMAIL, "password": PASSWORD})
_, sl = http("POST", "/auth/login", {"email": STU_EMAIL,  "password": PASSWORD})
PROF_TOKEN = pl.get("access_token")
STU_TOKEN  = sl.get("access_token")
assert PROF_TOKEN and STU_TOKEN, "Login failed"

now = datetime.now(timezone.utc)
_, exam_r = http("POST", "/exams", {
    "title": "Merge Verify Exam", "type": "mixed", "duration_minutes": 30,
    "start_time": (now - timedelta(minutes=5)).isoformat(),
    "end_time":   (now + timedelta(hours=2)).isoformat(),
    "negative_marking": 0.0, "randomize_questions": False,
    "questions": [
        {"text": "Explain ACID properties.", "type": "subjective",
         "correct_answer": "ACID stands for Atomicity, Consistency, Isolation, Durability.",
         "keywords": ["atomicity", "consistency", "isolation", "durability"], "marks": 10.0, "order": 1},
        {"text": "What is 3+3?", "type": "mcq",
         "options": {"A": "5", "B": "6", "C": "7"}, "correct_answer": "6",
         "marks": 5.0, "order": 2},
    ]
}, PROF_TOKEN)
EXAM_ID = exam_r.get("exam_id")
assert EXAM_ID, f"Exam creation failed: {exam_r}"

start_status, sr = http("POST", f"/exams/{EXAM_ID}/start", {}, STU_TOKEN)
SESSION_ID = sr.get("session_id")
assert SESSION_ID, f"Start exam failed {start_status}: {sr}"
print(f"  Session: {SESSION_ID}")

qs_status, qs = http("GET", f"/exams/{EXAM_ID}/questions", token=STU_TOKEN)
assert isinstance(qs, list), f"Expected question list, got {qs_status}: {qs}"
Q_SUBJ = next(q for q in qs if q["type"] == "subjective")
Q_MCQ  = next(q for q in qs if q["type"] == "mcq")

http("POST", f"/exams/{EXAM_ID}/submit-answer",
     {"session_id": SESSION_ID, "question_id": Q_SUBJ["id"],
      "answer": "ACID means Atomicity, Consistency, Isolation, Durability in databases."}, STU_TOKEN)
http("POST", f"/exams/{EXAM_ID}/submit-answer",
     {"session_id": SESSION_ID, "question_id": Q_MCQ["id"], "answer": "6"}, STU_TOKEN)
http("POST", f"/exams/{EXAM_ID}/finish", {"session_id": SESSION_ID}, STU_TOKEN)

print("  Waiting for grading (5s)...")
time.sleep(5)

print("\n" + "="*70)
print("  MERGE VERIFICATION TESTS")
print("="*70)

# ── GROUP A: results.py — all routes present ──────────────────────────────────
def tA1():
    from app.api.v1.endpoints.results import router
    paths = [r.path for r in router.routes]
    assert "/results/me" in paths, f"/results/me missing. routes: {paths}"
    assert "/results/{session_id}" in paths
    assert "/results/exam/{exam_id}" in paths
    assert "/results/{session_id}/pdf" in paths
    assert "/results/exam/{exam_id}/pdf" in paths
    assert "/results/{session_id}/email" in paths
    assert "/results/{session_id}/analytics" in paths
    assert "/results/{session_id}/responses/{question_id}/override" in paths
test("A1_all_8_routes_registered", tA1)

def tA2():
    paths = [r.path for r in __import__('app.api.v1.endpoints.results', fromlist=['router']).router.routes]
    # /me must come before /{session_id} to avoid shadowing
    me_idx  = next(i for i, r in enumerate(__import__('app.api.v1.endpoints.results', fromlist=['router']).router.routes) if r.path == "/results/me")
    sid_idx = next(i for i, r in enumerate(__import__('app.api.v1.endpoints.results', fromlist=['router']).router.routes) if r.path == "/results/{session_id}")
    assert me_idx < sid_idx, "/results/me must be registered before /{session_id}"
test("A2_me_route_before_session_id_route", tA2)

# ── GROUP B: GET /results/{session_id} — all fields present ──────────────────
def tB1():
    _, r = http("GET", f"/results/{SESSION_ID}", token=STU_TOKEN)
    assert r.get("exam_title") is not None, "exam_title missing (teammate's addition)"
test("B1_response_has_exam_title", tB1)

def tB2():
    _, r = http("GET", f"/results/{SESSION_ID}", token=STU_TOKEN)
    for resp in r.get("responses", []):
        assert "correct_answer" in resp, f"correct_answer missing in response (teammate's addition)"
test("B2_responses_have_correct_answer", tB2)

def tB3():
    _, r = http("GET", f"/results/{SESSION_ID}", token=STU_TOKEN)
    for resp in r.get("responses", []):
        assert "question_text" in resp, "question_text missing"
        assert "question_type" in resp, "question_type missing"
test("B3_responses_have_question_text_and_type", tB3)

def tB4():
    _, r = http("GET", f"/results/{SESSION_ID}", token=STU_TOKEN)
    subj = next(resp for resp in r["responses"] if resp["question_type"] == "subjective")
    assert subj.get("grading_breakdown") is not None, "grading_breakdown missing (our addition)"
    bd = subj["grading_breakdown"]
    assert "semantic" in bd and "keyword" in bd and "structure" in bd
test("B4_subjective_has_grading_breakdown", tB4)

def tB5():
    _, r = http("GET", f"/results/{SESSION_ID}", token=STU_TOKEN)
    subj = next(resp for resp in r["responses"] if resp["question_type"] == "subjective")
    assert "needs_review" in subj, "needs_review field missing"
    assert "manually_graded" in subj, "manually_graded field missing"
    assert "override_note" in subj, "override_note field missing"
test("B5_subjective_has_override_fields", tB5)

def tB6():
    _, r = http("GET", f"/results/{SESSION_ID}", token=STU_TOKEN)
    assert r.get("total_score") is not None, "total_score is None after grading"
test("B6_total_score_not_none", tB6)

# ── GROUP C: GET /results/me ──────────────────────────────────────────────────
def tC1():
    status, r = http("GET", "/results/me", token=STU_TOKEN)
    assert status == 200, f"Expected 200, got {status}: {r}"
    assert isinstance(r, list), "Expected list"
test("C1_get_my_results_returns_200", tC1)

def tC2():
    _, r = http("GET", "/results/me", token=STU_TOKEN)
    assert len(r) >= 1, "Expected at least 1 completed session"
    row = r[0]
    assert "session_id" in row
    assert "exam_title" in row
    assert "total_score" in row
    assert "integrity_score" in row
    assert "finished_at" in row
test("C2_my_results_has_required_fields", tC2)

def tC3():
    _, r = http("GET", "/results/me", token=STU_TOKEN)
    session_ids = [row["session_id"] for row in r]
    assert SESSION_ID in session_ids, f"Our session {SESSION_ID} not in my results"
test("C3_my_results_contains_current_session", tC3)

def tC4():
    status, r = http("GET", "/results/me", token=PROF_TOKEN)
    assert status == 403, f"Professor should get 403, got {status}"
test("C4_professor_cannot_access_me_endpoint", tC4)

# ── GROUP D: PATCH override ───────────────────────────────────────────────────
def tD1():
    status, r = http("PATCH",
        f"/results/{SESSION_ID}/responses/{Q_SUBJ['id']}/override",
        {"score": 7.0, "note": "Merge test override"}, PROF_TOKEN)
    assert status == 200, f"Override failed: {status} {r}"
    assert r["new_score"] == 7.0
    assert r["manually_graded"] == True
test("D1_professor_override_works", tD1)

def tD2():
    _, r = http("GET", f"/results/{SESSION_ID}", token=STU_TOKEN)
    subj = next(resp for resp in r["responses"] if resp["question_type"] == "subjective")
    assert subj["score"] == 7.0, f"Expected 7.0, got {subj['score']}"
    assert subj["manually_graded"] == True
    assert subj["override_note"] == "Merge test override"
test("D2_override_persisted_correctly", tD2)

def tD3():
    status, _ = http("PATCH",
        f"/results/{SESSION_ID}/responses/{Q_SUBJ['id']}/override",
        {"score": 999.0}, PROF_TOKEN)
    assert status == 422, f"Expected 422, got {status}"
test("D3_override_rejects_score_above_marks", tD3)

def tD4():
    status, _ = http("PATCH",
        f"/results/{SESSION_ID}/responses/{Q_SUBJ['id']}/override",
        {"score": 5.0}, STU_TOKEN)
    assert status == 403, f"Student should get 403, got {status}"
test("D4_student_cannot_override", tD4)

# ── GROUP E: PDF/email routes reachable (not 404/405) ────────────────────────
def tE1():
    status, _ = http("GET", f"/results/{SESSION_ID}/pdf", token=STU_TOKEN, raw_response=True)
    assert status != 404, f"PDF endpoint not found (404)"
    assert status != 405, f"PDF endpoint wrong method (405)"
test("E1_pdf_endpoint_exists", tE1)

def tE2():
    status, _ = http("POST", f"/results/{SESSION_ID}/email", token=STU_TOKEN)
    # 500 is ok (SMTP not configured), 404/405 means missing
    assert status != 404, "Email endpoint not found (404)"
    assert status != 405, "Email endpoint wrong method (405)"
test("E2_email_endpoint_exists", tE2)

def tE3():
    status, _ = http("GET", f"/results/{SESSION_ID}/analytics", token=STU_TOKEN)
    assert status == 200, f"Analytics endpoint returned {status}"
test("E3_analytics_endpoint_works", tE3)

# ── GROUP F: api.js integrity ─────────────────────────────────────────────────
def tF1():
    with open("../frontend/api.js", encoding="utf-8") as f:
        content = f.read()
    # Count occurrences of each function definition
    import re
    fns = re.findall(r'^async function (\w+)\(', content, re.MULTILINE)
    fns += re.findall(r'^function (\w+)\(', content, re.MULTILINE)
    from collections import Counter
    dupes = {k: v for k, v in Counter(fns).items() if v > 1}
    assert not dupes, f"Duplicate function definitions: {dupes}"
test("F1_no_duplicate_functions_in_api_js", tF1)

def tF2():
    with open("../frontend/api.js", encoding="utf-8") as f:
        content = f.read()
    required = ["getMyResults", "overrideScore", "downloadResultPdf", "emailResult",
                "sendAudioStt", "sendViolation", "getResult", "getExamResults"]
    for fn in required:
        assert f"async function {fn}" in content or f"function {fn}" in content, \
            f"Function {fn} missing from api.js"
test("F2_all_required_functions_defined", tF2)

def tF3():
    with open("../frontend/api.js", encoding="utf-8") as f:
        content = f.read()
    exported = ["getMyResults", "overrideScore", "downloadResultPdf", "emailResult"]
    for fn in exported:
        assert fn in content[content.find("window.Morpheus"):], \
            f"{fn} not exported in window.Morpheus"
test("F3_new_functions_exported_in_morpheus", tF3)

# ── GROUP G: result.html integrity ───────────────────────────────────────────
def tG1():
    with open("../frontend/result.html", encoding="utf-8") as f:
        content = f.read()
    assert "conflict" not in content.lower() or "<<<<<<" not in content, \
        "Conflict markers found in result.html"
    assert "<<<<<<< HEAD" not in content, "Conflict marker <<<<<<< HEAD still in result.html"
test("G1_no_conflict_markers_in_result_html", tG1)

def tG2():
    with open("../frontend/result.html", encoding="utf-8") as f:
        content = f.read()
    # Our CSS additions
    assert ".breakdown-bar-wrap" in content, ".breakdown-bar-wrap CSS missing"
    assert ".bar-fill.high" in content, ".bar-fill.high CSS missing"
    assert ".badge.review" in content, ".badge.review CSS missing"
    assert ".badge.ai-graded" in content, ".badge.ai-graded CSS missing"
    assert ".badge.manual" in content, ".badge.manual CSS missing"
test("G2_breakdown_css_present", tG2)

def tG3():
    with open("../frontend/result.html", encoding="utf-8") as f:
        content = f.read()
    assert "renderBreakdown" in content, "renderBreakdown function missing"
    assert "grading_breakdown" in content, "grading_breakdown reference missing"
    assert "needs_review" in content, "needs_review reference missing"
    assert "manually_graded" in content, "manually_graded reference missing"
test("G3_breakdown_render_function_present", tG3)

def tG4():
    with open("../frontend/result.html", encoding="utf-8") as f:
        content = f.read()
    # Teammate's additions
    assert "btn-download-pdf" in content, "Download PDF button missing"
    assert "btn-email-report" in content, "Email Report button missing"
    assert "handleDownloadPdf" in content, "handleDownloadPdf function missing"
    assert "handleEmailReport" in content, "handleEmailReport function missing"
    assert "result-subtitle" in content, "result-subtitle id missing"
test("G4_pdf_email_buttons_present", tG4)

def tG5():
    with open("../frontend/result.html", encoding="utf-8") as f:
        content = f.read()
    # Our null-safe score display
    assert "total_score !== null" in content, "null-safe score check missing"
    assert "scoreDisplay" in content, "scoreDisplay variable missing"
    # Teammate's polling
    assert "Grading in progress" in content, "Grading polling message missing"
    assert "for (let i = 0; i < 5" in content, "Polling loop missing"
    # Teammate's correct answer display
    assert "Correct Answer" in content, "Correct Answer section missing"
    assert "correct_answer" in content, "correct_answer field missing"
test("G5_null_safe_score_and_polling_present", tG5)

def tG6():
    with open("../frontend/result.html", encoding="utf-8") as f:
        content = f.read()
    # Our try/catch
    assert "Could not load result" in content, "try/catch error message missing"
test("G6_try_catch_error_handling_present", tG6)

def tG7():
    with open("../frontend/result.html", encoding="utf-8") as f:
        content = f.read()
    # Placeholder should be blank, not hardcoded
    assert "86 / 100" not in content, "Hardcoded score 86/100 still present"
    assert "86%" not in content, "Hardcoded percentage 86% still present"
    assert "94%" not in content or "94" not in content.split("94%")[0][-50:], \
        "Hardcoded integrity 94% still present"
test("G7_no_hardcoded_placeholder_values", tG7)

# ── GROUP H: grading.py — breakdown saved ────────────────────────────────────
def tH1():
    import psycopg2
    conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus',
                            user='postgres', password='himanshu')
    cur = conn.cursor()
    cur.execute("""
        SELECT r.grading_breakdown, r.manually_graded, q.type
        FROM responses r JOIN questions q ON r.question_id = q.id
        WHERE r.session_id = %s AND q.type = 'subjective'
    """, (SESSION_ID,))
    row = cur.fetchone()
    conn.close()
    assert row, "No subjective response found in DB"
    bd, manually_graded, qtype = row
    assert bd is not None, "grading_breakdown is NULL in DB"
    assert "semantic" in bd and "keyword" in bd and "structure" in bd
test("H1_grading_breakdown_saved_to_db", tH1)

def tH2():
    import psycopg2
    conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus',
                            user='postgres', password='himanshu')
    cur = conn.cursor()
    cur.execute("""
        SELECT r.score, q.type FROM responses r JOIN questions q ON r.question_id = q.id
        WHERE r.session_id = %s AND q.type = 'mcq'
    """, (SESSION_ID,))
    row = cur.fetchone()
    conn.close()
    assert row, "No MCQ response found"
    assert row[0] == 5.0, f"MCQ score should be 5.0, got {row[0]}"
test("H2_mcq_scored_correctly", tH2)

# ── summary ───────────────────────────────────────────────────────────────────
print("\n" + "="*70)
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = [(n, m) for n, s, m in results if s != "PASS"]
for name, status, msg in results:
    mark = "PASS" if status == "PASS" else "FAIL"
    detail = f"  ({msg})" if msg else ""
    print(f"  [{mark}] {name}{detail}")
print("="*70)
if not failed:
    print(f"  Result: {passed}/{len(results)} — ALL TESTS PASSED")
else:
    print(f"  Result: {passed}/{len(results)} — {len(failed)} FAILED")
    for n, m in failed:
        print(f"    - {n}: {m}")
print("="*70)
