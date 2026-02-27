from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: Literal["student", "professor"]


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = Field(default="bearer")
    role: str
    user_id: str


class FaceVerifyRequest(BaseModel):
    user_id: str
    face_embedding: list[float]
