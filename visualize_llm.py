# visualize_llm.py
# 視覺化 LLM vision 辨識的欄位座標

from PIL import Image, ImageDraw, ImageFont


# 不同 field_key 前綴對應不同顏色
FIELD_COLORS = {
    "applicant": "blue",
    "spouse": "purple",
    "guarantor": "orange",
    "other": "gray",
}


def get_color(field_key: str) -> str:
    for prefix, color in FIELD_COLORS.items():
        if field_key.startswith(prefix):
            return color
    return "gray"


def draw_llm_results(image_info: dict, fields: list, output_path: str):
    """
    把 LLM 辨識的欄位座標畫在圖片上。
    紅框：標籤區域（label_bbox）
    藍/紫/橘框：填寫區域（fill_bbox），顏色依欄位類型
    """
    img = image_info["image"].copy()
    draw = ImageDraw.Draw(img)

    for field in fields:
        label_bbox = field.get("label_bbox", {})
        fill_bbox = field.get("fill_bbox", {})
        field_key = field.get("field_key", "other")
        label_text = field.get("label_text", "")
        color = get_color(field_key)

        # 畫標籤框（紅色）
        if label_bbox:
            draw.rectangle(
                [label_bbox["x1"], label_bbox["y1"], label_bbox["x2"], label_bbox["y2"]],
                outline="red",
                width=3,
            )

        # 畫填寫區域框
        if fill_bbox:
            draw.rectangle(
                [fill_bbox["x1"], fill_bbox["y1"], fill_bbox["x2"], fill_bbox["y2"]],
                outline=color,
                width=3,
            )

        # 標註欄位名稱
        text_y = label_bbox.get("y1", fill_bbox.get("y1", 0)) - 20
        text_x = label_bbox.get("x1", fill_bbox.get("x1", 0))
        draw.text(
            (text_x, text_y),
            f"{label_text} [{field_key}]",
            fill=color,
        )

    img.save(output_path)
    print(f"視覺化結果儲存至：{output_path}")
