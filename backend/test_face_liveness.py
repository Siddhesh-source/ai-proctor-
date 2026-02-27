import os

from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:placeholder@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.api.v1.endpoints.auth import _profile_similarity, _validate_liveness_evidence
from app.schemas.auth import FaceVerifyRequest


def _make_samples() -> dict[str, list[float]]:
    base = [0.01 * i for i in range(128)]
    return {
        "center": base,
        "left": base,
        "right": base,
        "up": base,
        "down": base,
    }


def test_validate_liveness_evidence_passes_with_required_inputs() -> None:
    payload = FaceVerifyRequest(
        user_id="00000000-0000-0000-0000-000000000000",
        samples=_make_samples(),
        blink_count=1,
        action_order=["center", "left", "right", "up", "down", "blink"],
        capture_duration_ms=5000,
    )
    _validate_liveness_evidence(payload, payload.samples or {})


def test_validate_liveness_evidence_rejects_missing_blink() -> None:
    payload = FaceVerifyRequest(
        user_id="00000000-0000-0000-0000-000000000000",
        samples=_make_samples(),
        blink_count=0,
        action_order=["center", "left", "right", "up", "down"],
        capture_duration_ms=5000,
    )
    try:
        _validate_liveness_evidence(payload, payload.samples or {})
        raise AssertionError("Expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_profile_similarity_counts_common_poses() -> None:
    stored = _make_samples()
    incoming = {
        "center": stored["center"],
        "left": stored["left"],
        "right": stored["right"],
    }
    avg, min_score, matched = _profile_similarity(stored, incoming)
    assert matched == 3
    assert avg > 0.99
    assert min_score > 0.99
