# backend/retriever.py

import json
import shutil
import faiss
import numpy as np
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_model = None
DIMENSION = 384

# Root data directory — resolves to  <project_root>/data/avatars/
DATA_ROOT = Path(__file__).parent.parent / "data" / "avatars"


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


@dataclass
class AvatarStore:
    avatar_id: str
    name: str
    persona: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    index: faiss.IndexFlatL2 = field(default_factory=lambda: faiss.IndexFlatL2(DIMENSION))
    docs: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def dir(self) -> Path:
        return DATA_ROOT / self.avatar_id

    def files_dir(self) -> Path:
        return self.dir() / "files"


# In-memory registry
_avatars: Dict[str, AvatarStore] = {}


# ── Disk helpers ──────────────────────────────────────────────────────────────

def _avatar_dir(avatar_id: str) -> Path:
    return DATA_ROOT / avatar_id


def _save_avatar(store: AvatarStore):
    """Persist avatar metadata, chunks, and FAISS index to disk."""
    d = store.dir()
    d.mkdir(parents=True, exist_ok=True)
    store.files_dir().mkdir(exist_ok=True)

    # avatar.json — human-readable metadata
    meta = {
        "avatar_id": store.avatar_id,
        "name": store.name,
        "persona": store.persona,
        "created_at": store.created_at,
        "chunk_count": len(store.docs),
        "files": list(set(store.sources)),
    }
    (d / "avatar.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # chunks.json — all text chunks + their source file
    chunks_data = [
        {"text": t, "source": s}
        for t, s in zip(store.docs, store.sources)
    ]
    (d / "chunks.json").write_text(json.dumps(chunks_data, indent=2), encoding="utf-8")

    # index.faiss — vector index
    faiss.write_index(store.index, str(d / "index.faiss"))


def _load_avatar_from_disk(avatar_id: str) -> Optional[AvatarStore]:
    """Load a saved avatar from disk into memory."""
    d = _avatar_dir(avatar_id)
    meta_path   = d / "avatar.json"
    chunks_path = d / "chunks.json"
    index_path  = d / "index.faiss"

    if not (meta_path.exists() and chunks_path.exists() and index_path.exists()):
        return None

    meta   = json.loads(meta_path.read_text(encoding="utf-8"))
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    index  = faiss.read_index(str(index_path))

    store = AvatarStore(
        avatar_id  = avatar_id,
        name       = meta["name"],
        persona    = meta.get("persona", ""),
        created_at = meta.get("created_at", ""),
        index      = index,
        docs       = [c["text"]   for c in chunks],
        sources    = [c["source"] for c in chunks],
    )
    return store


def load_all_avatars_from_disk():
    """Called on server startup — rehydrates all saved avatars into memory."""
    if not DATA_ROOT.exists():
        return
    for avatar_dir in DATA_ROOT.iterdir():
        if avatar_dir.is_dir():
            avatar_id = avatar_dir.name
            if avatar_id not in _avatars:
                store = _load_avatar_from_disk(avatar_id)
                if store:
                    _avatars[avatar_id] = store


def save_uploaded_file(file_bytes: bytes, filename: str, avatar_id: str):
    """Save the original uploaded file into data/avatars/<id>/files/"""
    files_dir = _avatar_dir(avatar_id) / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    (files_dir / filename).write_bytes(file_bytes)


# ── Core API ──────────────────────────────────────────────────────────────────

def get_or_create_avatar(avatar_id: str, name: Optional[str] = None, persona: Optional[str] = None) -> AvatarStore:
    if avatar_id not in _avatars:
        store = _load_avatar_from_disk(avatar_id)
        if store:
            _avatars[avatar_id] = store
        else:
            _avatars[avatar_id] = AvatarStore(
                avatar_id=avatar_id,
                name=name or avatar_id,
                persona=persona or "",
            )
    else:
        if name and _avatars[avatar_id].name == avatar_id:
            _avatars[avatar_id].name = name
        if persona is not None:
            _avatars[avatar_id].persona = persona
    return _avatars[avatar_id]


def list_avatars() -> List[dict]:
    return [
        {
            "id":         v.avatar_id,
            "name":       v.name,
            "persona":    v.persona,
            "chunks":     len(v.docs),
            "created_at": v.created_at,
            "files":      list(set(v.sources)),
        }
        for v in _avatars.values()
    ]


def embed(text: str) -> np.ndarray:
    return get_model().encode(text).astype(np.float32)


def chunk_text(text: str, max_words: int = 600) -> List[str]:
    sentences = text.replace("\n", " ").split(". ")
    chunks, chunk = [], ""
    for s in sentences:
        if len(chunk.split()) + len(s.split()) > max_words:
            if chunk.strip():
                chunks.append(chunk.strip())
            chunk = s
        else:
            chunk += " " + s
    if chunk.strip():
        chunks.append(chunk.strip())
    return chunks


def add_document(text: str, source: str = "unknown", avatar_id: str = "default", name: Optional[str] = None, persona: Optional[str] = None) -> int:
    store  = get_or_create_avatar(avatar_id, name=name, persona=persona)
    chunks = chunk_text(text)
    for chunk in chunks:
        vector = embed(chunk)
        store.index.add(np.array([vector]))
        store.docs.append(chunk)
        store.sources.append(source)
    # Persist after every document added
    _save_avatar(store)
    return len(chunks)


def search(query: str, n_results: int = 3, avatar_id: str = "default") -> List[str]:
    store = get_or_create_avatar(avatar_id)
    if not store.docs:
        return []
    vector = embed(query)
    k = min(n_results, len(store.docs))
    _, indices = store.index.search(np.array([vector]), k)
    return [store.docs[i] for i in indices[0] if i < len(store.docs)]


def reset_avatar(avatar_id: str) -> bool:
    """Wipe avatar from memory and disk."""
    d = _avatar_dir(avatar_id)
    if d.exists():
        shutil.rmtree(d)
    if avatar_id in _avatars:
        del _avatars[avatar_id]
        return True
    return d.exists()  # was on disk but not in memory