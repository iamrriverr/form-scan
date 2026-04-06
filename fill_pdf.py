# fill_pdf.py
# 把使用者輸入的欄位值填入 PDF 對應位置

import fitz  # PyMuPDF
from address_parser import SUBLABEL_MAP


# field_key 對應中文標籤
FIELD_LABELS = {
    "applicant_name": "姓名",
    "applicant_id_number": "身分證字號",
    "applicant_birth_date": "出生日期",
    "applicant_address": "戶籍地址",
    "applicant_contact_address": "通訊地址",
    "applicant_phone": "電話",
    "spouse_name": "配偶姓名",
}

# 地址子欄位標籤
ADDRESS_SUB_LABELS = {
    "county": "縣/市",
    "district": "鄉鎮/市區",
    "road": "路/街",
    "section": "段",
    "lane": "巷",
    "alley": "弄",
    "number": "號",
    "floor": "樓",
}

# 地址類型的 field_key
ADDRESS_FIELD_KEYS = {"applicant_address", "applicant_contact_address", "guarantor_address"}


def find_address_sublabels(ocr_blocks: list, address_field: dict,
                           all_address_fields: list = None, tolerance: int = 60) -> list:
    """
    從 OCR 結果中找到地址欄位附近的子標籤。
    回傳 [(sublabel_key, x1, x2, y_center), ...] 按 x1 排序。

    all_address_fields: 所有地址欄位清單（用來避免跨欄位偵測干擾）
    """
    addr_bbox = address_field["label_bbox"]
    addr_y_center = (addr_bbox["y1"] + addr_bbox["y2"]) / 2
    page = address_field["page"]

    # 計算搜尋範圍：只在本欄位和下一個欄位之間搜尋
    y_min = addr_bbox["y1"] - tolerance
    y_max = addr_bbox["y2"] + tolerance
    if all_address_fields:
        # 找到其他地址欄位的 y 範圍，避免侵入
        for other in all_address_fields:
            if other is address_field or other["page"] != page:
                continue
            other_y_center = (other["label_bbox"]["y1"] + other["label_bbox"]["y2"]) / 2
            if other_y_center > addr_y_center:
                # 下方的欄位：限制搜尋上界
                y_max = min(y_max, other["label_bbox"]["y1"] - 10)
            elif other_y_center < addr_y_center:
                # 上方的欄位：限制搜尋下界
                y_min = max(y_min, other["label_bbox"]["y2"] + 10)

    # 建立子標籤文字 → key 的映射
    all_sublabel_texts = {}
    for key, texts in SUBLABEL_MAP.items():
        for t in texts:
            all_sublabel_texts[t] = key

    found = []
    for block in ocr_blocks:
        if block["page"] != page:
            continue
        b_y_center = (block["bbox"]["y1"] + block["bbox"]["y2"]) / 2
        if b_y_center < y_min or b_y_center > y_max:
            continue
        # 子標籤應該在地址標籤的右邊
        if block["bbox"]["x2"] < addr_bbox["x1"]:
            continue

        text = block["text"].strip().replace("`", "").replace("'", "")
        bx1, bx2 = block["bbox"]["x1"], block["bbox"]["x2"]

        # 處理合併偵測（如 "段巷弄號樓之"、"號樓"）
        matched_chars = [(i, c) for i, c in enumerate(text) if c in all_sublabel_texts]
        if len(matched_chars) > 1 and len(text) <= 8:
            char_width = (bx2 - bx1) / len(text)
            for i, c in matched_chars:
                cx1 = int(bx1 + i * char_width)
                cx2 = int(bx1 + (i + 1) * char_width)
                found.append((all_sublabel_texts[c], cx1, cx2, b_y_center))
            continue

        # 處理帶括號的複合標籤（如 "市 縣"、"區 鄉鎮市"、"路(街)"）
        for label_text, key in all_sublabel_texts.items():
            if label_text in text and len(text) <= 10:
                if any(f[0] == key for f in found):
                    continue
                found.append((key, bx1, bx2, b_y_center))
                break

    found.sort(key=lambda x: x[1])

    # 去重：同一個 key 只保留第一個
    seen = set()
    deduped = []
    for item in found:
        if item[0] not in seen:
            seen.add(item[0])
            deduped.append(item)

    # 推算缺失的子標籤位置
    # 如果有 county 和 road 但沒有 district，在兩者中間插入
    found_keys = {d[0] for d in deduped}
    if "county" in found_keys and "road" in found_keys and "district" not in found_keys:
        county_item = next(d for d in deduped if d[0] == "county")
        road_item = next(d for d in deduped if d[0] == "road")
        mid_x1 = county_item[2] + (road_item[1] - county_item[2]) // 3
        mid_x2 = county_item[2] + 2 * (road_item[1] - county_item[2]) // 3
        deduped.append(("district", mid_x1, mid_x2, county_item[3]))
        deduped.sort(key=lambda x: x[1])

    # 修正重疊：確保每個子標籤之間至少有 min_gap 的空隙
    min_gap = 30
    for i in range(1, len(deduped)):
        prev_x2 = deduped[i - 1][2]
        curr_x1 = deduped[i][1]
        if curr_x1 - prev_x2 < min_gap:
            # 把當前子標籤往右推
            shift = min_gap - (curr_x1 - prev_x2)
            key, x1, x2, yc = deduped[i]
            deduped[i] = (key, x1 + shift, x2 + shift, yc)

    return deduped


def fill_pdf(pdf_path: str, field_results: list, field_values: dict, output_path: str,
             ocr_blocks: list = None, ocr_dpi: int = 300):
    """
    將欄位值寫入 PDF。

    field_values 格式：
      - 一般欄位: {"applicant_name": "王小明"}
      - 地址欄位: {"applicant_address.county": "新北", ...}
    """
    doc = fitz.open(pdf_path)
    scale = 72 / ocr_dpi

    for field in field_results:
        field_key = field["field_key"]
        page_num = field["page"] - 1
        page = doc[page_num]

        if field_key in ADDRESS_FIELD_KEYS and ocr_blocks:
            addr_parts = {}
            for sub_key in ADDRESS_SUB_LABELS:
                val = field_values.get(f"{field_key}.{sub_key}", "")
                if val:
                    addr_parts[sub_key] = val
            if addr_parts:
                all_addr_fields = [f for f in field_results if f["field_key"] in ADDRESS_FIELD_KEYS]
                _fill_address(page, field, addr_parts, ocr_blocks, scale, all_addr_fields)
        else:
            value = field_values.get(field_key, "")
            if value:
                _fill_simple(page, field, value, scale)

    doc.save(output_path)
    doc.close()
    return output_path


def _fill_simple(page, field: dict, value: str, scale: float):
    """一般欄位：直接寫入 fill_bbox"""
    bbox = field["fill_bbox"]
    x1 = bbox["x1"] * scale
    y1 = bbox["y1"] * scale
    y2 = bbox["y2"] * scale

    box_height = y2 - y1
    font_size = max(8, min(box_height * 0.6, 14))
    text_y = y1 + (box_height - font_size) / 2 + font_size

    page.insert_text(
        (x1 + 4, text_y),
        value,
        fontsize=font_size,
        fontname="china-s",
        color=(0, 0, 0.8),
    )


def _fill_address(page, field: dict, addr_parts: dict, ocr_blocks: list, scale: float,
                  all_addr_fields: list = None):
    """
    地址欄位：找到子標籤位置，在每個子標籤的左邊空隙中填入對應值。
    支援多行排列（如段巷弄號樓在不同行）。
    """
    sublabels = find_address_sublabels(ocr_blocks, field, all_address_fields=all_addr_fields)

    if not sublabels:
        combined = "".join(addr_parts.values())
        _fill_simple(page, field, combined, scale)
        return

    addr_bbox = field["label_bbox"]
    font_size = 10

    # 按 y 分組（同一行的子標籤放一起），容差 40px
    rows = []
    for item in sublabels:
        placed = False
        for row in rows:
            if abs(row[0][3] - item[3]) < 40:
                row.append(item)
                placed = True
                break
        if not placed:
            rows.append([item])

    # 每行按 x 排序
    for row in rows:
        row.sort(key=lambda x: x[1])

    # 第一行的 prev_x2 從地址標籤結尾開始
    # 其他行的 prev_x2 從該行最左側子標籤的起始位置再往左一點
    for row in rows:
        row_y_center = row[0][3]
        # 計算這一行的 y 座標（用子標籤自身的 y）
        # 找到這行子標籤附近的 y 範圍
        row_y_pdf = row_y_center * scale
        text_y = row_y_pdf + font_size * 0.3

        # 決定這一行的 prev_x2
        # 如果這行的 y 接近地址標籤的 y，就用標籤的 x2
        addr_y_center = (addr_bbox["y1"] + addr_bbox["y2"]) / 2
        if abs(row_y_center - addr_y_center) < 40:
            prev_x2 = addr_bbox["x2"]
        else:
            # 其他行：從行的第一個子標籤左邊的空隙開始
            prev_x2 = row[0][1] - 150  # 預留空間

        for sublabel_key, sx1, sx2, _ in row:
            text = addr_parts.get(sublabel_key, "")

            fill_start = prev_x2
            fill_end = sx1

            if text and fill_end > fill_start:
                x = fill_start * scale + 4
                page.insert_text(
                    (x, text_y),
                    text,
                    fontsize=font_size,
                    fontname="china-s",
                    color=(0, 0, 0.8),
                )

            prev_x2 = sx2
