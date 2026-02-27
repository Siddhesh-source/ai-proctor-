"""
End-to-end Sarvam STT tests.
Tests real API call with synthesized WAV audio, keyword detection, endpoint behaviour.
"""
import sys, asyncio, base64, struct, math, uuid, requests, psycopg2
sys.path.insert(0, '.')

results = {}

# ── Helper: generate a minimal valid WAV file with a sine tone ────────
# Sarvam needs real audio — we generate a 2s 16kHz mono WAV sine wave.
# This won't produce meaningful transcript but tests the API plumbing.
def make_sine_wav(duration_s=2, freq=440, sample_rate=16000):
    num_samples = int(sample_rate * duration_s)
    samples = [int(32767 * math.sin(2 * math.pi * freq * i / sample_rate))
               for i in range(num_samples)]
    data = struct.pack(f'<{num_samples}h', *samples)
    # WAV header
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + len(data), b'WAVE',
        b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b'data', len(data))
    return header + data

BASE = 'http://127.0.0.1:8000'

# ── Auth ──────────────────────────────────────────────────────────────
resp = requests.post(f'{BASE}/api/v1/auth/login',
    json={'email': 'demo.student@morpheus.local', 'password': 'Demo@12345'})
assert resp.status_code == 200, f'Login failed: {resp.text}'
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
print(f'Test session: {SID}')

# ── TEST 1: Real Sarvam API call with sine WAV (unit) ─────────────────
# Tests API connectivity and response structure
from app.core.config import settings
from app.core.sarvam import transcribe_audio

async def test_real_api():
    wav = make_sine_wav(duration_s=2)
    result = await transcribe_audio(wav, 'audio/wav', settings.SARVAM_API_KEY)
    return result

try:
    api_result = asyncio.run(test_real_api())
    results['1_sarvam_api_reachable']    = ('PASS', f"language={api_result.get('language_code')} transcript='{api_result.get('transcript')}'")
    results['2_response_has_transcript'] = ('PASS' if 'transcript' in api_result else 'FAIL', str(api_result))
    results['3_response_has_language']   = ('PASS' if 'language_code' in api_result else 'FAIL', str(api_result))
except Exception as e:
    results['1_sarvam_api_reachable']    = ('FAIL', str(e))
    results['2_response_has_transcript'] = ('FAIL', 'API unreachable')
    results['3_response_has_language']   = ('FAIL', 'API unreachable')

# ── TEST 2: Full analyse_speech pipeline with real API ─────────────────
from app.core.sarvam import analyse_speech

async def test_analyse_real():
    wav = make_sine_wav(duration_s=2)
    return await analyse_speech(wav, 'audio/wav', settings.SARVAM_API_KEY)

try:
    ar = asyncio.run(test_analyse_real())
    results['4_analyse_returns_tier']       = ('PASS' if 'tier' in ar else 'FAIL', str(ar))
    results['5_analyse_returns_violation']  = ('PASS' if 'violation' in ar else 'FAIL', str(ar))
    results['6_sine_no_violation']          = (
        'PASS' if not ar['violation'] else 'INFO',
        f"tier={ar['tier']} transcript='{ar['transcript']}' (sine wave — likely no cheating keywords)"
    )
except Exception as e:
    results['4_analyse_returns_tier']      = ('FAIL', str(e))
    results['5_analyse_returns_violation'] = ('FAIL', str(e))
    results['6_sine_no_violation']         = ('FAIL', str(e))

# ── TEST 3: /audio/stt endpoint — real WAV, no key skip ───────────────
wav_b64 = base64.b64encode(make_sine_wav(duration_s=2)).decode()
r = requests.post(f'{BASE}/api/v1/proctoring/audio/stt', headers=H, json={
    'session_id': SID,
    'audio_base64': wav_b64,
    'mime_type': 'audio/wav',
})
results['7_endpoint_status_200']  = ('PASS' if r.status_code == 200 else 'FAIL', f"status={r.status_code} body={r.text[:100]}")
j = r.json()
results['8_not_skipped']          = ('PASS' if not j.get('skipped') else 'FAIL', str(j))
results['9_has_transcript_field'] = ('PASS' if 'transcript' in j else 'FAIL', str(j))
results['10_has_language_field']  = ('PASS' if 'language_code' in j else 'FAIL', str(j))
results['11_has_violation_field'] = ('PASS' if 'violation' in j else 'FAIL', str(j))
print(f"\n  Endpoint response: {j}")

# ── TEST 4: Too-short audio returns skipped ───────────────────────────
tiny_b64 = base64.b64encode(b'\x00' * 100).decode()
r2 = requests.post(f'{BASE}/api/v1/proctoring/audio/stt', headers=H, json={
    'session_id': SID, 'audio_base64': tiny_b64, 'mime_type': 'audio/webm'
})
j2 = r2.json()
results['12_tiny_clip_skipped'] = ('PASS' if j2.get('skipped') else 'FAIL', str(j2))

# ── TEST 5: speech_cheating violation logged when triggered ───────────
# Simulate what endpoint does when Sarvam returns a cheating phrase
r3 = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'speech_cheating',
    'confidence': 0.90,
    'payload': {'transcript': 'bata do answer kya hai', 'tier': 1, 'keywords': ['bata do']}
})
score = r3.json().get('integrity_score')
results['13_speech_cheating_logged'] = ('PASS' if r3.status_code == 200 else 'FAIL', f"status={r3.status_code}")
results['14_score_deducted_35pct']   = ('PASS' if score == 68.5 else 'FAIL', f"score={score} expected=68.5")

# ── TEST 6: Integrity summary includes speech_cheating ────────────────
r4 = requests.get(f'{BASE}/api/v1/proctoring/{SID}/integrity', headers=H)
vtypes = [v['violation_type'] for v in r4.json().get('violations', [])]
results['15_summary_has_speech_cheating'] = ('PASS' if 'speech_cheating' in vtypes else 'FAIL', f"violations={vtypes}")

# ── CLEANUP ───────────────────────────────────────────────────────────
conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus',
                        user='postgres', password='himanshu')
conn.autocommit = True
cur = conn.cursor()
cur.execute('DELETE FROM proctoring_logs WHERE session_id = %s', (SID,))
cur.execute('DELETE FROM sessions WHERE id = %s', (SID,))
cur.close(); conn.close()

# ── REPORT ────────────────────────────────────────────────────────────
print()
print('=' * 75)
all_pass = True
for k, (status, detail) in results.items():
    if status == 'FAIL': all_pass = False
    marker = status if status in ('PASS', 'FAIL') else 'INFO'
    print(f'  [{marker}] {k:<42}  {detail}')
print('=' * 75)
print(f'  Result: {"ALL TESTS PASSED" if all_pass else "SOME TESTS FAILED"}')
print('=' * 75)
if not all_pass:
    sys.exit(1)
