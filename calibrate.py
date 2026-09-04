#!/usr/bin/env python3
"""校准 rawparse：用主 bundle 的可读实例做 ground truth 对比。

使用时机（无需每次构建都跑，仅在以下情况手动调用）：
    1. 游戏版本更新后 —— 字段布局可能偏移
    2. 修改了 rawparse.py 的字段定义后 —— 验证改动是否正确
    3. build_web.py 出现解析错误时 —— 定位偏移位置

用法:
    python calibrate.py                     # 使用 .env 配置，自动查找 bundle
    python calibrate.py --bundle <path>     # 指定 bundle 文件
    python calibrate.py --out <path>        # 指定输出文件

结果解读:
    - bad=0: 字段布局没变，无需操作
    - bad>0: 对照输出里的 diffs，更新 rawparse.py 的 SPECS
"""
import glob
import io
import os
import sys
from pathlib import Path

# 加载 .env
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent / "lib"))

GAME_DIR = Path(os.environ.get("GAME_DIR", Path(__file__).parent))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="校准 rawparse")
    parser.add_argument("--bundle", type=str, help="主 bundle 文件路径")
    parser.add_argument("--cab", type=str, help="CAB 名称 (默认自动检测)")
    parser.add_argument("--out", type=str, default="probe_out.txt", help="输出文件路径")
    args = parser.parse_args()

    # 自动查找 bundle
    if args.bundle:
        bundle_path = Path(args.bundle)
    else:
        pattern = str(
            GAME_DIR
            / "Demonic Mahjong_Data"
            / "StreamingAssets"
            / "aa"
            / "StandaloneWindows64"
            / "defaultlocalgroup_assets_all_*.bundle"
        )
        matches = glob.glob(pattern)
        if not matches:
            print(f"错误: 未找到 defaultlocalgroup_assets_all_*.bundle")
            print(f"  搜索路径: {pattern}")
            sys.exit(1)
        bundle_path = Path(matches[0])

    print(f"Bundle: {bundle_path}")

    out_path = Path(args.out)
    orig_stdout = sys.stdout
    out = open(out_path, "w", encoding="utf-8")
    sys.stdout = out

    from UnityPy import AssetsManager
    from UnityPy.enums import ClassIDType

    import rawparse as rp
    from rawparse import LS

    am = AssetsManager()
    # 新版游戏将脚本元数据拆到独立 monoscripts bundle，需先加载
    ms_patterns = ["*_monoscripts_*.bundle"]
    for pat in ms_patterns:
        for ms_bf in bundle_path.parent.glob(pat):
            am.load_file(str(ms_bf))
            print(f"  loaded monoscripts: {ms_bf.name}")
            break
    bf = am.load_file(str(bundle_path))

    # 查找 CAB
    if args.cab:
        sf = bf.files[args.cab]
    else:
        cab_keys = [k for k in bf.files if k.startswith("CAB-")]
        if not cab_keys:
            print("错误: bundle 中没有 CAB-* 文件")
            sys.exit(1)
        sf = bf.files[cab_keys[0]]
        print(f"CAB: {cab_keys[0]}")

    def sn_of(d):
        ms = getattr(d, "m_Script", None)
        return getattr(ms.read(), "m_ClassName", "?") if ms else "?"

    def termkey(v):
        return getattr(v, "mTerm", "") if v is not None and hasattr(v, "mTerm") else ""

    def guid_of(av):
        if av is None:
            return None
        return getattr(av, "m_AssetGUID", None)

    def fnum(v):
        return round(v, 4) if isinstance(v, float) else v

    def expected(d, cls):
        exp = {}
        for name, t in rp.SPECS[cls]:
            if name == "descriptionTranslation":
                exp[name] = {}
                continue
            av = getattr(d, name, None)
            if t == "i":
                ev = int(av) if av is not None and not hasattr(av, "mTerm") else None
            elif t == "f":
                ev = fnum(av) if isinstance(av, (int, float)) else None
            elif t == "b":
                ev = bool(av) if av is not None else None
            elif t == "s":
                ev = (
                    getattr(av, "m_AssetGUID", None)
                    if hasattr(av, "m_AssetGUID")
                    else (str(av) if isinstance(av, str) else None)
                )
            elif t == "ar":
                ev = {"guid": guid_of(av)} if av is not None else None
            elif t == "p":
                ev = {"path_id": getattr(av, "path_id", None)} if av is not None else None
            elif t == LS:
                ev = termkey(av)
            elif t == "vi":
                ev = [int(x) for x in av] if isinstance(av, list) else []
            elif t == "vp":
                ev = [{"path_id": getattr(x, "path_id", None)} for x in av] if isinstance(av, list) else []
            elif t == "vls":
                ev = [termkey(x) for x in av] if isinstance(av, list) else []
            elif t == "v2":
                ev = [getattr(av, "x", 0), getattr(av, "y", 0)] if av is not None else None
            elif t == "c4":
                ev = None
            else:
                ev = None
            exp[name] = ev
        return exp

    buckets = {}
    for pid, obj in sf.objects.items():
        if obj.type != ClassIDType.MonoBehaviour:
            continue
        try:
            d = obj.read()
            sn = sn_of(d)
        except Exception:
            continue
        if sn in rp.SPECS:
            buckets.setdefault(sn, []).append((pid, d))

    for cls, items in buckets.items():
        print(f"===== {cls}: {len(items)} =====")
        okc = badc = 0
        for pid, d in items[:400]:
            try:
                raw = sf.objects[pid].get_raw_data()
                mine = rp.parse_payload(raw, cls)
            except Exception as e:
                print(f"  [{pid}] {getattr(d, 'm_Name', '?')} PARSE FAIL @: {str(e)[:70]}")
                badc += 1
                continue
            exp = expected(d, cls)
            diffs = []
            for name, t in rp.SPECS[cls]:
                if name == "descriptionTranslation":
                    continue
                mv, ev = mine.get(name), exp.get(name)
                if t == "p":
                    if (mv or {}).get("path_id") != (ev or {}).get("path_id"):
                        diffs.append((name, (mv or {}).get("path_id"), (ev or {}).get("path_id")))
                elif t == "vp":
                    m2 = [(x or {}).get("path_id") for x in (mv or [])]
                    e2 = [(x or {}).get("path_id") for x in (ev or [])]
                    if m2 != e2:
                        diffs.append((name, m2, e2))
                elif t == "vi":
                    if [int(x) for x in (mv or [])] != [int(x) for x in (ev or [])]:
                        diffs.append((name, mv, ev))
                elif t == "f":
                    if abs((mv or 0) - (ev or 0)) > 1e-4:
                        diffs.append((name, mv, ev))
                elif t == "ar":
                    if (mv or {}).get("guid") != (ev or {}).get("guid"):
                        diffs.append((name + ".guid", (mv or {}).get("guid"), (ev or {}).get("guid")))
                elif t == "v2":
                    if [round(x, 4) for x in (mv or [0, 0])] != [
                        round(float(x), 4) for x in (ev or [0, 0])
                    ]:
                        diffs.append((name, mv, ev))
                elif t in ("i", "s", "b", LS):
                    if t == "i" and mv is not None and ev is not None:
                        if int(mv) != int(ev):
                            diffs.append((name, mv, ev))
                    elif mv != ev:
                        diffs.append((name, mv, ev))
            if diffs:
                badc += 1
                print(f"  [{pid}] {mine.get('m_Name', '?')} {len(diffs)} diffs:")
                for k, a, b in diffs[:6]:
                    print(f"      {k}: mine={str(a)[:44]} exp={str(b)[:44]}")
            else:
                okc += 1
        print(f"  -> ok={okc} bad={badc}")
    print("DONE")
    sys.stdout = orig_stdout
    out.close()
    print(f"结果已写入: {out_path}")


if __name__ == "__main__":
    main()
