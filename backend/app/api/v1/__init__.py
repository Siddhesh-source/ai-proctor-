from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.exams import router as exams_router
from app.api.v1.endpoints.proctoring import router as proctoring_router
from app.api.v1.endpoints.results import router as results_router


router = APIRouter()
router.include_router(auth_router)
router.include_router(exams_router)
router.include_router(proctoring_router)
router.include_router(results_router)
