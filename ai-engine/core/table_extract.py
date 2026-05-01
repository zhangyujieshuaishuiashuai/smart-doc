"""
Table extraction helpers.

The primary path uses pdfplumber on real PDF text/table geometry.  When that
cannot find a table, OCR layout fallback infers conservative row/column tables
from PaddleOCR line boxes.  All extractors return the same dict shape:
id, page, title, markdown, html, rows.
"""
from __future__ import annotations

from hashlib import md5
from html import escape
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional
import re


def _rows_to_markdown(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:] if len(rows) > 1 else []

    def esc(c: str) -> str:
        return (c or "").replace("|", "\\|").replace("\n", " ").strip()

    lines = ["| " + " | ".join(esc(c) for c in header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in body:
        padded = list(row) + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(esc(c) for c in padded[: len(header)]) + " |")
    return "\n".join(lines)


def _rows_to_html(rows: List[List[str]]) -> str:
    if not rows:
        return "<table></table>"
    parts = ["<table>"]
    for i, row in enumerate(rows):
        tag = "th" if i == 0 else "td"
        parts.append("<tr>")
        for cell in row:
            parts.append(f"<{tag}>{escape(str(cell or ''))}</{tag}>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def _normalize_rows(table: Iterable[Iterable[Any]]) -> List[List[str]]:
    rows = [[("" if c is None else str(c)).strip() for c in row] for row in table if row is not None]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return []

    max_cols = max(len(row) for row in rows)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]
    keep_cols = [
        col
        for col in range(max_cols)
        if any(row[col].strip() for row in rows)
    ]
    if not keep_cols:
        return []
    return [[row[col] for col in keep_cols] for row in rows]


def _is_probable_table(rows: List[List[str]]) -> bool:
    rows = _normalize_rows(rows)
    if len(rows) < 2:
        return False
    cols = max(len(r) for r in rows)
    if cols < 2:
        return False

    non_empty_rows = [r for r in rows if sum(1 for c in r if c.strip()) >= 2]
    if len(non_empty_rows) < 2:
        return False

    non_empty_counts = [sum(1 for c in r if c.strip()) for r in non_empty_rows]
    all_cells = [c.strip() for r in non_empty_rows for c in r if c.strip()]
    if not all_cells:
        return False

    total_cell_chars = [len(c) for c in all_cells]
    avg_cell_chars = sum(total_cell_chars) / len(total_cell_chars)
    short_cell_ratio = sum(1 for n in total_cell_chars if n <= 32) / len(total_cell_chars)
    long_cell_ratio = sum(1 for n in total_cell_chars if n >= 56) / len(total_cell_chars)
    numeric_ratio = sum(1 for c in all_cells if re.search(r"\d", c)) / len(all_cells)
    prose_ratio = sum(1 for c in all_cells if _looks_like_prose_cell(c)) / len(all_cells)
    density = sum(non_empty_counts) / (len(non_empty_rows) * cols)

    if cols >= 3:
        rows_with_three_cells = sum(1 for n in non_empty_counts if n >= 3)
        if len(non_empty_rows) < 3:
            return False
        if rows_with_three_cells < max(2, int(len(non_empty_rows) * 0.35)):
            return False
        if density < 0.55:
            return False
        if short_cell_ratio < 0.45 and numeric_ratio < 0.18:
            return False
        if long_cell_ratio > 0.45 and numeric_ratio < 0.18:
            return False
        if prose_ratio > 0.45 and numeric_ratio < 0.18:
            return False
        if avg_cell_chars > 70 and numeric_ratio < 0.20:
            return False
        return len(non_empty_rows) >= 2

    # Two-column tables are easy to confuse with two-column papers.  Accept only
    # key-value-like rows where the first column is usually short.
    first_col_short = 0
    total_chars = []
    for row in non_empty_rows:
        first = row[0].strip()
        total_chars.append(sum(len(c.strip()) for c in row))
        if len(first) <= 28 or first.endswith((":", "：")):
            first_col_short += 1

    short_ratio = first_col_short / max(len(non_empty_rows), 1)
    avg_chars = sum(total_chars) / max(len(total_chars), 1)
    return (
        len(non_empty_rows) >= 3
        and density >= 0.65
        and short_ratio >= 0.6
        and avg_chars <= 130
        and (long_cell_ratio <= 0.35 or numeric_ratio >= 0.15)
        and prose_ratio <= 0.50
    )


def _looks_like_prose_cell(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 36:
        return False
    if re.search(r"[。；，、.!?;,:]\s*", s):
        return True
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", s))
    return chinese_chars >= 24


def _table_key(page_no: int, rows: List[List[str]]) -> str:
    text = "\n".join("\t".join(c.strip() for c in row) for row in rows)
    return f"{page_no}:{md5(text.encode('utf-8', errors='ignore')).hexdigest()}"


def _make_table(page_no: int, seq: int, rows: List[List[str]], source: str) -> Dict[str, Any]:
    return {
        "id": f"{source}-table-{page_no}-{seq}",
        "page": page_no,
        "title": None,
        "markdown": _rows_to_markdown(rows),
        "html": _rows_to_html(rows),
        "rows": rows,
        "source": source,
    }


PDFPLUMBER_TABLE_SETTINGS: List[Optional[Dict[str, Any]]] = [
    None,
    {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "intersection_tolerance": 5,
    },
    {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "min_words_vertical": 2,
        "min_words_horizontal": 1,
        "text_tolerance": 3,
    },
    {
        "vertical_strategy": "lines",
        "horizontal_strategy": "text",
        "min_words_horizontal": 1,
        "text_tolerance": 3,
    },
    {
        "vertical_strategy": "text",
        "horizontal_strategy": "lines",
        "min_words_vertical": 2,
        "text_tolerance": 3,
    },
]


def _requires_caption(settings: Optional[Dict[str, Any]]) -> bool:
    if not settings:
        return False
    return (
        settings.get("vertical_strategy") == "text"
        and settings.get("horizontal_strategy") == "text"
    )


def _has_nearby_table_caption(page: Any, bbox: Optional[Iterable[float]]) -> bool:
    if not bbox:
        return False
    try:
        _x0, top, _x1, bottom = [float(v) for v in bbox]
        width = float(getattr(page, "width", 0) or 0)
        height = float(getattr(page, "height", 0) or 0)
        if width <= 0 or height <= 0:
            return False
        above = page.within_bbox((0, max(0, top - 90), width, min(height, top + 18))).extract_text() or ""
        below = page.within_bbox((0, max(0, bottom - 8), width, min(height, bottom + 55))).extract_text() or ""
    except Exception:
        return False
    text = f"{above}\n{below}"
    return bool(re.search(r"(?im)^\s*(表|table)\s*[\d一二三四五六七八九十]+", text))


def _find_pdf_tables(page: Any, settings: Optional[Dict[str, Any]]) -> List[tuple[List[List[Any]], Optional[Iterable[float]]]]:
    try:
        table_objects = page.find_tables(table_settings=settings) if settings else page.find_tables()
    except Exception:
        table_objects = []

    found: List[tuple[List[List[Any]], Optional[Iterable[float]]]] = []
    for table_obj in table_objects or []:
        try:
            rows = table_obj.extract()
        except Exception:
            continue
        found.append((rows or [], getattr(table_obj, "bbox", None)))
    return found


def extract_tables_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """Extract text-layer PDF tables using several pdfplumber strategies."""
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    try:
        import pdfplumber
    except ImportError:
        return out

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                page_seq = 1
                for settings in PDFPLUMBER_TABLE_SETTINGS:
                    needs_caption = _requires_caption(settings)
                    for table, bbox in _find_pdf_tables(page, settings):
                        if needs_caption and not _has_nearby_table_caption(page, bbox):
                            continue
                        rows = _normalize_rows(table)
                        if not _is_probable_table(rows):
                            continue
                        key = _table_key(page_idx, rows)
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append(_make_table(page_idx, page_seq, rows, "pdf"))
                        page_seq += 1
    except Exception:
        return out
    return out


def _line_value(line: Any, name: str, default: Any = None) -> Any:
    if isinstance(line, dict):
        return line.get(name, default)
    return getattr(line, name, default)


def _line_geom(line: Any) -> Optional[Dict[str, Any]]:
    text = str(_line_value(line, "text", "") or "").strip()
    bbox = _line_value(line, "bbox", None)
    if not text or not bbox or len(bbox) < 4:
        return None
    try:
        xs = [float(p[0]) for p in bbox]
        ys = [float(p[1]) for p in bbox]
    except Exception:
        return None
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 <= x0 or y1 <= y0:
        return None
    return {
        "text": text,
        "x0": x0,
        "x1": x1,
        "y0": y0,
        "y1": y1,
        "cx": (x0 + x1) / 2,
        "cy": (y0 + y1) / 2,
        "h": y1 - y0,
    }


def _cluster_rows(lines: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    if not lines:
        return []
    heights = [ln["h"] for ln in lines if ln["h"] > 0]
    row_tol = max(8.0, min(24.0, (median(heights) if heights else 14.0) * 0.75))
    rows: List[List[Dict[str, Any]]] = []
    row_centers: List[float] = []

    for line in sorted(lines, key=lambda x: (x["cy"], x["x0"])):
        best_idx = None
        best_dist = None
        for idx, center in enumerate(row_centers):
            dist = abs(line["cy"] - center)
            if dist <= row_tol and (best_dist is None or dist < best_dist):
                best_idx = idx
                best_dist = dist
        if best_idx is None:
            rows.append([line])
            row_centers.append(line["cy"])
        else:
            rows[best_idx].append(line)
            row_centers[best_idx] = sum(ln["cy"] for ln in rows[best_idx]) / len(rows[best_idx])

    for row in rows:
        row.sort(key=lambda x: x["x0"])
    return rows


def _cluster_columns(rows: List[List[Dict[str, Any]]]) -> List[float]:
    xs = [cell["x0"] for row in rows if len(row) >= 2 for cell in row]
    if not xs:
        return []
    page_width = max(xs) - min(xs)
    col_tol = max(28.0, min(60.0, page_width * 0.05))
    anchors: List[float] = []
    counts: List[int] = []
    for x in sorted(xs):
        best_idx = None
        best_dist = None
        for idx, anchor in enumerate(anchors):
            dist = abs(x - anchor)
            if dist <= col_tol and (best_dist is None or dist < best_dist):
                best_idx = idx
                best_dist = dist
        if best_idx is None:
            anchors.append(x)
            counts.append(1)
        else:
            n = counts[best_idx]
            anchors[best_idx] = (anchors[best_idx] * n + x) / (n + 1)
            counts[best_idx] = n + 1
    return [x for _, x in sorted(zip(counts, anchors), reverse=True)][:8]


def _cells_for_row(row: List[Dict[str, Any]], anchors: List[float]) -> List[str]:
    cells = [""] * len(anchors)
    for cell in row:
        distances = [abs(cell["x0"] - anchor) for anchor in anchors]
        idx = distances.index(min(distances))
        cells[idx] = (cells[idx] + " " + cell["text"]).strip() if cells[idx] else cell["text"]
    return cells


def _split_table_blocks(rows: List[List[Dict[str, Any]]]) -> List[List[List[Dict[str, Any]]]]:
    candidate_rows = [row for row in rows if len(row) >= 2]
    if not candidate_rows:
        return []
    ys = [sum(cell["cy"] for cell in row) / len(row) for row in candidate_rows]
    gaps = [ys[i] - ys[i - 1] for i in range(1, len(ys)) if ys[i] > ys[i - 1]]
    normal_gap = median(gaps) if gaps else 30.0
    max_gap = max(45.0, min(100.0, normal_gap * 2.6))

    blocks: List[List[List[Dict[str, Any]]]] = []
    current: List[List[Dict[str, Any]]] = []
    last_y: Optional[float] = None
    for row, y in zip(candidate_rows, ys):
        if last_y is not None and y - last_y > max_gap:
            if current:
                blocks.append(current)
            current = []
        current.append(row)
        last_y = y
    if current:
        blocks.append(current)
    return blocks


def infer_tables_from_ocr_lines(page_no: int, lines: List[Any]) -> List[Dict[str, Any]]:
    """Infer conservative tables from OCR line bounding boxes."""
    geoms = [g for g in (_line_geom(line) for line in lines) if g is not None]
    if len(geoms) < 6:
        return []

    clustered_rows = _cluster_rows(geoms)
    tables: List[Dict[str, Any]] = []
    seq = 1
    for block in _split_table_blocks(clustered_rows):
        if len(block) < 3:
            continue
        anchors = sorted(_cluster_columns(block))
        if len(anchors) < 2:
            continue
        row_values = _normalize_rows(_cells_for_row(row, anchors) for row in block)
        if not _is_probable_table(row_values):
            continue
        tables.append(_make_table(page_no, seq, row_values, "ocr"))
        seq += 1
    return tables


def infer_tables_from_ocr_pages(pages: List[Any]) -> List[Dict[str, Any]]:
    tables: List[Dict[str, Any]] = []
    for page in pages:
        page_no = int(_line_value(page, "page_no", _line_value(page, "page", 0)) or 0)
        lines = _line_value(page, "lines", []) or []
        tables.extend(infer_tables_from_ocr_lines(page_no, lines))
    return tables


def merge_tables(*table_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for group in table_groups:
        for table in group or []:
            rows = _normalize_rows(table.get("rows") or [])
            if not rows:
                continue
            key = _table_key(int(table.get("page") or 0), rows)
            if key in seen:
                continue
            seen.add(key)
            if table.get("rows") is not rows:
                table = dict(table)
                table["rows"] = rows
                table["markdown"] = table.get("markdown") or _rows_to_markdown(rows)
                table["html"] = table.get("html") or _rows_to_html(rows)
            out.append(table)
    return out


def tables_for_page(all_tables: List[Dict[str, Any]], page_no: int) -> List[Dict[str, Any]]:
    return [t for t in all_tables if int(t.get("page", 0)) == page_no]
