# -*- coding: utf-8 -*-
"""인물 사진 라이브러리 — 제목에 인물이 나오는 기사(오너·CEO·셀럽)용.

자동차 기사에서 '정의선', '손흥민이 타는 차'처럼 인물이 제목의 주인공인 경우,
차 사진만 쓰면 제목-썸네일이 어긋나 이탈이 커진다. 그래서 인물 사진을 미리 쌓아둔다.

    python _engine/build_people_library.py            # 전체
    python _engine/build_people_library.py 정의선      # 한 명만
    python _engine/build_people_library.py --add "Son Heung-min" --name 손흥민   # 새 인물 추가 소싱

저장 위치는 assets/photos/ (버킷명 = 인물명). 기존 photo_category 로직을 그대로 타므로
기사 JSON에서 photo_category: "정의선" 으로 쓰면 된다.

【라이선스】 PD/CC 계열만 통과시킨다(Commons 기준). 공인을 공적 활동 맥락에서
보도·정보전달로 다루는 용도. 상업적 보증처럼 쓰거나 명예훼손과 결합하지 않는다.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from image_sourcing import wikimedia_portrait_candidates, fetch_image, prepare_photo

DIR = os.path.join("assets", "photos")
INDEX = os.path.join(DIR, "index.json")

# 인물명(버킷) -> Commons 검색어. 영문 정식표기 + 소속이 적중률이 높다.
PEOPLE = {
    "정의선": "Chung Eui-sun Hyundai",
    "머스크": "Elon Musk",
    "손흥민": "Son Heung-min",
    "블루메": "Oliver Blume Porsche",
    "토요다아키오": "Akio Toyoda",
    "올리버칩세": "Oliver Zipse BMW",
    "왕촨푸": "Wang Chuanfu BYD",
}

BAD_WORDS = ["air show", "squadron", "aircraft", "navy"]  # 명백히 무관한 컷만 배제
# ※ 'Trump/White House'는 빼지 않는다 — 정의선의 대미 투자발표 사진 제목이 그 형태라
#    같이 걸러져 0장이 되던 문제가 있었다(실측). 대신 아래 score의 이름 매칭으로 판별한다.


def load_index():
    if os.path.exists(INDEX):
        try:
            with open(INDEX, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return {}
    return {}


def save_index(idx):
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX)


def score(title, query):
    """그 인물이 실제 주인공일 가능성 점수. 정치인·행사 배경 컷을 걸러낸다."""
    t = (title or "").lower()
    s = 0
    for w in [w for w in query.lower().split() if len(w) > 2]:
        if w in t:
            s += 2
    for b in BAD_WORDS:
        if b in t:
            s -= 3
    if "cropped" in t or "portrait" in t:
        s += 2                      # 인물 단독 크롭이면 썸네일에 좋다
    return s


def source_one(name, query, per=3, min_width=700):
    cands = wikimedia_portrait_candidates(query, limit=10, min_width=min_width)
    ranked = sorted(cands, key=lambda c: -score(c.get("title"), query))
    got = []
    for c in ranked:
        if len(got) >= per:
            break
        if score(c.get("title"), query) <= 0:
            continue
        urls = [u for u in (c.get("thumb"), c.get("url")) if u]   # 썸네일 실패 시 원본으로 폴백
        if not urls:
            continue
        url = urls[0]
        path = os.path.join(DIR, f"{name}_{len(got)}.jpg")
        try:
            # Commons는 연속 요청에 429를 잘 던진다 — 간격을 두고, 429면 늘려가며 재시도
            data, last_err = None, None
            for attempt in range(4):
                u = urls[min(attempt, len(urls) - 1)]   # 1회 실패 후엔 원본 URL로
                try:
                    time.sleep(1.5 + attempt * 2.5)
                    data = fetch_image(u)
                    break
                except Exception as e:
                    last_err = e
            if data is None:
                raise last_err
            with open(path, "wb") as f:
                f.write(data)
            prepare_photo(path, path, size=1400)
            got.append({"file": os.path.basename(path), "title": c["title"],
                        "license": c["license"]})
        except Exception as e:
            print(f"   실패 {c['title'][:40]}: {str(e)[:40]}")
    return name, query, got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("person", nargs="?", help="특정 인물만 (생략 시 전체)")
    ap.add_argument("--add", help="새 인물 Commons 검색어 (--name 과 함께)")
    ap.add_argument("--name", help="새 인물 버킷명(한글)")
    ap.add_argument("--per", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    os.makedirs(DIR, exist_ok=True)
    idx = load_index()

    if args.add:
        if not args.name:
            print("--add 는 --name 과 함께 써야 합니다.")
            return 1
        targets = {args.name: args.add}
    elif args.person:
        if args.person not in PEOPLE:
            print("없는 인물입니다. 가능한 값:", ", ".join(PEOPLE))
            return 1
        targets = {args.person: PEOPLE[args.person]}
    else:
        targets = PEOPLE

    jobs = [(n, q) for n, q in targets.items()]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(lambda j: source_one(j[0], j[1], args.per), jobs))

    total = 0
    for name, query, got in results:
        if not got:
            print(f"   {name:<10} 실패 - 적합 후보 없음")
            continue
        for g in got:
            idx[g["file"]] = {
                "카테고리": name,
                "license": g["license"],
                "credit": g["title"],
                "attribution_required": True,
                "처리": "인물 사진 · 정사각 1400px",
                "검색어": query,
                "검수": "미확인 — 반드시 눈으로 본인인지 확인",
            }
        print(f"   {name:<10} {len(got)}장  " + ", ".join(g["file"] for g in got))
        total += len(got)

    save_index(idx)
    print(f"\n총 {total}장 -> {DIR}/  (버킷명=인물명, photo_category로 사용)")
    print("반드시 컨택트시트로 '본인 맞는지' 눈 확인 후 사용하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
