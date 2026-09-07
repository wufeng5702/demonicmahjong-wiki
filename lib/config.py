#!/usr/bin/env python3
"""环境变量加载 + 路径常量 + bundle/I2 自动定位。"""
import json
import os
from pathlib import Path

GAME_DIR = Path(r"E:\DemonicMahjong")
GAME_DATA_DIR = GAME_DIR / "DemonicMahjong" / "Demonic Mahjong_Data"
AA_DIR = GAME_DATA_DIR / "StreamingAssets/aa/StandaloneWindows64"
CATALOG = GAME_DATA_DIR / "StreamingAssets/aa/catalog.json"
SHARED0 = GAME_DATA_DIR / "sharedassets0.assets"
SHARED1 = GAME_DATA_DIR / "sharedassets1.assets"
SHARED2 = GAME_DATA_DIR / "sharedassets2.assets"
SHARED3 = GAME_DATA_DIR / "sharedassets3.assets"
SHARED4 = GAME_DATA_DIR / "sharedassets4.assets"
DUMP_CS = GAME_DIR / "dump_output/dump.cs"
SITE_DIR = GAME_DIR / "site"

# 加载 .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    GAME_DIR = Path(os.environ.get("GAME_DIR", GAME_DIR))
    GAME_DATA_DIR = GAME_DIR / "Demonic Mahjong_Data"
    AA_DIR = GAME_DATA_DIR / "StreamingAssets/aa/StandaloneWindows64"
    CATALOG = GAME_DATA_DIR / "StreamingAssets/aa/catalog.json"
    SHARED1 = GAME_DATA_DIR / "sharedassets1.assets"
    SHARED4 = GAME_DATA_DIR / "sharedassets4.assets"
    DUMP_CS = Path(os.environ.get("DUMP_CS", GAME_DIR.parent / "dump_output/dump.cs"))
    SITE_DIR = Path(__file__).resolve().parent.parent / "output" / "site"


def locate_bundle():
    """从 catalog.json 解析当前版本的主数据 bundle (defaultlocalgroup*)。"""
    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        for x in cat.get("m_InternalIds", []):
            s = str(x).replace("\\", "/")
            name = s.rsplit("/", 1)[-1]
            if name.startswith("defaultlocalgroup") and name.endswith(".bundle"):
                p = AA_DIR / name
                if p.exists():
                    return p
    except Exception:
        pass
    hits = sorted(AA_DIR.glob("defaultlocalgroup*.bundle"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


BUNDLE_PATH = locate_bundle()

I2_OBJECT_PATH_ID = 13759


def locate_i2_object(bf):
    """自动定位 I2 LanguageSource: 最大的含 I2 key 模式的 MonoBehaviour。"""
    try:
        raw = bf.objects[I2_OBJECT_PATH_ID].get_raw_data()
        if len(raw) > 1_000_000 and b"/Name" in raw[:200000]:
            return I2_OBJECT_PATH_ID
    except Exception:
        pass
    best = None
    for pid, obj in bf.objects.items():
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            raw = obj.get_raw_data()
        except Exception:
            continue
        if len(raw) > 1_000_000 and b"/Name" in raw[:200000] and b"/Description" in raw:
            if best is None or len(raw) > best[1]:
                best = (pid, len(raw))
    return best[0] if best else None
