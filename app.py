# app.py
# Streamlit 表單填寫介面
# 啟動: uv run streamlit run app.py

import streamlit as st
import os
import json
import zipfile
from io import BytesIO
from pdf_to_image import pdf_to_images
from ocr_engine import run_ocr
from rule_engine import process_form
from llm_filter import filter_fields_with_llm
from fill_pdf import fill_pdf, FIELD_LABELS, ADDRESS_FIELD_KEYS, ADDRESS_SUB_LABELS

PDF_DIR = os.path.join(os.path.dirname(__file__), "pdfs")


def get_pdf_list():
    return [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf") and "_filled" not in f]


def detect_fields(pdf_path: str) -> tuple[list, list]:
    """執行 OCR + 規則引擎 + LLM 過濾，回傳 (欄位清單, OCR原始結果)"""
    images = pdf_to_images(pdf_path, dpi=300)
    all_blocks = []
    all_fields = []

    for img_info in images:
        blocks = run_ocr(img_info)
        all_blocks.extend(blocks)

        fields = process_form(
            all_blocks, img_info["width"], img_info["page"], img_info["height"]
        )
        if fields:
            form_name = os.path.basename(pdf_path).replace(".pdf", "")
            filtered = filter_fields_with_llm(fields, form_name)
            all_fields.extend(filtered)

    return all_fields, all_blocks


def load_cached(pdf_path: str) -> tuple[list, list] | None:
    fields_path = pdf_path.replace(".pdf", "_fields.json")
    ocr_path = pdf_path.replace(".pdf", "_ocr_result.json")
    if os.path.exists(fields_path) and os.path.exists(ocr_path):
        with open(fields_path, "r", encoding="utf-8") as f:
            fields = json.load(f)
        with open(ocr_path, "r", encoding="utf-8") as f:
            ocr_blocks = json.load(f)
        return fields, ocr_blocks
    return None


def save_cached(pdf_path: str, fields: list, ocr_blocks: list):
    fields_path = pdf_path.replace(".pdf", "_fields.json")
    ocr_path = pdf_path.replace(".pdf", "_ocr_result.json")
    with open(fields_path, "w", encoding="utf-8") as f:
        json.dump(fields, f, ensure_ascii=False, indent=2)
    with open(ocr_path, "w", encoding="utf-8") as f:
        json.dump(ocr_blocks, f, ensure_ascii=False, indent=2)


def get_union_field_keys(all_pdf_data: dict) -> list:
    """從多份表單的欄位中取聯集，保持穩定順序"""
    # 定義欄位的優先順序
    priority = list(FIELD_LABELS.keys())
    seen = set()
    result = []

    # 先按優先順序加入已知欄位
    for key in priority:
        for pdf_name, data in all_pdf_data.items():
            for f in data["fields"]:
                if f["field_key"] == key and key not in seen:
                    seen.add(key)
                    result.append({"field_key": key, "label_text": f["label_text"]})
                    break

    # 再加入不在優先清單中的欄位
    for pdf_name, data in all_pdf_data.items():
        for f in data["fields"]:
            if f["field_key"] not in seen:
                seen.add(f["field_key"])
                result.append({"field_key": f["field_key"], "label_text": f["label_text"]})

    return result


# --- Streamlit UI ---

st.set_page_config(page_title="農會表單自動填寫", layout="centered")
st.title("農會表單自動填寫")

# 選擇 PDF（多選）
pdf_files = get_pdf_list()
if not pdf_files:
    st.error("pdfs/ 資料夾中沒有 PDF 檔案")
    st.stop()

selected_pdfs = st.multiselect("選擇表單（可多選）", pdf_files, default=pdf_files)

if not selected_pdfs:
    st.info("請選擇至少一份表單")
    st.stop()

# 偵測欄位
if "pdf_data" not in st.session_state:
    st.session_state.pdf_data = {}  # {pdf_name: {"fields": [...], "ocr_blocks": [...]}}

if st.button("偵測欄位") or st.session_state.pdf_data:
    need_detect = [p for p in selected_pdfs if p not in st.session_state.pdf_data]

    if need_detect:
        progress = st.progress(0, text="偵測中...")
        for i, pdf_name in enumerate(need_detect):
            pdf_path = os.path.join(PDF_DIR, pdf_name)
            progress.progress((i) / len(need_detect), text=f"分析：{pdf_name}")

            cached = load_cached(pdf_path)
            if cached:
                fields, ocr_blocks = cached
            else:
                fields, ocr_blocks = detect_fields(pdf_path)
                save_cached(pdf_path, fields, ocr_blocks)

            st.session_state.pdf_data[pdf_name] = {
                "fields": fields,
                "ocr_blocks": ocr_blocks,
            }
        progress.progress(1.0, text="偵測完成")

    # 顯示各表單偵測到的欄位數
    selected_data = {k: v for k, v in st.session_state.pdf_data.items() if k in selected_pdfs}
    st.subheader("偵測結果")
    for pdf_name, data in selected_data.items():
        keys = [f["field_key"] for f in data["fields"]]
        st.caption(f"**{pdf_name}**：{', '.join(FIELD_LABELS.get(k, k) for k in dict.fromkeys(keys))}")

    # 取聯集欄位
    union_fields = get_union_field_keys(selected_data)

    if not union_fields:
        st.warning("未偵測到可填寫欄位")
        st.stop()

    # 顯示輸入表單
    st.subheader("請填寫以下欄位（聯集）")

    field_values = {}
    for f in union_fields:
        key = f["field_key"]
        label = FIELD_LABELS.get(key, f["label_text"])

        if key in ADDRESS_FIELD_KEYS:
            st.markdown(f"**{label}**")
            cols = st.columns([2, 2, 2, 1, 1, 1, 1, 1])
            for col, (sub_key, sub_label) in zip(cols, ADDRESS_SUB_LABELS.items()):
                with col:
                    field_values[f"{key}.{sub_key}"] = st.text_input(
                        sub_label, key=f"input_{key}_{sub_key}", label_visibility="visible"
                    )
        else:
            field_values[key] = st.text_input(label, key=f"input_{key}")

    # 填入 PDF
    if st.button("填入 PDF"):
        filled_count = sum(1 for v in field_values.values() if v)
        if filled_count == 0:
            st.warning("請至少填寫一個欄位")
        else:
            output_files = []
            for pdf_name in selected_pdfs:
                data = st.session_state.pdf_data[pdf_name]
                pdf_path = os.path.join(PDF_DIR, pdf_name)
                output_name = pdf_name.replace(".pdf", "_filled.pdf")
                output_path = os.path.join(PDF_DIR, output_name)

                fill_pdf(pdf_path, data["fields"], field_values, output_path,
                         ocr_blocks=data["ocr_blocks"])
                output_files.append((output_name, output_path))

            st.success(f"已填入 {filled_count} 個欄位到 {len(output_files)} 份表單")

            # 多檔打包下載
            if len(output_files) == 1:
                name, path = output_files[0]
                with open(path, "rb") as f:
                    st.download_button("下載填寫完成的 PDF", data=f.read(),
                                       file_name=name, mime="application/pdf")
            else:
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for name, path in output_files:
                        zf.write(path, name)
                st.download_button("下載全部（ZIP）", data=zip_buffer.getvalue(),
                                   file_name="filled_forms.zip", mime="application/zip")
