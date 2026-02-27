import os
from functools import lru_cache

import chromadb


def _get_chroma_path() -> str:
    return os.getenv("CHROMA_DB_PATH", os.path.join(os.getcwd(), "chroma_db"))


@lru_cache
def get_chroma_client():
    return chromadb.PersistentClient(path=_get_chroma_path())


@lru_cache
def get_face_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="face_embeddings",
        metadata={"hnsw:space": "cosine"},
    )


def get_face_embedding(user_id: str) -> list[float] | None:
    collection = get_face_collection()
    result = collection.get(ids=[user_id], include=["embeddings"])
    if not result.get("ids"):
        return None
    embeddings = result.get("embeddings") or []
    if not embeddings:
        return None
    return embeddings[0]


def upsert_face_embedding(user_id: str, embedding: list[float]) -> None:
    collection = get_face_collection()
    existing = collection.get(ids=[user_id], include=[])
    if existing.get("ids"):
        collection.update(ids=[user_id], embeddings=[embedding])
        return
    collection.add(ids=[user_id], embeddings=[embedding], metadatas=[{"user_id": user_id}])
