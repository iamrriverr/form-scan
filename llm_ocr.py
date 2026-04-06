# llm_ocr.py
# 用 OpenAI vision API 直接辨識表單欄位座標

import json
import base64
import urllib.request
import os
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()


def image_to_base64(pil_image) -> str:
    buffer = BytesIO()
    pil_image.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


def call_openai_vision(image_base64: str, prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 環境變數未設定")

    payload = json.dumps({
        "model": "gpt-4o",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    with urllib.request.urlopen(req, timeout=120) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def detect_form_fields(image_info: dict) -> list:
    """
    用 LLM vision 直接辨識表單圖片中的可填寫欄位。
    回傳格式與 rule_engine.process_form 相容。
    """
    img = image_info["image"]
    page = image_info["page"]
    width = image_info["width"]
    height = image_info["height"]

    image_b64 = image_to_base64(img)

    prompt = f"""你是表單分析專家。這張圖片是一份農會表單的第 {page} 頁。
圖片尺寸為 {width} x {height} 像素。

請找出所有「需要填寫」的欄位，包含：
- 姓名、身分證字號/統一編號、出生日期/設立日期、住址/戶籍地址、通訊地址、電話/手機
- 也包含配偶、保證人等區塊的欄位

對每個欄位，請提供：
1. label_text：欄位標籤文字（例如「姓名」「身分證統一編號」）
2. field_key：語意鍵，從以下選擇：
   applicant_name, applicant_id_number, applicant_birth_date,
   applicant_address, applicant_contact_address, applicant_phone,
   spouse_name, spouse_id_number, spouse_birth_date,
   guarantor_name, guarantor_id_number, guarantor_address, guarantor_phone,
   other
3. label_bbox：標籤文字的邊界框，格式 {{"x1": int, "y1": int, "x2": int, "y2": int}}
4. fill_bbox：填寫區域的邊界框（通常在標籤右邊或下方的空白處），同樣格式

座標請以像素為單位，基於圖片的實際尺寸 {width}x{height}。
請盡量精確地標記座標位置。

請只回傳 JSON 陣列，不要有其他文字。範例格式：
[
  {{
    "label_text": "姓名",
    "field_key": "applicant_name",
    "label_bbox": {{"x1": 100, "y1": 200, "x2": 250, "y2": 240}},
    "fill_bbox": {{"x1": 260, "y1": 200, "x2": 600, "y2": 240}}
  }}
]"""

    response = call_openai_vision(image_b64, prompt)

    # 解析 JSON
    try:
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
            clean = clean.strip()
        fields = json.loads(clean)
    except Exception as e:
        print(f"LLM 回傳解析失敗: {e}")
        print(f"原始回傳:\n{response}")
        return []

    # 補上 page 和 confidence
    for field in fields:
        field["page"] = page
        field["confidence"] = 0  # LLM 不回傳信心度

    return fields
