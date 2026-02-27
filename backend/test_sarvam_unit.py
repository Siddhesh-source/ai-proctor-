"""
Pure unit tests — no ML models loaded, no DB, no network.
Tests: keyword logic, integrity weight, config field, sarvam analyse_speech mock.
"""
import sys, asyncio
sys.path.insert(0, '.')

results = {}

# ─── TEST 1: Keyword detection ───────────────────────────────────────
from app.core.sarvam import _check_keywords

cases = [
    ("bata do answer kya hai",                                          1),
    ("what is the answer to question 3",                                1),
    ("correct answer is option C",                                      1),
    ("which of the following options correctly describes the process",   2),
    ("kya yeh option sahi hai ya kaun sa option select karna chahiye",  2),
    ("I am sitting here quietly",                                       0),
    ("okay fine yes",                                                   0),
]
for text, expected_tier in cases:
    tier, kw = _check_keywords(text)
    key = f"T{expected_tier}_{text[:20].replace(' ','_')}"
    results[key] = ('PASS' if tier == expected_tier else 'FAIL', f"tier={tier} kw={kw}")

# ─── TEST 2: Integrity weight ────────────────────────────────────────
from app.utils.integrity import WEIGHTS, update_integrity
w = WEIGHTS.get('speech_cheating')
results['weight_0.35']    = ('PASS' if w == 0.35 else 'FAIL', f"weight={w}")
score = update_integrity(100.0, 'speech_cheating', 0.90)
results['penalty_68.5']   = ('PASS' if score == 68.5 else 'FAIL', f"score={score}")

# ─── TEST 3: Config field ────────────────────────────────────────────
from app.core.config import Settings
results['config_field']   = ('PASS' if 'SARVAM_API_KEY' in Settings.model_fields else 'FAIL', 'SARVAM_API_KEY in Settings')

# ─── TEST 4: analyse_speech tier-1 mock ─────────────────────────────
from unittest.mock import AsyncMock, patch
from app.core.sarvam import analyse_speech

async def test_t1():
    with patch('app.core.sarvam.transcribe_audio', new=AsyncMock(
        return_value={'transcript': 'bata do sahi jawab kya hai', 'language_code': 'hi-IN'})):
        return await analyse_speech(b'x', 'audio/webm', 'key')

r1 = asyncio.run(test_t1())
results['tier1_violation']  = ('PASS' if r1['violation'] and r1['tier'] == 1 else 'FAIL', str(r1))
results['tier1_conf_0.90']  = ('PASS' if r1['confidence'] == 0.90 else 'FAIL', f"conf={r1['confidence']}")

# ─── TEST 5: analyse_speech tier-2 mock ─────────────────────────────
async def test_t2():
    with patch('app.core.sarvam.transcribe_audio', new=AsyncMock(
        return_value={'transcript': 'which of the following correctly describes this phenomenon', 'language_code': 'en-IN'})):
        return await analyse_speech(b'x', 'audio/webm', 'key')

r2 = asyncio.run(test_t2())
results['tier2_violation']  = ('PASS' if r2['violation'] and r2['tier'] == 2 else 'FAIL', str(r2))
results['tier2_conf_0.65']  = ('PASS' if r2['confidence'] == 0.65 else 'FAIL', f"conf={r2['confidence']}")

# ─── TEST 6: analyse_speech clean speech mock ────────────────────────
async def test_clean():
    with patch('app.core.sarvam.transcribe_audio', new=AsyncMock(
        return_value={'transcript': 'I am feeling fine today', 'language_code': 'en-IN'})):
        return await analyse_speech(b'x', 'audio/webm', 'key')

r3 = asyncio.run(test_clean())
results['clean_no_violation'] = ('PASS' if not r3['violation'] and r3['tier'] == 0 else 'FAIL', str(r3))

# ─── TEST 7: Empty transcript → no violation ────────────────────────
async def test_empty():
    with patch('app.core.sarvam.transcribe_audio', new=AsyncMock(
        return_value={'transcript': '', 'language_code': 'unknown'})):
        return await analyse_speech(b'x', 'audio/webm', 'key')

r4 = asyncio.run(test_empty())
results['empty_no_violation'] = ('PASS' if not r4['violation'] else 'FAIL', str(r4))

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
