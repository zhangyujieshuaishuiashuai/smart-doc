from paddleocr import PaddleOCR
import logging

# 关闭繁杂的调试日志
logging.getLogger("ppocr").setLevel(logging.WARNING)

print("正在初始化 OCR 模型...")

# 1. 初始化
# 修正：彻底删除了 use_gpu 参数，让它自动处理
# 修正：改回了最通用的 use_angle_cls=True，防止新参数又不兼容
ocr = PaddleOCR(use_angle_cls=True, lang="ch") 

# 2. 图片路径
img_path = 'https://paddleocr.bj.bcebos.com/dygraph_v2.1/ppocr_system/ppocr_img/imgs/11.jpg'

print("开始下载图片并识别（第一次运行会自动下载模型，需稍等）...")

try:
    # 3. 识别
    result = ocr.ocr(img_path)
    print("\n" + "="*20 + " 识别成功 " + "="*20)
    for idx in range(len(result)):
        res = result[idx]
        for line in res:
            # line[1][0] 是文字，line[1][1] 是置信度
            print(f"文字: {line[1][0]}")

except Exception as e:
    print(f"发生错误: {e}")