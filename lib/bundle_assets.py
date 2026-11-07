"""加载主 bundle 及更新后拆分到子目录的共享/UI bundle。"""
from types import SimpleNamespace

from UnityPy import AssetsManager

from config import AA_DIR, BUNDLE_PATH


def load_bundle_assets():
    am = AssetsManager()
    for path in AA_DIR.glob("*_monoscripts_*.bundle"):
        am.load_file(str(path))
        break
    objects, container = {}, {}
    paths = [BUNDLE_PATH]
    for pattern in ("shared_core*.bundle", "ui_icons*.bundle", "ui_event*.bundle"):
        paths.extend(sorted(AA_DIR.rglob(pattern)))
    for path in paths:
        bf = am.load_file(str(path))
        for key, sf in bf.files.items():
            if key.startswith("CAB-") and hasattr(sf, "objects"):
                objects.update(sf.objects)
                container.update(sf.container)
    return am, SimpleNamespace(objects=objects, container=container)
