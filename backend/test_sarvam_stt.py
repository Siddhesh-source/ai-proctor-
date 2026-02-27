import sys, asyncio
sys.path.insert(0, '.')

results = {}

# ─── TEST 1: Keyword detection logic ────────────────────────────────
from app.core.sarvam import _check_keywords

cases = [
    ("bata do answer kya hai",                                          1),
    ("what is the answer to question 3",                                1),
    ("correct answer is option C",                                      1),
    ("which of the following options correctly describes the process",   2),
    ("kya yeh option sahi hai ya kaun sa option select karna chahiye",  2),
    ("I am sitting here quietly",                                       0),
    ("okay fine yes no",                                                0),
]
for text, expected_tier in cases:
    tier, kw = _check_keywords(text)
    key = f"keyword_{expected_tier}_{text[:25].replace(' ','_')}"
    results[key] = ('PASS' if tier == expected_tier else 'FAIL', f"tier={tier} kw={kw}")

# ─── TEST 2: Integrity weight ────────────────────────────────────────
from app.utils.integrity import WEIGHTS, update_integrity

w = WEIGHTS.get('speech_cheating')
results['weight_defined']   = ('PASS' if w == 0.35 else 'FAIL', f"weight={w}")
score = update_integrity(100.0, 'speech_cheating', 0.90)
results['weight_penalty']   = ('PASS' if score == 68.5 else 'FAIL', f"score={score} expected=68.5")

# ─── TEST 3: Config field ────────────────────────────────────────────
from app.core.config import Settings
results['config_field']     = ('PASS' if 'SARVAM_API_KEY' in Settings.model_fields else 'FAIL', 'SARVAM_API_KEY in Settings')

# ─── TEST 4: Endpoint registered ─────────────────────────────────────
from app.api.v1.endpoints.proctoring import router
routes = [r.path for r in router.routes]
results['endpoint_exists']  = ('PASS' if '/proctoring/audio/stt' in routes else 'FAIL', f"routes={routes}")

# ─── TEST 5: No-key returns skipped ─────────────────────────────────
import requests, uuid, psycopg2

BASE = 'http://127.0.0.1:8000'
resp = requests.post(f'{BASE}/api/v1/auth/login', json={'email': 'demo.student@morpheus.local', 'password': 'Demo@12345'})
token = resp.json()['access_token']
H = {'Authorization': f'Bearer {token}'}

async def make_session():
    from app.core.database import AsyncSessionLocal
    from app.models.db import Session, User
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(User).where(User.email == 'demo.student@morpheus.local'))
        user = r.scalars().first()
        sid = uuid.uuid4()
        db.add(Session(id=sid, student_id=user.id,
            exam_id=uuid.UUID('997edabb-33af-4832-852d-4886deb19d92'),
            status='active', integrity_score=100.0))
        await db.commit()
        return str(sid)

SID = asyncio.run(make_session())

# Send a dummy audio clip — should return skipped if API key not set
import base64
dummy_audio = base64.b64encode(b'\x00' * 600).decode()
r = requests.post(f'{BASE}/api/v1/proctoring/audio/stt', headers=H, json={
    'session_id': SID, 'audio_base64': dummy_audio, 'mime_type': 'audio/webm'
})
results['endpoint_responds'] = ('PASS' if r.status_code == 200 else 'FAIL', f"status={r.status_code}")
j = r.json()
# Either skipped (no real key) or processed (real key)
results['endpoint_returns_valid'] = (
    'PASS' if 'skipped' in j or 'transcript' in j else 'FAIL',
    str(j)
)

# ─── TEST 6: speech_cheating violation via generic endpoint ──────────
r2 = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'speech_cheating',
    'confidence': 0.90, 'payload': {'transcript': 'bata do answer', 'tier': 1}
})
score = r2.json().get('integrity_score')
results['speech_cheating_violation'] = ('PASS' if r2.status_code == 200 else 'FAIL', f"score={score}")
results['speech_cheating_score']     = ('PASS' if score == 68.5 else 'FAIL', f"score={score} expected=68.5")

# ─── TEST 7: sarvam.py analyse_speech mock (no real API call) ────────
from unittest.mock import AsyncMock, patch
from app.core.sarvam import analyse_speech

async def test_analyse():
    mock_result = {'transcript': 'bata do sahi jawab kya hai', 'language_code': 'hi-IN'}
    with patch('app.core.sarvam.transcribe_audio', new=AsyncMock(return_value=mock_result)):
        result = await analyse_speech(b'fakeaudio', 'audio/webm', 'fake_key')
    return result

ar = asyncio.run(test_analyse())
results['analyse_tier1']     = ('PASS' if ar['tier'] == 1 else 'FAIL', f"tier={ar['tier']} violation={ar['violation']}")
results['analyse_confidence']= ('PASS' if ar['confidence'] == 0.90 else 'FAIL', f"conf={ar['confidence']}")

# ─── TEST 8: Tier-2 detection via mock ───────────────────────────────
async def test_tier2():
    mock_result = {'transcript': 'which of the following correctly describes this concept', 'language_code': 'en-IN'}
    with patch('app.core.sarvam.transcribe_audio', new=AsyncMock(return_value=mock_result)):
        result = await analyse_speech(b'fakeaudio', 'audio/webm', 'fake_key')
    return result

ar2 = asyncio.run(test_tier2())
results['analyse_tier2']     = ('PASS' if ar2['tier'] == 2 else 'FAIL', f"tier={ar2['tier']} conf={ar2['confidence']}")

# ─── CLEANUP ─────────────────────────────────────────────────────────
conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus', user='postgres', password='himanshu')
conn.autocommit = True
cur = conn.cursor()
cur.execute('DELETE FROM proctoring_logs WHERE session_id = %s', (SID,))
cur.execute('DELETE FROM sessions WHERE id = %s', (SID,))
cur.close(); conn.close()

# ─── REPORT ──────────────────────────────────────────────────────────
print()
print('=' * 70)
all_pass = True
for k, (status, detail) in results.items():
    if status == 'FAIL': all_pass = False
    print(f'  [{status}] {k:<40}  {detail}')
print('=' * 70)
print(f'  Result: {"ALL TESTS PASSED" if all_pass else "SOME TESTS FAILED"}')
print('=' * 70)
if not all_pass:
    sys.exit(1)
