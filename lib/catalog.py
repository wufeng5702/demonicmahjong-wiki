"""
catalog.py - Unity Addressables JSON catalog 解析器
====================================================
格式参考 AddressablesTools/AddressablesToolsPy (nesrak1/anosu)。

用法:
    cat = Catalog.load(path)
    addr = cat.guid_to_address(guid)   # GUID -> Assets/... 地址
"""

import base64
import json
import struct


class _R:
    def __init__(self, b):
        self.b = b
        self.p = 0

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def u8(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def seek(self, p):
        self.p = p

    def bytes(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v


def _decode_object(r: _R):
    """SerializedObjectDecoder.decode_v1"""
    t = r.u8()
    if t == 0:  # ascii string
        n = r.i32()
        return r.bytes(n).decode("utf-8", "replace")
    if t == 1:  # unicode string
        n = r.i32()
        return r.bytes(n).decode("utf-16-le", "replace")
    if t == 2:
        return struct.unpack_from("<H", r.b, r.p)[0]
    if t == 3:
        return struct.unpack_from("<I", r.b, r.p)[0]
    if t == 4:
        return struct.unpack_from("<i", r.b, r.p)[0]
    if t == 7:  # json object (AssetBundleRequestOptions 等)
        alen = r.u8()
        r.bytes(alen)  # assembly
        clen = r.u8()
        r.bytes(clen)  # class
        jlen = r.i32()
        return r.bytes(jlen).decode("utf-16-le", "replace")
    raise ValueError(f"unknown serialized type {t} @ {r.p-1}")


class Catalog:
    def __init__(self, path):
        j = json.load(open(path, encoding="utf-8"))
        self.internal_ids = j["m_InternalIds"]
        self.provider_ids = j["m_ProviderIds"]
        self.resource_types = j.get("m_resourceTypes", [])
        bd = base64.b64decode(j["m_BucketDataString"])
        kd = base64.b64decode(j["m_KeyDataString"])
        ed = base64.b64decode(j["m_EntryDataString"])

        br = _R(bd)
        bcount = br.i32()
        self.buckets = []  # (keydata_offset, [entry_index...])
        for _ in range(bcount):
            off = br.i32()
            ec = br.i32()
            entries = [struct.unpack_from("<i", bd, br.p + 4 * k)[0] for k in range(ec)]
            br.p += 4 * ec
            self.buckets.append((off, entries))

        kr = _R(kd)
        kcount = kr.i32()
        self.keys = []
        for i in range(kcount):
            kr.seek(self.buckets[i][0])
            self.keys.append(_decode_object(kr))

        er = _R(ed)
        ecount = er.i32()
        self.entries = []
        for _ in range(ecount):
            internal_id_idx = er.i32()
            er.i32()  # provider
            dep_idx = er.i32()
            er.i32()  # dep hash
            data_idx = er.i32()
            pk_idx = er.i32()
            er.i32()  # resource type
            self.entries.append({
                "internal_id": self.internal_ids[internal_id_idx],
                "dep": self.keys[dep_idx] if 0 <= dep_idx < len(self.keys) else None,
                "primary": self.keys[pk_idx] if 0 <= pk_idx < len(self.keys) else None,
            })

        # 桶按 entries 分组: 同组桶的键互为别名 (GUID ↔ 地址)
        from collections import defaultdict
        alias_groups = defaultdict(list)
        for i, (_off, entries) in enumerate(self.buckets):
            alias_groups[tuple(entries)].append(i)

        # GUID -> 地址 / 资源信息
        self.by_guid = {}
        for i, k in enumerate(self.keys):
            if isinstance(k, str) and len(k) == 32:
                try:
                    int(k, 16)
                    is_guid = True
                except ValueError:
                    is_guid = False
            else:
                is_guid = False
            if not is_guid:
                continue
            siblings = []
            for j in alias_groups.get(tuple(self.buckets[i][1]), []):
                if j != i and isinstance(self.keys[j], str):
                    siblings.append(self.keys[j])
            addr = next((s for s in siblings if s.startswith("Assets/")), None)
            b = self.buckets[i]
            locs = [self.entries[e] for e in b[1] if e < len(self.entries)]
            internal_id = locs[0]["internal_id"] if locs else None
            self.by_guid[k.lower()] = {"address": addr or k, "internal_id": internal_id,
                                       "siblings": siblings}

    @classmethod
    def load(cls, path):
        return cls(path)

    def guid_to_address(self, guid):
        """GUID -> (Assets/... 地址, internal_id)；无结果返回 (None, None)"""
        info = self.by_guid.get(guid.lower())
        if not info:
            return None, None
        return info["address"], info["internal_id"]

    def guid_to_internal_ids(self, guid):
        """GUID -> 资源在 bundle 内的地址集合 (即 container 键)"""
        info = self.by_guid.get(guid.lower())
        if not info:
            return set()
        return {info["internal_id"]} if info.get("internal_id") else set()
