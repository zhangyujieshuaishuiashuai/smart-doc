"""记录已成功建库的 doc_id，便于跨文档问答时列举「已上传可检索」文档。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from core.config import VECTOR_DIR

REGISTRY_PATH: Path = VECTOR_DIR / "indexed_doc_ids.json"


def _has_vector_files(path: Path) -> bool:
    return path.is_dir() and (path / "index.faiss").is_file() and (path / "meta.json").is_file()


#注册文档
def register_doc_id(doc_id: str) -> None:
    doc_id = (doc_id or "").strip()
    if not doc_id:
        return
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)#递归创建父目录,且目录存在不报错
    existing = list_registered()
    if doc_id not in existing:
        existing.append(doc_id)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:#以utf-8编码写入文件返回Json格式
        json.dump(existing, f, ensure_ascii=False, indent=2)

#已注册的文档
def list_registered() -> List[str]:
    doc_ids: List[str] = []
    if not REGISTRY_PATH.exists():
        data = []
    else:
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):#捕获json解析错误或是文件IO错误
            data = []

    if isinstance(data, list):#验证结果是否为列表
        for item in data:
            doc_id = str(item).strip()
            if doc_id and doc_id not in doc_ids:
                doc_ids.append(doc_id)

    if VECTOR_DIR.exists():
        for child in sorted(VECTOR_DIR.iterdir(), key=lambda p: p.name):
            if _has_vector_files(child) and child.name not in doc_ids:
                doc_ids.append(child.name)

    return doc_ids
