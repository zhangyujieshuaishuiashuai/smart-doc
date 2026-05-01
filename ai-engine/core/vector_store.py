import json
import os
import site
import threading
import faiss
import numpy as np
from pathlib import Path
from typing import List, Dict, Any


def _prepare_windows_torch_dll_path() -> None:
    """Windows：先注册 torch\\lib，再加载扩展，避免 uvicorn 下 shm.dll 报 WinError 127。"""
    if os.name != "nt":
        return
    for sp in sorted({*site.getsitepackages(), site.getusersitepackages()}):
        if not sp:
            continue
        lib = Path(sp) / "torch" / "lib"
        if not lib.is_dir():
            continue
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(lib))
            except OSError:
                pass
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
        break


_prepare_windows_torch_dll_path()

from sentence_transformers import SentenceTransformer

from core.config import settings, VECTOR_DIR


class VectorStore:
    #模型加载线程锁
    _model_lock = threading.Lock()
    _shared_model: SentenceTransformer | None = None
    _shared_model_name: str | None = None
    #索引缓存线程锁
    _index_lock = threading.Lock()
    _index_cache: dict[str, tuple[Any, List[Dict[str, Any]]]] = {}

    @classmethod
    def _get_shared_model(cls) -> SentenceTransformer:
        model_name = settings.EMBEDDING_MODEL
        if cls._shared_model is not None and cls._shared_model_name == model_name:
            return cls._shared_model

        with cls._model_lock:
            if cls._shared_model is None or cls._shared_model_name != model_name:
                # Keep one embedding model per process to avoid repeated heavy loads.
                cls._shared_model = SentenceTransformer(model_name)
                cls._shared_model_name = model_name
        return cls._shared_model

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.doc_dir = VECTOR_DIR / doc_id
        self.doc_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.doc_dir / "index.faiss"
        self.meta_path = self.doc_dir / "meta.json"

        self.model = self._get_shared_model()
        self.index = None
        self.metadata = []

    def build(self, chunks: List[Dict[str, Any]]):
        texts = [item["content"] for item in chunks]
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        embeddings = np.array(embeddings).astype("float32")

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embeddings)

        self.metadata = chunks

        faiss.write_index(self.index, str(self.index_path))
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

        with self._index_lock:
            self._index_cache[self.doc_id] = (self.index, self.metadata)

    def load(self):
        with self._index_lock:
            cached = self._index_cache.get(self.doc_id)
        if cached is not None:
            self.index, self.metadata = cached
            return

        if not self.index_path.exists() or not self.meta_path.exists():
            raise FileNotFoundError(f"Vector store for doc_id={self.doc_id} not found")
        #从文件加载索引和元数据
        self.index = faiss.read_index(str(self.index_path))
        with open(self.meta_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)
        ## 添加到缓存
        with self._index_lock:
            self._index_cache[self.doc_id] = (self.index, self.metadata)

    def search(self, query: str, top_k: int = 5):
        if self.index is None:  # 索引不存在时加载
            self.load()

        #嵌入向量
        q_emb = self.model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        q_emb = np.array(q_emb).astype("float32")
        

        #执行FAISS搜索
        scores, indices = self.index.search(q_emb, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            item = dict(self.metadata[idx])
            item["score"] = float(score)
            results.append(item)
        return results
