# address_parser.py
# 解析台灣地址為各子欄位

import re


def parse_address(address: str) -> dict:
    """
    解析台灣地址，拆成各個子欄位。
    例如: "新北市汐止區大同路一段100巷5弄10號3樓"
    → {county: "新北", district: "汐止", road: "大同", section: "一", lane: "100", alley: "5", number: "10", floor: "3"}
    """
    result = {
        "county": "",     # 縣/市
        "district": "",   # 鄉/鎮/市/區
        "road": "",       # 路/街
        "section": "",    # 段
        "lane": "",       # 巷
        "alley": "",      # 弄
        "number": "",     # 號
        "floor": "",      # 樓
    }

    addr = address.strip()

    # 縣/市
    m = re.match(r"(.+?[縣市])", addr)
    if m:
        result["county"] = m.group(1).rstrip("縣市")
        addr = addr[m.end():]

    # 鄉/鎮/市/區
    m = re.match(r"(.+?[鄉鎮市區])", addr)
    if m:
        result["district"] = m.group(1).rstrip("鄉鎮市區")
        addr = addr[m.end():]

    # 路/街
    m = re.match(r"(.+?[路街])", addr)
    if m:
        result["road"] = m.group(1).rstrip("路街")
        addr = addr[m.end():]

    # 段
    m = re.match(r"(.+?)段", addr)
    if m:
        result["section"] = m.group(1)
        addr = addr[m.end():]

    # 巷
    m = re.match(r"(\d+)巷", addr)
    if m:
        result["lane"] = m.group(1)
        addr = addr[m.end():]

    # 弄
    m = re.match(r"(\d+)弄", addr)
    if m:
        result["alley"] = m.group(1)
        addr = addr[m.end():]

    # 號
    m = re.match(r"(\d+)號", addr)
    if m:
        result["number"] = m.group(1)
        addr = addr[m.end():]

    # 樓
    m = re.match(r"(\d+)樓", addr)
    if m:
        result["floor"] = m.group(1)
        addr = addr[m.end():]

    return result


# 子欄位對應的表單提示字
SUBLABEL_MAP = {
    "county": ["縣", "市"],
    "district": ["鄉鎮", "市區", "鄉鎮市", "區"],
    "road": ["路", "(街)", "街"],
    "section": ["段"],
    "lane": ["巷"],
    "alley": ["弄"],
    "number": ["號"],
    "floor": ["樓", "樓之"],
}
