"""牌灵/宝牌的旧版独立 Payload 与新版统一 Payload 分类。"""

BAOLING_CLASSES = ("BaoLingPayload", "PaiLingPayload", "BaoPaiPayload")


def baoling_category(class_name, payload):
    """新版按 baoLingType 分类；旧版按脚本类名分类。无效 ID 不输出。"""
    if class_name not in BAOLING_CLASSES:
        return None
    if int(getattr(payload, "id", 0) or 0) <= 0:
        return None
    if class_name == "PaiLingPayload":
        return "pailing"
    if class_name == "BaoPaiPayload":
        return "baopai"
    kind = getattr(payload, "baoLingType", None)
    if kind == 0:
        return "baopai"
    if kind in (1, 2):  # 牌灵 / 念灵共用图鉴的牌灵分类
        return "pailing"
    raise ValueError(f"未知 BaoLingPayload.baoLingType: {kind!r}")
