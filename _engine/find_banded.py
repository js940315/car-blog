#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정사각화하면서 흐린 띠가 박힌 사진을 찾아낸다 (2026-08-20 신설).

배경: 예전 smart_square/_pad_to_square 가 와이드 프레스컷을 정사각으로
만들면서 위아래(또는 좌우)를 **가장자리 띠를 늘려 흐리게** 채웠다.
assets/photos 539장이 전부 1400x1400 으로 그렇게 저장돼 있고 원본은 덮였다.
코드는 고쳤지만 기존분은 재소싱해야 해서, 멀쩡한 것과 망가진 것을 가른다.

판별 원리: 띠는 **몇 픽셀을 세로로 길게 늘려** 만든다. 그래서 띠 안에서는
위아래로 인접한 줄이 거의 같다(세로 변화량 ≈ 0). 진짜 사진은 그렇지 않다.
"""
import os
import sys

from PIL import Image

N = 160          # 판정용 축소 크기
FLAT = 1.2       # 이 값 미만이면 '늘려 만든 띠'로 본다 (0~255 기준)
SPIKE = 1.0      # 띠가 끝나는 자리의 단차
# 띠 크기 범위. _pad_to_square 가 만드는 띠는 (1 - 짧은변/긴변) / 2 다.
#   4:3 -> 12.5%   3:2 -> 17%   16:9 -> 22%   3:1 -> 33%
# 그래서 12% 미만은 애초에 띠가 아니고(원본이 거의 정사각), 35% 초과는
# 물리적으로 안 나온다 — 그건 단색 사진(국기·어두운 표지)이 평탄해서 잡힌 것이다.
MIN_BAND = 0.12
MAX_BAND = 0.35


def _profile(px, n, vertical=True):
    """줄마다 '다음 줄과 얼마나 다른가'를 잰다."""
    out = []
    for i in range(n - 1):
        s = 0
        for j in range(n):
            a = px[(j, i)] if vertical else px[(i, j)]
            b = px[(j, i + 1)] if vertical else px[(i + 1, j)]
            s += abs(a - b)
        out.append(s / n)
    return out


def _band_len(prof):
    """앞에서부터 평탄한 구간 + **그 끝에 이음매가 있는가**.

    평탄하기만 한 건 띠가 아니다 — 단색 국기·어두운 표지도 평탄하다(실측으로
    빨간 국기가 50%, 검은 책 표지가 61% 로 잡혔다). 진짜 띠는 원본을 그대로
    가운데 붙여서 만들기 때문에 **띠가 끝나는 자리에 급격한 단차**가 남는다.
    그 단차가 없으면 0을 돌려 띠가 아니라고 본다.
    """
    k = 0
    for v in prof:
        if v >= FLAT:
            break
        k += 1
    if k == 0 or k >= len(prof):
        return 0
    if prof[k] < SPIKE:          # 이음매 없음 = 그냥 평탄한 사진
        return 0
    return k


def inspect(path):
    im = Image.open(path).convert("L").resize((N, N), Image.BOX)
    px = im.load()
    res = {}
    for name, vert in (("세로", True), ("가로", False)):
        prof = _profile(px, N, vert)
        head = _band_len(prof)
        tail = _band_len(prof[::-1])
        res[name] = (head / N, tail / N)
    return res


def is_banded(res):
    for head, tail in res.values():
        for r in (head, tail):
            if MIN_BAND <= r <= MAX_BAND:
                return True
    return False


def main(folder):
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".jpg"))
    bad = []
    for f in files:
        try:
            r = inspect(os.path.join(folder, f))
        except Exception as e:
            print("  [건너뜀] %s: %s" % (f, e))
            continue
        if is_banded(r):
            v, h = r["세로"], r["가로"]
            bad.append((f, max(v[0], v[1], h[0], h[1])))
    bad.sort(key=lambda x: -x[1])
    print("검사 %d장 / 띠 있음 %d장 (%.0f%%)"
          % (len(files), len(bad), 100.0 * len(bad) / max(1, len(files))))
    for f, r in bad[:15]:
        print("   %-46s 띠 %.0f%%" % (f, r * 100))
    if len(bad) > 15:
        print("   ... 외 %d장" % (len(bad) - 15))
    return bad


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "assets/photos")
