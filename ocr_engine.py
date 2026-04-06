# ocr_engine.py
import easyocr

# 初始化一次就好，不要每次呼叫都重新初始化（很慢）
reader = easyocr.Reader(['ch_tra', 'en'], gpu=True)

def run_ocr(image_info: dict) -> list:
    import numpy as np
    img = image_info["image"]
    page = image_info["page"]
    
    # PIL Image 轉 numpy array
    img_array = np.array(img)
    
    # 跑 OCR，detail=1 回傳座標
    results = reader.readtext(img_array, detail=1)
    
    blocks = []
    for (bbox_points, text, confidence) in results:
        text = text.strip()
        if text == "" or confidence < 0.3:
            continue
        
        # EasyOCR 回傳四個角點，取左上和右下
        x_coords = [p[0] for p in bbox_points]
        y_coords = [p[1] for p in bbox_points]
        
        blocks.append({
            "page": page,
            "text": text,
            "confidence": round(confidence * 100, 1),
            "bbox": {
                "x1": int(min(x_coords)),
                "y1": int(min(y_coords)),
                "x2": int(max(x_coords)),
                "y2": int(max(y_coords))
            }
        })
    
    return blocks