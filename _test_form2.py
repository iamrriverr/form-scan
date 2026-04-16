"""快速 harness：在不啟動 Streamlit 情況下 run 整條 pipeline 到 fill_pdf。
會產生 _filled.pdf 和每個 address 的 debug 資訊。
"""
import os
import sys
import json

from pdf_to_image import pdf_to_images
from ocr_engine import run_ocr
from rule_engine import process_form
from fill_pdf import fill_pdf, find_address_sublabels, ADDRESS_FIELD_KEYS

PDF = sys.argv[1] if len(sys.argv) > 1 else "2.個人資料表-徵信報告書(印刷版).pdf"
OUT_SUFFIX = sys.argv[2] if len(sys.argv) > 2 else "_filled_test"

TEST_VALUES = {
    "applicant_name": "王小明",
    "applicant_id_number": "A123456789",
    "applicant_birth_date": "80/01/01",
    "applicant_phone": "02-12345678",
    # Address sub-fields
    "applicant_address.county": "新北市",
    "applicant_address.district": "汐止區",
    "applicant_address.road": "大同路",
    "applicant_address.section": "一",
    "applicant_address.lane": "100",
    "applicant_address.alley": "5",
    "applicant_address.number": "10",
    "applicant_address.floor": "3",
    "applicant_contact_address.county": "臺北市",
    "applicant_contact_address.district": "信義區",
    "applicant_contact_address.road": "松仁路",
    "applicant_contact_address.section": "二",
    "applicant_contact_address.lane": "200",
    "applicant_contact_address.alley": "8",
    "applicant_contact_address.number": "20",
    "applicant_contact_address.floor": "5",
}

cache_fields = PDF.replace(".pdf", "_fields.json")
cache_ocr = PDF.replace(".pdf", "_ocr_result.json")

if os.path.exists(cache_fields) and os.path.exists(cache_ocr):
    print(f"[cache] 讀取 {cache_fields}")
    with open(cache_fields, "r", encoding="utf-8") as f:
        all_fields = json.load(f)
    with open(cache_ocr, "r", encoding="utf-8") as f:
        all_blocks = json.load(f)
else:
    print(f"[run] OCR + rule_engine on {PDF}")
    images = pdf_to_images(PDF, dpi=300)
    all_blocks = []
    all_fields = []
    for img_info in images:
        blocks = run_ocr(img_info)
        all_blocks.extend(blocks)
        # Only this page's blocks to process_form (fix P0 bug)
        page_blocks = [b for b in all_blocks if b["page"] == img_info["page"]]
        fields = process_form(page_blocks, img_info["width"], img_info["page"], img_info["height"])
        all_fields.extend(fields)

    with open(cache_fields, "w", encoding="utf-8") as f:
        json.dump(all_fields, f, ensure_ascii=False, indent=2)
    with open(cache_ocr, "w", encoding="utf-8") as f:
        json.dump(all_blocks, f, ensure_ascii=False, indent=2)
    print(f"[saved] {cache_fields}, {cache_ocr}")

print(f"\n=== 偵測到 {len(all_fields)} 個欄位 ===")
for f in all_fields:
    print(f"  {f['field_key']:30s}  label='{f['label_text']}'  y1={f['label_bbox']['y1']}")

print("\n=== 地址子標籤偵測結果 ===")
addr_fields = [f for f in all_fields if f["field_key"] in ADDRESS_FIELD_KEYS]
for af in addr_fields:
    subs = find_address_sublabels(all_blocks, af, all_address_fields=addr_fields)
    print(f"  [{af['field_key']}] label_y={af['label_bbox']['y1']}-{af['label_bbox']['y2']}")
    for key, x1, x2, yc in subs:
        print(f"    {key:10s} x1={x1:5d} x2={x2:5d} yc={yc:.1f}")

output = PDF.replace(".pdf", f"{OUT_SUFFIX}.pdf")
fill_pdf(PDF, all_fields, TEST_VALUES, output, ocr_blocks=all_blocks)
print(f"\n=> Output: {output}")
