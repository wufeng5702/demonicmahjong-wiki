#!/usr/bin/env python3
"""
全部图标提取函数:
  - extract_achievement_icons
  - extract_lingyong_icons
  - extract_character_avatars
  - extract_character_skill_icons
  - extract_relic_icons
  - extract_offering_icons
  - extract_offering_skill_icons
  - extract_baopai_icons
  - render_pailing_icons (从 3D 模型软件光栅化)
"""
import math
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

import UnityPy
from UnityPy import AssetsManager
from UnityPy.enums import ClassIDType

from config import (AA_DIR, BUNDLE_PATH, SHARED0, SHARED1, SHARED2, SHARED3,
                    SHARED4, SITE_DIR)
import rawparse as rp

SIZE = 512
SS = 2  # 超采样倍数


# ============================================================
# 牌灵 3D 渲染 (原 render_pl_icons.py)
# ============================================================
def apply_bloom(im, threshold=0.55, blur_radius=14, intensity=0.55):
    arr = np.array(im, np.float32) / 255.0
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3:4]
    bright = np.clip(rgb - threshold, 0, 1)
    mask = bright.max(axis=2, keepdims=True)
    bloom_src = Image.fromarray((bright * mask * 255).astype(np.uint8), "RGB")
    bloom_blur = bloom_src.filter(ImageFilter.GaussianBlur(blur_radius))
    bloom_arr = np.array(bloom_blur, np.float32) / 255.0
    result = np.clip(rgb + bloom_arr * intensity, 0, 1)
    out = np.concatenate([result, alpha], axis=2)
    return Image.fromarray((out * 255).astype(np.uint8), "RGBA")


def quat_to_mat(x, y, z, w):
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def tr_to_mat(d):
    t = d.m_LocalPosition
    r = d.m_LocalRotation
    s = d.m_LocalScale
    M = np.eye(4)
    R = quat_to_mat(r.x, r.y, r.z, r.w)
    M[:3, :3] = R @ np.diag([s.x, s.y, s.z])
    M[:3, 3] = [t.x, t.y, t.z]
    return M


def parse_obj(text):
    vs, vts, vns, tris = [], [], [], []
    tris = []
    for line in text.splitlines():
        if not line.startswith("f "):
            continue
        idx = []
        for tok in line.split()[1:]:
            a = tok.split("/")
            vi = int(a[0]) - 1
            ti = int(a[1]) - 1 if len(a) > 1 and a[1] else vi
            ni = int(a[2]) - 1 if len(a) > 2 and a[2] else vi
            idx.append((vi, ti, ni))
        for k in range(1, len(idx) - 1):
            tris.append((idx[0], idx[k], idx[k + 1]))
    for line in text.splitlines():
        if line.startswith("v "):
            p = line.split()
            vs.append((float(p[1]), float(p[2]), float(p[3])))
        elif line.startswith("vt "):
            p = line.split()
            vts.append((float(p[1]), float(p[2])))
        elif line.startswith("vn "):
            p = line.split()
            vns.append((float(p[1]), float(p[2]), float(p[3])))
    return (np.array(vs, np.float64), np.array(vts, np.float64).reshape(-1, 2),
            np.array(vns, np.float64).reshape(-1, 3), tris)


def collect_parts(objs, root_pid):
    go_name, go_comps = {}, {}
    for pid, o in objs.items():
        if o.type.name == "GameObject":
            try:
                d = o.read()
                go_name[pid] = d.m_Name
                go_comps[pid] = [(c.path_id) for c in (d.m_Components or [])]
            except Exception:
                pass
    tr_data = {}
    for pid, o in objs.items():
        if o.type.name != "Transform":
            continue
        try:
            d = o.read()
            tr_data[d.m_GameObject.path_id] = (pid, d, [c.path_id for c in (d.m_Children or [])])
        except Exception:
            pass

    def comps(go_pid):
        out = []
        for cpid in go_comps.get(go_pid, []):
            if cpid in objs:
                out.append((objs[cpid].type.name, objs[cpid]))
        return out

    parts = []

    def get_tex_from_mat(mat_pid):
        main = mask = None
        if mat_pid not in objs:
            return None, None
        try:
            md = objs[mat_pid].read()
            sp = getattr(md, "m_SavedProperties", None)
            for k, v in (sp.m_TexEnvs if sp else []):
                key = k.first.name if hasattr(k, "first") else str(k)
                tp = getattr(getattr(v, "m_Texture", None), "path_id", 0)
                if tp and tp in objs:
                    img = objs[tp].read().image.convert("RGBA")
                    if key == "_MainTex":
                        main = img
                    elif key == "_MaskTex":
                        mask = img
        except Exception:
            pass
        return main, mask

    def walk(go_pid, M):
        td = tr_data.get(go_pid)
        local = tr_to_mat(td[1]) if td else np.eye(4)
        WM = M @ local
        for ct, co in comps(go_pid):
            if ct == "MeshFilter":
                mesh_pid = co.read().m_Mesh.path_id
                if mesh_pid not in objs:
                    continue
                mesh_obj = objs[mesh_pid]
                main = mask = None
                for ct2, co2 in comps(go_pid):
                    if ct2 in ("MeshRenderer", "SkinnedMeshRenderer"):
                        d2 = co2.read()
                        mats = [m.path_id for m in (d2.m_Materials or [])]
                        if mats:
                            main, mask = get_tex_from_mat(mats[0])
                        break
                parts.append((mesh_obj, main, mask, WM))
        if td:
            for ch in td[2]:
                try:
                    cgo = objs[ch].read().m_GameObject.path_id
                except Exception:
                    continue
                walk(cgo, WM)

    walk(root_pid, np.eye(4))
    return parts


FACE_ANCHOR = {10036: [(0.5615, 0.5850), (0.8398, 0.5508)], 10037: (0.68, 0.62)}
ROLL = {10015: 5, 10025: -5, 10028: 6, 10030: -5, 10036: 202, 10037: 90}


def face_basis(parts, anchor=None):
    mesh_obj, main, mask, WM = parts[0]
    anchors = []
    if main is not None and mask is not None and mask.size[0] > 4:
        ma = np.asarray(mask.convert("L"), np.float32) / 255.0
        ys, xs = np.where(ma > 0.5)
        if len(xs) > 0:
            anchors = [(xs.mean() / ma.shape[1], 1 - ys.mean() / ma.shape[0])]
    if not anchors:
        if not anchor:
            return None
        anchors = list(anchor) if isinstance(anchor[0], (tuple, list)) else [anchor]
    text = mesh_obj.read().export("obj")
    vs, vts, vns, tris = parse_obj(text)
    wv = (WM @ np.hstack([vs, np.ones((len(vs), 1))]).T).T[:, :3]
    wn = (WM[:3, :3] @ vns.T).T
    face = np.zeros(3)
    up = np.zeros(3)
    for mu, mv in anchors:
        sel = []
        r = 0.05
        while r <= 0.45 and len(sel) < 24:
            sel = [t for t in tris
                   if np.linalg.norm((vts[t[0][1]] + vts[t[1][1]] + vts[t[2][1]]) / 3 - [mu, mv]) < r]
            r *= 1.5
        for (a, b, c) in sel:
            face += wn[a[2]] + wn[b[2]] + wn[c[2]]
            p0, p1, p2 = wv[a[0]], wv[b[0]], wv[c[0]]
            e1, e2 = p1 - p0, p2 - p0
            t0, t1, t2 = vts[a[1]], vts[b[1]], vts[c[1]]
            du1, dv1 = t1[0] - t0[0], t1[1] - t0[1]
            du2, dv2 = t2[0] - t0[0], t2[1] - t0[1]
            det = du1 * dv2 - du2 * dv1
            if abs(det) < 1e-12:
                continue
            up += (e2 * du1 - e1 * du2) / det
    fn = np.linalg.norm(face)
    un = np.linalg.norm(up)
    if fn < 1e-9 or un < 1e-9:
        return None
    face /= fn
    up /= un
    up = up - face * (up @ face)
    un = np.linalg.norm(up)
    if un < 1e-6:
        return None
    up /= un
    xc = np.cross(up, face)
    xc /= np.linalg.norm(xc)
    return xc, up, face


def render(parts, size=SIZE, basis=None, roll=0.0):
    S = size * SS
    if basis is None:
        basis = face_basis(parts)
    if basis is not None and roll:
        xc, yc, zc = basis
        a = math.radians(roll)
        xr = xc * math.cos(a) + yc * math.sin(a)
        yr = -xc * math.sin(a) + yc * math.cos(a)
        basis = (xr, yr, zc)
    if basis is None:
        xc, yc, zc = np.eye(3)
    else:
        xc, yc, zc = basis
    all_v = []
    cache = {}
    for mesh_obj, tex, mask, WM in parts:
        text = mesh_obj.read().export("obj")
        vs, vts, vns, tris = parse_obj(text)
        w = (WM @ np.hstack([vs, np.ones((len(vs), 1))]).T).T[:, :3]
        px = w @ xc
        py = w @ yc
        pz = w @ zc
        cache[mesh_obj.path_id] = (vs, vts, vns, tris, px, py, pz)
        all_v.append(np.stack([px, py], 1))
    P = np.vstack(all_v)
    mn, mx = P.min(0), P.max(0)
    cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
    span = max(mx[0] - mn[0], mx[1] - mn[1]) * 1.12
    scale = S / span

    img = np.zeros((S, S, 4), np.float32)
    zbuf = np.full((S, S), -1e18, np.float32)
    L = np.array([-0.25, 0.45, 0.85])
    L = L / np.linalg.norm(L)

    for mesh_obj, tex, mask, WM in parts:
        if tex is None:
            continue
        tarr = np.asarray(tex, np.float32) / 255.0
        TH, TW = tarr.shape[:2]
        vs, vts, vns, tris, sx0, sy0, sz = cache[mesh_obj.path_id]
        wn = (WM[:3, :3] @ vns.T).T
        nx = wn @ xc
        ny = wn @ yc
        nz = wn @ zc
        sx = (sx0 - cx) * scale + S / 2
        sy = S / 2 - (sy0 - cy) * scale
        for (a, b, c) in tris:
            ia, ib, ic = a[0], b[0], c[0]
            ta, tb, tc = a[1], b[1], c[1]
            x0, y0, z0 = sx[ia], sy[ia], sz[ia]
            x1, y1, z1 = sx[ib], sy[ib], sz[ib]
            x2, y2, z2 = sx[ic], sy[ic], sz[ic]
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-9:
                continue
            xmin = max(int(min(x0, x1, x2)), 0)
            xmax = min(int(max(x0, x1, x2)) + 1, S - 1)
            ymin = max(int(min(y0, y1, y2)), 0)
            ymax = min(int(max(y0, y1, y2)) + 1, S - 1)
            if xmin > xmax or ymin > ymax:
                continue
            xs_ = np.arange(xmin, xmax + 1) + 0.5
            ys_ = np.arange(ymin, ymax + 1) + 0.5
            gx, gy = np.meshgrid(xs_, ys_)
            w0 = ((x1 - gx) * (y2 - gy) - (x2 - gx) * (y1 - gy)) / area
            w1 = ((x2 - gx) * (y0 - gy) - (x0 - gx) * (y2 - gy)) / area
            w2 = ((x0 - gx) * (y1 - gy) - (x1 - gx) * (y0 - gy)) / area
            m_ = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not m_.any():
                continue
            pz = w0 * z0 + w1 * z1 + w2 * z2
            sub_z = zbuf[ymin:ymax + 1, xmin:xmax + 1]
            upd = m_ & (pz > sub_z)
            if not upd.any():
                continue
            n = np.stack([w0 * nx[ia] + w1 * nx[ib] + w2 * nx[ic],
                          w0 * ny[ia] + w1 * ny[ib] + w2 * ny[ic],
                          w0 * nz[ia] + w1 * nz[ib] + w2 * nz[ic]], -1)
            nl = np.linalg.norm(n, axis=-1)
            nl[nl == 0] = 1
            n = n / nl[..., None]
            back = n[:, :, 2] > 0
            n[back] *= -1
            ndl = np.clip((n * L).sum(-1), 0, 1)
            shade = 0.92 + 0.08 * ndl
            uu = w0 * vts[ta, 0] + w1 * vts[tb, 0] + w2 * vts[tc, 0]
            vv = w0 * vts[ta, 1] + w1 * vts[tb, 1] + w2 * vts[tc, 1]
            px_ = np.clip((uu * (TW - 1)).round().astype(int), 0, TW - 1)
            py_ = np.clip(((1 - vv) * (TH - 1)).round().astype(int), 0, TH - 1)
            col = tarr[py_, px_]
            upd &= col[:, :, 3] >= 0.5
            if not upd.any():
                continue
            out = img[ymin:ymax + 1, xmin:xmax + 1]
            for ch in range(3):
                cv = col[:, :, ch] * shade
                out[:, :, ch][upd] = cv[upd]
            out[:, :, 3][upd] = 1.0
            sub_z[upd] = pz[upd]

    im = Image.fromarray((img * 255).astype(np.uint8), "RGBA")
    im = im.resize((size, size), Image.LANCZOS)
    im = apply_bloom(im)
    a = np.array(im)
    ys, xs = np.where(a[:, :, 3] > 8)
    if len(xs) == 0:
        return None
    pad = 6
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, size - 1)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, size - 1)
    side = max(x1 - x0, y1 - y0)
    cx0, cy0 = (x0 + x1) // 2, (y0 + y1) // 2
    half = side // 2 + 1
    box = (cx0 - half, cy0 - half, cx0 + half + 1, cy0 + half + 1)
    im = im.crop(box)
    side = im.width
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, (0, 0), im)
    return canvas


def render_pailing_icons(bundle_path, out_dir):
    """渲染牌灵图标。bundle_path: 主 bundle 路径, out_dir: 输出目录 (site/icons/)。"""
    from pathlib import Path as _Path
    am = AssetsManager()
    bundle_path = _Path(bundle_path)
    for ms_bf in bundle_path.parent.glob("*_monoscripts_*.bundle"):
        am.load_file(str(ms_bf))
        break
    bf = am.load_file(str(bundle_path))
    cab_keys = [k for k in bf.files if k.startswith("CAB-")]
    env = bf.files[cab_keys[0]]
    objs = {o.path_id: o for o in env.objects.values()}

    pls = []
    for o in objs.values():
        if o.type.name != "MonoBehaviour":
            continue
        try:
            d = o.read()
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
        except Exception:
            continue
        if sn == "PaiLingPayload":
            pls.append(d)

    pailing_dir = out_dir / "pailing"
    pailing_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    for d in sorted(pls, key=lambda x: int(getattr(x, "id", 0) or 0)):
        pid = int(getattr(d, "id", 0) or 0)
        if pid < 10000:
            continue
        lm = getattr(d, "lingModel", None)
        gpid = getattr(lm, "path_id", None) if lm is not None else None
        if not gpid or gpid not in objs:
            print(f"{pid}: no lingModel")
            continue
        parts = collect_parts(objs, gpid)
        if not parts:
            print(f"{pid}: no mesh parts")
            continue
        im = render(parts, roll=ROLL.get(pid, 0.0),
                    basis=face_basis(parts, FACE_ANCHOR.get(pid)) if pid in FACE_ANCHOR else None)
        if im is None:
            print(f"{pid}: render empty")
            continue
        im.save(pailing_dir / f"{pid}.png")
        ok += 1
        print(f"{pid}: rendered {im.size} parts={len(parts)}")
    print(f"pailing: ok={ok}")
    return ok


# ============================================================
# 其余图标提取函数
# ============================================================
def extract_achievement_icons():
    out_dir = SITE_DIR / "icons" / "achievements"
    out_dir.mkdir(parents=True, exist_ok=True)
    bpath = BUNDLE_PATH
    if not bpath:
        print("  [WARN] bundle not found, skip achievement icons")
        return
    am = AssetsManager()
    bf = am.load_file(str(bpath))
    sf = bf.files[list(bf.files.keys())[0]]
    count = 0
    seen = set()
    for cpath, pp in sf.container.items():
        if "/Achievement/" not in cpath or not cpath.endswith(".png"):
            continue
        m = re.search(r"AchievementIcon(\d+)", cpath)
        if not m:
            continue
        icon_id = int(m.group(1))
        if icon_id in seen:
            continue
        seen.add(icon_id)
        try:
            obj = pp.read()
            img = obj.image
            img.save(str(out_dir / f"{icon_id}.png"))
            count += 1
        except Exception:
            continue
    print(f"  achievement icons: {count} extracted to {out_dir}")


def extract_lingyong_icons():
    out_dir = SITE_DIR / "icons"
    (out_dir / "lingyong").mkdir(parents=True, exist_ok=True)
    (out_dir / "lingyong_BOSS").mkdir(parents=True, exist_ok=True)

    bpath = BUNDLE_PATH
    if not bpath:
        print("  [WARN] bundle not found, skip lingyong icons")
        return
    am = AssetsManager()
    for ms_bf in AA_DIR.glob("*_monoscripts_*.bundle"):
        am.load_file(str(ms_bf))
        break
    bf = am.load_file(str(bpath))
    cab_keys = [k for k in bf.files if k.startswith("CAB-")]
    sf = bf.files[cab_keys[0]]

    sprite_map = {}
    for obj in sf.objects.values():
        if obj.type.name == "Sprite":
            try:
                d = obj.read()
                nm = getattr(d, "m_Name", "")
                if nm:
                    sprite_map[nm] = obj
            except Exception:
                pass

    count = 0
    seen = set()

    def _save_icon(xid, sub):
        nonlocal count
        if xid in seen or xid == 0 or not sub:
            return
        if sub not in sprite_map:
            return
        if 20000 <= xid < 30000:
            return
        seen.add(xid)
        try:
            img = sprite_map[sub].read().image
            if (10000 <= xid < 20000) or (30000 <= xid < 40000):
                target = out_dir / "lingyong_BOSS"
            else:
                target = out_dir / "lingyong"
            img.save(str(target / f"{xid}.png"))
            count += 1
        except Exception:
            pass

    for obj in sf.objects.values():
        if obj.type != ClassIDType.MonoBehaviour:
            continue
        try:
            d = obj.read()
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "XiaoChouPaiPayload":
                continue
            xid = int(getattr(d, "id", 0) or 0)
            ic = getattr(d, "iconReference", None)
            if ic is None:
                continue
            sub = getattr(ic, "m_SubObjectName", "") or ""
            _save_icon(xid, sub)
        except Exception:
            continue

    env1 = UnityPy.load(str(SHARED1))
    for obj in env1.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            d = obj.read(check_read=False)
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "XiaoChouPaiPayload":
                continue
            raw = obj.get_raw_data()
            pd = rp.parse_payload(raw, "XiaoChouPaiPayload")
            xid = int(pd.get("id", 0))
            ic = pd.get("iconReference") or {}
            sub = ic.get("sub", "")
            _save_icon(xid, sub)
        except Exception:
            continue

    env4 = UnityPy.load(str(SHARED4))
    for obj in env4.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            d = obj.read(check_read=False)
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "XiaoChouPaiPayload":
                continue
            raw = obj.get_raw_data()
            pd = rp.parse_payload(raw, "XiaoChouPaiPayload")
            xid = int(pd.get("id", 0))
            ic = pd.get("iconReference") or {}
            sub = ic.get("sub", "")
            _save_icon(xid, sub)
        except Exception:
            continue

    print(f"  lingyong icons: {count} extracted")


def extract_character_avatars():
    out_dir = SITE_DIR / "icons" / "character"
    out_dir.mkdir(parents=True, exist_ok=True)

    env4 = UnityPy.load(str(SHARED4))
    count = 0
    for obj in env4.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            d = obj.read(check_read=False)
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "RoleAvatar":
                continue
            raw = obj.get_raw_data()
            pd = rp.parse_payload(raw, "RoleAvatar")
            cid = int(pd.get("characterID", 0))
            if cid == 0:
                continue
            hi = pd.get("headIcon") or {}
            pid = hi.get("path_id", 0)
            if pid == 0:
                continue
            for io in env4.objects:
                if io.path_id == pid:
                    img = io.read().image
                    img.save(str(out_dir / f"{cid}.png"))
                    count += 1
                    break
        except Exception:
            continue
    print(f"  character avatars: {count} extracted")


def extract_character_skill_icons():
    out_dir = SITE_DIR / "icons" / "character_skill"
    out_dir.mkdir(parents=True, exist_ok=True)

    bpath = BUNDLE_PATH
    if not bpath:
        print("  [WARN] bundle not found, skip character skill icons")
        return
    am = AssetsManager()
    for ms_bf in AA_DIR.glob("*_monoscripts_*.bundle"):
        am.load_file(str(ms_bf))
        break
    bf = am.load_file(str(bpath))
    cab_keys = [k for k in bf.files if k.startswith("CAB-")]
    sf = bf.files[cab_keys[0]]

    sprite_map = {}
    sprite_by_lower = {}
    for obj in sf.objects.values():
        if obj.type.name == "Sprite":
            try:
                d = obj.read()
                nm = getattr(d, "m_Name", "")
                if nm:
                    sprite_map[nm] = obj
                    if nm.lower().startswith("iconskill"):
                        sprite_by_lower[nm.lower()] = obj
            except Exception:
                pass

    count = 0
    seen = set()

    def _save_passive(xid, sub, mname=""):
        nonlocal count
        # 角色主动和被动 xid 是 20000~30000
        if xid < 20000 or xid in seen or xid > 30000:
            return
        obj = None
        if sub and sub in sprite_map:
            obj = sprite_map[sub]
        elif not sub and mname:
            base = re.sub(r"\d+$", "", mname)
            predicted = f"IconSkill{base}".lower()
            if predicted in sprite_by_lower:
                obj = sprite_by_lower[predicted]
        if obj is None:
            return
        seen.add(xid)
        try:
            img = obj.read().image
            img.save(str(out_dir / f"{xid}_passive.png"))
            count += 1
        except Exception:
            pass

    for obj in sf.objects.values():
        if obj.type != ClassIDType.MonoBehaviour:
            continue
        try:
            d = obj.read()
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "XiaoChouPaiPayload":
                continue
            xid = int(getattr(d, "id", 0) or 0)
            ic = getattr(d, "iconReference", None)
            if ic is None:
                continue
            sub = getattr(ic, "m_SubObjectName", "") or ""
            mname = getattr(d, "m_Name", "") or ""
            _save_passive(xid, sub, mname)
        except Exception:
            continue

    env4 = UnityPy.load(str(SHARED4))
    for obj in env4.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            d = obj.read(check_read=False)
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "XiaoChouPaiPayload":
                continue
            raw = obj.get_raw_data()
            pd = rp.parse_payload(raw, "XiaoChouPaiPayload")
            xid = int(pd.get("id", 0))
            ic = pd.get("iconReference") or {}
            sub = ic.get("sub", "")
            mname = pd.get("m_Name", "")
            _save_passive(xid, sub, mname)
        except Exception:
            continue
    print(f"  character skill icons: {count} extracted")


def extract_relic_icons():
    out_dir = SITE_DIR / "icons" / "relics"
    out_dir.mkdir(parents=True, exist_ok=True)

    env4 = UnityPy.load(str(SHARED4))
    count = 0
    seen = set()

    pid_map = {o.path_id: o for o in env4.objects}

    def _save_icon(did, io):
        nonlocal count
        if did in seen:
            return
        try:
            d = io.read()
            if hasattr(d, "image"):
                img = d.image
            elif io.type.name == "Texture2D":
                img = d.image
            else:
                return
            img.save(str(out_dir / f"{did}.png"))
            count += 1
            seen.add(did)
        except Exception:
            pass

    list_names = ["RelicDisplayList", "RelicDisplayMysteriousList", "RelicDisplayOutsiderList"]
    for ln in list_names:
        for obj in env4.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                d = obj.read(check_read=False)
                ms = getattr(d, "m_Script", None)
                sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
                if sn != ln:
                    continue
                raw = obj.get_raw_data()
                _, _, _, _, pos = rp.mb_header(raw)
                vals = rp.parse_fields(raw, pos, [("value", "vp")])["value"]
                for ref in vals:
                    rpid = (ref or {}).get("path_id")
                    if not rpid or rpid not in pid_map:
                        continue
                    ro = pid_map[rpid]
                    try:
                        rraw = ro.get_raw_data()
                        rd = rp.parse_payload(rraw, "RelicDisplay")
                        did = int(rd.get("displayId", 0))
                        if did == 0 or did in seen:
                            continue
                        icon = rd.get("icon") or {}
                        ipid = icon.get("path_id", 0)
                        fid = icon.get("file_id", 0)
                        if ipid == 0 or fid != 0:
                            continue
                        if ipid in pid_map:
                            _save_icon(did, pid_map[ipid])
                    except Exception:
                        pass
            except Exception:
                continue

    bpath = BUNDLE_PATH
    if bpath:
        am = AssetsManager()
        for ms_bf in AA_DIR.glob("*_monoscripts_*.bundle"):
            am.load_file(str(ms_bf))
            break
        bf = am.load_file(str(bpath))
        cab_keys = [k for k in bf.files if k.startswith("CAB-")]
        sf = bf.files[cab_keys[0]]

        for obj in sf.objects.values():
            if obj.type != ClassIDType.MonoBehaviour:
                continue
            try:
                d = obj.read()
                ms = getattr(d, "m_Script", None)
                sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
                if not sn.endswith("Display"):
                    continue
                did = int(getattr(d, "displayId", 0) or 0)
                if did == 0 or did in seen:
                    continue
                icon = getattr(d, "icon", None)
                if icon is None:
                    continue
                ipid = getattr(icon, "path_id", 0)
                fid = getattr(icon, "m_FileID", 0)
                if ipid == 0 or fid != 0:
                    continue
                for io in sf.objects.values():
                    if io.path_id == ipid:
                        _save_icon(did, io)
                        break
            except Exception:
                continue

    print(f"  relic icons: {count} extracted")


def extract_offering_icons():
    out_dir = SITE_DIR / "icons" / "offerings"
    out_dir.mkdir(parents=True, exist_ok=True)

    env1 = UnityPy.load(str(SHARED1))
    count = 0
    seen = set()
    for obj in env1.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            d = obj.read(check_read=False)
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "OfferingPayload":
                continue
            raw = obj.get_raw_data()
            pd = rp.parse_payload(raw, "OfferingPayload")
            did = int(pd.get("displayId", 0))
            if did == 0 or did in seen:
                continue
            seen.add(did)
            icon = pd.get("icon") or {}
            ipid = icon.get("path_id", 0)
            fid = icon.get("file_id", 0)
            if ipid == 0 or fid != 0:
                continue
            for io in env1.objects:
                if io.path_id == ipid:
                    img = io.read().image
                    img.save(str(out_dir / f"{did}.png"))
                    count += 1
                    break
        except Exception:
            continue
    print(f"  offering icons: {count} extracted")


def extract_offering_skill_icons():
    out_dir = SITE_DIR / "icons" / "character_skill"
    out_dir.mkdir(parents=True, exist_ok=True)

    env4 = UnityPy.load(str(SHARED4))
    env1 = UnityPy.load(str(SHARED1))
    other_envs = []
    for sa in [SHARED0, SHARED2, SHARED3]:
        if sa.exists():
            other_envs.append(UnityPy.load(str(sa)))
    count = 0
    seen = set()
    for obj in env4.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            d = obj.read(check_read=False)
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "OfferingPayload":
                continue
            raw = obj.get_raw_data()
            pd = rp.parse_payload(raw, "OfferingPayload")
            did = int(pd.get("displayId", 0))
            if did < 20000 or did in seen:
                continue
            seen.add(did)
            icon = pd.get("icon") or {}
            ipid = icon.get("path_id", 0)
            fid = icon.get("file_id", 0)
            if ipid == 0:
                continue
            resolved = False
            envs_to_try = [env4] if fid == 0 else [env1] + other_envs
            for e in envs_to_try:
                for io in e.objects:
                    if io.path_id == ipid:
                        try:
                            img = io.read().image
                            img.save(str(out_dir / f"{did}_active.png"))
                            count += 1
                            resolved = True
                        except Exception:
                            pass
                        break
                if resolved:
                    break
        except Exception:
            continue
    print(f"  offering skill icons: {count} extracted")


def extract_baopai_icons():
    out_dir = SITE_DIR / "icons" / "baopai"
    out_dir.mkdir(parents=True, exist_ok=True)

    bpath = BUNDLE_PATH
    if not bpath:
        print("  [WARN] bundle not found, skip baopai icons")
        return
    am = AssetsManager()
    for ms_bf in AA_DIR.glob("*_monoscripts_*.bundle"):
        am.load_file(str(ms_bf))
        break
    bf = am.load_file(str(bpath))
    cab_keys = [k for k in bf.files if k.startswith("CAB-")]
    sf = bf.files[cab_keys[0]]

    count = 0
    for obj in sf.objects.values():
        if obj.type != ClassIDType.MonoBehaviour:
            continue
        try:
            d = obj.read()
            ms = getattr(d, "m_Script", None)
            sn = getattr(ms.read(), "m_ClassName", "?") if ms else "?"
            if sn != "BaoPaiPayload":
                continue
            bid = int(getattr(d, "id", 0) or 0)
            if bid == 0:
                continue

            baoMaterialMask = getattr(d, "baoMaterialMask", None)
            if not baoMaterialMask:
                continue
            bpid = getattr(baoMaterialMask, "path_id", 0)
            if not bpid:
                continue

            bg_arr = None
            mask_arr = None

            for bo in sf.objects.values():
                if bo.path_id == bpid:
                    bd = bo.read()
                    props = bd.m_SavedProperties
                    texenvs = getattr(props, "m_TexEnvs", None)
                    for texenv in texenvs:
                        name = texenv[0]
                        tex = texenv[1].m_Texture
                        tpid = getattr(tex, "path_id", 0)
                        if tpid:
                            for to in sf.objects.values():
                                if to.path_id == tpid:
                                    td = to.read()
                                    img = td.image
                                    if name == "_MainTex":
                                        bg_arr = np.array(img)[:, :, :3].astype(np.float32)
                                    elif name == "_MaskTex":
                                        mask_arr = np.array(img).astype(np.float32)
                                    break
                    break

            if bg_arr is None or mask_arr is None:
                continue

            if bg_arr.shape[0] != 512 or bg_arr.shape[1] != 512:
                bg_img = Image.fromarray(bg_arr.astype(np.uint8)).resize((512, 512), Image.LANCZOS)
                bg_arr = np.array(bg_img).astype(np.float32)

            blue = mask_arr[:, :, 2] / 255.0
            card_mask = blue > 0.1
            ys, xs = np.where(card_mask)
            y_min, y_max = ys.min(), ys.max()
            x_min, x_max = xs.min(), xs.max()

            output = np.zeros((512, 512, 3), dtype=np.float32)
            output[card_mask] = bg_arr[card_mask]

            red = mask_arr[:, :, 0] / 255.0

            red_img = Image.fromarray((mask_arr[:, :, 0]).astype(np.uint8))
            dilated = red_img.filter(ImageFilter.MaxFilter(7))
            eroded = red_img.filter(ImageFilter.MinFilter(5))
            outline = np.array(dilated).astype(np.float32) - np.array(eroded).astype(np.float32)
            outline = np.clip(outline, 0, 255) / 255.0

            white = np.ones((512, 512, 3), dtype=np.float32) * 240
            dark = np.ones((512, 512, 3), dtype=np.float32) * 30

            output = output * (1 - red[:, :, np.newaxis]) + white * red[:, :, np.newaxis]
            output = output * (1 - outline[:, :, np.newaxis]) + dark * outline[:, :, np.newaxis]

            cropped = output[y_min:y_max + 1, x_min:x_max + 1]
            cropped_img = Image.fromarray(cropped.astype(np.uint8))
            w, h = cropped_img.size
            target_h = 350
            target_w = int(w * target_h / h)
            final = cropped_img.resize((target_w, target_h), Image.LANCZOS)
            final.save(str(out_dir / f"{bid}.png"))
            count += 1
        except Exception:
            continue
    print(f"  baopai icons: {count} extracted")


def composite_skill_icons():
    """把角色技能 icon 合成到底图上，覆盖 icons/character_skill/。"""
    assets = Path(__file__).resolve().parent.parent / "assets"
    bg_passive = Image.open(assets / "skill_bg" / "SelectPopBgA11.png").convert("RGBA")
    bg_active = Image.open(assets / "skill_bg" / "SelectPopBgA12.png").convert("RGBA")
    icons_dir = SITE_DIR / "icons" / "character_skill"
    if not icons_dir.exists():
        return
    bg_w, bg_h = bg_passive.size
    center_x, center_y = bg_w // 2, int(bg_h * 0.585)
    circle_radius = 85
    count = 0
    for p in icons_dir.glob("*.png"):
        if "_passive.png" in p.name:
            bg = bg_passive
        elif "_active.png" in p.name:
            bg = bg_active
        else:
            continue
        try:
            icon = Image.open(p).convert("RGBA")
            iw, ih = icon.size
            scale = (circle_radius * 2) / max(iw, ih)
            icon_resized = icon.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
            result = bg.copy()
            x = center_x - icon_resized.width // 2
            y = center_y - icon_resized.height // 2
            result.paste(icon_resized, (x, y), icon_resized)
            result.save(p)
            count += 1
        except Exception:
            pass
    print(f"  skill icons composited: {count}")
