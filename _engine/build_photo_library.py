# -*- coding: utf-8 -*-
"""카테고리별 사진 라이브러리를 미리 채워두는 도구.

매일 아침 기사마다 사진을 새로 검색하면 (1) 느리고 (2) 429에 걸리고
(3) 무관한 사진이 걸려도 아무도 못 잡는다. 그래서 미리 카테고리별로 쌓아두고
매일은 '고르기만' 하는 구조로 간다.

    python build_photo_library.py            # 전체 카테고리
    python build_photo_library.py 수출무역    # 특정 카테고리만

받은 뒤 Read 도구로 눈으로 확인하고, 주제에 안 맞는 파일은 지운다.
지우면 index.json 도 같이 정리해야 하므로 --prune 으로 정리한다.

소스는 Wikimedia Commons 직접 경로만 쓴다:
  - Openverse는 rawpixel 등이 축소본(1024px)만 줘서 카드(1080px)에 못 쓴다
  - korea.kr(정책브리핑)은 720px 상한 + 항목별 공공누리 부착 여부 확인 필요라 제외
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from image_sourcing import (prepare_photo, wikimedia_photo_candidates,
                            photo_candidates, stock_photo_candidates)

DIR = os.path.join("assets", "photos")
INDEX = os.path.join(DIR, "index.json")

# 카테고리 -> 검색어. 한국 소재를 우선하되, 한국 사진이 부족한 주제는
# 일반 소재로 보완한다 (Commons는 한국 사진 재고가 서구권보다 적다).
CATEGORIES = {
    "신차출시": ["Hyundai Ioniq 5 car", "Kia EV6 car"],
    "전기차친환경": ["electric car charging station", "electric vehicle battery pack"],
    "산업수출": ["automobile factory production line", "car carrier ship vehicles"],
    "리콜안전정책": ["car dashboard warning light", "highway traffic many cars"],
    "모터스포츠": ["motorsport race car circuit", "formula racing car on track"],
    "중고차시장": ["used car dealership lot rows", "car sales showroom interior"],
    "브랜드기업": ["Hyundai Motor headquarters building", "automobile company office tower"],
    "셀럽차": ["luxury SUV black premium", "premium luxury sedan car"],

    # --- 인기 모델 버킷 ---------------------------------------------------
    # 자동차 블로그는 '그 차 사진'이 생명. 기사가 특정 모델을 다루면 photo_category에
    # 아래 모델명을 지정해 실제 그 차 사진을 쓴다(테마 카테고리보다 우선). 모델 쿼리는
    # Commons 적중률이 높다(단일 차량 피사체). 없으면 테마 카테고리로 폴백.
    "팰리세이드": ["Hyundai Palisade car"],
    "싼타페": ["Hyundai Santa Fe car"],
    "쏘렌토": ["Kia Sorento car"],
    "스포티지": ["Kia Sportage car"],
    "셀토스": ["Kia Seltos car"],
    "카니발": ["Kia Carnival Sedona car"],
    "그랜저": ["Hyundai Grandeur Azera car"],
    "코나": ["Hyundai Kona car"],
    "아이오닉5": ["Hyundai Ioniq 5 grey", "Hyundai Ioniq 5 parked street"],
    "아이오닉6": ["Hyundai Ioniq 6 car"],
    "EV6": ["Kia EV6 car"],
    "EV9": ["Kia EV9 car"],
    "GV80": ["Genesis GV80 car"],
    "G80": ["Genesis G80 sedan car"],
    "테슬라모델Y": ["Tesla Model Y car"],
    "테슬라모델3": ["Tesla Model 3 car"],
    "벤츠E클래스": ["Mercedes-Benz E-Class car"],
    "BMW5시리즈": ["BMW 5 Series car"],
    "BYD차": ["BYD Seal car", "BYD Atto 3 electric car"],
    # --- 신차·주요 모델 보강 (제목-사진 불일치 방지) ---
    "아이오닉9": ["Hyundai Ioniq 9 car"],
    "EV3": ["Kia EV3 car"],
    "GV70": ["Genesis GV70 car"],
    "G90": ["Genesis G90 car"],
    "쏘나타": ["Hyundai Sonata car"],
    "투싼": ["Hyundai Tucson car"],
    "아반떼": ["Hyundai Elantra Avante car"],
    "타스만": ["Kia Tasman pickup truck"],
    "스타리아": ["Hyundai Staria van"],
    # --- 브랜드 외관(수입) ---
    "아우디차": ["Audi A6 car", "Audi Q7 SUV car"],
    "벤츠차": ["Mercedes-Benz S-Class car", "Mercedes-Benz GLE SUV"],
    "BMW차": ["BMW X5 car", "BMW 3 Series car"],
    "폭스바겐차": ["Volkswagen Golf car", "Volkswagen Tiguan SUV"],
    "볼보차": ["Volvo XC60 car", "Volvo XC90 SUV"],
    "포르쉐차": ["Porsche 911 car", "Porsche Cayenne SUV"],
    "렉서스차": ["Lexus ES car", "Lexus RX SUV"],
    "토요타차": ["Toyota Camry car", "Toyota RAV4 SUV"],
    # --- 산업·현장(인물 대체용) ---
    "공장생산": ["car factory assembly line", "automobile production plant workers"],
    "본사사옥": ["Hyundai Motor headquarters building", "automotive company headquarters"],
    "발표행사": ["auto show press conference stage", "car unveiling event presentation"],
    "노조시위": ["IG Metall strike autoworkers", "car factory workers strike protest"],
    # --- 맥락 이미지(차가 아닌 소재를 말할 때) ---------------------------------
    # "카카오톡 공유로 응모" 같은 문장에 차 사진을 붙이면 센스가 없다. 소재 자체를 보여준다.
    "SNS공유": ["smartphone messenger app screen", "person using smartphone social media"],
    "온라인구매": ["online shopping laptop screen", "person browsing website laptop"],
    "계약서류": ["signing contract documents pen", "car dealership paperwork signing"],
    "국기중국": ["flag of China", "Chinese flag waving"],
    "국기미국": ["flag of the United States", "American flag waving"],
    "국기유럽": ["flag of the European Union", "German flag waving"],
    "돈가격": ["Korean won banknotes money", "calculator money finance desk"],

    # --- 실내(인테리어) 버킷 ------------------------------------------------
    # 자동차 글은 외관만큼 실내도 궁금해한다. 5장 세트에 실내 최소 1장 넣는다.
    "실내고급": ["Genesis GV80 interior", "Genesis G90 interior dashboard"],
    "실내운전석": ["Hyundai Ioniq 5 interior", "Kia EV9 interior dashboard"],
    "실내벤츠": ["Mercedes-Benz interior dashboard", "Mercedes-Benz cockpit steering interior"],
    "실내BMW": ["BMW interior dashboard cockpit", "BMW curved display interior"],
    "실내테슬라": ["Tesla Model 3 interior minimalist", "Tesla interior center screen"],
    "실내수입": ["luxury car interior leather dashboard", "premium car cockpit interior"],
}


# ── 버킷별 소스 라우팅 (실측으로 확인된 소스별 강·약점) ──────────────────
# 스톡(Pexels/Unsplash)은 'interior' 같은 한정어를 무시하고 일반 고급차 외관을 준다
# → 실내 버킷이 외관으로 오염됐다(실측). 반대로 중국·한국 신차는 스톡에 거의 없고
#   Commons(wiki)에 실차가 많다. 그래서 버킷 성격별로 쓸 소스를 제한한다.
SOURCE_ROUTING = [
    (("실내",), ["wiki", "openverse"]),          # 실내: 한정어를 지키는 wiki만
    (("노조시위", "발표행사", "공장생산"), ["wiki", "stock"]),
    (("BYD차", "아이오닉", "EV3", "EV6", "EV9", "GV", "G80", "G90",
      "타스만", "셀토스", "쏘렌토", "스포티지", "카니발", "팰리세이드",
      "싼타페", "투싼", "코나", "그랜저", "쏘나타", "아반떼", "스타리아"),
     ["wiki", "openverse"]),                     # 국산·중국 모델: 실차는 wiki가 정확
]


def sources_for(bucket, default):
    """그 버킷에 허용된 소스 목록(라우팅 규칙 우선, 없으면 사용자가 준 기본값)."""
    for keys, allowed in SOURCE_ROUTING:
        if any(bucket.startswith(k) or k in bucket for k in keys):
            return [s for s in default if s in allowed] or allowed
    return default


def _file_hash(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def existing_hashes():
    """라이브러리에 이미 있는 사진들의 해시 — 같은 사진이 여러 버킷에 박히는 걸 막는다."""
    out = {}
    if not os.path.isdir(DIR):
        return out
    for fn in os.listdir(DIR):
        if fn.lower().endswith((".jpg", ".png")):
            try:
                out[_file_hash(os.path.join(DIR, fn))] = fn
            except OSError:
                pass
    return out


def load_index():
    # 손상(빈/NUL) JSON을 만나도 크래시 대신 {}로 복구(불안정 환경·블루스크린 대비)
    if os.path.exists(INDEX):
        try:
            with open(INDEX, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            print("  [경고] index.json 손상 — 빈 인덱스로 복구")
            return {}
    return {}


def save_index(idx):
    # 원자적 저장: 임시파일에 다 쓴 뒤 os.replace로 교체 → 쓰는 중 크래시해도 원본 안 깨짐
    os.makedirs(os.path.dirname(INDEX) or ".", exist_ok=True)
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX)


def prune(idx):
    """파일이 지워진 항목을 index에서 정리한다."""
    gone = [k for k in idx if not k.startswith("_") and
            not os.path.exists(os.path.join(DIR, k))]
    for k in gone:
        idx.pop(k)
    return gone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category", nargs="?", help="특정 카테고리만 (생략 시 전체)")
    ap.add_argument("--per", type=int, default=2, help="검색어당 채택 수")
    ap.add_argument("--min-width", type=int, default=1600)
    ap.add_argument("--sources", default="wiki,openverse,stock",
                    help="쉼표구분: wiki,openverse,stock — 다양한 소스에서 모은다. "
                         "stock(Pexels/Unsplash/Pixabay)은 환경변수 API키가 있어야 동작.")
    ap.add_argument("--workers", type=int, default=3,
                    help="동시 다운로드/가공 스레드 수. 기본 3 — 이 PC는 MEMORY_MANAGEMENT "
                         "블루스크린 이력이 있어 순간 메모리 스파이크를 낮게 유지한다. "
                         "안정적인 클라우드/다른 PC에서는 8까지 올려도 된다.")
    ap.add_argument("--prune", action="store_true", help="index 정리만 하고 종료")
    ap.add_argument("--tagcars", action="store_true",
                    help="차량 검출을 돌려 index에 '차검출' 태그 심기(본문 사진 품질 게이트용)")
    ap.add_argument("--dedup", action="store_true",
                    help="완전 중복 사진 자동 정리(구체적 버킷 우선 유지)")
    ap.add_argument("--audit", action="store_true",
                    help="라이브러리 품질 감사(중복·빈 버킷·흑백 의심)만 하고 종료")
    ap.add_argument("--register", action="store_true",
                    help="수동으로 넣은 사진을 index에 등록(카테고리=파일명 '_' 앞부분). "
                         "속보용 프레스 사진을 직접 넣을 때 사용.")
    args = ap.parse_args()

    os.makedirs(DIR, exist_ok=True)
    idx = load_index()

    if args.prune:
        gone = prune(idx)
        save_index(idx)
        print(f"index에서 {len(gone)}건 정리: {gone}")
        return 0

    if args.tagcars:
        # 라이브러리 전체에 차량 검출을 돌려 index.json 에 '차검출' 태그를 심는다.
        # pick_photo 가 이 태그를 보고 '차가 보이는 사진'을 우선 고른다(본문 품질 게이트).
        # 검출은 느리므로(장당 수십 ms) 소싱 후 한 번만 돌리면 된다.
        from frame_quality import car_presence, _imread
        from photo_match import car_required
        idx = load_index()
        files = [f for f in os.listdir(DIR) if f.lower().endswith((".jpg", ".png"))]
        n_car = n_no = 0
        for f in files:
            b = f.split("_")[0]
            img = _imread(os.path.join(DIR, f))
            if img is None:
                continue
            meta = idx.get(f) or {"카테고리": b}
            if car_required(b):               # 인물·실내·건물 버킷은 차량검출 생략
                conf, area = car_presence(img)
                meta["차검출"] = bool(conf >= 0.45)
                meta["차신뢰도"] = round(float(conf), 2)
                meta["차면적"] = round(float(area), 3)
            has = meta.get("차검출", True)
            # 밝기 — 사진 위에 스크림(어둡게)을 깔고 흰 글씨를 얹으므로, 원본이 어두우면
            # 차가 아예 안 보인다(실측: 검은 세단·어두운 공장 컷). 뽑을 때 밝은 걸 우선한다.
            meta["밝기"] = int(img.mean())
            idx[f] = meta
            n_car += has
            n_no += (not has)
        save_index(idx)
        print(f"차 검출 태깅 완료: 검출 {n_car}장 / 미검출 {n_no}장")
        print("→ pick_photo 가 '차 보이는 사진'을 우선 선택합니다(본문 품질 게이트).")
        return 0

    if args.audit:
        # 무인 루틴은 사람 눈이 없다 — 라이브러리가 오염되면 그대로 발행된다.
        # 중복/빈약한 버킷을 기계적으로 잡아 검수 대상을 좁혀준다.
        import collections
        files = [f for f in os.listdir(DIR) if f.lower().endswith((".jpg", ".png"))]
        by_hash = collections.defaultdict(list)
        by_bucket = collections.Counter()
        for f in files:
            by_bucket[f.split("_")[0]] += 1
            try:
                by_hash[_file_hash(os.path.join(DIR, f))].append(f)
            except OSError:
                pass
        dups = {h: v for h, v in by_hash.items() if len(v) > 1}
        thin = [(b, c) for b, c in sorted(by_bucket.items()) if c <= 2]
        print(f"사진 {len(files)}장 / 버킷 {len(by_bucket)}개")
        print(f"\n[중복] {len(dups)}건 (같은 사진이 여러 버킷에 존재 → 반복 노출·버킷 오염)")
        for v in list(dups.values())[:15]:
            print("   " + " = ".join(v))
        print(f"\n[빈약한 버킷] {len(thin)}개 (2장 이하 — 반복 위험)")
        for b, c in thin[:20]:
            print(f"   {b:<14} {c}장")
        missing = [c for c in CATEGORIES if not by_bucket.get(c)]
        print(f"\n[미소싱 카테고리] {len(missing)}개: {', '.join(missing) if missing else '없음'}")
        print("\n※ 중복은 `--dedup`으로 자동 정리, 빈약한 버킷은 `--per` 올려 재소싱 권장.")
        return 0

    if args.dedup:
        # 완전 동일 파일을 정리한다. '더 구체적인 버킷'(모델명/인물)을 남기고
        # 테마 버킷 쪽 사본을 지운다 — 실내 버킷에 외관이 남는 오염도 이때 줄어든다.
        import collections
        THEME = {"신차출시", "전기차친환경", "산업수출", "리콜안전정책", "모터스포츠",
                 "중고차시장", "브랜드기업", "셀럽차", "공장생산", "본사사옥", "발표행사", "노조시위"}
        files = [f for f in os.listdir(DIR) if f.lower().endswith((".jpg", ".png"))]
        by_hash = collections.defaultdict(list)
        for f in files:
            try:
                by_hash[_file_hash(os.path.join(DIR, f))].append(f)
            except OSError:
                pass
        idx = load_index()
        removed = 0
        for h, group in by_hash.items():
            if len(group) < 2:
                continue
            # 구체적 버킷(테마가 아닌 것) 우선 유지, 그 안에서는 이름 짧은 것
            group.sort(key=lambda f: (f.split("_")[0] in THEME, len(f)))
            for f in group[1:]:
                p = os.path.join(DIR, f)
                try:
                    os.remove(p)
                    idx.pop(f, None)
                    removed += 1
                except OSError:
                    pass
        save_index(idx)
        print(f"중복 {removed}장 정리 완료 (남은 사진 {len(files) - removed}장)")
        return 0

    if args.register:
        # 사용자가 assets/photos/ 에 직접 넣은(속보용 프레스 등) 사진을 index에 등록한다.
        # 카테고리는 파일명의 첫 '_' 앞부분에서 뽑는다. 예: GV90_press_0.jpg -> 카테고리 "GV90".
        # 정사각 1400px로 맞춰 다른 사진과 규격을 통일한다.
        added = 0
        for fn in sorted(os.listdir(DIR)):
            if fn == "index.json" or not fn.lower().endswith((".jpg", ".png")):
                continue
            if fn in idx:
                continue
            cat = os.path.splitext(fn)[0].split("_")[0]  # 확장자 먼저 떼고(GV90.jpg→GV90)
            path = os.path.join(DIR, fn)
            try:
                prepare_photo(path, path, size=1400)
            except Exception as e:
                print(f"   가공 실패 {fn}: {str(e)[:40]}")
            idx[fn] = {
                "카테고리": cat,
                "license": "수동추가(사용자 책임)",
                "credit": "",
                "attribution_required": False,
                "처리": "수동 등록 + 정사각 1400px",
                "검색어": "manual",
                "검수": "수동추가 — 사용자 확인함",
            }
            print(f"   등록  {fn:<26} -> 카테고리 '{cat}'")
            added += 1
        save_index(idx)
        print(f"\n{added}장 등록 완료. (git add -f 로 커밋하세요)")
        return 0

    targets = ({args.category: CATEGORIES[args.category]}
               if args.category else CATEGORIES)
    if args.category and args.category not in CATEGORIES:
        print("없는 카테고리입니다. 가능한 값:", ", ".join(CATEGORIES))
        return 1

    src_names = [s.strip() for s in args.sources.split(",") if s.strip()]
    total_ok = total_skip = 0

    # 병목 제거: (카테고리 × 검색어 × 소스)를 전부 독립 작업으로 만들어
    # 네트워크 다운로드를 스레드풀로 동시에 돌린다. 예전엔 버킷마다 프로세스를
    # 새로 띄우고, 소스도 순차, 다운로드마다 1초씩 쉬느라 느렸다.
    # 버킷 성격에 맞는 소스만 쓴다(실내에 스톡을 쓰면 외관이 섞이는 문제 방지)
    jobs = [(cat, qi, q, sname)
            for cat, queries in targets.items()
            for qi, q in enumerate(queries)
            for sname in sources_for(cat, src_names)]

    def source_one(job):
        cat, qi, q, sname = job
        sprefix = f"{cat}_{qi}{sname[0]}"
        try:
            if sname == "wiki":
                rep = wikimedia_photo_candidates(
                    q, DIR, limit=args.per, min_width=args.min_width, prefix=sprefix)
            elif sname == "openverse":
                rep = photo_candidates(
                    q, DIR, limit=args.per, min_width=args.min_width, prefix=sprefix)
            elif sname == "stock":
                rep = stock_photo_candidates(
                    q, DIR, keep=args.per, min_side=args.min_width, prefix=sprefix)
            else:
                print(f"   [{sname}] 알 수 없는 소스 — 건너뜀")
                rep = []
        except Exception as e:
            print(f"   [{sname}/{cat}] 소싱 실패: {str(e)[:60]}")
            rep = []
        return cat, q, rep

    # 1단계: 다운로드(네트워크) 병렬
    downloaded = []   # (cat, q, r)
    seen_hashes = existing_hashes()      # 같은 사진이 여러 버킷에 중복 저장되는 것 차단
    dup_n = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for cat, q, rep in ex.map(source_one, jobs):
            for r in rep:
                if "path" in r:
                    try:
                        h = _file_hash(r["path"])
                    except OSError:
                        continue
                    if h in seen_hashes:      # 이미 라이브러리에 있는 사진 → 버린다
                        os.remove(r["path"])
                        dup_n += 1
                        continue
                    seen_hashes[h] = os.path.basename(r["path"])
                    downloaded.append((cat, q, r))
                elif "skipped" in r:
                    total_skip += 1
    if dup_n:
        print(f"   중복 {dup_n}장 자동 제외(이미 라이브러리에 있는 사진)")

    # 2단계: 카드 규격(정사각 1400px) 가공도 병렬 (CPU/IO)
    def prep_one(item):
        _, _, r = item
        try:
            prepare_photo(r["path"], r["path"], size=1400)
        except Exception as e:
            print(f"   가공 실패 {os.path.basename(r['path'])}: {str(e)[:40]}")
        return item

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        prepared = list(ex.map(prep_one, downloaded))

    # 3단계: 인덱스 기록(직렬 — 공유 dict 안전)
    for cat, q, r in prepared:
        fname = os.path.basename(r["path"])
        idx[fname] = {
            "카테고리": cat,
            "license": r["license"],
            "credit": r["credit"],
            "attribution_required": True,
            "원본해상도": f"{r.get('src_w') or r.get('w')}x{r.get('src_h') or r.get('h')}",
            "처리": "정사각 1400px + 시리즈 톤 + 비네트",
            "검색어": q,
            "검수": "미확인 — Read로 눈 확인 필요",
        }
        print(f"   OK   {fname:<26} [{r['license']}]")
        total_ok += 1

    save_index(idx)
    print(f"\n채택 {total_ok}장 / 폐기 {total_skip}건 -> {DIR}/")
    print("이제 Read 도구로 각 파일을 열어 주제에 맞는지 확인하세요.")
    print("안 맞는 건 파일 삭제 후: python build_photo_library.py --prune")
    return 0


if __name__ == "__main__":
    sys.exit(main())
