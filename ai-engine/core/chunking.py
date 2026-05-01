"""
将解析结果（页级正文 / OCR / 表格）转为向量库 chunk，供 RAG 检索。
DeepSeek 侧不读原图，仅基于这些结构化文本与表格片段生成答案。
"""
from __future__ import annotations #延迟注解,在类型注解中使用尚未定义的类名

from typing import Any, Dict, List, Optional
import re

from core.utils import split_text

# 与常见 embedding 长度配合：略小于 1024 汉字量级，避免单 chunk 过大
_DEFAULT_MAX_CHARS = 900
_DEFAULT_OVERLAP = 120

# 页级页码
def _page_no_from(p: Dict[str, Any]) -> int:
    v = p.get("page")
    if v is None:
        v = p.get("page_no")
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def build_chunks_from_parse(
    pages: List[Dict[str, Any]],
    pdf_tables: Optional[List[Dict[str, Any]]] = None,
    *,#强制以关键字传参
    max_chars: int = _DEFAULT_MAX_CHARS,
    overlap: int = _DEFAULT_OVERLAP,
) -> List[Dict[str, Any]]:
    """
    由 `/parse/*` 返回的 pages、tables 构建 chunk 列表。
    每条 chunk 必须含 `content`（与 VectorStore.build 一致）。
    """
    pdf_tables = pdf_tables or []
    chunks: List[Dict[str, Any]] = []

    #遍历页面字典
    for p in pages:
        pno = _page_no_from(p)
        clean = (p.get("clean_text_for_rag") or "").strip()
        raw_ocr = (p.get("raw_ocr_text") or "").strip()
        display = (p.get("display_text") or p.get("text") or "").strip()

        for i, piece in enumerate(split_text(clean, max_chars, overlap)):#调用共享 split_text 后遍历所有文本块
            chunks.append({
                "content": f"【第{pno}页·正文/RAG链路程式化】\n{piece}",
                "source_type": "page_body",
                "page_no": pno,
                "chunk_index": i,#为该页的第几个文本块
            })

        ocr_norm = re.sub(r"\s+", "", raw_ocr)
        clean_norm = re.sub(r"\s+", "", clean)
        if raw_ocr and ocr_norm != clean_norm:
            for i, piece in enumerate(split_text(raw_ocr, max_chars, overlap)):
                chunks.append({
                    "content": f"【第{pno}页·OCR原始文本】\n{piece}",
                    "source_type": "page_ocr",
                    "page_no": pno,
                    "chunk_index": i,
                })
        elif not clean and display:
            for i, piece in enumerate(split_text(display, max_chars, overlap)):
                chunks.append({
                    "content": f"【第{pno}页·展示文本】\n{piece}",
                    "source_type": "page_display",
                    "page_no": pno,
                    "chunk_index": i,
                })

    #遍历表格字典
    for t in pdf_tables:
        pno = int(t.get("page") or 0)
        tid = str(t.get("id") or t.get("table_id") or "")
        md = (t.get("markdown") or "").strip()
        rows = t.get("rows")
        if md:
            body = md
        elif isinstance(rows, list) and rows:
            body = "\n".join("\t".join(str(c or "") for c in row) for row in rows)
        else:
            continue
        title = (t.get("title") or "").strip()
        header = f"【表格 {tid or '未命名'} · 第{pno}页】"
        if title:
            header += f" {title}"
        chunks.append({
            "content": f"{header}\n{body}",
            "source_type": "table",
            "page_no": pno,
            "table_id": tid or None,
        })
    #seen集合来检查重复
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in chunks:
        key = c.get("content", "")[:200]#做唯一标识符
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


# 端到端索引向量库
def index_parse_to_vector_store(
    doc_id: str,
    pages: List[Dict[str, Any]],
    pdf_tables: Optional[List[Dict[str, Any]]] = None,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    overlap: int = _DEFAULT_OVERLAP,
) -> int:
    """
    将解析结果写入该 doc_id 的 FAISS 向量库并登记到知识库注册表。
    """
    from core.vector_store import VectorStore
    from core.knowledge_registry import register_doc_id

    chunks = build_chunks_from_parse(pages, pdf_tables, max_chars=max_chars, overlap=overlap)
    if not chunks:
        raise ValueError("没有可用于建库的正文或表格内容")
    store = VectorStore(doc_id)
    store.build(chunks)#转为向量
    register_doc_id(doc_id)#添加到注册表
    return len(chunks)
