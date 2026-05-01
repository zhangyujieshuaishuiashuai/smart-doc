from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import re
import time

from paddleocr import PaddleOCR
from core.config import settings, UPLOAD_DIR, PAGE_DIR
from core.schemas import OCRLine, PageParseResult
from core.reading_order import (
    reorder_pdf_lines,
    sort_single_column_lines,
    filter_lines,
    lines_to_text,
    build_rag_text,
    build_raw_ocr_text,
    build_display_from_preclean,
    detect_two_column_page,
)
from core.table_extract import (
    extract_tables_from_pdf,
    infer_tables_from_ocr_pages,
    merge_tables,
    tables_for_page,
)

READING_ORDER_VERSION = "v2"

ocr_engine = PaddleOCR(
    lang="ch",
    use_angle_cls=settings.OCR_USE_ANGLE_CLS,
    enable_mkldnn=settings.OCR_ENABLE_MKLDNN,
    cpu_threads=settings.OCR_CPU_THREADS,
)

STATIC_UPLOAD_MOUNT = "/static/uploads"
STATIC_PAGES_MOUNT = "/static/pages"


#将本地文件路径转换为web可访问路径
def build_image_url(image_path: Path) -> Optional[str]:
    """
    将本地磁盘路径映射为前端可访问的 HTTP URL。
    - 上传图片：/static/uploads/<file>
    - PDF 渲染页：/static/pages/<doc_id>/page_<n>.png
    """
    try:
        #用户上传的图片路径
        rel = image_path.relative_to(UPLOAD_DIR)#计算image_path 相对于 UPLOAD_DIR 的相对路径
        return f"{STATIC_UPLOAD_MOUNT}/{rel.as_posix()}"#/static/uploads+相对路径
    except ValueError:
        pass

    try:
        rel = image_path.relative_to(PAGE_DIR)#pdf渲染生成的页面图片
        return f"{STATIC_PAGES_MOUNT}/{rel.as_posix()}"
    except ValueError:
        pass

    return None


#模式选择
def normalize_clean_mode(mode: Optional[str]) -> str:
    if not mode:
        return "general"
    m = str(mode).strip().lower()
    if m in ("paper", "notice", "general"):
        return m
    return "general"


#页眉页脚判断
def _is_likely_journal_or_header_title_line(ln: str) -> bool:
    """首行常为期刊名/卷期/DOI 等，不宜作为文档标题。"""
    s = (ln or "").strip()
    #太短不行
    if not s or len(s) < 4:
        return True
    #包含特定关键词
    if re.search(
        r"(?i)(computer era|cnki\.net|doi\s*:|^doi\s|journal of|vol\.|issue\s|"
        r"press|编辑部|杂志社|期刊名|中图分类号|文献标志码|文章编号)",
        s,
    ):
        return True
    #包含明显的卷期年份信息
    if re.search(r"(?i)\bno\.\s*\d+", s) and re.search(r"\b20\d{2}\b", s):
        return True
    #包含明显的卷期年份信息（中文格式）
    if re.search(r"\d{4}\s*年\s*\d+\s*卷\s*\d+\s*期", s):
        return True
    #全英文且较短，且不包含中文字符，可能是页眉页脚
    if not re.search(r"[\u4e00-\u9fff]", s) and len(s) < 90:
        return True
    return False


#标题判断
def _select_title_from_lines(lines: List[str]) -> Optional[str]:
    """优先选含中文、且不像期刊页眉的第一条标题候选。"""
    if not lines:
        return None
    for ln in lines[:50]:
        #跳过可能是页眉页脚的
        if _is_likely_journal_or_header_title_line(ln):
            continue
        t = ln.strip()
        if re.search(r"[\u4e00-\u9fff]", t) and len(t) >= 6:
            return t
    #只要不是页眉页脚的就是标题    
    for ln in lines[:50]:
        if not _is_likely_journal_or_header_title_line(ln):
            return ln.strip()
    return lines[0].strip()



def merge_lines_to_paragraph(texts: List[str]) -> str:
    """
    将 OCR 的逐行文本合并为更自然的段落文本
    """
    if not texts:
        return ""

    result = []
    first_line = texts[0].strip()
    if first_line:
        result.append(first_line)

    paragraph = ""
    for line in texts[1:]:
        line = line.strip()
        if not line:
            continue

        #paragraph非空且不易末句标点结尾的句子   
        if paragraph and not paragraph.endswith(("。", "！", "？", "；", ":", "：")):
            paragraph += line
        #为空就新开一段
        else:
            if paragraph:
                result.append(paragraph)
            paragraph = line
    #若paragraph有内容即不是刚开始循环就添加
    if paragraph:
        result.append(paragraph)
    
    return "\n".join(result).strip()


def extract_doc_meta(
    text: str,
    filename: Optional[str],
    doc_mode: str,
) -> Dict[str, Any]:
    mode = normalize_clean_mode(doc_mode)
    meta: Dict[str, Any] = {
        "title": None,
        "source_org": None,
        "publish_date": None,
        "doc_no": None,
        "filename": filename or None,
        "authors": None,
        "abstract": None,
        "keywords": None,
        "attachments": None,
    }
    if not (text or "").strip():
        return meta

    #预处理,分割文本为行
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    #论文模式
    if mode == "paper":
        meta["title"] = _select_title_from_lines(lines)
        m_abs = re.search(
            r"摘要\s*[:：]?\s*([\s\S]*?)(?=关键词|关键字|Key\s*words|KEY\s*WORDS)",
            text,
            re.I,
        )
        if m_abs:
            meta["abstract"] = m_abs.group(1).strip()[:4000]
        m_kw = re.search(
            r"(?:关键词|关键字)\s*[:：]?\s*([^\n]+)",
            text,
            re.I,
        )
        if m_kw:
            meta["keywords"] = m_kw.group(1).strip()[:800]
        if meta.get("title"):
            for i, ln in enumerate(lines):
                if ln.strip() == meta["title"]:
                    if i + 1 < len(lines):
                        second = lines[i + 1]
                        if len(second) < 120 and not _is_likely_journal_or_header_title_line(
                            second
                        ):
                            meta["authors"] = second
                    break
    
    #通知公告模式
    elif mode == "notice":
        title = None
        for ln in lines[:15]:
            if re.search(r"(关于|通知|公告|决定|通报|意见|方案|办法)", ln) and 6 <= len(ln) <= 200:
                title = ln
                break
        if not title and lines:
            pool = lines[:10]
            title = max(pool, key=len) if pool else None
        meta["title"] = title

        #来源
        for ln in lines:
            if re.search(
                r"^[\u4e00-\u9fff（）()]{2,30}(?:学院|办公室|处|委员会|中心|党委|党组|人民政府|司|局|署|部|组)\s*$",
                ln,
            ):
                meta["source_org"] = ln.strip()
                break

        dm = re.search(
            r"\d{4}年\d{1,2}月\d{1,2}日|\d{4}[-/年]\d{1,2}[-/月]\d{1,2}",
            text,
        )
        meta["publish_date"] = dm.group(0).replace("/", "-") if dm else None

        #文档编号
        wm = re.search(
            r"[\u4e00-\u9fff]{0,6}?〔\d{4}〕\s*\d+号|[\u4e00-\u9fff]{0,4}第\s*\d+\s*号",
            text,
        )
        if wm:
            meta["doc_no"] = re.sub(r"\s+", "", wm.group(0))
        #有无附件
        if re.search(r"附件\s*\d*\s*[:：]?", text):
            meta["attachments"] = True

    #通用模式
    else:
        meta["title"] = _select_title_from_lines(lines)
        dm = re.search(
            r"\d{4}年\d{1,2}月\d{1,2}日|\d{4}[-/]\d{1,2}[-/]\d{1,2}",
            text,
        )
        meta["publish_date"] = dm.group(0) if dm else None

    return meta


#兼容旧的parser,统一结构
def info_from_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """兼容旧 /parse 响应中的 info 结构。"""
    return {
        "title": meta.get("title"),
        "names": [],
        "time": meta.get("publish_date"),
        "organization": meta.get("source_org"),
    }


def extract_structured_info(text: str) -> Dict[str, Any]:
    """保留旧接口：按 general 模式从正文中抽取 meta 并映射为 info。"""
    return info_from_meta(extract_doc_meta(text, None, "general"))


#原始ocr文本转为OCRLine
def _dict_line_to_ocr_line(o: Dict[str, Any]) -> OCRLine:
    bb = o["bbox"]#取boarding box坐标
    """
        先将 p[0] 和 p[1] 转换为 float（以防原始数据是字符串），
        然后四舍五入取整（round），
        最后转为 int 类型。
    """
    bbox_int = [[int(round(float(p[0]))), int(round(float(p[1])))] for p in bb]
    return OCRLine(text=str(o["text"]), score=float(o["score"]), bbox=bbox_int)


#接受图像路径和清理参数
def ocr_image(
    image_path: Path,
    clean_mode: str = "general",
  ) -> Tuple[str, str, str, str, List[OCRLine], bool, int, int, int]:
    """
    原始 OCR 文本、显示文本、用于 RAG 的清洗文本、预清洗文本、OCR 行列表、是否双栏布局、原始行数、过滤后行数、处理耗时（毫秒）
    """
    t0 = time.perf_counter()
    mode = normalize_clean_mode(clean_mode)

    #耗时
    def _elapsed_ms() -> int:
        return int((time.perf_counter() - t0) * 1000)

    #调用 OCR 引擎
    try:
        result = ocr_engine.ocr(str(image_path), cls=settings.OCR_USE_ANGLE_CLS)
    except Exception as e:
        print(f"[ERROR] OCR执行失败: {e}")
        return "", "", "", "", [], False, 0, 0, _elapsed_ms()

    if not result or not result[0]:
        return "", "", "", "", [], False, 0, 0, _elapsed_ms()

    #遍历OCR结果
    raw_lines: List[Dict[str, Any]] = []
    for item in result[0]:
        try:
            bbox = [[int(p[0]), int(p[1])] for p in item[0]]
            text = item[1][0]
            score = float(item[1][1])
        except Exception as e:
            print(f"[ERROR] OCR解析失败: {e}")
            continue

        raw_lines.append({"text": text, "score": score, "bbox": bbox})

    ocr_line_count = len(raw_lines)

    #论文模式是不是双栏
    if mode == "paper":
        is_two = detect_two_column_page(raw_lines)
        ordered = reorder_pdf_lines(raw_lines)
    #通知模式强制单栏
    elif mode == "notice":
        is_two = False
        ordered = sort_single_column_lines(raw_lines)
    #其他情况普通模式并检测双栏
    else:
        is_two = detect_two_column_page(raw_lines)
        ordered = reorder_pdf_lines(raw_lines)

    # general 模式使用更低阈值，避免丢失手写单字
    if mode == "general":
        min_score = min(settings.OCR_FILTER_MIN_SCORE, 0.15)
    else:
        min_score = settings.OCR_FILTER_MIN_SCORE

    ordered = filter_lines(
        ordered,
        min_score=min_score,
        mode=mode,
    )
    filtered_line_count = len(ordered)
    raw_ocr_text = build_raw_ocr_text(raw_lines)
    preclean_text = lines_to_text(ordered)
    display_text = build_display_from_preclean(preclean_text, mode)
    #专用于RAG的精炼文本
    clean_text_for_rag = build_rag_text(preclean_text, mode)
    #字典转换为OCRLine对象列表
    lines_out = [_dict_line_to_ocr_line(o) for o in ordered]
    parse_ms = _elapsed_ms()
    return (
        raw_ocr_text,
        display_text,
        clean_text_for_rag,
        preclean_text,
        lines_out,
        is_two,
        ocr_line_count,
        filtered_line_count,
        parse_ms,
    )


def parse_pages(
    image_paths: List[Path],
    clean_mode: str = "general",
    pdf_path: Optional[Path] = None,
) -> Tuple[List[PageParseResult], List[Dict[str, Any]]]:
    mode = normalize_clean_mode(clean_mode)
    page_results: List[PageParseResult] = []
    pdf_tables: List[Dict[str, Any]] = []
    if pdf_path is not None:
        pdf_tables = extract_tables_from_pdf(pdf_path)


    for idx, image_path in enumerate(image_paths, start=1):
        (
            raw_ocr_text,
            display_text,
            clean_text_for_rag,
            preclean_text,
            lines,
            is_two,
            ocr_line_count,
            filtered_line_count,
            parse_ms,
        ) = ocr_image(image_path, clean_mode=mode)

        page_results.append(
            PageParseResult(
                page_no=idx,
                image_path=str(image_path),
                image_url=build_image_url(image_path),
                text=display_text,
                display_text=display_text,
                clean_text_for_rag=clean_text_for_rag,
                raw_ocr_text=raw_ocr_text,
                lines=lines,
                preclean_text=preclean_text,
                clean_mode=mode,
                tables=[],
                is_two_column=is_two,
                reading_order_version=READING_ORDER_VERSION,
                ocr_line_count=ocr_line_count,
                filtered_line_count=filtered_line_count,
                parse_ms=parse_ms,
            )
        )

    ocr_tables = infer_tables_from_ocr_pages(page_results)
    pdf_tables = merge_tables(pdf_tables, ocr_tables)
    for page_result in page_results:
        page_result.tables = tables_for_page(pdf_tables, page_result.page_no)

    return page_results, pdf_tables


def table_extract_status_for(
    source: str,
    pdf_tables: List[Dict[str, Any]],
    pdf_path: Optional[Path],
) -> str:
    if pdf_tables:
        return "extracted"
    if source == "image":
        return "no_table_found"
    if pdf_path is None:
        return "no_table_found"
    #pdfplumber pdf表格提取
    try:
        import pdfplumber  # noqa: F401  # type: ignore[import-not-found]忽略未使用导入
    except ImportError:
        return "library_unavailable"
    if pdf_tables:
        return "extracted"
    return "no_table_found"
