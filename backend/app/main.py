from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api.v1 import router as api_v1_router
from app.api.v1.websocket import router as ws_router
from app.core.database import init_db
from app.models.grading import nlp_model
from app.models.ml_models import yolo


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

handler = Mangum(app)
