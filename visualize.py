# visualize.py
from PIL import Image, ImageDraw, ImageFont
import json

def draw_ocr_results(image_info: dict, blocks: list, output_path: str):
    """
    把 OCR 結果畫在圖片上，方便人工驗證
    綠色框：高信心度（>70）
    黃色框：中信心度（30-70）
    """
    img = image_info["image"].copy()
    draw = ImageDraw.Draw(img)
    
    for block in blocks:
        bbox = block["bbox"]
        conf = block["confidence"]
        
        # 根據信心度決定顏色
        color = "green" if conf > 70 else "yellow"
        
        # 畫邊框
        draw.rectangle(
            [bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]],
            outline=color,
            width=2
        )
        
        # 標註文字和信心度
        draw.text(
            (bbox["x1"], bbox["y1"] - 15),
            f"{block['text']}({conf}%)",
            fill=color
        )
    
    img.save(output_path)
    print(f"視覺化結果儲存至：{output_path}")