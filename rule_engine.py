# rule_engine.py

# 填寫提示文字黑名單（這些不算右側邊界）
FILL_HINT_TEXTS = [
    '市', '縣', '區', '鄉鎮', '鄉鎮市', '路', '街', '巷', '弄', '號', '樓',
    '市(縣)', '區(鄉鎮市)', '路(街)', '(街)', '(縣)', '(鄉鎮市)',
    '年', '月', '日', '元', '：', ':', '#'
]

# 排除標籤關鍵字（這些標籤文字不是填寫欄位）
EXCLUDE_LABEL_KEYWORDS = [
    '同意', '依據', '蒐集', '條款', '保護法', '附件', '核發',
    '申請，', '敬請', '此致', '填屬實', '以上'
]

# 帶冒號的標籤通常是簽名欄或說明欄，需要特別處理
SIGNATURE_PATTERNS = ['申請人:', '申請人：', '簽章', '簽名']


def is_fill_hint(text: str) -> bool:
    """判斷是否為填寫提示文字"""
    clean = text.strip().replace(' ', '')
    return clean in FILL_HINT_TEXTS or len(clean) <= 1


def find_fill_region(label_block: dict, all_blocks: list, page_width: int, same_row_tolerance: int = 30) -> dict:
    label_bbox = label_block['bbox']
    label_y_center = (label_bbox['y1'] + label_bbox['y2']) / 2
    label_x2 = label_bbox['x2']
    label_y1 = label_bbox['y1']
    label_y2 = label_bbox['y2']

    # 找同一行的其他區塊
    same_row_blocks = []
    for block in all_blocks:
        if block is label_block:
            continue
        b = block['bbox']
        b_y_center = (b['y1'] + b['y2']) / 2
        if abs(b_y_center - label_y_center) <= same_row_tolerance:
            same_row_blocks.append(block)

    # 找標籤右側的區塊，跳過填寫提示文字
    right_blocks = [
        b for b in same_row_blocks
        if b['bbox']['x1'] > label_x2 and not is_fill_hint(b['text'])
    ]

    if right_blocks:
        nearest_right = min(right_blocks, key=lambda b: b['bbox']['x1'])
        fill_x2 = nearest_right['bbox']['x1'] - 5
    else:
        fill_x2 = page_width - 50

    # 最小寬度保護
    min_fill_width = 400
    if fill_x2 - label_x2 < min_fill_width:
        fill_x2 = min(label_x2 + min_fill_width, page_width - 50)

    return {
        'x1': label_x2 + 5,
        'y1': label_y1,
        'x2': fill_x2,
        'y2': label_y2
    }


def match_field_key(label_text: str) -> str:
    label = label_text.replace(' ', '').replace('　', '')

    # 長度過濾
    if len(label) > 15:
        return 'none'

    # 排除條款和說明文字
    for kw in EXCLUDE_LABEL_KEYWORDS:
        if kw in label:
            return 'none'

    # 排除簽名欄
    for pattern in SIGNATURE_PATTERNS:
        if pattern in label_text:
            return 'none'

    mapping = [
        (['申請人', '姓名'], 'applicant_name'),
        (['身分證', '統一編號', '統編'], 'applicant_id_number'),
        (['出生', '設立日期'], 'applicant_birth_date'),
        (['住址', '戶籍地', '營業處所'], 'applicant_address'),
        (['通訊處'], 'applicant_contact_address'),
        (['電話', '手機'], 'applicant_phone'),
        (['配偶姓名'], 'spouse_name'),
    ]

    for keywords, field_key in mapping:
        for kw in keywords:
            if kw in label:
                return field_key

    return 'none'


def process_form(ocr_blocks: list, page_width: int, page_num: int = 1, page_height: int = None) -> list:
    page_blocks = [b for b in ocr_blocks if b['page'] == page_num]

    # 申請人基本資料通常在頁面上半部（前50%），用來過濾重複欄位
    primary_zone_y_max = (page_height * 0.5) if page_height else float('inf')

    results = []
    seen_field_keys = {}  # 記錄每個 field_key 第一次出現的位置

    # 先按 y 座標排序，確保從上到下處理
    sorted_blocks = sorted(page_blocks, key=lambda b: b['bbox']['y1'])

    for block in sorted_blocks:
        field_key = match_field_key(block['text'])
        if field_key == 'none':
            continue

        y1 = block['bbox']['y1']

        # 如果這個 field_key 已經出現過，且新出現的位置超過頁面一半，跳過
        if field_key in seen_field_keys:
            if page_height and y1 > primary_zone_y_max:
                continue

        seen_field_keys[field_key] = y1
        fill_region = find_fill_region(block, page_blocks, page_width)

        results.append({
            'label_text': block['text'],
            'field_key': field_key,
            'label_bbox': block['bbox'],
            'fill_bbox': fill_region,
            'confidence': block['confidence'],
            'page': page_num
        })

    return results