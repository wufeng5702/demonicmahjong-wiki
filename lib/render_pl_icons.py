#!/usr/bin/env python3
"""
牌灵图标渲染器: 从 bundle 提取 lingModel 3D 模型 (Mesh+材质贴图),
软件光栅化正交渲染生成收集页风格头像图标 → site/icons/pailing/{id}.png
"""
import math
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

import numpy as np
from PIL import Image, ImageFilter

import UnityPy

SIZE = 512
SS = 2  # 超采样倍数


def apply_bloom(im, threshold=0.55, blur_radius=14, intensity=0.55):
    """Bloom 后处理: 提取亮部 → 高斯模糊 → 叠加回原图"""
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


# ---------- 变换 ----------
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


# ---------- OBJ 解析 ----------
def parse_obj(text):
    vs, vts, vns, tris = [], [], [], []
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
        elif line.startswith("f "):
            idx = []
            for tok in line.split()[1:]:
                a = tok.split("/")
                vi = int(a[0]) - 1
                ti = int(a[1]) - 1 if len(a) > 1 and a[1] else vi
                ni = int(a[2]) - 1 if len(a) > 2 and a[2] else vi
                idx.append((vi, ti, ni))
            for k in (1, 2):
                tris.append((idx[0], idx[k], idx[k + 1] if k + 1 < len(idx) else None))
    # 修正三角扇
    tris = []
    for line in text.splitlines():
        if not line.startswith("f "):
            continue
            idx = []
        idx = []
        for tok in line.split()[1:]:
            a = tok.split("/")
            vi = int(a[0]) - 1
            ti = int(a[1]) - 1 if len(a) > 1 and a[1] else vi
            ni = int(a[2]) - 1 if len(a) > 2 and a[2] else vi
            idx.append((vi, ti, ni))
        for k in range(1, len(idx) - 1):
            tris.append((idx[0], idx[k], idx[k + 1]))
    return (np.array(vs, np.float64), np.array(vts, np.float64).reshape(-1, 2),
            np.array(vns, np.float64).reshape(-1, 3), tris)


# ---------- 收集模型部件 ----------
def collect_parts(objs, root_pid):
    """从 lingModel 根遍历, 返回 [(mesh_obj, main_tex, mask_tex, world_M)]"""
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


# 无 _MaskTex 的模型: 手动指定眼部 UV 锚点 (u, v)；可给多个锚点(左右眼)取法线对称轴
FACE_ANCHOR = {10036: [(0.5615, 0.5850), (0.8398, 0.5508)], 10037: (0.68, 0.62)}
# 每模型附加滚转角(度) — 修正 UV 竖排导致的 roll
ROLL = {10015: 5, 10025: -5, 10028: 6, 10030: -5, 10036: 202, 10037: 90}


def face_basis(parts, anchor=None):
    """E 遮罩亮点定位眼部 → 脸朝向 + 头顶方向 → 相机基 (x,y,z)
    anchor 可为单个 (u,v) 或多个锚点列表(如左右眼), 法线取对称轴平均"""
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
        # 收集脸部三角形 (UV 质心靠近锚点, 半径渐扩)
        sel = []
        r = 0.05
        while r <= 0.45 and len(sel) < 24:
            sel = [t for t in tris
                   if np.linalg.norm((vts[t[0][1]] + vts[t[1][1]] + vts[t[2][1]]) / 3 - [mu, mv]) < r]
            r *= 1.5
        for (a, b, c) in sel:
            face += wn[a[2]] + wn[b[2]] + wn[c[2]]
            # +V 纹理方向对应的 3D 方向 (bitangent)
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


# ---------- 光栅化 ----------
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
    # 先变换所有顶点求包围盒
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

    # 相机空间光照: 前-上-左
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
            # 法线(双面: 统一朝向相机)
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
            # UV
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
    # 裁剪内容
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


# ---------- 主流程 ----------
def render_pailing_icons(bundle_path, out_dir):
    """渲染牌灵图标。bundle_path: 主 bundle 路径, out_dir: 输出目录 (site/icons/)。"""
    env = UnityPy.load(str(bundle_path))
    objs = {o.path_id: o for o in env.objects}

    # 收集 PaiLingPayload
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


if __name__ == "__main__":
    import os
    from pathlib import Path
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    GAME_DIR = Path(os.environ.get("GAME_DIR", Path(__file__).parent.parent / "DemonicMahjong"))
    BUNDLE_DIR = GAME_DIR / "Demonic Mahjong_Data/StreamingAssets/aa/StandaloneWindows64"
    # 查找 defaultlocalgroup bundle
    bundle_path = None
    for f in BUNDLE_DIR.glob("defaultlocalgroup_*.bundle"):
        bundle_path = f
        break
    OUT_DIR = Path(__file__).parent.parent / "output" / "site" / "icons"
    render_pailing_icons(bundle_path, OUT_DIR)
