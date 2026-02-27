import logging
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.core.vector_store import get_face_embedding, upsert_face_embedding
from app.models.db import User
from app.schemas.auth import FaceVerifyRequest, LoginRequest, RegisterRequest, TokenResponse


router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


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
    logger.info("Face verify request", extra={"user_id": payload.user_id, "length": len(payload.face_embedding)})
    try:
        user_id = uuid.UUID(payload.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id") from exc
    if len(payload.face_embedding) != 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid embedding length")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    stored_embedding = get_face_embedding(str(user.id))
    if stored_embedding is None:
        logger.info("Face embedding registered", extra={"user_id": str(user.id)})
        upsert_face_embedding(str(user.id), payload.face_embedding)
        return {"registered": True}
    similarity = _cosine_similarity(stored_embedding, payload.face_embedding)
    logger.info("Face similarity computed", extra={"user_id": str(user.id), "similarity": similarity})
    if similarity > 0.85:
        return {"verified": True}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Face mismatch")


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
    }
