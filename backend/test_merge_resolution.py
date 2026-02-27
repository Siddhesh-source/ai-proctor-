import requests, uuid, asyncio, sys, subprocess, re, psycopg2
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

# ─── TEST A: screenshot_attempt — PrintScreen ────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'screenshot_attempt',
    'confidence': 0.6, 'payload': {'key': 'PrintScreen'}
})
results['A_screenshot_printscreen'] = (
    'PASS' if r.status_code == 200 else 'FAIL',
    f"score={r.json().get('integrity_score')}"
)

# ─── TEST B: screenshot_attempt — Ctrl+Shift+S ───────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'screenshot_attempt',
    'confidence': 0.6, 'payload': {'key': 'Ctrl+Shift+S'}
})
results['B_screenshot_ctrl_shift_s'] = (
    'PASS' if r.status_code == 200 else 'FAIL',
    f"score={r.json().get('integrity_score')}"
)

# ─── TEST C: screenshot_attempt — blur reason ────────────────────────
r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
    'session_id': SID, 'violation_type': 'screenshot_attempt',
    'confidence': 0.6, 'payload': {'reason': 'blur'}
})
results['C_screenshot_blur_reason'] = (
    'PASS' if r.status_code == 200 else 'FAIL',
    f"score={r.json().get('integrity_score')}"
)

# ─── TEST D: integrity summary includes screenshot_attempt ───────────
r = requests.get(f'{BASE}/api/v1/proctoring/{SID}/integrity', headers=H)
j = r.json()
vtypes = set(v['violation_type'] for v in j.get('violations', []))
results['D_integrity_has_screenshot'] = (
    'PASS' if 'screenshot_attempt' in vtypes else 'FAIL',
    f"violations={sorted(vtypes)}"
)

# ─── TEST E: All proctoring violation types still work post-merge ─────
for vtype, conf, payload in [
    ('tab_switch',       0.90, {'source': 'visibilitychange'}),
    ('tab_switch',       0.90, {'source': 'window_blur'}),
    ('tab_switch',       0.90, {'source': 'hasfocus_poll'}),
    ('tab_switch',       0.90, {'source': 'raf_drift'}),
    ('copy_paste',       0.90, {'event': 'copy'}),
    ('multiple_monitors',0.90, {'screen_width': 3840}),
    ('gaze_away',        0.80, {'direction': 'left'}),
    ('no_mouse',         0.75, {'away_ms': 3500}),
    ('window_resize',    0.90, {'current_width': 800}),
]:
    r = requests.post(f'{BASE}/api/v1/proctoring/violation', headers=H, json={
        'session_id': SID, 'violation_type': vtype, 'confidence': conf, 'payload': payload
    })
    key = f"E_{vtype}_{list(payload.values())[0]}"
    results[key] = (
        'PASS' if r.status_code == 200 else 'FAIL',
        f"score={r.json().get('integrity_score')} status={r.status_code}"
    )

# ─── TEST F: No conflict markers in exam-interface.html ──────────────
html_path = '../frontend/morpheus-frontend/exam-interface.html'
html = open(html_path, encoding='utf-8').read()
markers = [m for m in ['<<<<<<<', '=======', '>>>>>>>'] if m in html]
results['F_no_conflict_markers'] = (
    'PASS' if not markers else 'FAIL',
    'clean' if not markers else f'found: {markers}'
)

# ─── TEST G: Frontend syntax valid ───────────────────────────────────
res = subprocess.run(
    ['node', '-e', r"""
const fs = require('fs');
const html = fs.readFileSync('../frontend/morpheus-frontend/exam-interface.html', 'utf8');
const scripts = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);
let ok = true;
scripts.forEach((s,i) => { try { new Function(s); } catch(e) { ok=false; process.stdout.write('Block '+i+' ERR: '+e.message+'\n'); } });
process.stdout.write(ok ? 'SYNTAX_OK\n' : 'SYNTAX_FAIL\n');
"""],
    capture_output=True, text=True, cwd=r'C:\Users\Lenovo\Desktop\ai-proctor-\backend'
)
syntax_ok = 'SYNTAX_OK' in res.stdout
results['G_frontend_syntax'] = (
    'PASS' if syntax_ok else 'FAIL',
    res.stdout.strip() or res.stderr.strip()
)

# ─── TEST H: Native API cache block is first in IIFE ─────────────────
script_blocks = re.findall(r'<script(?![^>]*src)[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE)
src = script_blocks[0] if script_blocks else ''
cache_pos  = src.find('_dateNow')
auth_pos   = src.find('requireAuth')
results['H_cache_before_requireAuth'] = (
    'PASS' if 0 < cache_pos < auth_pos else 'FAIL',
    f"cache@{cache_pos} auth@{auth_pos}"
)

# ─── TEST I: No bare window.setInterval/setTimeout remain ────────────
bare = [l.strip() for (i, l) in enumerate(src.split('\n'))
        if i > 15
        and re.search(r'window\.(setInterval|setTimeout|clearTimeout)\(', l)
        and not l.strip().startswith('//')]
results['I_no_bare_timers'] = (
    'PASS' if not bare else 'FAIL',
    'clean' if not bare else str(bare)
)

# ─── TEST J: screenshot_attempt + all violation types in final summary─
r = requests.get(f'{BASE}/api/v1/proctoring/{SID}/integrity', headers=H)
j = r.json()
vtypes = set(v['violation_type'] for v in j.get('violations', []))
expected = {'screenshot_attempt', 'tab_switch', 'copy_paste', 'multiple_monitors',
            'gaze_away', 'no_mouse', 'window_resize'}
missing = expected - vtypes
results['J_final_integrity_summary'] = (
    'PASS' if not missing else 'FAIL',
    f"score={j.get('integrity_score')}  missing={sorted(missing) or 'none'}"
)

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
    print(f'  [{status}] {k:<38}  {detail}')
print('=' * 70)
print(f'  Result: {"ALL TESTS PASSED" if all_pass else "SOME TESTS FAILED"}')
print('=' * 70)
if not all_pass:
    sys.exit(1)
