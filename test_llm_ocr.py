# test_llm_ocr.py
# 測試用 LLM vision 辨識表單欄位座標

import os
import json
from pdf_to_image import pdf_to_images
from llm_ocr import detect_form_fields
from visualize_llm import draw_llm_results


def test_pdf(pdf_path: str):
    print(f"\n處理：{pdf_path}")
    print("=" * 50)

    print("Step 1：PDF 轉圖片...")
    images = pdf_to_images(pdf_path, dpi=300)
    print(f"共 {len(images)} 頁")

    all_fields = []

    for img_info in images:
        page = img_info["page"]
        print(f"\n--- 第 {page} 頁 ({img_info['width']}x{img_info['height']}) ---")

        print("Step 2：LLM vision 辨識欄位...")
        fields = detect_form_fields(img_info)
        all_fields.extend(fields)

        print(f"找到 {len(fields)} 個欄位：")
        for f in fields:
            print(f"  {f['field_key']:35s} | {f['label_text']}")
            print(f"    標籤: {f['label_bbox']}")
            print(f"    填寫: {f['fill_bbox']}")

        # 視覺化
        form_name = os.path.basename(pdf_path).replace(".pdf", "")
        output_path = f"llm_output_{form_name}_page{page}.png"
        draw_llm_results(img_info, fields, output_path)

    # 儲存 JSON
    form_name = os.path.basename(pdf_path).replace(".pdf", "")
    output_json = f"llm_result_{form_name}.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_fields, f, ensure_ascii=False, indent=2)
    print(f"\n結果儲存至：{output_json}")

    return all_fields


if __name__ == "__main__":
    pdf_dir = os.path.join(os.path.dirname(__file__), "pdfs")
    test_pdf(os.path.join(pdf_dir, "1.授信申請書.pdf"))
    test_pdf(os.path.join(pdf_dir, "2.個人資料表-徵信報告書(印刷版).pdf"))
