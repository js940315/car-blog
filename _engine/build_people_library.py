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
import re
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
    # 셀럽·연예인차용 (2026-08-09~). 이 목록은 '이미 확보해 둔' 인물이라 전체 재소싱 때
    # 같이 갱신된다. 새 인물은 --probe 로 확인 후 --add 로 받고, 여기 한 줄 추가해 두면 좋다.
    "신혜선": "Shin Hye-sun",
    "현빈": "Hyun Bin",
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


# 검색어에 붙이는 '힌트' 단어 — 이름이 아니므로 이름 매칭에서 제외한다.
# (안 빼면 "IU singer" 의 'singer' 만 맞아도 아무 가수 사진이 통과한다)
HINT_WORDS = {"singer", "actor", "actress", "rapper", "idol", "group", "band",
              "korean", "south", "kpop", "k-pop", "comedian", "model",
              "hyundai", "kia", "genesis", "porsche", "bmw", "byd", "toyota",
              "tesla", "motor", "ceo", "chairman"}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def name_tokens(query):
    """검색어에서 '이름' 토큰만 뽑는다."""
    return [w for w in re.split(r"\s+", (query or "").lower()) if w and w not in HINT_WORDS]


def name_match(title, query):
    """제목이 **그 사람**을 가리키는가.

    2026-08-09 실측으로 드러난 두 가지 오탐을 막는다:
      1) 부분 매칭 — 'Kyung Soo-jin' 을 찾는데 'Park Soo-Kyung'(다른 사람)이 'kyung'
         하나로 통과했다. → 이름 토큰을 **전부** 만족해야 한다.
      2) 보너스 단독 통과 — 이름이 하나도 안 맞는데 제목에 'portrait/cropped' 가 있다는
         이유로 점수 2를 받아 통과했다(마동석 검색에 엉뚱한 배우 단체컷).
         → 이름 매칭이 0이면 보너스와 무관하게 탈락시킨다.
    ★ 부분문자열 매칭은 쓰지 않는다. 제목을 **토큰으로 쪼개** 비교한다 —
      'Don Lee' 를 찾는데 'Lee Dong-wook'(다른 사람)이 'don' ⊂ 'dongwook' 으로
      통과하던 오탐이 있었다(실측 2026-08-09). 이름은 토큰 경계에서 맞아야 한다.
      단 'Hye-sun' 처럼 붙여 쓰는 표기를 살리려고 **인접 토큰 결합**도 후보로 본다
      ('Shin Hye-sun' 의 'hyesun' ← 제목의 'Hye' + 'sun').
      'EUNHYUK180628' 처럼 이름 뒤에 숫자가 붙는 Commons 파일명도 인정한다."""
    toks = [_norm(t) for t in name_tokens(query)]
    toks = [t for t in toks if t]
    if not toks:
        return False
    parts = [p for p in re.split(r"[^a-z0-9]+", (title or "").lower()) if p]
    cands = set(parts)
    for i in range(len(parts) - 1):                  # 인접 2·3개 결합
        cands.add(parts[i] + parts[i + 1])
        if i + 2 < len(parts):
            cands.add(parts[i] + parts[i + 1] + parts[i + 2])
    for tok in toks:
        if tok in cands:
            continue
        # 'eunhyuk180628' 처럼 이름 뒤에 숫자만 붙은 경우도 같은 사람으로 본다
        if any(p.startswith(tok) and p[len(tok):].isdigit() for p in parts):
            continue
        return False
    return True


def score(title, query):
    """그 인물이 실제 주인공일 가능성 점수. 정치인·행사 배경 컷을 걸러낸다.

    이름이 안 맞으면 **무조건 0 이하** — 보너스로 되살아나지 못하게 한다."""
    if not name_match(title, query):
        return 0
    t = (title or "").lower()
    s = 2
    for b in BAD_WORDS:
        if b in t:
            s -= 3
    if "cropped" in t or "portrait" in t:
        s += 2                      # 인물 단독 크롭이면 썸네일에 좋다
    return s


MIN_FACE_AREA = 0.06     # 얼굴이 화면의 6% 미만이면 '누가 누군지' 안 보인다

# 한 번 실행에서 429 백오프로 쓸 수 있는 총 대기 시간(초). 이걸 안 두면 후보마다
# 수십 초씩 쉬다가 실행이 통째로 죽는다(실측 2026-08-09: 10분 타임아웃).
_BUDGET = {"slept": 0.0, "max": 120.0}


def face_ok(path):
    """인물 사진에 **얼굴이 크게** 잡혀 있는가.

    2026-08-09 실측: Commons 검색은 이름이 제목에 있어도 엉뚱한 컷을 준다.
    경수진 검색 결과 1위가 **얼굴이 아예 없는 모델 3명의 다리 사진**이었고,
    신혜선 2번째는 얼굴이 3%인 단체 컷이었다. 썸네일에 쓰면 '이 사람 누구지'가 된다.
    사람 눈 대신 얼굴 검출로 기계적으로 거른다.

    반환: (통과여부, 사유). 검출기를 못 쓰면 **통과시키되 경고**한다
    (조용히 실패해 규칙이 무력화되는 걸 막는다 — 이 저장소의 반복 사고 유형)."""
    try:
        import cv2
        from frame_quality import _imread          # 한글 경로 대응 imread
        img = _imread(path)
        if img is None:
            return True, "이미지 열기 실패 — 검사 못 함(통과)"
        cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
        if cascade.empty():
            return True, "얼굴 검출기 없음 — 검사 못 함(통과)"
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5,
                                         minSize=(int(w * 0.10), int(w * 0.10)))
        if len(faces) == 0:
            return False, "얼굴 없음"
        big = max(fw * fh for _, _, fw, fh in faces) / float(w * h)
        if big < MIN_FACE_AREA:
            return False, f"얼굴이 너무 작음({big:.1%}) — 단체·원거리 컷"
        return True, f"얼굴 {big:.0%}"
    except Exception as e:
        print(f"   [경고] 얼굴 검사 실패(통과 처리): {type(e).__name__}: {str(e)[:50]}")
        return True, "검사 실패"


def probe(query, min_width=700):
    """다운로드 없이 '이 인물 사진을 구할 수 있는가'만 확인한다.

    루틴이 셀럽 기사를 **쓰기 전에** 먼저 이걸로 확인하라고 만든 모드다.
    사진이 없으면 그 인물로 기사를 시작하지 말고 다른 인물로 바꾸면 된다
    (다 써놓고 사진이 없어 배너에 걸리는 낭비를 막는다).
    검색어는 `|` 로 여러 표기를 넘길 수 있다 — 로마자 표기가 갈리는 이름이 많다
    (실측: 'Ma Dong-seok' 로는 0건인데 Commons 는 다른 표기를 쓰는 경우가 있다)."""
    rows = []
    for q in [x.strip() for x in str(query).split("|") if x.strip()]:
        cands = wikimedia_portrait_candidates(q, limit=10, min_width=min_width)
        ok = [c for c in cands if score(c.get("title"), q) > 0]
        rows.append((q, len(cands), ok))
    return rows


def source_one(name, query, per=3, min_width=700):
    # 검색어는 '|' 로 여러 표기를 받는다. 앞에서부터 시도해 처음 걸리는 표기를 쓴다.
    queries = [x.strip() for x in str(query).split("|") if x.strip()] or [query]
    cands, query = [], queries[0]
    for q in queries:
        found = wikimedia_portrait_candidates(q, limit=10, min_width=min_width)
        if any(score(c.get("title"), q) > 0 for c in found):
            cands, query = found, q
            break
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
            for attempt in range(3):
                u = urls[min(attempt, len(urls) - 1)]   # 1회 실패 후엔 원본 URL로
                try:
                    # 429가 나오면 짧은 백오프로는 안 풀린다(실측 2026-08-09:
                    # 1.5/4/6.5/9초로는 연속 5건이 전부 429였다). 429면 더 쉰다.
                    # 단 **전체 대기 예산**을 두지 않으면 후보마다 1분씩 쉬다가
                    # 10분을 넘겨 통째로 죽는다(실측). 예산을 넘기면 즉시 포기한다.
                    wait = 1.5 + attempt * 2.5
                    if last_err is not None and "429" in str(last_err):
                        wait = 25
                    if _BUDGET["slept"] + wait > _BUDGET["max"]:
                        raise RuntimeError(
                            "Commons 요청 한도(429)에 걸렸고 대기 예산을 다 썼습니다 — "
                            "몇 분 뒤 다시 실행하세요")
                    _BUDGET["slept"] += wait
                    time.sleep(wait)
                    data = fetch_image(u)
                    break
                except Exception as e:
                    last_err = e
                    if "대기 예산" in str(e):
                        break
            if data is None:
                raise last_err
            with open(path, "wb") as f:
                f.write(data)
            prepare_photo(path, path, size=1400)
            ok, why = face_ok(path)
            if not ok:
                os.remove(path)                    # 얼굴 게이트 탈락 — 남기지 않는다
                print(f"   버림 {c['title'][:36]}: {why}")
                continue
            got.append({"file": os.path.basename(path), "title": c["title"],
                        "license": c["license"], "얼굴": why})
        except Exception as e:
            print(f"   실패 {c['title'][:40]}: {str(e)[:40]}")
    return name, query, got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("person", nargs="?", help="특정 인물만 (생략 시 전체)")
    ap.add_argument("--add", help="새 인물 Commons 검색어 (--name 과 함께)")
    ap.add_argument("--name", help="새 인물 버킷명(한글)")
    ap.add_argument("--per", type=int, default=3)
    ap.add_argument("--probe", metavar="검색어",
                    help="다운로드 없이 '사진을 구할 수 있는지'만 확인. "
                         "셀럽 기사를 쓰기 전에 먼저 돌려볼 것. "
                         "'|' 로 여러 표기를 넘길 수 있다: --probe \"Ma Dong-seok|Don Lee actor\"")
    ap.add_argument("--workers", type=int, default=2,
                    help="동시 다운로드 수. 기본 2 — Commons 429 방지 + 메모리 스파이크 억제")
    args = ap.parse_args()

    if args.probe:
        rows = probe(args.probe)
        best = 0
        for q, n_all, ok in rows:
            print(f"  '{q}' — 검색 {n_all}건 / 이름 일치 {len(ok)}건")
            for c in ok[:4]:
                print(f"      {c['title'][:58]}  [{c['license']}] {c['width']}px")
            best = max(best, len(ok))
        print("\n" + ("사용 가능 — --add 로 받으세요." if best else
                     "사용 불가 — 이 인물은 기사에서 빼고 다른 인물로 바꾸세요."
                     " (표기를 바꿔 재시도해볼 수 있습니다)"))
        return 0 if best else 2

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
