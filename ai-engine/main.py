import logging
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from openai import OpenAIError
from fastapi.staticfiles import StaticFiles

from core.chunking import index_parse_to_vector_store
from core.config import PAGE_DIR, UPLOAD_DIR, VECTOR_DIR, settings
from core.knowledge_registry import list_registered
from core.schemas import KnowledgeIndexRequest, RagAskRequest, RagAskResponse
from core.utils import gen_doc_id, pdf_to_images, save_upload_file


logger = logging.getLogger(__name__)

# Windows 上 PaddleOCR 先加载时，后续再导入 torch/sentence-transformers
# 可能触发 shm.dll 的 WinError 127。这里尽量先做一次轻量预加载。
if os.name == "nt":
    try:
        import core.vector_store as _vector_store_preload  # noqa: F401
        logger.info("[RAG_PRELOAD] preloaded core.vector_store before parser import")
    except Exception as e:  # noqa: BLE001
        logger.warning("[RAG_PRELOAD] preload skipped: %s", e)

from core.parser import (
    extract_doc_meta,
    info_from_meta,
    normalize_clean_mode,
    parse_pages,
    table_extract_status_for,
)

app = FastAPI(title=settings.APP_NAME)

app.mount("/static/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/static/pages", StaticFiles(directory=str(PAGE_DIR)), name="pages")


@app.on_event("startup")
async def _log_startup_paths() -> None:
    """便于核对：向量文件一定写在该绝对路径下，与资源管理器里打开的目录须一致。"""
    print(f"[STARTUP] VECTOR_DIR={VECTOR_DIR.resolve()}", flush=True)
    print(f"[STARTUP] Python 解释器={sys.executable}", flush=True)

CleanMode = Literal["paper", "notice", "general"]

_RAG_ENV_HINT = (
    "若需基于文档的向量问答，请安装 Microsoft Visual C++ 可再发行组件，或在 venv 中重装 CPU 版 torch："
    "pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cpu"
)


def _form_truthy(v: Optional[str]) -> bool:
    """multipart中布尔常被当成字符串；兼容 Java/Spring 与 Postman。"""
    if v is None:
        return False
    s = str(v).strip()
    if not s:
        return False
    return s.lower() in ("1", "true", "yes", "on")


#整理 RAG 检索返回的上下文片段，使其变成接口可以返回给前端的格式
def _contexts_for_response(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items:
        row: Dict[str, Any] = {
            "content": (item.get("content") or item.get("text") or "")[:8000],
            "score": item.get("score"),
            "source_type": item.get("source_type"),
            "page_no": item.get("page_no"),
            "table_id": item.get("table_id"),
        }
        if item.get("doc_id"):
            row["doc_id"] = item["doc_id"]
        if item.get("doc_name"):
            row["doc_name"] = item["doc_name"]
        out.append({k: v for k, v in row.items() if v is not None})
    return out


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/knowledge/index")
#异步接口,为实现多文件传输而设计,返回已建库的文档列表,但向量化和索引写入过程本身仍可能是同步计算任务
async def knowledge_index(body: KnowledgeIndexRequest) -> Dict[str, Any]:
    """将解析结果（正文、OCR、表格）分块写入向量库，供 RAG 检索。"""
    try:
        n = index_parse_to_vector_store(
            body.doc_id,
            body.pages,
            body.tables,
            max_chars=body.max_chars_per_chunk,
            overlap=body.chunk_overlap,
        )
        return {"doc_id": body.doc_id, "chunks": n, "status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "向量模型依赖（PyTorch / sentence-transformers）在本机加载失败，无法建库。"
                "可先仅用解析接口；若需 RAG，请安装 Microsoft Visual C++ 可再发行组件，"
                "或在虚拟环境中重装 CPU 版 torch："
                "pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cpu"
                f" 原始错误：{e!s}"
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge/docs")

async def knowledge_list() -> Dict[str, Any]:
    """已建库、可参与全局检索的 doc_id 列表（由入库接口维护）。"""
    return {"doc_ids": list_registered()}


@app.post("/rag/ask", response_model=RagAskResponse)
async def rag_ask(body: RagAskRequest) -> RagAskResponse:
    """
    RAG 问答：隔离模式 = 单文档；非隔离 = 跨多文档检索后汇总生成。
    须先对目标文档调用 `/knowledge/index` 或在解析时开启 `index_for_rag`。
    """
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        raise HTTPException(status_code=503, detail="未配置 DEEPSEEK_API_KEY")

    #可能会讲解加载pytorch等,即使rag失效了解析功能依旧可以使用
    try:
        from core.rag import answer_question_across_docs, answer_question_in_doc
    except OSError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "向量检索依赖（PyTorch）未就绪，无法执行 RAG。"
                "解析接口仍可单独使用。修复可参考 /knowledge/index 返回的说明。"
                f" 原始错误：{e!s}"
            ),
        )

    try:
        if body.isolated:
            answer, ctx = answer_question_in_doc(
                body.doc_id or "",
                body.question,
                top_k=body.top_k,
                #将内部文档 ID 映射为用户可读的文档名称
                doc_name_map=body.doc_name_map or {},
            )
            return RagAskResponse(
                answer=answer,
                isolated=True,
                contexts=_contexts_for_response(ctx),
            )
        answer, ctx = answer_question_across_docs(
            body.doc_ids or [],
            body.question,
            top_k=body.top_k,
            doc_name_map=body.doc_name_map or {},
        )
        return RagAskResponse(
            answer=answer,
            isolated=False,
            contexts=_contexts_for_response(ctx),
        )
    except OpenAIError as e:
        # 密钥无效、欠费、网络、DeepSeek 侧 4xx/5xx 等
        raise HTTPException(
            status_code=502,
            detail=f"大模型调用失败（DeepSeek/OpenAI 兼容接口）: {e}",
        ) from e
    #对于未预期异常，系统会记录异常堆栈，并向前端返回 500 错误
    except Exception as e:
        logger.exception("rag_ask failed")
        #当前 HTTPException 是由原始异常 e 引起的
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/parse/image")
async def parse_image(
    file: UploadFile = File(...),
    clean_mode: CleanMode = Form("general"),
    index_for_rag: Optional[str] = Form(default=None),
    client_doc_id: Optional[str] = Form(None, alias="doc_id"),
) -> Dict[str, Any]:
    index_for_rag_flag = _form_truthy(index_for_rag)
    print(
        f"[PARSE_IMAGE][START] file={file.filename}, clean_mode={clean_mode}, "
        f"index_for_rag_raw={index_for_rag!r} -> {index_for_rag_flag}"
    )
    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".bmp"]:
        raise HTTPException(status_code=400, detail="请上传图片文件")

    try:
        cid = (client_doc_id or "").strip()
        doc_id = cid if cid else gen_doc_id()
        image_path = save_upload_file(file, UPLOAD_DIR)
        cm = normalize_clean_mode(clean_mode)

        pages, pdf_tables = parse_pages([image_path], clean_mode=cm, pdf_path=None)

        merged_raw = "\n\n".join(p.raw_ocr_text for p in pages if p.raw_ocr_text).strip()
        merged_display = "\n\n".join(p.display_text for p in pages if p.display_text).strip()
        merged_rag = "\n\n".join(p.clean_text_for_rag for p in pages if p.clean_text_for_rag).strip()
        meta = extract_doc_meta(merged_display, file.filename, cm)
        tstat = table_extract_status_for("image", pdf_tables, None)

        print(f"[PARSE_IMAGE][DONE] file={file.filename}, pages={len(pages)}, mode={cm}")
        payload: Dict[str, Any] = {
            "doc_id": doc_id,
            "doc_type": "image",
            "clean_mode": cm,
            "raw_ocr_text": merged_raw,
            "display_text": merged_display,
            "clean_text_for_rag": merged_rag,
            "text": merged_display,
            "text_rag": merged_rag,
            "table_extract_status": tstat,
            "tables": pdf_tables,
            "pages": [p.model_dump(by_alias=True) for p in pages],
            "meta": meta,
            "info": info_from_meta(meta),
        }
        if index_for_rag_flag:
            page_dicts = [p.model_dump(by_alias=True) for p in pages]
            try:
                payload["indexed_chunks"] = index_parse_to_vector_store(
                    doc_id, page_dicts, pdf_tables
                )
                print(
                    f"[PARSE_IMAGE][INDEX_OK] doc_id={doc_id} chunks={payload['indexed_chunks']} "
                    f"path={VECTOR_DIR / doc_id}"
                )
            except ValueError as ie:
                payload["index_error"] = str(ie)
                print(f"[PARSE_IMAGE][INDEX_ERROR] doc_id={doc_id} {ie}")
            except Exception as ie:
                payload["index_error"] = (
                    f"向量入库失败（多为 PyTorch / shm.dll 等本机依赖问题），解析结果仍已返回。{_RAG_ENV_HINT} "
                    f"原始错误：{ie!s}"
                )
                print(f"[PARSE_IMAGE][INDEX_ERROR] doc_id={doc_id} {ie!s}")
        else:
            print(f"[PARSE_IMAGE][INDEX_SKIP] doc_id={doc_id}（未传 index_for_rag 或为 false）")
        return payload

    except Exception as e:
        print(f"[PARSE_IMAGE][ERROR] file={file.filename}, err={e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/parse/pdf")
async def parse_pdf(
    file: UploadFile = File(...),
    clean_mode: CleanMode = Form("paper"),
    index_for_rag: Optional[str] = Form(default=None),
    client_doc_id: Optional[str] = Form(None, alias="doc_id"),
) -> Dict[str, Any]:
    index_for_rag_flag = _form_truthy(index_for_rag)
    print(
        f"[PARSE_PDF][START] file={file.filename}, clean_mode={clean_mode}, "
        f"index_for_rag_raw={index_for_rag!r} -> {index_for_rag_flag}, doc_id={(client_doc_id or '')!r}"
    )
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件")

    try:
        cid = (client_doc_id or "").strip()
        doc_id = cid if cid else gen_doc_id()
        pdf_path = save_upload_file(file, UPLOAD_DIR)
        cm = normalize_clean_mode(clean_mode)

        image_dir = PAGE_DIR / doc_id
        image_paths = pdf_to_images(pdf_path, image_dir, dpi=settings.PDF_RENDER_DPI)
        print(f"[PARSE_PDF][RENDERED] file={file.filename}, images={len(image_paths)}")

        pages, pdf_tables = parse_pages(image_paths, clean_mode=cm, pdf_path=pdf_path)

        merged_raw = "\n\n".join(p.raw_ocr_text for p in pages if p.raw_ocr_text).strip()
        merged_display = "\n\n".join(p.display_text for p in pages if p.display_text).strip()
        merged_rag = "\n\n".join(p.clean_text_for_rag for p in pages if p.clean_text_for_rag).strip()
        meta = extract_doc_meta(merged_display, file.filename, cm)
        tstat = table_extract_status_for("pdf", pdf_tables, pdf_path)

        print(f"[PARSE_PDF][DONE] file={file.filename}, pages={len(pages)}, mode={cm}")
        payload = {
            "doc_id": doc_id,
            "doc_type": "pdf",
            "clean_mode": cm,
            "raw_ocr_text": merged_raw,
            "display_text": merged_display,
            "clean_text_for_rag": merged_rag,
            "text": merged_display,
            "text_rag": merged_rag,
            "table_extract_status": tstat,
            "tables": pdf_tables,
            "pages": [p.model_dump(by_alias=True) for p in pages],
            "meta": meta,
            "info": info_from_meta(meta),
        }

        # 索引向量库
        if index_for_rag_flag:
            page_dicts = [p.model_dump(by_alias=True) for p in pages]
            try:
                payload["indexed_chunks"] = index_parse_to_vector_store(
                    doc_id, page_dicts, pdf_tables
                )
                print(
                    f"[PARSE_PDF][INDEX_OK] doc_id={doc_id} chunks={payload['indexed_chunks']} "
                    f"path={VECTOR_DIR / doc_id}"
                )
            except ValueError as ie:
                payload["index_error"] = str(ie)
                print(f"[PARSE_PDF][INDEX_ERROR] doc_id={doc_id} {ie}")
            except Exception as ie:
                payload["index_error"] = (
                    f"向量入库失败（多为 PyTorch / shm.dll 等本机依赖问题），解析结果仍已返回。{_RAG_ENV_HINT} "
                    f"原始错误：{ie!s}"
                )
                print(f"[PARSE_PDF][INDEX_ERROR] doc_id={doc_id} {ie!s}")
        else:
            print(f"[PARSE_PDF][INDEX_SKIP] doc_id={doc_id}（未传 index_for_rag 或为 false）")
        return payload

    except Exception as e:
        print(f"[PARSE_PDF][ERROR] file={file.filename}, err={e}")
        raise HTTPException(status_code=500, detail=str(e))
