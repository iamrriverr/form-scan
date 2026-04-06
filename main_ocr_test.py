# main_ocr_test.py
import os
import json
import pandas as pd
from pdf_to_image import pdf_to_images
from ocr_engine import run_ocr
from visualize import draw_ocr_results
from rule_engine import process_form
from llm_filter import filter_fields_with_llm, print_filter_comparison


def test_pdf(pdf_path: str):
    print(f"\n處理：{pdf_path}")
    print("=" * 50)
    
    print("Step 1：PDF 轉圖片...")
    images = pdf_to_images(pdf_path, dpi=300)
    print(f"共 {len(images)} 頁")
    
    all_blocks = []
    
    for img_info in images:
        print(f"\n處理第 {img_info['page']} 頁...")
        print(f"圖片尺寸：{img_info['width']} x {img_info['height']} px")
        
        blocks = run_ocr(img_info)
        all_blocks.extend(blocks)
        
        output_path = f"output_{pdf_path.split(os.sep)[-1].replace('.pdf', '')}_page{img_info['page']}.png"
        draw_ocr_results(img_info, blocks, output_path)
        
        print(f"辨識到 {len(blocks)} 個文字區塊")

        # 規則引擎
        print(f"\n=== 規則引擎結果（第 {img_info['page']} 頁）===")
        field_results = process_form(all_blocks, img_info['width'], img_info['page'], img_info['height'])
        print(f"規則引擎找到 {len(field_results)} 個欄位")

        # LLM 過濾
        print("LLM 語意過濾中...")
        form_name = pdf_path.split(os.sep)[-1].replace('.pdf', '')
        filtered_results = filter_fields_with_llm(field_results, form_name)

        print(f"\n=== LLM 過濾結果（第 {img_info['page']} 頁）===")
        print_filter_comparison(field_results, filtered_results)
        print("最終保留欄位：")
        for r in filtered_results:
            print(f"  {r['field_key']:35s} | 標籤:[{r['label_text']}] | 填寫區域:{r['fill_bbox']}")

    output_json = pdf_path.replace(".pdf", "_ocr_result.json")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_blocks, f, ensure_ascii=False, indent=2)
    
    df = pd.DataFrame(all_blocks)
    print("\n=== OCR 結果統計 ===")
    print(f"總文字區塊數：{len(all_blocks)}")
    print(f"平均信心度：{df['confidence'].mean():.1f}%")
    print(f"高信心度（>70%）：{len(df[df['confidence']>70])} 個")
    print(f"中信心度（30-70%）：{len(df[(df['confidence']>=30) & (df['confidence']<=70)])} 個")
    
    return all_blocks


if __name__ == "__main__":
    results = {}
    pdf_dir = os.path.join(os.path.dirname(__file__), "pdfs")
    results["授信申請書"] = test_pdf(os.path.join(pdf_dir, "1.授信申請書.pdf"))
    results["個人資料表"] = test_pdf(os.path.join(pdf_dir, "2.個人資料表-徵信報告書(印刷版).pdf"))