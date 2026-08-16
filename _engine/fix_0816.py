#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0816 산출물 사후 수정 (2026-08-16 1회성).

이미 만들어진 output/0816/ 10슬롯을 새 규격에 맞춘다.
articles.json 이 남아 있지 않아 재생성이 불가능하므로 산출물을 직접 고친다.

고치는 것 세 가지
  1) 해시태그에 # 이 빠졌다 (0816 10편 전량). 붙여준다.
  2) 이미지 8장 -> 6장 (사용자 확정).
  3) 위아래 띠가 있는 사진(레터박스) 10장. 원본 비율을 복구할 수 없으므로
     **버리거나(트림 대상 우선) 정사각 자산으로 교체**한다.

    python _engine/fix_0816.py            # 시뮬레이션 (아무것도 안 바꾼다)
    python _engine/fix_0816.py --apply    # 실제 적용
"""
import argparse
import io
import os
import re
import shutil
import sys

from PIL import Image, ImageStat

for _s in (sys.stdout, sys.stderr):     # 윈도우 콘솔 기본 cp949 에서 깨진다
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output", "0816")
ASSETS = os.path.join(ROOT, "assets", "photos")
KEEP = 6

# 레터박스가 살아남는 슬롯만 교체가 필요하다. 슬롯 주제에 맞는 버킷을 지정한다.
REPLACE_BUCKET = {
    "1": "쏘나타",      # 쏘나타 트림 가격 기사 (띠 5장, 썸네일 포함)
    "5": "GV80",        # GV80 하이브리드 기사 (띠가 썸네일 1장)
    "9": "본사사옥",    # 정의선 보수 공시 — 인물컷 1장뿐이라 맥락 사진으로 채운다
}


def is_letterboxed(path, k=40, tol=3.0):
    """위아래 또는 좌우 가장자리가 단색이면 띠를 채운 것이다."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        d = {n: max(ImageStat.Stat(im.crop(b)).stddev) for n, b in (
            ("t", (0, 0, w, k)), ("b", (0, h - k, w, h)),
            ("l", (0, 0, k, h)), ("r", (w - k, 0, w, h)))}
    return (d["t"] < tol and d["b"] < tol) or (d["l"] < tol and d["r"] < tol)


def square_assets(bucket, used):
    """그 버킷에서 정사각에 가까운 자산을 고른다."""
    out = []
    for f in sorted(os.listdir(ASSETS)):
        if bucket not in f or f in used:
            continue
        p = os.path.join(ASSETS, f)
        try:
            with Image.open(p) as im:
                w, h = im.size
        except Exception:
            continue
        if max(w, h) / max(1, min(w, h)) <= 1.25:
            out.append(p)
    return out


def fix_hashtags(lines):
    """마지막 태그 블록에 # 을 붙인다. 본문 문장은 건드리지 않는다."""
    n = 0
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        # 태그 후보: 짧고 공백이 없는 한 단어 줄
        if len(s) <= 30 and " " not in s and not s.startswith("⠀"):
            if not s.startswith("#"):
                lines[i] = "#" + s
                n += 1
        else:
            break                       # 문장을 만나면 태그 블록이 끝난 것
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    dry = not a.apply
    print("=== 0816 수정 " + ("(시뮬레이션 — 아무것도 안 바꾼다)" if dry else "(실제 적용)") + " ===\n")

    for slot in sorted(os.listdir(OUT), key=lambda x: (len(x), x)):
        d = os.path.join(OUT, slot)
        if not os.path.isdir(d):
            continue
        body_p = os.path.join(d, "0번 본문.txt")
        imgs = sorted((f for f in os.listdir(d) if re.match(r"\d+번 사진\.jpg$", f)),
                      key=lambda f: int(f.split("번")[0]))
        boxed = {f for f in imgs if is_letterboxed(os.path.join(d, f))}

        # 버릴 2장: 레터박스를 뒤에서부터 우선, 모자라면 끝에서 채운다.
        # 1번(썸네일)은 자리를 비우지 않는다 — 필요하면 교체한다.
        drop = []
        for f in reversed(imgs):
            if len(drop) >= len(imgs) - KEEP:
                break
            if f in boxed and f != imgs[0]:
                drop.append(f)
        for f in reversed(imgs):
            if len(drop) >= len(imgs) - KEEP:
                break
            if f not in drop and f != imgs[0]:
                drop.append(f)

        keep = [f for f in imgs if f not in drop]
        still = [f for f in keep if f in boxed]
        bucket = REPLACE_BUCKET.get(slot)
        pool = square_assets(bucket, set()) if bucket else []

        print(f"슬롯 {slot:>2}: {len(imgs)}장 -> {len(keep)}장 · 띠 {len(boxed)}장 · "
              f"버림 {[x.split('번')[0] for x in drop]} · 교체필요 {len(still)}장"
              + (f" (버킷 {bucket}, 후보 {len(pool)}장)" if still else ""))
        if still and not pool:
            print(f"    ⚠️ 교체할 정사각 자산이 없다 — 그대로 둔다")

        if dry:
            continue

        # 1) 교체
        for i, f in enumerate(still):
            if i < len(pool):
                shutil.copyfile(pool[i], os.path.join(d, f))
        # 2) 삭제
        for f in drop:
            os.remove(os.path.join(d, f))
        # 3) 번호 다시 매기기 (임시 이름을 거쳐 충돌 방지)
        order = {old: n + 1 for n, old in enumerate(keep)}
        for old, new in order.items():
            os.rename(os.path.join(d, old), os.path.join(d, f"_tmp{new}.jpg"))
        for new in order.values():
            os.rename(os.path.join(d, f"_tmp{new}.jpg"), os.path.join(d, f"{new}번 사진.jpg"))
        # 4) 본문 마커 갱신 + 해시태그
        lines = io.open(body_p, encoding="utf-8").read().split("\n")
        dropped_no = {int(f.split("번")[0]) for f in drop}
        out_lines = []
        for ln in lines:
            m = re.fullmatch(r"\s*【(\d+)번 사진】\s*", ln)
            if m:
                no = int(m.group(1))
                if no in dropped_no:
                    continue                      # 마커 줄 제거
                new_no = order[f"{no}번 사진.jpg"]
                out_lines.append(f"【{new_no}번 사진】")
                continue
            out_lines.append(ln)
        n_tag = fix_hashtags(out_lines)
        io.open(body_p, "w", encoding="utf-8").write("\n".join(out_lines))
        print(f"    적용 — 사진 {len(keep)}장 · 해시태그 {n_tag}개에 # 추가")

    if dry:
        print("\n실제로 바꾸려면  --apply  를 붙여 다시 실행한다.")


if __name__ == "__main__":
    sys.exit(main())
