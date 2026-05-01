import uuid
from pathlib import Path
from typing import Any, List, Optional


def gen_doc_id() -> str:
    return uuid.uuid4().hex


def save_upload_file(upload_file: Any, save_dir: Path) -> Path:
    ext = Path(upload_file.filename).suffix.lower()
    #UUID 十六进制字符串 + 原始扩展名
    file_name = f"{uuid.uuid4().hex}{ext}"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / file_name

    content = upload_file.file.read()
    if not content:
        raise ValueError("Uploaded file is empty")

    #以二进制写入模式打开文件，并将上传文件的内容写入磁盘
    with open(save_path, "wb") as f:
        f.write(content)
    return save_path


#pdf转图片
def pdf_to_images(pdf_path: Path, output_dir: Path, dpi: Optional[int] = None) -> List[Path]:
    from pdf2image import convert_from_path

    output_dir.mkdir(parents=True, exist_ok=True)
    render_dpi = dpi if dpi is not None else 200
    pages = convert_from_path(str(pdf_path), dpi=render_dpi)
    image_paths = []
    for idx, page in enumerate(pages, start=1):
        img_path = output_dir / f"page_{idx}.png"
        page.save(img_path, "PNG")
        image_paths.append(img_path)
    return image_paths


def split_text(text: str, chunk_size: int = 300, overlap: int = 50) -> List[str]:
    """Split long text with overlap, preferring paragraph and sentence boundaries."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be greater than or equal to 0 and less than chunk_size")

    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= chunk_size:
        return [t]

    chunks: List[str] = []
    start = 0
    while start < len(t):
        end = min(len(t), start + chunk_size)
        chunk = t[start:end]
        if end < len(t):
            # 尽量在段落或句末截断，避免把中文句子切碎。
            cut = max(
                chunk.rfind("\n\n"),
                chunk.rfind("。"),
                chunk.rfind("！"),
                chunk.rfind("？"),
            )
            if cut > chunk_size // 3:
                chunk = chunk[: cut + 1]

        cleaned = chunk.strip()
        if cleaned:
            chunks.append(cleaned)
        if end >= len(t):
            break

        next_start = start + len(chunk) - overlap
        if next_start <= start:
            next_start = end - overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start
    return chunks
