"""
RAG 文档问答模块：先检索向量库片段（正文/OCR/表格），再调用 DeepSeek 生成答案。
"""
from typing import List, Dict, Any, Tuple

from core.llm import chat_with_deepseek

# 向量库缺失、torch/sentence-transformers 加载或推理失败（含 Windows DLL / RuntimeError）
_VECTOR_FAIL_TYPES = (FileNotFoundError, OSError, ImportError, RuntimeError)


def _degraded_answer(question: str) -> Tuple[str, List[Dict[str, Any]]]:
    """向量库或本地 embedding 不可用时：仍走通用对话，避免接口直接 500。"""
    answer = chat_with_deepseek(
        [
            {"role": "system", "content": "你是友好的中文助手，请简洁、准确地回答用户。"},
            {"role": "user", "content": question},
        ]
    )
    prefix = (
        "【提示】向量检索不可用（文档未入库、或本机 PyTorch/sentence-transformers 加载失败——"
        "Windows 上常见为 torch 的 DLL 问题）。以下回答未结合已上传文档，仅作通用对话。\n\n"
    )
    return prefix + (answer or ""), []


#提取文本内容
def _chunk_excerpt(item: Dict[str, Any]) -> str:
    return (item.get("content") or item.get("text") or "").strip()


#获取文档标签
def _doc_label(doc_id: str, doc_name_map: Dict[str, str] | None = None) -> str:
    if doc_name_map:
        name = (doc_name_map.get(str(doc_id)) or "").strip()
        if name:
            return name
    return str(doc_id)


def answer_question_in_doc(
    doc_id: str,
    question: str,
    top_k: int = 5,
    doc_name_map: Dict[str, str] | None = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """隔离模式：仅在单个文档内检索后回答。"""
    """
    尝试导入VectorStore类并创建实例，对指定文档ID进行向量搜索，获取top_k个最相关的上下文片段。
    为每个检索结果添加文档ID和文档名称信息。
    如果发生_VECTOR_FAIL_TYPES中定义的异常，则调用降级回答函数。
    """
    
    try:
        from core.vector_store import VectorStore

        store = VectorStore(doc_id)
        contexts = store.search(question, top_k=top_k)
        label = _doc_label(doc_id, doc_name_map)
        for item in contexts:
            item["doc_id"] = str(doc_id)
            item["doc_name"] = label
    except _VECTOR_FAIL_TYPES:
        return _degraded_answer(question)

    #空行连接优化过的上下文
    context_text = "\n\n".join(
        f"[片段{i+1}]\n{_chunk_excerpt(item)}"
        for i, item in enumerate(contexts)
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是文档智能问答助手。检索片段可能包含：页级正文、OCR 原始文本、或结构化表格（Markdown/表格）。"
                "必须严格依据这些片段作答；引用表格时请按片段中的行列含义回答。"
                "若片段不足以回答，请明确说‘未在文档中找到足够依据’，不要凭模型记忆臆测。"
                "可作简要归纳，但不要编造片段中不存在的事实。"
            ),
        },
        {
            "role": "user",
            "content": f"问题：{question}\n\n检索上下文：\n{context_text}",
        },
    ]

    answer = chat_with_deepseek(messages)
    return answer, contexts


def search_all_docs(
    question: str,
    doc_ids: List[str],
    top_k: int = 5,
    doc_name_map: Dict[str, str] | None = None,
) -> List[Dict[str, Any]]:
    """非隔离模式：跨多个文档检索。"""
    try:
        from core.vector_store import VectorStore
    except _VECTOR_FAIL_TYPES:
        return []

    hits: List[Dict[str, Any]] = []
    for doc_id in doc_ids:
        try:
            store = VectorStore(doc_id)
            for item in store.search(question, top_k=3):
                item_with_doc = item.copy()
                item_with_doc["doc_id"] = str(doc_id)
                item_with_doc["doc_name"] = _doc_label(str(doc_id), doc_name_map)
                hits.append(item_with_doc)
        except _VECTOR_FAIL_TYPES:
            # 单库缺失或本机 torch/DLL 未就绪，跳过该文档
            continue

    hits.sort(key=lambda x: x.get("score", 0), reverse=True)
    return hits[:top_k]


def answer_question_across_docs(
    doc_ids: List[str],
    question: str,
    top_k: int = 8,
    doc_name_map: Dict[str, str] | None = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """非隔离模式：在多文档检索结果上生成答案。"""
    contexts = search_all_docs(question, doc_ids, top_k=top_k, doc_name_map=doc_name_map)
    if not contexts:
        return _degraded_answer(question)

    context_text = "\n\n".join(
        f"[文件 {item.get('doc_name') or item.get('doc_id')} · 片段]\n{_chunk_excerpt(item)}"
        for item in contexts
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是跨文档知识库问答助手。上下文来自多个已上传文档的检索结果（正文/OCR/表格等）。"
                "请综合多片段作答；若问题涉及‘来自哪个文件’，答案中请优先使用文件名，"
                "不要只写 doc_id。"
                "若检索片段均不足以支持结论，请说明‘未在已检索到的内容中找到足够依据’。"
                "不要编造未发现于片段中的来源或细节。"
            ),
        },
        {"role": "user", "content": f"问题：{question}\n\n检索上下文：\n{context_text}"},
    ]

    answer = chat_with_deepseek(messages)
    return answer, contexts
