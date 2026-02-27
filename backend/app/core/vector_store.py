import os
from functools import lru_cache

import chromadb


def _get_chroma_path() -> str:
    default_path = os.path.join(os.path.expanduser("~"), ".morpheus", "chroma_db")
    return os.getenv("CHROMA_DB_PATH", default_path)


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
    profile = get_face_profile(user_id)
    return profile.get("center")


def upsert_face_embedding(user_id: str, embedding: list[float]) -> None:
    upsert_face_profile(user_id, {"center": embedding})


def get_face_profile(user_id: str) -> dict[str, list[float]]:
    collection = get_face_collection()
    result = collection.get(where={"user_id": user_id}, include=["embeddings", "metadatas"])
    ids = result.get("ids")
    embeddings = result.get("embeddings")
    metadatas = result.get("metadatas")
    ids = list(ids) if ids is not None else []
    embeddings = list(embeddings) if embeddings is not None else []
    metadatas = list(metadatas) if metadatas is not None else []

    profile: dict[str, list[float]] = {}
    for idx, _ in enumerate(ids):
        metadata = metadatas[idx] if idx < len(metadatas) else None
        pose = metadata.get("pose") if isinstance(metadata, dict) else None
        if not pose:
            pose = "center"
        emb = embeddings[idx] if idx < len(embeddings) else None
        if emb is None:
            continue
        profile[pose] = list(emb)
    return profile


def upsert_face_profile(user_id: str, samples: dict[str, list[float]]) -> None:
    collection = get_face_collection()
    for pose, embedding in samples.items():
        vector_id = f"{user_id}:{pose}"
        metadata = {"user_id": user_id, "pose": pose}
        existing = collection.get(ids=[vector_id], include=[])
        if existing.get("ids"):
            collection.update(ids=[vector_id], embeddings=[embedding], metadatas=[metadata])
            continue
        collection.add(ids=[vector_id], embeddings=[embedding], metadatas=[metadata])
