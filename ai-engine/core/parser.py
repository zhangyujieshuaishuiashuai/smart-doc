import fitz  # PyMuPDF
import camelot
import pdfplumber
from paddleocr import PaddleOCR
import logging
import os
import tempfile

# 抑制 PaddleOCR 的繁杂日志
logging.getLogger("ppocr").setLevel(logging.ERROR)

class DocParser:
    def __init__(self):
        print(">>> [Parser] 初始化 OCR 引擎 (高精度模式)...")
        # 在这里开启方向分类器 (use_angle_cls=True)
        # 注意：不要加 show_log 参数
        self.ocr = PaddleOCR(use_angle_cls=True, lang="ch")

    def ocr_image(self, image_path):
        ocr_result = self.ocr.ocr(image_path)
        if not ocr_result or not ocr_result[0]:
            return ""
        return "\n".join([line[1][0] for line in ocr_result[0] if line[1][1] > 0.6])

    def extract_tables(self, file_path):
        print(f">>> [Parser] 正在提取表格结构: {file_path}")
        table_entries = []
        try:
            tables = camelot.read_pdf(file_path, pages='all', flavor='lattice', line_scale=40)
            for table_id, table in enumerate(tables):
                table_entries.append({
                    "table_id": table_id,
                    "page_no": table.page,
                    "table_markdown": table.df.to_markdown(index=False),
                    "table_json": {
                        "columns": list(table.df.columns),
                        "rows": table.df.to_dict(orient="records"),
                    }
                })
            print(f">>> [Parser] 共提取到 {len(table_entries)} 个结构化表格")
        except Exception as e:
            print(f"⚠️ 表格提取部分失败: {e}")
        return table_entries

    def parse_pdf(self, file_path):
        """
        高精度解析：300DPI截图 + 表格容错 + 结构化清洗
        """
        full_content = []
        pages = []
        os.makedirs("temp_uploads", exist_ok=True)
        table_entries = self.extract_tables(file_path)
        table_map = {}
        for table in table_entries:
            table_map.setdefault(table["page_no"], []).append(table)

        text_layers = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text_layers.append(page.extract_text() or "")
        except Exception as e:
            print(f"⚠️ PDF 文本层提取失败: {e}")

        # --- 2. 视觉 OCR 阶段 (PyMuPDF + PaddleOCR) ---
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            print(f">>> [Parser] 开始逐页高精度 OCR (共 {total_pages} 页)...")
            
            for i, page in enumerate(doc):
                page_no = i + 1
                print(f"    -> 正在处理第 {i+1}/{total_pages} 页...")
                try:
                    # 3倍分辨率 (300 DPI)
                    zoom_matrix = fitz.Matrix(3, 3) 
                    pix = page.get_pixmap(matrix=zoom_matrix)

                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir="temp_uploads") as tmp:
                        img_name = tmp.name
                    pix.save(img_name)

                    page_pure_text = self.ocr_image(img_name)

                    if os.path.exists(img_name):
                        os.remove(img_name)

                    # 数据组装
                    page_content = f"\n\n--- 第 {i+1} 页数据开始 ---\n"

                    text_layer = text_layers[i] if i < len(text_layers) else ""
                    if text_layer:
                        page_content += f"\n【文本层】:\n{text_layer}\n"

                    if page_no in table_map:
                        page_content += "\n【检测到本页包含统计表，已结构化还原】:\n"
                        for table in table_map[page_no]:
                            page_content += f"\n{table['table_markdown']}\n"

                    if page_pure_text:
                        page_content += f"\n[本页OCR原始文本补充]:\n{page_pure_text}\n"

                    page_content += f"\n--- 第 {i+1} 页数据结束 ---\n"
                    full_content.append(page_content)
                    pages.append({
                        "page_no": page_no,
                        "ocr_text": page_pure_text,
                        "text_layer": text_layer
                    })

                except Exception as inner_e:
                    print(f"❌ 第 {i+1} 页解析出错: {inner_e}")
                    # 打印具体错误以便调试
                    continue 

            doc.close()
            return {
                "text": "\n".join(full_content),
                "pages": pages,
                "tables": table_entries
            }
            
        except Exception as e:
            print(f"❌ PDF 文件打开失败: {e}")
            return {
                "text": "",
                "pages": [],
                "tables": []
            }

if __name__ == "__main__":
    parser = DocParser()
    print("模型加载完毕，等待调用...")
