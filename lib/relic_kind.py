"""遗物主分类：游戏原始标签与脚本类名，不受人工补充标签影响。"""

CURSED_RELIC_SCRIPTS = {
    "GuiChengDisplay", "PoWanDisplay", "ShengXiuDingZiDisplay", "ShouKaoDisplay",
    "WuGuWaWaDisplay", "ZhiRenDisplay", "ZouMaDengDisplay",
    "ZuZhouFangChuiDisplay", "MiDaSiDiaoXiangDisplay",
}
MYSTERIOUS_RELIC_SCRIPTS = {
    "BaiBaoXiangDisplay", "BaiYuShanDisplay", "BianXingFuDisplay",
    "DiZangWangBaoJianDisplay", "DuShiWangBaoJianDisplay", "LingDengDisplay",
    "LingLongBaoTaDisplay", "NingHunZhuDisplay", "NvWaTuDisplay",
    "QinGuangWangBaoJianDisplay", "RanHunQiangDisplay", "SenLuoBaoJianDisplay",
    "ShangHunRenDisplay", "ShenMiGongTaiDisplay", "ShiHunZhuDisplay",
    "ShouXiangDisplay", "TaiShanShiDisplay", "TaiShanWangBaoJianDisplay",
    "XuanYuanBaoJingDisplay", "YanLuoWangBaoJianDisplay", "YueGuangBaoHeDisplay",
    "YueGuangBaoHeSuiPianDisplay", "ZhaoYaoJingDisplay", "ZiJinTiYuDisplay",
}


def relic_kind(script_name, list_kind="", raw_tags=()):
    """只接受游戏原始数值 tags；中文/人工标签可能仅表示与诅咒相关。"""
    if 56000 in (raw_tags or ()) or script_name in CURSED_RELIC_SCRIPTS:
        return "诅咒"
    if list_kind:
        return list_kind
    return "神秘" if script_name in MYSTERIOUS_RELIC_SCRIPTS else ""
