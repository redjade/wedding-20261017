# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=11.0"]
# ///
"""원본 사진(images-full-size)을 웹용 크기로 줄이고 docs/photos.js 목록을 만든다.

    uv run tools/build_photos.py            # 새로 넣었거나 바뀐 사진만 만든다
    uv run tools/build_photos.py --force    # 전부 다시 만든다

- 긴 변 800 / 1600 / 2560px 세 벌을 docs/img/<크기>/ 아래에 만든다.
- 세로 사진은 바로 세우고, EXIF(촬영 위치 포함)는 모두 지운다.
- 순서는 촬영 시각 → 파일 이름.
- 원본 폴더에서 뺀 사진은 docs/img 에서도 지운다.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageCms, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "images-full-size"
DOCS = ROOT / "docs"
OUT = DOCS / "img"

# 긴 변 px → JPEG 품질. 800은 목록, 1600·2560은 크게 보기·슬라이드 쇼에 쓴다.
SIZES = {800: 84, 1600: 86, 2560: 90}

# 카카오톡 등 링크 미리보기에 쓸 사진(확장자 없는 파일 이름). None이면 첫 가로 사진.
OG_PHOTO: str | None = "DSC_3548"
# 카카오톡·텔레그램은 정사각형을 줘도 가운데 1.91:1 띠만 보여 주므로 처음부터 그 비율로 만든다.
OG_SIZE = (1200, 630)
# 미리보기 사진을 어디쯤에서 자를지(가로, 세로 0~1). 세로 사진은 세로 값을 낮추면 위쪽이 남는다.
OG_CENTER = (0.5, 0.3)
# 세로 사진에서 담을 위아래 범위(사진 높이에 대한 비율). 띠보다 길면 줄여 가운데 두고,
# 좌우 빈 곳은 같은 사진을 흐리게 깔아 채운다. None이면 OG_CENTER 기준으로 꽉 차게 자른다.
OG_RANGE: tuple[float, float] | None = (0.15, 0.66)

EXTS = {".jpg", ".jpeg"}


def taken_at(im: Image.Image) -> str:
    exif = im.getexif()
    sub = exif.get_ifd(0x8769)
    return f"{sub.get(36867) or exif.get(306) or ''}.{sub.get(0x9291) or '00'}"


def load_upright(path: Path) -> Image.Image:
    im = Image.open(path)
    icc = im.info.get("icc_profile")
    im = ImageOps.exif_transpose(im).convert("RGB")
    if icc:
        # sRGB가 아닌 프로파일(Adobe RGB 등)은 sRGB로 바꿔 색이 틀어지지 않게 한다.
        try:
            im = ImageCms.profileToProfile(
                im, ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile("sRGB")
            )
        except ImageCms.PyCMSError:
            pass
    return im


def fit(size: tuple[int, int], long_edge: int) -> tuple[int, int]:
    w, h = size
    scale = min(1.0, long_edge / max(w, h))
    return max(1, round(w * scale)), max(1, round(h * scale))


def process(args: tuple[str, bool]) -> dict:
    path, force = Path(args[0]), args[1]
    stem = path.stem
    targets = {s: OUT / str(s) / f"{stem}.jpg" for s in SIZES}
    largest, smallest = targets[max(SIZES)], targets[min(SIZES)]
    mtime = path.stat().st_mtime
    fresh = not force and all(t.exists() and t.stat().st_mtime >= mtime for t in targets.values())

    with Image.open(path) as head:
        when = taken_at(head)

    if not fresh:
        im = load_upright(path)
        for s in sorted(SIZES, reverse=True):
            # 큰 것부터 차례로 줄여 나가면 빠르고 결과도 깨끗하다.
            im = im.resize(fit(im.size, s), Image.Resampling.LANCZOS, reducing_gap=3.0)
            targets[s].parent.mkdir(parents=True, exist_ok=True)
            im.save(targets[s], "JPEG", quality=SIZES[s], optimize=True, progressive=True)

    with Image.open(largest) as big:
        w, h = big.size
    with Image.open(smallest) as small:
        r, g, b = small.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))

    return {"n": stem, "w": w, "h": h, "c": f"#{r:02x}{g:02x}{b:02x}", "t": when, "made": not fresh}


def prune(keep: set[str]) -> int:
    removed = 0
    for s in SIZES:
        for f in (OUT / str(s)).glob("*.jpg"):
            if f.stem not in keep:
                f.unlink()
                removed += 1
    return removed


def make_og(photos: list[dict]) -> str | None:
    name = OG_PHOTO or next((p["n"] for p in photos if p["w"] > p["h"]), None)
    if not name or name not in {p["n"] for p in photos}:
        return None
    with Image.open(OUT / str(max(SIZES)) / f"{name}.jpg") as im:
        og = ImageOps.fit(im, OG_SIZE, Image.Resampling.LANCZOS, centering=OG_CENTER)
        if OG_RANGE:
            top, bottom = (round(im.height * f) for f in OG_RANGE)
            part = im.crop((0, top, im.width, bottom))
            w = round(part.width * OG_SIZE[1] / part.height)
            if w < OG_SIZE[0]:
                og = ImageEnhance.Brightness(og.filter(ImageFilter.GaussianBlur(36))).enhance(0.92)
                og.paste(part.resize((w, OG_SIZE[1]), Image.Resampling.LANCZOS), ((OG_SIZE[0] - w) // 2, 0))
        og.save(DOCS / "og.jpg", "JPEG", quality=85, optimize=True, progressive=True)
    return name


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="이미 만든 사진도 전부 다시 만든다")
    opts = ap.parse_args()

    sources = sorted(p for p in SRC.iterdir() if p.suffix.lower() in EXTS)
    if not sources:
        print(f"사진이 없습니다: {SRC}", file=sys.stderr)
        return 1

    with ProcessPoolExecutor() as pool:
        photos = []
        for i, info in enumerate(pool.map(process, [(str(p), opts.force) for p in sources]), 1):
            photos.append(info)
            print(f"\r{i}/{len(sources)} {info['n']}", end="", flush=True)
    print()

    photos.sort(key=lambda p: (p["t"], p["n"]))
    made = sum(p.pop("made") for p in photos)
    for p in photos:
        del p["t"]

    removed = prune({p["n"] for p in photos})
    og = make_og(photos)

    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").touch()
    (DOCS / "photos.js").write_text(
        f"window.PHOTO_SIZES = {json.dumps(sorted(SIZES))};\n"
        f"window.PHOTOS = {json.dumps(photos, separators=(',', ':'))};\n",
        encoding="utf-8",
    )

    total = sum(f.stat().st_size for f in OUT.rglob("*.jpg")) / 1e6
    print(f"사진 {len(photos)}장 (새로 만든 것 {made}장, 지운 파일 {removed}개)")
    for s in sorted(SIZES):
        mb = sum(f.stat().st_size for f in (OUT / str(s)).glob("*.jpg")) / 1e6
        print(f"  {s:>5}px  {mb:7.1f} MB  (장당 평균 {mb * 1000 / len(photos):.0f} KB)")
    print(f"  합계     {total:7.1f} MB")
    print(f"미리보기 사진(og.jpg): {og or '없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
