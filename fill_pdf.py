# fill_pdf.py
# 把使用者輸入的欄位值填入 PDF 對應位置

import os
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

# 子標籤預期順序（由左到右 / 由主題到細節）。用來推算缺失的子標籤位置。
SUBLABEL_ORDER = ["county", "district", "road", "section", "lane", "alley", "number", "floor"]

DEBUG = os.environ.get("FORM_SCAN_DEBUG", "").lower() in ("1", "true", "yes")


def _dbg(msg: str):
    if DEBUG:
        print(msg)


def _font_for(text: str) -> str:
    """
    "china-s" (Heiti) 會把 Latin 數字/字母渲染成全形 CJK 數字（2倍寬），
    所以純 ASCII 用 "helv" 以維持正確寬度；含中文字則用 "china-s"。
    """
    return "helv" if text.isascii() else "china-s"


def _scan_sublabels_in_block(text: str, bx1: int, bx2: int, y_center: float,
                             sublabel_lookup: dict) -> list:
    """
    在一個 OCR block 文字中掃描所有 sub-label 片段，估算各自的 x 範圍。
    回傳 [(key, cx1, cx2, y_center, source_width), ...]，source_width 是該 OCR block 的
    寬度，可用來判斷「獨立偵測」vs「合併偵測」的可靠度。
    """
    results = []
    text_len = max(len(text), 1)
    char_w = (bx2 - bx1) / text_len
    src_width = bx2 - bx1

    # caption 字元實際顯示寬度估計：~25-35px（300dpi）
    display_w = min(30, max(char_w * 0.85, 20))

    allow_inner = len(text) <= 10

    seen_keys = set()
    i = 0
    sorted_labels = sorted(sublabel_lookup.keys(), key=lambda s: -len(s))
    # 記錄所有 matched_label 的位置（不止第一個 key 出現的位置），用來判斷整塊是否只含單一 key
    all_matches = []  # [(key, label_text, start_idx)]
    while i < len(text):
        matched_label = None
        for label_text in sorted_labels:
            if text.startswith(label_text, i):
                matched_label = label_text
                break
        if matched_label:
            key = sublabel_lookup[matched_label]
            all_matches.append((key, matched_label, i))
            if not (key in seen_keys) and (allow_inner or i == 0):
                cx_center = bx1 + (i + len(matched_label) / 2) * char_w
                cx1 = int(cx_center - display_w / 2)
                cx2 = int(cx_center + display_w / 2)
                results.append((key, cx1, cx2, y_center, src_width))
                seen_keys.add(key)
            i += len(matched_label)
        else:
            i += 1

    # 若整塊只有一個 key（如 "市 縣"→county、"路(街)"→road、"區 鄉鎮市"→district），
    # 用整塊的 bbox 代表該 caption 範圍：fill_start 從 bx1 開始、fill_end 到 bx2。
    # 比估算的 display_w 更準確。
    if results and len({m[0] for m in all_matches}) == 1:
        key = results[0][0]
        return [(key, bx1, bx2, y_center, src_width)]
    return results


def _detect_sublabels_for_field(ocr_blocks: list, address_field: dict,
                                all_address_fields: list = None,
                                tolerance: int = 60) -> list:
    """
    單一地址欄位的 sub-label 偵測，回傳 [(key, x1, x2, yc, src_width), ...] by x1。
    未做跨欄位推論、未內插。
    """
    addr_bbox = address_field["label_bbox"]
    addr_y_center = (addr_bbox["y1"] + addr_bbox["y2"]) / 2
    page = address_field["page"]

    y_min = addr_bbox["y1"] - tolerance
    y_max = addr_bbox["y2"] + tolerance
    if all_address_fields:
        for other in all_address_fields:
            if other is address_field or other["page"] != page:
                continue
            other_yc = (other["label_bbox"]["y1"] + other["label_bbox"]["y2"]) / 2
            if other_yc > addr_y_center:
                y_max = min(y_max, other["label_bbox"]["y1"] - 10)
            elif other_yc < addr_y_center:
                y_min = max(y_min, other["label_bbox"]["y2"] + 10)

    sublabel_lookup = {}
    for key, texts in SUBLABEL_MAP.items():
        for t in texts:
            sublabel_lookup[t] = key

    found = []
    for block in ocr_blocks:
        if block["page"] != page:
            continue
        # 用「有效 y」：高 bbox（h>45，典型多行或含 ascender/descender 多餘空間）時
        # 以 y2-25 當 caption 位置代理，避免 yc 飄到 bbox 中心但實際 caption 偏下。
        # 這對表單裡用一個 OCR 方塊框住整行 "段巷弄號樓之" 的情況特別關鍵。
        by1, by2 = block["bbox"]["y1"], block["bbox"]["y2"]
        h = by2 - by1
        b_y_center = (by2 - 25) if h > 45 else (by1 + by2) / 2
        if b_y_center < y_min or b_y_center > y_max:
            continue
        if block["bbox"]["x2"] < addr_bbox["x1"]:
            continue
        text = block["text"].strip().replace("`", "").replace("'", "")
        bx1, bx2 = block["bbox"]["x1"], block["bbox"]["x2"]
        found.extend(_scan_sublabels_in_block(text, bx1, bx2, b_y_center, sublabel_lookup))

    found.sort(key=lambda x: x[1])
    # 跨 block 去重：同一 key 若有多種來源，優先選 y 接近 address label 的（對齊實際 fill 行）；
    # y 差距接近時（<15px）再取最窄來源。
    by_key = {}
    for item in found:
        key = item[0]
        item_dist = abs(item[3] - addr_y_center)
        if key not in by_key:
            by_key[key] = (item, item_dist)
            continue
        prev_item, prev_dist = by_key[key]
        # 主要判斷：y 接近度；差距 < 15 才視為「同一 fill 行」再比寬度
        if item_dist + 15 < prev_dist:
            by_key[key] = (item, item_dist)
        elif abs(item_dist - prev_dist) < 15 and item[4] < prev_item[4]:
            by_key[key] = (item, item_dist)
    deduped = sorted([v[0] for v in by_key.values()], key=lambda x: x[1])
    return deduped


def _interpolate_missing_sublabels(detected: list) -> list:
    """
    給定已偵測到的 sub-labels（list of (key, x1, x2, yc)），
    按 SUBLABEL_ORDER 在相鄰 anchors 之間線性內插補回缺失的 key。
    只在兩個 anchor 的 y 接近（同一 row）時才內插。
    """
    if len(detected) < 2:
        return detected

    by_key = {d[0]: d for d in detected}
    in_order = [k for k in SUBLABEL_ORDER if k in by_key]
    result = list(detected)

    for idx in range(len(in_order) - 1):
        left_key = in_order[idx]
        right_key = in_order[idx + 1]
        left_pos = SUBLABEL_ORDER.index(left_key)
        right_pos = SUBLABEL_ORDER.index(right_key)
        gap_keys = SUBLABEL_ORDER[left_pos + 1 : right_pos]
        if not gap_keys:
            continue

        L = by_key[left_key]
        R = by_key[right_key]
        # 同一 row 才內插（y_center 差 < 40）
        if abs(L[3] - R[3]) > 40:
            continue
        x_span = R[1] - L[2]
        if x_span <= 0:
            continue

        n_slots = len(gap_keys) + 1
        slot_w = x_span / n_slots
        yc = (L[3] + R[3]) / 2
        for i, mkey in enumerate(gap_keys):
            center = L[2] + (i + 1) * slot_w
            mx1 = int(center - slot_w * 0.15)
            mx2 = int(center + slot_w * 0.15)
            result.append((mkey, mx1, mx2, yc))

    result.sort(key=lambda x: x[1])
    return result


def find_address_sublabels(ocr_blocks: list, address_field: dict,
                           all_address_fields: list = None, tolerance: int = 60) -> list:
    """
    從 OCR 結果中找到地址欄位附近的子標籤。
    回傳 [(sublabel_key, x1, x2, y_center), ...] 按 x1 排序。

    跨欄位推論：多個 address field 共存時（如戶籍地+通訊處），若本欄位的某子標籤來自
    合併塊（較寬 src_width）、但其他欄位有更窄的獨立塊偵測到同一 key，則借用其他
    欄位的 x 座標（y 仍使用本欄位自己的偵測值）。這對相同欄位結構的表單特別有效。
    """
    my_raw = _detect_sublabels_for_field(ocr_blocks, address_field, all_address_fields, tolerance)

    # 收集所有地址欄位的 sub-label 偵測，找每個 key 最窄 src 的 (x1, x2)
    if all_address_fields and len(all_address_fields) > 1:
        best_by_key = {}  # key -> (x1, x2, src_width)
        for key, x1, x2, _, src_width in my_raw:
            if key not in best_by_key or src_width < best_by_key[key][2]:
                best_by_key[key] = (x1, x2, src_width)

        for other in all_address_fields:
            if other is address_field:
                continue
            # Same page only (跨頁 x 可能對不上）
            if other.get("page") != address_field.get("page"):
                continue
            other_raw = _detect_sublabels_for_field(ocr_blocks, other, all_address_fields, tolerance)
            for key, x1, x2, _, src_width in other_raw:
                if key not in best_by_key or src_width < best_by_key[key][2]:
                    best_by_key[key] = (x1, x2, src_width)

        # 若其他欄位有顯著更窄的偵測，替換本欄位的 x（保留 y）
        refined = []
        for key, x1, x2, yc, src_width in my_raw:
            if key in best_by_key and best_by_key[key][2] * 1.5 < src_width:
                bx1, bx2, _ = best_by_key[key]
                refined.append((key, bx1, bx2, yc))
                _dbg(f"  [cross-field] {key} src={src_width} → best={best_by_key[key][2]} x=({bx1},{bx2})")
            else:
                refined.append((key, x1, x2, yc))
        deduped = refined
    else:
        deduped = [(key, x1, x2, yc) for key, x1, x2, yc, _ in my_raw]

    # 內插推算缺失的 sub-labels
    deduped = _interpolate_missing_sublabels(deduped)

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
        fontname=_font_for(value),
        color=(0, 0, 0.8),
    )


def _cluster_rows_by_y(items: list, eps: float) -> list:
    """
    把 [(key, x1, x2, yc), ...] 依 y_center 用 sorted-gap clustering 分 row。
    eps：相鄰 y 差 < eps 就併到同 row。
    """
    if not items:
        return []
    sorted_by_y = sorted(items, key=lambda it: it[3])
    rows = [[sorted_by_y[0]]]
    for it in sorted_by_y[1:]:
        if it[3] - rows[-1][-1][3] < eps:
            rows[-1].append(it)
        else:
            rows.append([it])
    return rows


def _fill_address(page, field: dict, addr_parts: dict, ocr_blocks: list, scale: float,
                  all_addr_fields: list = None):
    """
    地址欄位：找到子標籤位置，在每個子標籤的左邊空隙中填入對應值。
    支援 2D 排列（如 form 2 的 段/巷/弄 在上行、號/樓 在下行）。
    """
    sublabels = find_address_sublabels(ocr_blocks, field, all_address_fields=all_addr_fields)

    if not sublabels:
        combined = "".join(addr_parts.get(k, "") for k in ADDRESS_SUB_LABELS if addr_parts.get(k))
        _fill_simple(page, field, combined, scale)
        return

    addr_bbox = field["label_bbox"]
    addr_y_center = (addr_bbox["y1"] + addr_bbox["y2"]) / 2
    addr_height = addr_bbox["y2"] - addr_bbox["y1"]
    font_size = 10

    # Row clustering：用 address label 高度的一半當 eps（DPI 自適應）
    row_eps = max(20, addr_height * 0.55)
    rows = _cluster_rows_by_y(sublabels, eps=row_eps)

    _dbg(f"[fill_address {field['field_key']}] rows={len(rows)} eps={row_eps:.1f}")
    for r in rows:
        _dbg(f"  row yc={sum(it[3] for it in r)/len(r):.1f}: "
             + " ".join(f"{it[0]}[{it[1]}-{it[2]}]" for it in sorted(r, key=lambda x: x[1])))

    for row in rows:
        row.sort(key=lambda it: it[1])

        # 用 row 內 y 的中位數做 text_y，避免 row[0] 的 OCR 抖動
        ys_sorted = sorted(it[3] for it in row)
        row_y_ocr = ys_sorted[len(ys_sorted) // 2]
        row_y_pdf = row_y_ocr * scale
        text_y = row_y_pdf + font_size * 0.5

        # 這 row 是「主 row」嗎（y 接近 address label 的 y_center）？
        is_main_row = abs(row_y_ocr - addr_y_center) < row_eps

        # 估計 row 的平均 sub-label 間距（用來決定 row-starting sub-label 的 prev_x2）
        if len(row) > 1:
            gaps = [row[i + 1][1] - row[i][2] for i in range(len(row) - 1)]
            gaps = [g for g in gaps if g > 0]
            avg_gap = sum(gaps) / len(gaps) if gaps else 60
        else:
            avg_gap = 100

        if is_main_row:
            prev_x2 = addr_bbox["x2"]
        else:
            # 次要 row（段/巷/弄 或 號/樓 單獨一列）
            # prev_x2 用 row 本身的平均間距預留，避免 150px 寫死
            prev_x2 = row[0][1] - max(avg_gap, 40)

        for sublabel_key, sx1, sx2, _ in row:
            text = addr_parts.get(sublabel_key, "")
            fill_start = prev_x2
            fill_end = sx1

            if text and fill_end > fill_start + 5:
                # 右對齊：value 右端貼近 caption 左側。value 比 slot 寬時往左溢出到前一
                # caption 的 whitespace（caption 實體字窄，右側多半是空白），比覆蓋下一
                # caption 好讀。
                fontname = _font_for(text)
                font = fitz.Font(fontname)
                text_w = font.text_length(text, fontsize=font_size)
                x_right = fill_end * scale - 2
                x = x_right - text_w
                # 絕對下限：不要寫到 address 主標籤左邊
                x_min_abs = addr_bbox["x2"] * scale + 2
                x = max(x, x_min_abs)
                page.insert_text(
                    (x, text_y),
                    text,
                    fontsize=font_size,
                    fontname=fontname,
                    color=(0, 0, 0.8),
                )
            prev_x2 = sx2
