#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정사각화하며 붙은 흐린 띠를 잘라내 원본 비율을 되살린다 (2026-08-20 신설).

재소싱이 필요 없다. _pad_to_square 는 원본을 **가운데 그대로 붙이고** 남는
자리만 띠로 채웠다. 즉 띠만 잘라내면 원본이 그대로 나온다 — 다운로드 0회,
추가 화질 손실 0.

사용:
    python3 _engine/fix_banded.py assets/photos            # 몇 장인지만 본다
    python3 _engine/fix_banded.py assets/photos --apply    # 실제로 자른다
"""
import os
import shutil
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find_banded import MAX_BAND, MIN_BAND, N, inspect  # noqa: E402

MARGIN = 1.0 / N * 1.5   # 띠 경계를 조금 더 안쪽으로 — 잔띠가 남는 것보다 낫다


def _cut(ratio_head, ratio_tail, size):
    """양끝에서 잘라낼 픽셀 수. 띠로 인정되는 범위일 때만 자른다."""
    def px(r):
        return int(round((r + MARGIN) * size)) if MIN_BAND <= r <= MAX_BAND else 0
    return px(ratio_head), px(ratio_tail)


def fix(path, apply=False):
    res = inspect(path)
    im = Image.open(path).convert("RGB")
    w, h = im.size
    top, bot = _cut(*res["세로"], size=h)
    left, right = _cut(*res["가로"], size=w)
    if not (top or bot or left or right):
        return None
    box = (left, top, w - right, h - bot)
    if box[2] - box[0] < w * 0.3 or box[3] - box[1] < h * 0.3:
        return "너무 많이 잘림 — 건너뜀"
    out = im.crop(box)
    if apply:
        out.save(path, "JPEG", quality=94, subsampling=1)
    return "%dx%d -> %dx%d" % (w, h, out.width, out.height)


def main(folder, apply=False):
    if apply:
        bak = folder.rstrip("/\\") + "_banded_backup"
        os.makedirs(bak, exist_ok=True)
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".jpg"))
    done, skipped = 0, 0
    for f in files:
        p = os.path.join(folder, f)
        try:
            if apply:
                pre = inspect(p)
                from find_banded import is_banded
                if is_banded(pre):
                    shutil.copy2(p, os.path.join(bak, f))
            r = fix(p, apply)
        except Exception as e:
            print("  [건너뜀] %s: %s" % (f, e))
            continue
        if r is None:
            continue
        if r.startswith("너무"):
            skipped += 1
            print("  [보류] %s — %s" % (f, r))
        else:
            done += 1
            if done <= 10:
                print("  %-46s %s" % (f, r))
    print("%s %d장%s" % ("잘라냄" if apply else "자를 대상", done,
                        (" / 보류 %d장" % skipped) if skipped else ""))
    if not apply:
        print("실제로 자르려면 --apply 를 붙여라. 원본은 _banded_backup 에 복사한다.")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0] if args else "assets/photos", "--apply" in args)
