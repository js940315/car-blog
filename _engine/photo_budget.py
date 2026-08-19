#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""차종별로 오늘 사진을 몇 장 쓸 수 있는지 알려준다 (2026-08-20 신설).

왜 필요한가: 사진 장수를 6장 고정에서 **있는 만큼(6~12장)** 으로 바꿨다.
글을 쓰기 전에 "이 차종은 몇 장까지 되는가"를 알아야 images 배열을 그만큼
설계할 수 있다. 모르면 예전처럼 6장으로 굳어진다.

사진이 모자란 차종도 같이 찍는다 — 나중에 그것만 골라 채우면 된다.

    python3 _engine/photo_budget.py             # 전체 현황
    python3 _engine/photo_budget.py 팰리세이드   # 그 차종만
"""
import io
import json
import os
import sys
from collections import Counter

for _s in (sys.stdout, sys.stderr):     # 윈도우 콘솔 기본 cp949 에서 깨진다
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, "assets", "photos", "index.json")

MIN, MAX = 6, 12


def counts():
    with open(INDEX, encoding="utf-8") as f:
        d = json.load(f)
    return Counter(v.get("카테고리", "?") for v in d.values())


def budget(n):
    """보유 n장일 때 이번 글에 쓸 장수."""
    return max(0, min(MAX, n))


def main(argv):
    c = counts()
    if argv:
        key = argv[0]
        hit = [(k, v) for k, v in c.items() if key in k]
        if not hit:
            print("그런 차종이 없다: %s" % key)
            return 1
        for k, v in sorted(hit, key=lambda x: -x[1]):
            b = budget(v)
            mark = "" if b >= MIN else "  ← 부족. 소싱 필요"
            print("%-16s 보유 %2d장 -> 이번 글 %2d장%s" % (k, v, b, mark))
        return 0

    short = [(k, v) for k, v in c.items() if v < MIN]
    full = [(k, v) for k, v in c.items() if v >= MAX]
    print("차종 %d개 / 사진 %d장" % (len(c), sum(c.values())))
    print("  %d장(최대)까지 쓸 수 있는 차종 : %d개" % (MAX, len(full)))
    print("  %d장(최소)도 안 되는 차종     : %d개" % (MIN, len(short)))
    if short:
        print("\n사진이 모자란 차종 — 여기부터 채우면 효과가 크다")
        for k, v in sorted(short, key=lambda x: x[1]):
            print("   %-16s %d장 (%d장 더 필요)" % (k, v, MIN - v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
