from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QuestionCreate(BaseModel):
    text: str
    type: Literal["mcq", "subjective", "code"]
    options: dict | None = None
    correct_answer: str
    keywords: list[str] | None = None
    marks: float
    order: int


class ExamCreate(BaseModel):
    title: str
    type: Literal["mcq", "subjective", "code", "mixed"]
    duration_minutes: int
    start_time: datetime
    end_time: datetime
    negative_marking: float = 0.0
    randomize_questions: bool = False
    questions: list[QuestionCreate]


class ExamResponse(BaseModel):
    id: str
    professor_id: str
    title: str
    type: str
    duration_minutes: int
    start_time: datetime
    end_time: datetime
    negative_marking: float
    randomize_questions: bool
    is_active: bool


class QuestionResponse(BaseModel):
    id: str
    exam_id: str
    text: str
    type: str
    options: dict | None = None
    correct_answer: str
    keywords: list[str] | None = None
    marks: float
    order: int


class ExamCreateResponse(BaseModel):
    exam_id: str
    question_count: int


class StartExamResponse(BaseModel):
    session_id: str
    duration_minutes: int


class SubmitAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    answer: str


class SubmitAnswerResponse(BaseModel):
    saved: bool = Field(default=True)


class FinishExamRequest(BaseModel):
    session_id: str


class FinishExamResponse(BaseModel):
    status: str
