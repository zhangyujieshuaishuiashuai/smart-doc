from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Any, Dict


class OCRLine(BaseModel):
    text: str
    score: float
    bbox: List[List[int]]


class PageParseResult(BaseModel):
    page_no: int = Field(serialization_alias="page")
    image_path: str
    image_url: Optional[str] = None
    text: str
    display_text: str
    clean_text_for_rag: str
    raw_ocr_text: str = ""
    lines: List[OCRLine]
    preclean_text: Optional[str] = None
    clean_mode: str = "general"
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    is_two_column: bool = False
    reading_order_version: str = "v2"
    ocr_line_count: int = 0
    filtered_line_count: int = 0
    parse_ms: int = 0

    model_config = {"populate_by_name": True}


class TableResult(BaseModel):
    page_no: int
    table_id: str
    markdown: str
    rows: List[List[str]]


class ParseResponse(BaseModel):
    doc_id: str
    pages: List[PageParseResult]
    tables: List[TableResult]


#查询请求类
class QueryRequest(BaseModel):
    doc_id: str
    question: str
    top_k: int = 5

#答案来源项
class SourceItem(BaseModel):
    content: str
    page_no: Optional[int] = None
    score: Optional[float] = None
    source_type: Optional[str] = "text"


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceItem]


class KnowledgeIndexRequest(BaseModel):
    """解析完成后写入向量库；`pages` / `tables` 与 `/parse/pdf|image` JSON 字段一致。"""

    doc_id: str
    pages: List[Dict[str, Any]]
    #tables 使用 default_factory=list 作为默认值，避免多个页面对象共享同一个列表
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    max_chars_per_chunk: int = 900
    chunk_overlap: int = 120


#RAG问答请求
class RagAskRequest(BaseModel):
    """isolated=True：仅当前文档；False：跨 doc_ids 全局检索与汇总。"""

    question: str
    doc_id: Optional[str] = None
    doc_ids: Optional[List[str]] = None
    doc_name_map: Optional[Dict[str, str]] = None
    isolated: bool = True
    #较小的 top_k 可以减少无关上下文，较大的 top_k 可以提高召回，但也可能引入噪声
    top_k: int = 5

    @model_validator(mode="after")
    def _check_ids(self):
        if self.isolated:
            if not (self.doc_id and str(self.doc_id).strip()):
                raise ValueError("隔离模式下必须提供 doc_id")
        else:
            ids = self.doc_ids or []
            if not ids:
                raise ValueError("非隔离模式下必须提供非空 doc_ids")
        return self


class RagAskResponse(BaseModel):
    answer: str
    isolated: bool
    contexts: List[Dict[str, Any]]
