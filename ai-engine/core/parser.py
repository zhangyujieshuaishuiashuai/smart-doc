import fitz  # PyMuPDF
import camelot
from paddleocr import PaddleOCR
import os
import logging
import traceback

# 抑制 PaddleOCR 的繁杂日志
logging.getLogger("ppocr").setLevel(logging.ERROR)

class DocParser:
    def __init__(self):
        print(">>> [Parser] 初始化 OCR 引擎 (高精度模式)...")
        # 在这里开启方向分类器 (use_angle_cls=True)
        # 注意：不要加 show_log 参数
        self.ocr = PaddleOCR(use_angle_cls=True, lang="ch")

    def parse_pdf(self, file_path):
        """
        高精度解析：300DPI截图 + 表格容错 + 结构化清洗
        """
        full_content = []
        
        # --- 1. 表格解析阶段 (Camelot) ---
        print(f">>> [Parser] 正在提取表格结构: {file_path}")
        table_map = {}
        try:
            # 提取表格，line_scale 调大有助于识别线条
            tables = camelot.read_pdf(file_path, pages='all', flavor='lattice', line_scale=40)
            
            for table in tables:
                page_idx = table.page - 1
                if page_idx not in table_map:
                    table_map[page_idx] = []
                
                # 转为 Markdown
                md_text = table.df.to_markdown(index=False)
                table_map[page_idx].append(md_text)
                
            print(f">>> [Parser] 共提取到 {len(tables)} 个结构化表格")
        except Exception as e:
            print(f"⚠️ 表格提取部分失败: {e}")

        # --- 2. 视觉 OCR 阶段 (PyMuPDF + PaddleOCR) ---
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            print(f">>> [Parser] 开始逐页高精度 OCR (共 {total_pages} 页)...")
            
            for i, page in enumerate(doc):
                print(f"    -> 正在处理第 {i+1}/{total_pages} 页...")
                try:
                    # 3倍分辨率 (300 DPI)
                    zoom_matrix = fitz.Matrix(3, 3) 
                    pix = page.get_pixmap(matrix=zoom_matrix)
                    
                    img_name = f"temp_page_{i}.png"
                    pix.save(img_name)
                    
                    # ✅【关键修复】这里去掉了 cls=True，只传图片路径
                    ocr_result = self.ocr.ocr(img_name)
                    
                    # 提取纯文本
                    page_pure_text = ""
                    if ocr_result and ocr_result[0]:
                        # 过滤低置信度字符
                        page_pure_text = "\n".join([line[1][0] for line in ocr_result[0] if line[1][1] > 0.6])
                    
                    # 清理临时图片
                    if os.path.exists(img_name):
                        os.remove(img_name)

                    # 数据组装
                    page_content = f"\n\n--- 第 {i+1} 页数据开始 ---\n"
                    
                    if i in table_map:
                        page_content += "\n【检测到本页包含统计表，已结构化还原】:\n"
                        for tbl_md in table_map[i]:
                            page_content += f"\n{tbl_md}\n"
                        
                        page_content +=f"\n[本页OCR原始文本补充]:\n{page_pure_text}\n"
                    else:
                        page_content += page_pure_text

                    page_content += f"\n--- 第 {i+1} 页数据结束 ---\n"
                    full_content.append(page_content)

                except Exception as inner_e:
                    print(f"❌ 第 {i+1} 页解析出错: {inner_e}")
                    # 打印具体错误以便调试
                    # traceback.print_exc() 
                    continue 

            doc.close()
            return "\n".join(full_content)
            
        except Exception as e:
            print(f"❌ PDF 文件打开失败: {e}")
            return ""

if __name__ == "__main__":
    parser = DocParser()
    print("模型加载完毕，等待调用...")