import logging
import logging
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.core.vector_store import get_face_profile, upsert_face_profile
from app.models.db import User
from app.schemas.auth import FaceVerifyRequest, LoginRequest, RegisterRequest, TokenResponse


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
REQUIRED_POSES = ("center", "left", "right", "up", "down")
REQUIRED_ACTIONS = ("center", "left", "right", "up", "down", "blink")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize_samples(payload: FaceVerifyRequest) -> dict[str, list[float]]:
    if payload.samples:
        return payload.samples
    if payload.face_embedding:
        return {"center": payload.face_embedding}
    return {}


def _validate_samples(samples: dict[str, list[float]]) -> None:
    if not samples:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No face samples provided")
    for pose, emb in samples.items():
        if len(emb) < 16:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Embedding too short for pose '{pose}'",
            )


def _validate_liveness_evidence(payload: FaceVerifyRequest, samples: dict[str, list[float]]) -> None:
    missing_poses = [pose for pose in REQUIRED_POSES if pose not in samples]
    if missing_poses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required liveness poses: {', '.join(missing_poses)}",
        )

    action_set = set(payload.action_order)
    missing_actions = [action for action in REQUIRED_ACTIONS if action not in action_set]
    if missing_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required liveness actions: {', '.join(missing_actions)}",
        )

    if payload.blink_count < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Blink check failed")

    if payload.capture_duration_ms < 2340:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Liveness capture too short")


def _profile_similarity(stored: dict[str, list[float]], incoming: dict[str, list[float]]) -> tuple[float, float, int]:
    common_poses = [pose for pose in REQUIRED_POSES if pose in stored and pose in incoming]
    if not common_poses:
        return 0.0, 0.0, 0
    scores = [_cosine_similarity(stored[pose], incoming[pose]) for pose in common_poses]
    return (sum(scores) / len(scores), min(scores), len(common_poses))


@router.post("/register", response_model=TokenResponse)
async def register_user(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        full_name=payload.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token, role=user.role, user_id=str(user.id))


@router.post("/login", response_model=TokenResponse)
async def login_user(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token, role=user.role, user_id=str(user.id))


@router.post("/face-verify")
async def face_verify(
    payload: FaceVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    face_length = len(payload.face_embedding) if payload.face_embedding else 0
    logger.info(
        "Face verify request",
        extra={"user_id": payload.user_id, "length": face_length},
    )
    try:
        user_id = uuid.UUID(payload.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id") from exc
    samples = _normalize_samples(payload)
    _validate_samples(samples)
    _validate_liveness_evidence(payload, samples)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    stored_profile = get_face_profile(str(user.id))
    if not stored_profile:
        upsert_face_profile(str(user.id), samples)
        return {
            "registered": True,
            "poses_registered": sorted(samples.keys()),
        }

    stored_required_count = len([pose for pose in REQUIRED_POSES if pose in stored_profile])
    if stored_required_count < 3:
        upsert_face_profile(str(user.id), samples)
        return {
            "registered": True,
            "upgraded": True,
            "poses_registered": sorted(samples.keys()),
        }

    avg_similarity, min_similarity, matched_poses = _profile_similarity(stored_profile, samples)
    if matched_poses < 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Insufficient pose match")

    if avg_similarity > 0.88 and min_similarity > 0.79:
        return {
            "verified": True,
            "confidence": round(avg_similarity, 4),
            "matched_poses": matched_poses,
        }

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Face mismatch")


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)) -> dict:
    full_name = (current_user.full_name or "").strip()
    if not full_name and current_user.email:
        full_name = current_user.email.split("@", 1)[0]
    logger.info(
        "Auth me resolved",
        extra={"user_id": str(current_user.id), "email": current_user.email, "full_name": full_name},
    )
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": full_name,
        "role": current_user.role,
    }
