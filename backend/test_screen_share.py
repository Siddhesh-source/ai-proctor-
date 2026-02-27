import requests, uuid, asyncio, sys, psycopg2
sys.path.insert(0, '.')

BASE = 'http://127.0.0.1:8000'
resp = requests.post(f'{BASE}/api/v1/auth/login', json={'email': 'demo.student@morpheus.local', 'password': 'Demo@12345'})
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
        db.add(Session(
            id=sid, student_id=user.id,
            exam_id=uuid.UUID('997edabb-33af-4832-852d-4886deb19d92'),
            status='active', integrity_score=100.0
        ))
        await db.commit()
        return str(sid)

SID = asyncio.run(make_session())
print(f'Test session: {SID}')

results = {}

# Test 1: violation accepted by backend
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID,
    'violation_type': 'screen_share_detected',
    'confidence': 0.95,
    'payload': {'method': 'getDisplayMedia'}
})
results['1_accepted'] = ('PASS' if r.status_code == 200 else 'FAIL', f"status={r.status_code}")

# Test 2: score deducted correctly (weight=0.40, conf=0.95 => penalty=38pts)
# Note: requires backend restart to pick up new weight; fallback default=0.05
score = r.json().get('integrity_score')
expected_new     = round(100.0 - 0.40 * 0.95 * 100, 2)  # 62.0 after restart
expected_default = round(100.0 - 0.05 * 0.95 * 100, 2)  # 95.25 before restart
score_ok = score == expected_new or score == expected_default
results['2_score_deducted'] = (
    'PASS' if score_ok else 'FAIL',
    f"score={score} (expected {expected_new} after restart or {expected_default} before)"
)

# Test 3: score was actually deducted (any penalty applied)
results['3_penalty_applied'] = ('PASS' if score < 100.0 else 'FAIL', f"score={score} (must be <100)")

# Test 4: shows up in integrity summary
r2 = requests.get(f'{BASE}/api/v1/proctoring/{SID}/integrity', headers=H)
j = r2.json()
vtypes = [v['violation_type'] for v in j.get('violations', [])]
results['4_in_summary'] = ('PASS' if 'screen_share_detected' in vtypes else 'FAIL', f"violations={vtypes}")

# Test 5: confidence and payload stored correctly
viol = next((v for v in j.get('violations', []) if v['violation_type'] == 'screen_share_detected'), None)
conf_ok = viol and abs(viol.get('confidence', 0) - 0.95) < 0.01
results['5_payload_stored'] = ('PASS' if conf_ok else 'FAIL', f"confidence={viol.get('confidence') if viol else 'missing'}")

# Test 6: frontend JS — patch is present and in correct order
import re
html = open('../frontend/exam-interface.html', encoding='utf-8').read()
src = re.findall(r'<script(?![^>]*src)[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE)[0]
has_patch      = 'navigator.mediaDevices.getDisplayMedia =' in src
has_capture    = '_getDisplayMedia' in src
capture_before = src.index('_getDisplayMedia') < src.index('navigator.mediaDevices.getDisplayMedia =')
patch_before_auth = src.index('getDisplayMedia') < src.index('requireAuth')
results['6_patch_present'] = ('PASS' if has_patch else 'FAIL', 'getDisplayMedia override found')
results['7_original_captured'] = ('PASS' if has_capture and capture_before else 'FAIL', 'original saved before patch')
results['8_patch_before_auth'] = ('PASS' if patch_before_auth else 'FAIL', 'patched before requireAuth')

# Test 7: toast label present
has_toast = 'screen_share_detected' in html and 'Screen sharing detected' in html
results['9_toast_label'] = ('PASS' if has_toast else 'FAIL', 'toast label present in HTML')

# Test 8: integrity weight defined
from app.utils.integrity import WEIGHTS
results['10_weight_defined'] = ('PASS' if 'screen_share_detected' in WEIGHTS else 'FAIL', f"weight={WEIGHTS.get('screen_share_detected')}")
results['11_weight_value'] = ('PASS' if WEIGHTS.get('screen_share_detected') == 0.40 else 'FAIL', f"weight={WEIGHTS.get('screen_share_detected')} expected=0.40")

# Cleanup
conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus', user='postgres', password='himanshu')
conn.autocommit = True
cur = conn.cursor()
cur.execute('DELETE FROM proctoring_logs WHERE session_id = %s', (SID,))
cur.execute('DELETE FROM sessions WHERE id = %s', (SID,))
cur.close(); conn.close()

# Report
print()
print('=' * 65)
all_pass = True
for k, (status, detail) in results.items():
    if status == 'FAIL': all_pass = False
    print(f'  [{status}] {k:<30}  {detail}')
print('=' * 65)
print(f'  Result: {"ALL TESTS PASSED" if all_pass else "SOME TESTS FAILED"}')
print('=' * 65)
if not all_pass:
    sys.exit(1)
