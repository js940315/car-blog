#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본문 안 사진 마커를 고르게 다시 배치한다.

2026-08-16 사용자 지적: "사진 넣는 간격 좀 신경 써라. 마지막에는 그냥 쌩 글이고
위에는 간격이 너무 짧다." 실측(0816 슬롯1): 내용 34줄인데 마커 6개가 앞 22줄에
몰려 있고 **뒤 11줄이 통째로 사진 없이** 남았다.

원인은 생성기가 마커를 문단 흐름대로 찍기 때문이고, 8->6장으로 줄이면서
뒤쪽 마커(7·8번)를 지운 것이 겹쳤다.

    python _engine/respace_photos.py 0816            # 시뮬레이션
    python _engine/respace_photos.py 0816 --apply
"""
import argparse
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPACER = "⠀⠀⠀"
MARK = re.compile(r"^【(\d+)번 사진】$")


def split_body(raw):
    """(요소 리스트, 태그 리스트) 로 나눈다. 요소는 텍스트 또는 ('mark', n)."""
    lines = [l.rstrip() for l in raw.split("\n")]
    tags = []
    while lines and (not lines[-1].strip() or lines[-1].strip().startswith("#")):
        s = lines.pop().strip()
        if s.startswith("#"):
            tags.insert(0, s)
    elems = []
    for l in lines:
        s = l.strip()
        if not s or s == SPACER:
            continue
        m = MARK.match(s)
        elems.append(("mark", int(m.group(1))) if m else ("text", l))
    return elems, tags


def respace(elems, n_marks):
    """텍스트는 순서 그대로 두고 마커만 고르게 다시 꽂는다.

    1번은 제목 바로 뒤(도입 사진), 나머지는 남은 본문에 균등 배치한다.
    마커끼리 붙지 않게 하고, 마지막 마커 뒤에도 최소 2줄은 글이 남게 한다
    — 그래야 '사진으로 끝나는 글'이 안 된다.
    """
    texts = [e for e in elems if e[0] == "text"]
    t = len(texts)
    if t < 3 or n_marks < 1:
        return elems
    slots = [1]                                   # 제목(0) 다음
    rest = n_marks - 1
    if rest > 0:
        # 마지막 마커가 끝에서 최소 2줄 앞에 오도록 상한을 둔다
        hi = max(2, t - 2)
        step = (hi - 1) / (rest + 1)
        for k in range(1, rest + 1):
            p = int(round(1 + step * k))
            while p in slots and p < hi:          # 붙는 것 방지
                p += 1
            slots.append(min(p, hi))
    out, mi = [], 0
    for i, e in enumerate(texts):
        while mi < len(slots) and slots[mi] == i:
            out.append(("mark", mi + 1)); mi += 1
        out.append(e)
    while mi < len(slots):
        out.append(("mark", mi + 1)); mi += 1
    return out


def render(elems, tags):
    parts = [e[1] if e[0] == "text" else f"【{e[1]}번 사진】" for e in elems]
    body = f"\n{SPACER}\n".join(parts)
    return body + "\n" + SPACER + "\n" + "\n".join(tags) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="MMDD")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    base = os.path.join(ROOT, "output", a.date)
    print(f"=== {a.date} 사진 간격 재배치 " +
          ("(시뮬레이션)" if not a.apply else "(적용)") + " ===\n")

    for slot in sorted(os.listdir(base), key=lambda x: (len(x), x)):
        d = os.path.join(base, slot)
        p = os.path.join(d, "0번 본문.txt")
        if not os.path.isdir(d) or not os.path.exists(p):
            continue
        raw = io.open(p, encoding="utf-8").read()
        elems, tags = split_body(raw)
        n = sum(1 for e in elems if e[0] == "mark")
        new = respace(elems, n)
        before = [i for i, e in enumerate([x for x in elems]) if e[0] == "mark"]
        after = [i for i, e in enumerate(new) if e[0] == "mark"]
        texts = sum(1 for e in new if e[0] == "text")
        tail = len(new) - 1 - after[-1] if after else 0
        print(f"  슬롯 {slot:>2}: 마커 {n}개 · 위치 {before} -> {after} · "
              f"본문 {texts}줄 · 마지막 사진 뒤 {tail}줄")
        if a.apply:
            io.open(p, "w", encoding="utf-8").write(render(new, tags))
    if not a.apply:
        print("\n실제로 바꾸려면  --apply  를 붙인다.")


if __name__ == "__main__":
    main()
