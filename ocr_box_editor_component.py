import base64
import os
from io import BytesIO

import streamlit.components.v1 as components


_component_func = components.declare_component(
    "ocr_box_editor",
    path=os.path.join(os.path.dirname(__file__), "ocr_box_component"),
)


def pil_image_to_data_url(image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def ocr_box_editor(image_data_url: str, fields: list, key: str, height: int = 760):
    return _component_func(
        image_data_url=image_data_url,
        fields=fields,
        height=height,
        key=key,
        default=None,
    )
