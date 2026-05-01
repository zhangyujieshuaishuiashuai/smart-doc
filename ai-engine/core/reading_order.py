"""
双栏/单栏阅读顺序重排：基于 OCR 行的 bbox 做启发式排序，非完整版面分析。
"""
import re
import statistics
from typing import Any, Dict, List, Tuple

# 手写/试卷等场景常见单字，不得因 len<=1 被滤掉
SPECIAL_KEEP = frozenset({
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "口", "日", "目", "田", "〇", "○", "□", "■",
    "①", "②", "③", "㈠", "㈡", "㈢",
})


#判断是否为有意义的token
def is_meaningful_token(token: str) -> bool:
    t = token.strip()
    if not t:
        return False
    if t in SPECIAL_KEEP:
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]", t):
        return True
    if re.fullmatch(r"[A-Za-z0-9]", t):
        return True
    return len(t) > 1


def _safe_text(s: Any) -> str:
    return "" if s is None else str(s).strip()


# bbox 转为矩形坐标
def _bbox_to_rect(bbox: List[List[float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return min(xs), min(ys), max(xs), max(ys)#left, top, right, bottom

#获取数据对原始OCR结果进行标准化
#OCR 原始结果转换为包含几何特征的标准结构
def _normalize_lines(raw_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for item in raw_lines or []:
        text = _safe_text(item.get("text"))
        bbox = item.get("bbox")
        score = float(item.get("score", 0.0))

        if not text or not bbox or len(bbox) < 4:
            continue

        left, top, right, bottom = _bbox_to_rect(bbox)
        width = max(1.0, right - left)
        height = max(1.0, bottom - top)
        center_x = (left + right) / 2.0
        center_y = (top + bottom) / 2.0

        rows.append({
            "text": text,
            "score": score,
            "bbox": bbox,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": width,
            "height": height,
            "center_x": center_x,
            "center_y": center_y,
        })

    return rows


#分组
def _group_by_rows(lines: List[Dict[str, Any]], y_tol: float = 18.0) -> List[List[Dict[str, Any]]]:
    if not lines:
        return []

    lines = sorted(lines, key=lambda x: (x["center_y"], x["left"]))
    groups = []
    current = [lines[0]]

    #按中心点(center_y)和水平位置(left)排序所有行
    for line in lines[1:]:
        prev_y = statistics.mean([x["center_y"] for x in current])
        #按垂直容差归为一组
        if abs(line["center_y"] - prev_y) <= y_tol:
            current.append(line)
        #按水平位置排序
        else:
            groups.append(sorted(current, key=lambda x: x["left"]))
            current = [line]

    groups.append(sorted(current, key=lambda x: x["left"]))
    return groups


#计算页面指标
def _estimate_page_metrics(lines: List[Dict[str, Any]]) -> Dict[str, float]:
    if not lines:
        return {
            "page_left": 0.0,
            "page_right": 0.0,
            "page_width": 0.0,
            "median_height": 20.0,
            "median_width": 100.0,
        }

    page_left = min(x["left"] for x in lines)
    page_right = max(x["right"] for x in lines)
    page_width = max(1.0, page_right - page_left)

    heights = [x["height"] for x in lines]
    widths = [x["width"] for x in lines]

    return {
        "page_left": page_left,
        "page_right": page_right,
        "page_width": page_width,
        "median_height": statistics.median(heights) if heights else 20.0,
        "median_width": statistics.median(widths) if widths else 100.0,
    }


#判断是否为双栏
def _detect_two_columns(lines: List[Dict[str, Any]], metrics: Dict[str, float]) -> bool:
    if len(lines) < 12:
        return False
    #太短了,不够判断

    page_width = metrics["page_width"]
    if page_width <= 0:
        return False

    body_candidates = [
        x for x in lines
        if 0.18 * page_width <= x["width"] <= 0.65 * page_width
    ]

    if len(body_candidates) < 8:
        return False

    #计算中心点和候选行的最大间隙
    centers = sorted(x["center_x"] for x in body_candidates)
    if len(centers) < 8:
        return False

    gaps = []
    for i in range(len(centers) - 1):
        gaps.append((centers[i + 1] - centers[i], i))

    if not gaps:
        return False

    max_gap, idx = max(gaps, key=lambda x: x[0])

    #如果最大缝隙小于页面宽度的12%,则不是双栏
    if max_gap < page_width * 0.12:
        return False

    left_cluster = centers[:idx + 1]
    right_cluster = centers[idx + 1:]

    #检查左右两栏是否至少3行
    if len(left_cluster) < 3 or len(right_cluster) < 3:
        return False

    return True


#拆分页眉、页脚和正文
def _split_header_footer_and_body(lines: List[Dict[str, Any]], metrics: Dict[str, float]):
    if not lines:
        return [], [], []

    page_top = min(x["top"] for x in lines)
    page_bottom = max(x["bottom"] for x in lines)
    page_height = max(1.0, page_bottom - page_top)

    header_limit = page_top + page_height * 0.18
    footer_limit = page_bottom - page_height * 0.12

    header = [x for x in lines if x["bottom"] <= header_limit]
    footer = [x for x in lines if x["top"] >= footer_limit]
    body = [x for x in lines if x not in header and x not in footer]

    return header, body, footer


#判断是否为全宽
def _split_full_width_and_column_candidates(
    lines: List[Dict[str, Any]],
    metrics: Dict[str, float],
):
    page_width = metrics["page_width"]
    full_width = []
    column_candidates = []

    #宽度大于0.72的行是全宽行,否则是双栏候选行
    for x in lines:
        if x["width"] >= 0.72 * page_width:
            full_width.append(x)
        else:
            column_candidates.append(x)

    return full_width, column_candidates


#分为左右两行
def _cluster_two_columns(lines: List[Dict[str, Any]], metrics: Dict[str, float]):
    if not lines:
        return [], []

    #找到最大间隙的位置
    centers = sorted(x["center_x"] for x in lines)
    gaps = [(centers[i + 1] - centers[i], i) for i in range(len(centers) - 1)]
    if not gaps:
        return sorted(lines, key=lambda x: (x["top"], x["left"])), []
    

    #按垂直,水平进行排序
    max_gap, idx = max(gaps, key=lambda x: x[0])
    split_x = (centers[idx] + centers[idx + 1]) / 2.0

    left_col = [x for x in lines if x["center_x"] <= split_x]
    right_col = [x for x in lines if x["center_x"] > split_x]

    left_col = sorted(left_col, key=lambda x: (x["top"], x["left"]))
    right_col = sorted(right_col, key=lambda x: (x["top"], x["left"]))

    return left_col, right_col


#单栏排序
def _sort_single_column(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups = _group_by_rows(lines)
    ordered = []
    for g in groups:
        ordered.extend(sorted(g, key=lambda x: x["left"]))
    return ordered

#双栏排序
def _sort_two_columns(lines: List[Dict[str, Any]], metrics: Dict[str, float]) -> List[Dict[str, Any]]:
    header, body, footer = _split_header_footer_and_body(lines, metrics)

    header_sorted = _sort_single_column(header)
    footer_sorted = _sort_single_column(footer)

    full_width, column_candidates = _split_full_width_and_column_candidates(body, metrics)

    full_width_sorted = sorted(full_width, key=lambda x: (x["top"], x["left"]))

    left_col, right_col = _cluster_two_columns(column_candidates, metrics)
    left_sorted = _sort_single_column(left_col)
    right_sorted = _sort_single_column(right_col)
    # Block-wise assembly: keep near-top full-width lines as title/meta,
    # then force body as left-column followed by right-column to avoid cross-column stitching.
    if left_sorted or right_sorted:
        body_start_top = min(x["top"] for x in (left_sorted + right_sorted))
        anchor = body_start_top + max(12.0, float(metrics.get("median_height", 20.0)) * 1.5)
        lead_full_width = [x for x in full_width_sorted if x["bottom"] <= anchor]
        tail_full_width = [x for x in full_width_sorted if x["bottom"] > anchor]
    else:
        lead_full_width = full_width_sorted
        tail_full_width = []

   #按页眉 → 标题 → 左栏 → 右栏 → 正文末尾全宽行 → 页脚的顺序组装
    return header_sorted + lead_full_width + left_sorted + right_sorted + tail_full_width + footer_sorted


""" 主要入口函数"""
def reorder_pdf_lines(raw_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lines = _normalize_lines(raw_lines)
    if not lines:
        return []

    metrics = _estimate_page_metrics(lines)
    is_two_col = _detect_two_columns(lines, metrics)

    if is_two_col:
        return _sort_two_columns(lines, metrics)
    return _sort_single_column(lines)


def sort_single_column_lines(raw_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """公开接口：仅单栏阅读顺序（公告/通知类默认用）。"""
    lines = _normalize_lines(raw_lines)
    if not lines:
        return []
    return _sort_single_column(lines)


#判断是否为纯页码
def _is_line_pure_page_number_text(t: str) -> bool:
    return bool(re.fullmatch(r"[-·\s]*\d+[-·\s]*", t.strip()))


def _filter_line_drop_for_mode(t: str, mode: str) -> bool:
    """若该行应丢弃（在通用规则之后按模式追加），返回 True。"""
    tl = t.strip()
    if mode == "paper":
        if re.search(
            r"(?i)(cnki|doi:|doi\s|http|www\.|计算机时代|computer era|"
            r"收稿日期|修回日期|基金项目|作者简介|版权声明|copyright)",
            tl,
        ):
            return True
        if re.match(r"(?i)^\s*(中图分类号|文献标志码|文章编号|关键词|key words)\s*[:：]", tl):
            return False
        if re.search(r"(?i)^(.*编辑部|.*杂志社)\s*$", tl) and len(tl) < 48:
            return True
    elif mode == "notice":
        if re.search(r"(?i)^https?://\S+$", tl):
            return True
    elif mode == "general":
        if re.search(r"(?i)^https?://\S+$", tl) and len(tl) > 30:
            return True
    return False

"""过滤行数据"""
def filter_lines(
    lines: List[Dict[str, Any]],
    min_score: float = 0.35,
    min_text_len: int = 1,
    mode: str = "general",
) -> List[Dict[str, Any]]:
    noise_single = {",", ".", ";", ":", "'", '"', "|", "\\", "/", "·", "•", "-", "—"}
    out = []
    for x in lines:
        t = _safe_text(x.get("text"))
        if not t:
            continue
        if mode == "general":
            if not is_meaningful_token(t) and len(t) < min_text_len:
                continue
        elif len(t) < min_text_len:
            continue
        if float(x.get("score", 0.0)) < min_score:
            continue
        if len(t) == 1 and t in noise_single and not is_meaningful_token(t):
            continue
        if _is_line_pure_page_number_text(t):
            continue
        if _filter_line_drop_for_mode(t, mode):
            continue
        out.append(x)
    return out

#转文本
def lines_to_text(lines: List[Dict[str, Any]]) -> str:
    if not lines:
        return ""

    output = []
    prev = None

    for line in lines:
        text = _safe_text(line.get("text"))
        if not text:
            continue

        if prev is None:
            output.append(text)
            prev = line
            continue

        vertical_gap = float(line["top"]) - float(prev["bottom"])
        same_row = abs(float(line["center_y"]) - float(prev["center_y"])) <= max(
            float(prev["height"]), float(line["height"])
        ) * 0.6

        #水平相近的合并为一行
        if same_row:
            output[-1] = output[-1] + " " + text
        #大间隔换行
        elif vertical_gap > max(float(prev["height"]), float(line["height"])) * 1.2:
            output.append("\n" + text)
        else:
            output.append(text)

        prev = line

    return "\n".join(output).replace("\n\n\n", "\n\n").strip()


def build_raw_ocr_text(raw_lines: List[Dict[str, Any]]) -> str:
    """OCR 引擎返回顺序下的原始行拼接（未做双栏重排）。"""
    parts = []
    for item in raw_lines or []:
        t = _safe_text(item.get("text"))
        if t:
            parts.append(t)
    return "\n".join(parts)


def display_clean_minimal_general(s: str) -> str:
    """general 展示：仅空白归一化，不删单字、不删短行、不删框符。"""
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s.strip()


def build_display_from_preclean(preclean: str, clean_mode: str) -> str:
    """已拼好的 preclean 串 -> 展示文本（避免重复 lines_to_text）。"""
    if clean_mode == "general":
        return display_clean_minimal_general(preclean)
    return clean_page_text(preclean, clean_mode)


def build_display_text(ordered_lines: List[Dict[str, Any]], clean_mode: str) -> str:
    """
    重排+过滤后的行 -> 展示向文本。
    general：轻量保留结构；paper/notice：沿用 clean_page_text。
    """
    return build_display_from_preclean(lines_to_text(ordered_lines), clean_mode)


#构建 RAG 文本
def build_rag_text_from_lines(ordered_lines: List[Dict[str, Any]], clean_mode: str) -> str:
    """与 build_rag_text(preclean) 等价，入参为重排后的行列表。"""
    preclean = lines_to_text(ordered_lines)
    return build_rag_text(preclean, clean_mode)


#检测纯符号短行
def _is_pure_symbol_short_line(line: str, max_len: int = 12) -> bool:
    s = line.strip()
    if not s or len(s) > max_len:
        return False
    if re.search(r"[\u4e00-\u9fff]", s):
        return False
    if re.search(r"[0-9A-Za-z]", s):
        return False
    return True

#合并英文连字符断行并
def _merge_english_hyphen_linebreaks(text: str) -> str:
    return re.sub(r"([a-zA-Z])-\s*\n\s*([a-zA-Z])", r"\1\2", text)


def _space_cjk_and_latin(text: str) -> str:
    text = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", text)
    lines = text.split("\n")
    out = []
    for ln in lines:
        ln = re.sub(r" +", " ", ln.strip())
        out.append(ln)
    return "\n".join(out)


def _ensure_heading_blank_lines(text: str) -> str:
    # 章节/小节标题前保留空行，便于分段与展示
    text = re.sub(
        r"([^\n])\n(第[0-9一二三四五六七八九十百零两]+[章节编]\s)",
        r"\1\n\n\2",
        text,
    )
    text = re.sub(
        r"([^\n])\n((?:\d+|[一二三四五六七八九十]+)[、.．]\s*[\u4e00-\u9fa5])",
        r"\1\n\n\2",
        text,
    )
    return text


#根据不同模式进行清洗
def clean_page_text(s: str, mode: str = "general") -> str:
    """
    展示向清洗：按文档模式保留/删除不同内容。
    paper：期刊/论文噪声较强；notice：保留标题、单位、文号、日期等；
    general：请优先用 display_clean_minimal_general（此处兼容旧调用，与之一致）。
    """
    if not s:
        return ""

    if mode == "general":
        return display_clean_minimal_general(s)

    s = s.strip()
    s = re.sub(r"(?m)^\s*[-·]?\s*\d+\s*[-·]?\s*$", "", s)

    if mode == "paper":
        s = re.sub(
            "(?im)^.*(cnki|doi|http|www\\.|\u8ba1\u7b97\u673a\u65f6\u4ee3|computer era|journal of|\u73b0\u4ee3\u60c5\u62a5|\u6536\u7a3f\u65e5\u671f|\u4fee\u56de\u65e5\u671f|\u57fa\u91d1\u9879\u76ee|\u4f5c\u8005\u7b80\u4ecb|copyright).*$",
            "",
            s,
        )
        s = re.sub(
            "(?im)^.*(\u7b2c\\s*\\d+\\s*\u5377|\u7b2c\\s*\\d+\\s*\u671f|vol\\.\\s*\\d+|no\\.\\s*\\d+|mar\\.,\\s*\\d{4}).*$",
            "",
            s,
        )
        s = re.sub("(?im)^\\s*(\u56fe|\u8868|Fig\\.|FIG\\.)\\s*\\d+.*$", "", s)
        s = re.sub(r"(?im)^\s*[A-Z][A-Za-z0-9 ./-]{0,30}\s*$", "", s)
    elif mode == "notice":
        s = re.sub(r"(?im)^https?://\S+$", "", s)

    kept = []
    for line in s.split("\n"):
        if _is_pure_symbol_short_line(line):
            continue
        if not line.strip():
            kept.append("")
            continue
        kept.append(line.rstrip())

    s = "\n".join(kept)
    s = re.sub(r"\n{3,}", "\n\n", s)

    s = _merge_english_hyphen_linebreaks(s)
    s = _ensure_heading_blank_lines(s)
    s = _space_cjk_and_latin(s)

    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s.strip()


# 论文页中示意图里常见短标签（入库 RAG 时可弱化，不误伤长句）
_RAG_DIAGRAM_CN_FRAGMENTS = frozenset({
    "移动客户端", "Web浏览器环境", "Web浏览器", "浏览器环境", "数据库1", "数据库2",
    "问题分析", "问题转换", "输出SQL语句", "输出 SQL 语句",
})

# 仅字母数字与少量符号的极短行，多为图注/轴标签
_RAG_SHORT_EN_TOKEN = re.compile(
    r"^\s*[A-Za-z0-9./\-–—]{1,24}\s*$"
)


def _strip_rag_diagram_lines(t: str, mode: str) -> str:
    if not t:
        return ""
    aggressive = mode == "paper"
    out_lines = []
    for line in t.split("\n"):
        s = line.strip()
        if not s:
            out_lines.append("")
            continue
        if re.search(r"(?i)(参考文献|references|引用文献)\s*$", s):
            out_lines.append(line.rstrip())
            continue
        if re.match(r"^\s*\[\d+\]", s) or re.match(r"^\s*\d+[\.\s]+\[?\d+\]?", s):
            out_lines.append(line.rstrip())
            continue
        if s in _RAG_DIAGRAM_CN_FRAGMENTS:
            continue
        if aggressive and len(s) <= 24 and _RAG_SHORT_EN_TOKEN.match(s):
            if re.fullmatch(r"(?i)(json|tcp/ip|tcp|ip|http|https|xml|html|sql|api|web|mysql|oracle|json)", s):
                continue
            if "/" in s and len(s) <= 16 and not re.search(r"[\u4e00-\u9fff]", s):
                continue
        if aggressive and len(s) <= 18 and not re.search(r"[\u4e00-\u9fff]", s):
            if re.search(r"^[A-Za-z./\-]+$", s) and len(s) <= 18:
                continue
        out_lines.append(line.rstrip())
    return "\n".join(out_lines)


def _rag_strip_journal_lines_for_general(t: str) -> str:
    """general 展示保留期刊信息，RAG 入库时可再压一层（与 paper 展示级接近）。"""
    t = re.sub(
        r"(?im)^.*(cnki|doi\s*:|http|www\.|计算机时代|computer era|"
        r"收稿日期|修回日期|基金项目|作者简介|版权声明|copyright).*$",
        "",
        t,
    )
    return t


def build_rag_text(s: str, mode: str = "general") -> str:
    """
    向量/问答用文本：在展示清洗基础上再压一层噪声（同一 preclean 输入）。
    paper：与 display 拉开差距（图注短行、分类号等）；general：RAG 额外去期刊/DOI 行。
    """
    if not s:
        return ""
    t = clean_page_text(s, mode)
    if mode == "general":
        t = _rag_strip_journal_lines_for_general(t)
    if mode == "paper":
        t = re.sub(
            r"(?im)^.*(中图分类号|文献标志码|文章编号|图表索引).*$",
            "",
            t,
        )
        t = re.sub(r"(?im)^\s*(图|表|Fig\.|FIG\.)\s*\d+[^。]*$", "", t)
    t = _strip_rag_diagram_lines(t, mode)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    return t.strip()


#双侧检测公开接口
def detect_two_column_page(raw_lines: List[Dict[str, Any]]) -> bool:
    lines = _normalize_lines(raw_lines)
    if not lines:
        return False
    metrics = _estimate_page_metrics(lines)
    return _detect_two_columns(lines, metrics)
