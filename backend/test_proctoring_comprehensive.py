import requests, uuid, base64, sys, os, asyncio
sys.path.insert(0, '.')
from PIL import Image
from io import BytesIO
import urllib.request

BASE = 'http://127.0.0.1:8000'

# --- Auth ---
resp = requests.post(f'{BASE}/api/v1/auth/login', json={'email': 'demo.student@morpheus.local', 'password': 'Demo@12345'})
assert resp.status_code == 200, f'Login failed: {resp.text}'
token = resp.json()['access_token']
H = {'Authorization': f'Bearer {token}'}

# --- Create fresh test session ---
async def make_session():
    from app.core.database import AsyncSessionLocal
    from app.models.db import Session, User
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(User).where(User.email == 'demo.student@morpheus.local'))
        user = r.scalars().first()
        sid = uuid.uuid4()
        db.add(Session(
            id=sid,
            student_id=user.id,
            exam_id=uuid.UUID('997edabb-33af-4832-852d-4886deb19d92'),
            status='active',
            integrity_score=100.0
        ))
        await db.commit()
        return str(sid)

SID = asyncio.run(make_session())
print(f'Test session: {SID}')

results = {}

def img_b64(img):
    buf = BytesIO()
    img.save(buf, format='JPEG')
    return base64.b64encode(buf.getvalue()).decode()

# ─── TEST 1: Tab switch (RAF) ───────────────────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/raf', json={'session_id': SID, 'delta_ms': 700}, headers=H)
j = r.json()
results['1_tab_switch_flags'] = ('PASS' if j.get('violation') == True else 'FAIL', str(j))

r2 = requests.post(f'{BASE}/api/v1/proctoring/raf', json={'session_id': SID, 'delta_ms': 80}, headers=H)
results['1_tab_switch_ok'] = ('PASS' if r2.json().get('violation') == False else 'FAIL', str(r2.json()))

# ─── TEST 2: Multiple persons (YOLO) ───────────────────────────────
urllib.request.urlretrieve('https://ultralytics.com/images/bus.jpg', '_test_bus.jpg')
img = Image.open('_test_bus.jpg').convert('RGB')
r = requests.post(f'{BASE}/api/v1/proctoring/frame', json={'session_id': SID, 'frame_base64': img_b64(img)}, headers=H)
j = r.json()
results['2_multiple_persons'] = ('PASS' if 'multiple_faces' in j.get('violations', []) else 'FAIL', str(j))
os.remove('_test_bus.jpg')

# ─── TEST 3: Audio detection ────────────────────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/audio', json={'session_id': SID, 'voice_energy': 85}, headers=H)
results['3_audio_flags'] = ('PASS' if r.json().get('violation') == True else 'FAIL', str(r.json()))

r2 = requests.post(f'{BASE}/api/v1/proctoring/audio', json={'session_id': SID, 'voice_energy': 20}, headers=H)
results['3_audio_ok'] = ('PASS' if r2.json().get('violation') == False else 'FAIL', str(r2.json()))

# ─── TEST 4: Window resize ──────────────────────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'window_resize',
    'confidence': 0.9, 'payload': {'start_width': 1920, 'current_width': 800}
})
results['4_window_resize'] = ('PASS' if r.status_code == 200 else 'FAIL', f"score={r.json().get('integrity_score')}")

# ─── TEST 5: Gaze away (new) ────────────────────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'gaze_away',
    'confidence': 0.8, 'payload': {'direction': 'left'}
})
results['5_gaze_away'] = ('PASS' if r.status_code == 200 else 'FAIL', f"score={r.json().get('integrity_score')}")

# ─── TEST 6: No mouse / mouse leave (new) ───────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'no_mouse',
    'confidence': 0.75, 'payload': {'away_ms': 4200}
})
results['6_no_mouse'] = ('PASS' if r.status_code == 200 else 'FAIL', f"score={r.json().get('integrity_score')}")

# ─── TEST 8: WebSocket real-time ────────────────────────────────────
async def ws_test():
    import websockets, json as _json
    uri = f'ws://127.0.0.1:8000/ws/proctoring/{SID}?token={token}'
    async with websockets.connect(uri) as ws:
        await ws.send(_json.dumps({'type': 'violation', 'violation_type': 'gaze_away', 'confidence': 0.8}))
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        return _json.loads(msg)

loop = asyncio.new_event_loop()
ws_result = loop.run_until_complete(ws_test())
results['8_websocket'] = ('PASS' if 'integrity_score' in ws_result else 'FAIL', str(ws_result))

# ─── TEST 9: Gaze away direction variants ───────────────────────────
directions_ok = True
for direction in ['right', 'up', 'down']:
    r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
        'session_id': SID, 'violation_type': 'gaze_away',
        'confidence': 0.8, 'payload': {'direction': direction}
    })
    if r.status_code != 200:
        directions_ok = False
results['9_gaze_directions'] = ('PASS' if directions_ok else 'FAIL', 'left/right/up/down all accepted')

# ─── TEST 10: No mouse with varying away_ms ─────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'no_mouse',
    'confidence': 0.75, 'payload': {'away_ms': 15000}
})
results['10_no_mouse_long'] = ('PASS' if r.status_code == 200 else 'FAIL', f"score={r.json().get('integrity_score')}")

# ─── TEST 11: Copy/paste violation ───────────────────────────────────
for evt in ['copy', 'paste', 'cut']:
    r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
        'session_id': SID, 'violation_type': 'copy_paste',
        'confidence': 0.9, 'payload': {'event': evt}
    })
    if r.status_code != 200:
        results[f'11_copy_paste_{evt}'] = ('FAIL', f"status={r.status_code}")
    else:
        results[f'11_copy_paste_{evt}'] = ('PASS', f"score={r.json().get('integrity_score')}")

# ─── TEST 12: Multiple monitors violation ────────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'multiple_monitors',
    'confidence': 0.9, 'payload': {'screen_width': 3840, 'screen_height': 1080}
})
results['12_multiple_monitors'] = ('PASS' if r.status_code == 200 else 'FAIL', f"score={r.json().get('integrity_score')}")

# ─── TEST 13: Foolproof tab switch (tab_switch type) ─────────────────
for source in ['visibilitychange', 'window_blur', 'hasfocus_poll', 'raf_drift']:
    r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
        'session_id': SID, 'violation_type': 'tab_switch',
        'confidence': 0.90, 'payload': {'source': source}
    })
    if r.status_code != 200:
        results[f'13_tab_switch_{source}'] = ('FAIL', f"status={r.status_code}")
    else:
        results[f'13_tab_switch_{source}'] = ('PASS', f"score={r.json().get('integrity_score')}")

# ─── TEST 7: Integrity score summary (run last — all violations now logged) ──
r = requests.get(f'{BASE}/api/v1/proctoring/{SID}/integrity', headers=H)
j = r.json()
vtypes = set(v['violation_type'] for v in j.get('violations', []))
expected = {'raf_tab_switch', 'multiple_faces', 'speech_detected', 'window_resize', 'gaze_away', 'no_mouse',
            'copy_paste', 'multiple_monitors', 'tab_switch'}
missing = expected - vtypes
results['7_integrity_summary'] = (
    'PASS' if not missing else 'FAIL',
    f"score={j.get('integrity_score')}  violations={sorted(vtypes)}  missing={sorted(missing)}"
)

# ─── CLEANUP via psycopg2 (avoids asyncpg event-loop binding issues) ─
import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus', user='postgres', password='himanshu')
conn.autocommit = True
cur = conn.cursor()
cur.execute("DELETE FROM proctoring_logs WHERE session_id = %s", (SID,))
cur.execute("DELETE FROM sessions WHERE id = %s", (SID,))
cur.close()
conn.close()

# ─── REPORT ─────────────────────────────────────────────────────────
print()
print('=' * 65)
all_pass = True
for k, (status, detail) in results.items():
    if status == 'FAIL':
        all_pass = False
    marker = 'PASS' if status == 'PASS' else 'FAIL'
    print(f'  [{marker}] {k:<28}  {detail}')
print('=' * 65)
print(f'  Result: {"ALL 10 TESTS PASSED" if all_pass else "SOME TESTS FAILED"}')
print('=' * 65)

if not all_pass:
    sys.exit(1)
