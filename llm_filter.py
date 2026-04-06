# llm_filter.py
import json
import urllib.request
import os
from dotenv import load_dotenv

load_dotenv()


def call_llm(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 環境變數未設定")

    payload = json.dumps({
        "model": "gpt-4o",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    with urllib.request.urlopen(req, timeout=60) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def filter_fields_with_llm(raw_results: list, form_name: str = "") -> list:
    """
    把規則引擎的輸出送給 LLM 過濾，
    回傳只保留申請人基本資料欄位的清單。
    """
    if not raw_results:
        return []

    # 整理成簡潔的輸入格式給 LLM
    fields_summary = []
    for i, r in enumerate(raw_results):
        fields_summary.append({
            "index": i,
            "label": r["label_text"],
            "field_key": r["field_key"],
            "y_position": r["label_bbox"]["y1"],
        })

    prompt = f"""你是農會表單分析助手。以下是從表單「{form_name}」中用規則引擎找到的欄位清單，
每個欄位包含標籤文字、語意鍵和在頁面上的垂直位置（y座標，數字越大越靠下）。

欄位清單：
{json.dumps(fields_summary, ensure_ascii=False, indent=2)}

請執行以下任務：
1. 判斷每個欄位是否屬於「申請人本人的基本資料」（姓名、身分證、地址、電話等）
2. 排除保證人、配偶、事業機構、審核人員等其他分區的欄位
3. 如果同一個 field_key 出現多次，只保留最靠上方的那一個（y_position 最小的）
4. 排除標籤文字明顯是複合句子或說明文字的欄位

請只回傳 JSON 陣列，內容是應該保留的欄位 index 清單，不要有任何其他文字。
範例格式：[0, 1, 3]"""

    response = call_llm(prompt)
    
    # 解析 LLM 回傳的 JSON
    try:
        # 清理可能的多餘字元
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        keep_indices = json.loads(clean.strip())
        
        filtered = [raw_results[i] for i in keep_indices if i < len(raw_results)]
        return filtered
    
    except Exception as e:
        print(f"LLM 回傳解析失敗: {e}")
        print(f"原始回傳: {response}")
        return raw_results  # 解析失敗時回傳原始結果


def print_filter_comparison(raw_results: list, filtered_results: list):
    """
    印出過濾前後的對比
    """
    raw_keys = set(r["label_text"] for r in raw_results)
    filtered_keys = set(r["label_text"] for r in filtered_results)
    removed = raw_keys - filtered_keys
    
    print(f"  過濾前：{len(raw_results)} 個欄位")
    print(f"  過濾後：{len(filtered_results)} 個欄位")
    if removed:
        print(f"  移除了：{removed}")