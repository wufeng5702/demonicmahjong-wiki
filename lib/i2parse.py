#!/usr/bin/env python3
"""I2 LanguageSource 手工解析 + 翻译查找 + 文本回填。"""
import re
import struct

from UnityPy import AssetsManager

from config import SHARED1, locate_i2_object, I2_OBJECT_PATH_ID

LANG_ZH = 0
LANG_EN = 1

KEY_SEG_RE = re.compile(rb"[A-Za-z0-9][A-Za-z0-9_.\-]*(?:\s*/[A-Za-z0-9][A-Za-z0-9_.\-]*)+")
VALID_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*(?:\s*/[A-Za-z0-9][A-Za-z0-9_.\-]*)+$")
TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


def parse_i2_source(raw):
    """从 MonoBehaviour 原始字节解析 I2 LanguageSource 的 mTerms。"""
    anchors = []
    for m in KEY_SEG_RE.finditer(raw):
        s, e = m.span()
        if s < 44:
            continue
        if struct.unpack_from("<i", raw, s - 4)[0] != e - s:
            continue
        raw_key = m.group().decode("ascii")
        key = re.sub(r'\s+', '', raw_key)
        if VALID_KEY_RE.match(key):
            anchors.append((s, key, e - s))
    anchors.sort()

    def rd_str(p):
        n = struct.unpack_from("<i", raw, p)[0]
        if n < 0 or n > 1_000_000:
            raise ValueError(f"bad strlen {n}@{p}")
        v = raw[p + 4:p + 4 + n].decode("utf-8", "replace")
        return v, p + 4 + n + ((-(p + 4 + n)) % 4)

    def parse_at(koff, klen):
        kend = koff + ((klen + 3) // 4 * 4)
        best = None
        for skip_type in (0, 4):
            p = kend + skip_type
            try:
                _, p = rd_str(p)
                nl = struct.unpack_from("<i", raw, p)[0]
                p += 4
                if not 3 <= nl <= 8:
                    raise ValueError("nl")
                langs = []
                for _ in range(nl):
                    t, p = rd_str(p)
                    langs.append(t)
                nf = struct.unpack_from("<i", raw, p)[0]
                p += 4
                if not 0 <= nf <= 16:
                    raise ValueError("nf")
                p += nf + (-p % 4)
                nt = struct.unpack_from("<i", raw, p)[0]
                p += 4
                if not 0 <= nt <= 10:
                    raise ValueError("nt")
                for _ in range(nt):
                    _, p = rd_str(p)
                score = sum(len(x) for x in langs)
                cand = (langs, p, skip_type)
                if best is None or score > best[1]:
                    best = (cand[0], score, skip_type)
                if skip_type == 0:
                    break
            except Exception:
                continue
        return best[0] if best else None

    terms = {}
    ok = fail = 0
    for koff, key, raw_klen in anchors:
        langs = parse_at(koff, raw_klen)
        if langs is None:
            fail += 1
            continue
        ok += 1
        prev = terms.get(key)
        if prev is None or sum(map(len, langs)) > sum(map(len, prev)):
            terms[key] = langs
    return terms, ok, fail


def load_i2_terms():
    am = AssetsManager()
    bf = am.load_file(str(SHARED1))
    pid = locate_i2_object(bf)
    if pid is None:
        raise RuntimeError("未找到 I2 LanguageSource (sharedassets1 中无匹配对象)")
    if pid != I2_OBJECT_PATH_ID:
        print(f"  [warn] I2 path_id 漂移: {I2_OBJECT_PATH_ID} -> {pid} (已自动定位)")
    raw = bf.objects[pid].get_raw_data()
    terms, ok, fail = parse_i2_source(raw)
    print(f"  I2 terms parsed: {ok} ok, {fail} failed anchors -> {len(terms)} unique keys")
    return terms


def clean_markup(s):
    """清洗 I2 内联标记: <Term Default=47>三元牌</Term> -> 三元牌"""
    if not s:
        return s
    return TAG_RE.sub("", s)


def tr(term_key, i2):
    """取词条文本: 优先简中, 回退英文。"""
    if not term_key:
        return ""
    langs = i2.get(term_key)
    if not langs:
        langs = i2.get(re.sub(r'\s+', '', term_key))
    if not langs:
        return None
    zh = langs[LANG_ZH].strip()
    if zh:
        return clean_markup(zh)
    en = langs[LANG_EN].strip()
    return clean_markup(en) if en else ""


def apply_text(entries, i2, id_fields=("nameKey", "descKey")):
    """对所有条目应用 I2 翻译 (name/desc)。"""
    missing = 0
    for e in entries:
        nk, dk = e.get("nameKey", ""), e.get("descKey", "")
        if not nk and not dk:
            continue
        name_txt = tr(nk, i2)
        desc_txt = tr(dk, i2)
        if dk and desc_txt is None:
            fixed_dk = re.sub(r'(Individual)(\d)', r'\1/\2', dk)
            if fixed_dk != dk:
                desc_txt = tr(fixed_dk, i2)
                if desc_txt is not None:
                    dk = fixed_dk
                    e["descKey"] = dk
        e["name"] = name_txt if name_txt is not None else ""
        e["desc"] = desc_txt if desc_txt is not None else ""
        if (nk and name_txt is None) or (dk and desc_txt is None):
            missing += 1
    return missing
