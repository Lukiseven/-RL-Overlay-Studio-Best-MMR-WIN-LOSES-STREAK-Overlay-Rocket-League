from pathlib import Path
from collections import deque
from PIL import Image
import hashlib
import shutil
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PREVIEWS = ROOT / "media" / "previews"
PAGES_ASSETS = ROOT / "docs" / "assets"
PAGES_ASSETS.mkdir(parents=True, exist_ok=True)

def transparent_background(path: Path):
    im = Image.open(path).convert("RGBA")
    a = np.array(im)
    rgb = a[:, :, :3]
    h, w = rgb.shape[:2]
    mn = rgb.min(axis=2)
    mx = rgb.max(axis=2)
    candidate = (mn >= 215) & ((mx - mn) <= 18)

    seen = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        if candidate[0, x]:
            q.append((0, x)); seen[0, x] = True
        if candidate[h - 1, x] and not seen[h - 1, x]:
            q.append((h - 1, x)); seen[h - 1, x] = True
    for y in range(h):
        if candidate[y, 0] and not seen[y, 0]:
            q.append((y, 0)); seen[y, 0] = True
        if candidate[y, w - 1] and not seen[y, w - 1]:
            q.append((y, w - 1)); seen[y, w - 1] = True

    while q:
        y, x = q.popleft()
        for yy, xx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
            if 0 <= yy < h and 0 <= xx < w and candidate[yy, xx] and not seen[yy, xx]:
                seen[yy, xx] = True
                q.append((yy, xx))

    alpha = a[:, :, 3].astype(np.float32)
    soft = np.clip((255 - mn.astype(np.float32)) * 4.5, 0, 180)
    alpha[seen] = np.minimum(alpha[seen], soft[seen])
    alpha[seen & (mn >= 250)] = 0
    a[:, :, 3] = alpha.astype(np.uint8)

    out = Image.fromarray(a, "RGBA")
    bbox = out.getbbox()
    if bbox:
        l, t, r, b = bbox
        pad = max(24, int(min(w, h) * 0.035))
        out = out.crop((max(0,l-pad), max(0,t-pad), min(w,r+pad), min(h,b+pad)))
    out.save(path, optimize=True)
    shutil.copy2(path, PAGES_ASSETS / path.name)

for path in sorted(PREVIEWS.glob("*.png")):
    transparent_background(path)

# Refresh repository SHA-256 manifest after presentation changes.
manifest = []
skip = {
    "SOURCE_MANIFEST.sha256",
    ".github/workflows/prepare-presentation-assets.yml",
    "tools/prepare_presentation_assets.py",
}
for p in sorted(ROOT.rglob("*")):
    if not p.is_file():
        continue
    rel = p.relative_to(ROOT).as_posix()
    if rel in skip or rel.startswith(".git/"):
        continue
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest.append(f"{digest}  {rel}")
(ROOT / "SOURCE_MANIFEST.sha256").write_text("\n".join(manifest) + "\n", encoding="utf-8")

# One-shot helper: remove it and its workflow after the generated assets exist.
for rel in ["tools/prepare_presentation_assets.py", ".github/workflows/prepare-presentation-assets.yml"]:
    p = ROOT / rel
    if p.exists():
        p.unlink()
