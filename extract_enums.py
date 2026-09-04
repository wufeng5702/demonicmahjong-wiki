#!/usr/bin/env python3
"""从 Il2CppDumper 输出的 dump.cs 中提取枚举定义，生成 enums.json。

用法:
    python extract_enums.py [dump.cs路径]

输出: assets/enums.json（约50KB，可提交 git）
"""
import json
import re
import sys
from pathlib import Path

# 需要提取的枚举类型
TARGET_ENUMS = {
    "Tag", "XiaoChou", "Offering", "RelicId", "FanZhong",
    "CharacterID", "Rarity",
}


def extract_enums(dump_path: Path):
    content = dump_path.read_text(encoding="utf-8", errors="replace")

    # --- 1. InspectorName 属性映射 ---
    inspector_names = {}
    pat_inspector = (
        r'\[InspectorName\("([^"]+)"\)\]\s*\n\s*(?:\[[^\]]*\]\s*\n\s*)*'
        r"public const (\w+) (\w+) = (-?\d+);"
    )
    for m in re.finditer(pat_inspector, content):
        cn, etype, _fname, val = m.groups()
        inspector_names[f"{etype}.{int(val)}"] = cn

    # --- 2. 枚举常量值 ---
    enum_values = {}
    pat_val = r"public const (\w+) (\w+) = (-?\d+);"
    for m in re.finditer(pat_val, content):
        etype, fname, val = m.groups()
        if etype in TARGET_ENUMS:
            enum_values.setdefault(etype, {})[int(val)] = fname

    # --- 3. 完整枚举定义（含所有成员，用于调试/参考） ---
    # 注意: JSON 不支持 int key，这里按 string 存储，build_web.py 加载时会转回 int
    enum_defs = {}
    for name in TARGET_ENUMS:
        pattern = rf"public enum {name}\s*//.*?\{{(.*?)\}}"
        m = re.search(pattern, content, re.DOTALL)
        if not m:
            continue
        body = m.group(1)
        members = {}
        for line in body.splitlines():
            line = line.strip()
            cm = re.match(
                r"public const (\w+) (\w+) = (-?\d+);", line
            )
            if cm:
                _, fname, val = cm.groups()
                members[str(val)] = fname
        enum_defs[name] = members

    return enum_values, inspector_names, enum_defs


def main():
    if len(sys.argv) > 1:
        dump_path = Path(sys.argv[1])
    else:
        # 默认路径
        dump_path = Path(__file__).parent / "dump_output" / "dump.cs"

    if not dump_path.exists():
        print(f"错误: {dump_path} 不存在")
        print("用法: python extract_enums.py [dump.cs路径]")
        sys.exit(1)

    print(f"读取 {dump_path} ({dump_path.stat().st_size / 1024 / 1024:.1f} MB)")
    enum_values, inspector_names, enum_defs = extract_enums(dump_path)

    out = {
        "enum_values": enum_values,
        "inspector_names": inspector_names,
        "enum_defs": enum_defs,
    }

    out_path = Path(__file__).parent / "assets" / "enums.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")
    print(f"  枚举类型: {list(enum_values.keys())}")
    print(f"  InspectorName: {len(inspector_names)} 条")


if __name__ == "__main__":
    main()
