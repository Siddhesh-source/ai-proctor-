"""Comprehensive tests for Judge0 RapidAPI code execution + grading."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env manually (no python-dotenv dependency needed)
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from app.models.grading import run_code_judge0, grade_code, _resolve_judge0_language

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []

def check(label, ok, detail=""):
    results.append(ok)
    status = PASS if ok else FAIL
    print(f"  [{status}] {label}" + (f"  => {detail}" if detail else ""))


# ── 1. Environment / config ───────────────────────────────────────────────────
print("\n=== 1. Environment ===")
key = os.getenv("JUDGE0_API_KEY", "")
host = os.getenv("JUDGE0_API_HOST", "judge0-ce.p.rapidapi.com")
check("JUDGE0_API_KEY loaded", bool(key), f"{key[:8]}..." if key else "MISSING")
check("JUDGE0_API_HOST set", bool(host), host)


# ── 2. Language ID resolution ─────────────────────────────────────────────────
print("\n=== 2. Language ID resolution ===")
lang_cases = [
    ("python", 71), ("python3", 71), ("javascript", 63), ("js", 63),
    ("java", 62), ("c++", 54), ("cpp", 54), ("go", 60), ("rust", 73),
    ("ruby", 72), ("kotlin", 78), ("swift", 83), ("r", 80), ("php", 68),
    ("csharp", 51), ("c#", 51), ("typescript", 74),
]
for lang, expected_id in lang_cases:
    try:
        got = _resolve_judge0_language(lang)
        check(f"resolve '{lang}' → {expected_id}", got == expected_id, f"got {got}")
    except Exception as e:
        check(f"resolve '{lang}'", False, str(e))

try:
    _resolve_judge0_language("brainfuck")
    check("unknown language raises ValueError", False, "no error raised")
except ValueError:
    check("unknown language raises ValueError", True)


# ── 3. Basic run_code_judge0 ──────────────────────────────────────────────────
print("\n=== 3. run_code_judge0 — basic execution ===")

async def test_run():
    # Python hello world
    r = await run_code_judge0('print("Hello, World!")', "python")
    check("Python: hello world stdout", r["stdout"].strip() == "Hello, World!", repr(r["stdout"].strip()))

    # Python stdin
    r = await run_code_judge0("n = int(input()); print(n * 2)", "python", stdin="5")
    check("Python: stdin → stdout", r["stdout"].strip() == "10", repr(r["stdout"].strip()))

    # Python multi-line output
    r = await run_code_judge0("for i in range(3): print(i)", "python")
    check("Python: multi-line output", r["stdout"].strip() == "0\n1\n2", repr(r["stdout"].strip()))

    # Python syntax error → stderr
    r = await run_code_judge0("def broken(", "python")
    has_err = bool(r["stderr"].strip())
    check("Python: syntax error → stderr non-empty", has_err, repr(r["stderr"][:60]))

    # JavaScript
    r = await run_code_judge0('console.log("JS works")', "javascript")
    check("JavaScript: hello world", r["stdout"].strip() == "JS works", repr(r["stdout"].strip()))

    # JavaScript stdin via process.stdin
    r = await run_code_judge0(
        'const lines=[]; process.stdin.on("data",d=>lines.push(...d.toString().trim().split("\\n"))); process.stdin.on("end",()=>{console.log(parseInt(lines[0])*3)});',
        "javascript", stdin="4"
    )
    check("JavaScript: stdin multiply", r["stdout"].strip() == "12", repr(r["stdout"].strip()))

asyncio.run(test_run())


# ── 4. grade_code ─────────────────────────────────────────────────────────────
print("\n=== 4. grade_code — test case grading ===")

async def test_grade():
    # All pass
    code = "n = int(input()); print(n * 2)"
    cases = [
        {"input": "3", "expected_output": "6"},
        {"input": "5", "expected_output": "10"},
        {"input": "0", "expected_output": "0"},
    ]
    g = await grade_code(code, "python", cases, 10.0)
    check("grade_code: all pass → score=10.0", g["score"] == 10.0, str(g))
    check("grade_code: all pass → passed=3", g["passed"] == 3, str(g["passed"]))
    check("grade_code: total=3", g["total"] == 3, str(g["total"]))
    check("grade_code: results list length", len(g["results"]) == 3, str(len(g["results"])))

    # Partial pass
    code2 = "n = int(input()); print(n + 1)"  # wrong: adds 1 instead of *2
    g2 = await grade_code(code2, "python", cases, 10.0)
    check("grade_code: partial fail → passed<3", g2["passed"] < 3, f"passed={g2['passed']}")
    check("grade_code: partial fail → score<10", g2["score"] < 10.0, f"score={g2['score']}")

    # All fail
    code3 = "print('wrong')"
    g3 = await grade_code(code3, "python", cases, 10.0)
    check("grade_code: all fail → passed=0", g3["passed"] == 0, str(g3["passed"]))
    check("grade_code: all fail → score=0", g3["score"] == 0.0, str(g3["score"]))

    # Result structure
    res = g["results"][0]
    check("grade_code: result has 'input'", "input" in res, str(res.keys()))
    check("grade_code: result has 'expected'", "expected" in res, str(res.keys()))
    check("grade_code: result has 'got'", "got" in res, str(res.keys()))
    check("grade_code: result has 'passed'", "passed" in res, str(res.keys()))
    check("grade_code: result has 'stderr'", "stderr" in res, str(res.keys()))

    # Empty test cases
    g4 = await grade_code("print(1)", "python", [], 10.0)
    check("grade_code: empty test_cases → score=0", g4["score"] == 0.0, str(g4))

    # Empty code
    g5 = await grade_code("", "python", cases, 10.0)
    check("grade_code: empty code → score=0", g5["score"] == 0.0, str(g5))

    # Marks proportional
    code6 = "n = int(input()); print(n * 2)"
    cases6 = [
        {"input": "1", "expected_output": "2"},
        {"input": "2", "expected_output": "WRONG"},  # will fail
    ]
    g6 = await grade_code(code6, "python", cases6, 20.0)
    check("grade_code: 1/2 pass → score=10.0", g6["score"] == 10.0, str(g6["score"]))

asyncio.run(test_grade())


# ── 5. /run-code endpoint via FastAPI test client ─────────────────────────────
print("\n=== 5. /run-code endpoint (FastAPI TestClient) ===")
try:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)

    # Need a valid token — create one inline
    from app.utils.auth import create_access_token
    token = create_access_token({"sub": "test@test.com", "role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/v1/exams/run-code", json={
        "code": "print('endpoint works')",
        "language": "python",
        "stdin": "",
    }, headers=headers)
    check("/run-code: HTTP 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        data = r.json()
        check("/run-code: stdout present", "stdout" in data, str(data.keys()))
        check("/run-code: stdout correct", data["stdout"].strip() == "endpoint works", repr(data["stdout"]))
        check("/run-code: stderr key present", "stderr" in data, str(data.keys()))
        check("/run-code: exit_code key present", "exit_code" in data, str(data.keys()))
    else:
        print(f"    Response: {r.text[:200]}")
        for _ in range(4): results.append(False)

    # Language mismatch (unsupported)
    r2 = client.post("/api/v1/exams/run-code", json={
        "code": "print(1)", "language": "brainfuck", "stdin": ""
    }, headers=headers)
    check("/run-code: unsupported language → 4xx", r2.status_code >= 400, f"status={r2.status_code}")

except Exception as e:
    print(f"  [SKIP] TestClient unavailable: {e}")


# ── Summary ───────────────────────────────────────────────────────────────────
total = len(results)
passed = sum(results)
failed = total - passed
print(f"\n{'='*50}")
print(f"TOTAL: {passed}/{total} passed  ({failed} failed)")
print("=" * 50)
if failed:
    sys.exit(1)
