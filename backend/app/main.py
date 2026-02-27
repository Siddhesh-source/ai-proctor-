import logging
import os as _os
import pathlib as _pathlib
import traceback

# Load .env before any module-level os.getenv() calls
_env_file = _pathlib.Path(__file__).parent.parent / ".env"
if _env_file.exists():
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from app.api.v1 import router as api_v1_router
from app.api.v1.websocket import router as ws_router
from app.api.v1.webrtc import router as webrtc_router
from app.core.database import init_db
from app.models.grading import nlp_model
from app.models.ml_models import yolo

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    logger.debug(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    _ = yolo
    _ = nlp_model


@app.get("/")
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0"}


app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(ws_router)
app.include_router(webrtc_router)

handler = Mangum(app)
