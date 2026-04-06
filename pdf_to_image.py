# pdf_to_image.py
import fitz  # PyMuPDF
from pathlib import Path

def pdf_to_images(pdf_path: str, dpi: int = 300) -> list:
    """
    把 PDF 每頁轉成圖片
    回傳：每頁的 PIL Image 物件清單
    """
    doc = fitz.open(pdf_path)
    images = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # 根據 DPI 計算縮放比例（PDF 預設 72 DPI）
        scale = dpi / 72
        matrix = fitz.Matrix(scale, scale)
        
        # 轉成像素圖
        pixmap = page.get_pixmap(matrix=matrix)
        
        # 轉成 PIL Image
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(pixmap.tobytes("png")))
        images.append({
            "page": page_num + 1,
            "image": img,
            "width": img.width,
            "height": img.height,
            "dpi": dpi
        })
    
    doc.close()
    return images