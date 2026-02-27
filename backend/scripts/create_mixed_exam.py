"""Create a mixed exam with 30 questions via API."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:8000/api/v1"
PROF_EMAIL = "faculty.demo@vit.edu"
PROF_PASSWORD = "Faculty@12345"


def _request(method: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
    body = json.dumps(payload or {}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"{BASE}{path}", data=body if payload is not None else None, headers=headers, method=method)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_questions() -> list[dict]:
    questions: list[dict] = []
    for idx in range(1, 21):
        questions.append(
            {
                "text": f"MCQ {idx}: Which option is correct?",
                "type": "mcq",
                "options": {
                    "A": "Option A",
                    "B": "Option B",
                    "C": "Option C",
                    "D": "Option D",
                },
                "correct_answer": "B",
                "keywords": ["concept", "mcq"],
                "marks": 1,
                "order": idx,
            }
        )

    for idx in range(21, 29):
        questions.append(
            {
                "text": f"Subjective {idx - 20}: Explain the concept clearly.",
                "type": "subjective",
                "options": None,
                "correct_answer": "Provide a concise explanation of the concept.",
                "keywords": ["explain", "concept"],
                "marks": 5,
                "order": idx,
            }
        )

    questions.append(
        {
            "text": "Code 1: Read two integers and print their sum.",
            "type": "code",
            "options": {
                "language": "python 3x",
                "test_cases": [
                    {"stdin": "2 3\n", "expected_output": "5", "marks": 10},
                    {"stdin": "10 20\n", "expected_output": "30", "marks": 10},
                ],
            },
            "correct_answer": "",
            "keywords": None,
            "marks": 10,
            "order": 29,
        }
    )

    questions.append(
        {
            "text": "Code 2: Given n, print factorial of n.",
            "type": "code",
            "options": {
                "language": "python 3x",
                "test_cases": [
                    {"stdin": "5\n", "expected_output": "120", "marks": 10},
                    {"stdin": "3\n", "expected_output": "6", "marks": 10},
                ],
            },
            "correct_answer": "",
            "keywords": None,
            "marks": 10,
            "order": 30,
        }
    )

    return questions


def main() -> None:
    token = _request("POST", "/auth/login", {"email": PROF_EMAIL, "password": PROF_PASSWORD})["access_token"]
    now = datetime.now(timezone.utc)
    payload = {
        "title": "Midterm Mixed 30Q",
        "type": "mixed",
        "duration_minutes": 120,
        "start_time": (now + timedelta(minutes=1)).isoformat(),
        "end_time": (now + timedelta(minutes=121)).isoformat(),
        "negative_marking": 0.0,
        "randomize_questions": False,
        "questions": build_questions(),
    }
    result = _request("POST", "/exams", payload, token=token)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
