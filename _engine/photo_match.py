# -*- coding: utf-8 -*-
"""제목 → 사진 버킷 자동 매칭 (홈판 썸네일 성공률의 핵심).

문제: 루틴(에이전트)이 photo_category를 '기억'으로 고르다 보니 없는 버킷명을 쓰거나
      GV90 기사에 아이오닉5를 붙이는 사고가 났다. 문서 규칙만으로는 못 막는다.
해결: 제목·본문에서 실제 소재(모델·브랜드·인물·상황)를 뽑아 **보유 버킷으로 강제 교정**한다.
      또 지정된 버킷이 실제로 없으면(오타·미보유) 같은 브랜드 → 상황 순으로 폴백한다.

    from photo_match import resolve_category, available_buckets
    cat, why = resolve_category(title, spec_category)   # -> ("아이오닉9", "제목 모델 매칭")

우선순위:
  1) 제목에 모델명이 있으면 그 모델 버킷 (가장 강함 — 썸네일 불일치의 주범을 차단)
  2) 제목에 인물명이 있으면 인물 버킷
  3) 제목에 상황어(수출/파업/공장/공개)가 있으면 상황 버킷
  4) 에이전트가 준 카테고리가 실제 존재하면 그대로
  5) 브랜드만 알면 그 브랜드 대표 버킷 → 그래도 없으면 테마
"""

import os
import re

PHOTO_DIR = os.path.join("assets", "photos")

# 별칭(제목에 나오는 표기) -> 버킷명. 긴 것부터 매칭해야 '아이오닉5'가 '아이오닉'에 안 먹힌다.
MODEL_ALIASES = {
    "아이오닉9": "아이오닉9", "아이오닉 9": "아이오닉9",
    "아이오닉6": "아이오닉6", "아이오닉 6": "아이오닉6",
    "아이오닉5": "아이오닉5", "아이오닉 5": "아이오닉5",
    "팰리세이드": "팰리세이드", "싼타페": "싼타페", "투싼": "투싼", "코나": "코나",
    "그랜저": "그랜저", "쏘나타": "쏘나타", "아반떼": "아반떼", "스타리아": "스타리아",
    "쏘렌토": "쏘렌토", "스포티지": "스포티지", "셀토스": "셀토스", "카니발": "카니발",
    "타스만": "타스만", "EV6": "EV6", "EV9": "EV9", "EV3": "EV3",
    "GV80": "GV80", "GV70": "GV70", "G80": "G80", "G90": "G90",
    "모델Y": "테슬라모델Y", "모델 Y": "테슬라모델Y",
    "모델3": "테슬라모델3", "모델 3": "테슬라모델3",
    "E클래스": "벤츠E클래스", "5시리즈": "BMW5시리즈",
}

# 미보유 신차 등 → 같은 브랜드 대체 (썸네일이 최소한 브랜드는 맞게)
MODEL_FALLBACK = {
    "GV90": ["GV80", "G90"], "GV60": ["GV70", "GV80"], "G70": ["G80", "GV70"],
    "아이오닉7": ["아이오닉9", "EV9"], "EV4": ["EV3", "EV6"], "EV5": ["EV6", "EV9"],
    "캐스퍼": ["코나", "셀토스"], "레이": ["카니발", "셀토스"], "모하비": ["팰리세이드"],
    "넥쏘": ["투싼", "싼타페"], "모델S": ["테슬라모델3"], "모델X": ["테슬라모델Y"],
    "사이버트럭": ["테슬라모델Y"],
}

BRAND_ALIASES = {          # 브랜드 -> 그 브랜드 대표 버킷 후보
    "제네시스": ["GV80", "G90", "G80", "GV70"],
    "현대": ["아이오닉5", "팰리세이드", "싼타페", "그랜저"],
    "기아": ["쏘렌토", "EV6", "스포티지", "카니발"],
    "테슬라": ["테슬라모델Y", "테슬라모델3"],
    "벤츠": ["벤츠차", "벤츠E클래스"], "메르세데스": ["벤츠차"],
    "BMW": ["BMW차", "BMW5시리즈"], "아우디": ["아우디차"],
    "폭스바겐": ["폭스바겐차"], "볼보": ["볼보차"], "포르쉐": ["포르쉐차"],
    "렉서스": ["렉서스차"], "토요타": ["토요타차"], "도요타": ["토요타차"],
    "BYD": ["BYD차"], "비야디": ["BYD차"],
}

PEOPLE_ALIASES = {
    "정의선": "정의선", "머스크": "머스크", "일론": "머스크",
    "손흥민": "손흥민", "블루메": "블루메", "왕촨푸": "왕촨푸",
    "토요다": "토요다아키오", "아키오": "토요다아키오",
}

# 상황어 -> 버킷 (제목이 사건·현상 중심일 때)
# 맥락 소재 — 차가 아닌 것을 말하면 그 소재를 보여준다("카카오톡 공유"에 차 사진은 센스 없음).
# ※ 브랜드·모델 판정보다 뒤에서 검사한다. 안 그러면 "'중국차'라고 웃었는데 BYD…" 같은
#   제목이 국기 사진으로 가로채인다(브랜드가 있으면 그 차를 보여주는 게 맞다).
CONTEXT_RULES = [
    (r"카카오톡|카톡|공유\s*이벤트|SNS|인스타|메신저", "SNS공유"),
    (r"홈페이지|온라인|앱에서|사이트|접속|응모", "온라인구매"),
    (r"계약서|서류|약관|청약|신청서", "계약서류"),
    (r"중국|체리|지리|상하이|베이징", "국기중국"),
    (r"미국\s*관세|미국\s*정부|트럼프|미국\s*시장|워싱턴", "국기미국"),
    (r"유럽\s*연합|EU\s|독일\s*정부|유럽\s*규제|브뤼셀", "국기유럽"),
]

SITUATION_RULES = [
    (r"수출|선적|운반선|물량|해외\s*판매|미국\s*판매|유럽\s*판매", "산업수출"),
    (r"파업|노조|시위|집회|농성", "노조시위"),
    (r"공장|생산\s*라인|증산|감산|가동", "공장생산"),
    (r"공개|출시\s*행사|기자회견|발표회|언박싱|모터쇼", "발표행사"),
    (r"리콜|결함|화재|단속|벌점|과태료|안전\s*기준", "리콜안전정책"),
    (r"중고차|시세|감가", "중고차시장"),
    (r"충전|배터리|전기차\s*보조금", "전기차친환경"),
    (r"본사|사옥|그룹|지배구조|실적|영업이익", "브랜드기업"),
    (r"레이스|모터스포츠|F1|그랑프리", "모터스포츠"),
]

# ── 버킷별 '차가 보여야 하는가' 기대치 ────────────────────────────────────
# 인물·사옥·시위 버킷은 차가 없는 게 정상이다. 하지만 모델·전기차·중고차 버킷에
# 차가 안 보이는 사진(오토바이·실외기·길거리 풍경)이 섞이면 본문 품질이 무너진다.
# CAR_REQUIRED 에 해당하는 버킷만 차량 검출을 강제한다.
NO_CAR_OK = {"정의선", "머스크", "손흥민", "블루메", "왕촨푸", "토요다아키오", "올리버칩세",
             "본사사옥", "노조시위", "발표행사", "브랜드기업",
             "실내고급", "실내운전석", "실내벤츠", "실내BMW", "실내테슬라", "실내수입",
             # 맥락 이미지(차가 아닌 소재를 말할 때) — 차가 없는 게 정상
             "SNS공유", "온라인구매", "계약서류", "국기중국", "국기미국", "국기유럽", "돈가격"}


# 버킷 → 브랜드 (한 포스트 안에서 타 브랜드 차가 섞이는 걸 막는 데 쓴다)
BUCKET_BRAND = {
    "팰리세이드": "현대", "싼타페": "현대", "투싼": "현대", "코나": "현대", "그랜저": "현대",
    "쏘나타": "현대", "아반떼": "현대", "스타리아": "현대",
    "아이오닉5": "현대", "아이오닉6": "현대", "아이오닉9": "현대", "실내운전석": "현대",
    "쏘렌토": "기아", "스포티지": "기아", "셀토스": "기아", "카니발": "기아",
    "EV3": "기아", "EV6": "기아", "EV9": "기아", "타스만": "기아",
    "GV80": "제네시스", "GV70": "제네시스", "G80": "제네시스", "G90": "제네시스",
    "실내고급": "제네시스",
    "테슬라모델Y": "테슬라", "테슬라모델3": "테슬라", "실내테슬라": "테슬라",
    "벤츠차": "벤츠", "벤츠E클래스": "벤츠", "실내벤츠": "벤츠",
    "BMW차": "BMW", "BMW5시리즈": "BMW", "실내BMW": "BMW",
    "아우디차": "아우디", "폭스바겐차": "폭스바겐", "볼보차": "볼보",
    "포르쉐차": "포르쉐", "렉서스차": "렉서스", "토요타차": "토요타", "BYD차": "BYD",
}


def brand_of_bucket(bucket):
    return BUCKET_BRAND.get(bucket or "")


def same_brand_bucket(brand, exclude=()):
    """그 브랜드의 사진 버킷 중 보유한 것 하나(외관 우선, 실내는 뒤로)."""
    if not brand:
        return None
    have = available_buckets()
    cands = [b for b, br in BUCKET_BRAND.items()
             if br == brand and b not in exclude and have.get(b)]
    if not cands:
        return None
    cands.sort(key=lambda b: (b.startswith("실내"), -have.get(b, 0)))
    return cands[0]


def car_required(bucket):
    """그 버킷 사진에 차가 보여야 하는가(실내·인물·건물 버킷은 예외)."""
    if not bucket:
        return False
    if bucket in NO_CAR_OK or bucket.startswith("실내"):
        return False
    return True


_bucket_cache = None


def available_buckets(refresh=False):
    """assets/photos 에 실제로 존재하는 버킷명 집합(파일 접두어 기준)."""
    global _bucket_cache
    if _bucket_cache is not None and not refresh:
        return _bucket_cache
    buckets = {}
    if os.path.isdir(PHOTO_DIR):
        for fn in os.listdir(PHOTO_DIR):
            if not fn.lower().endswith((".jpg", ".png")) or fn == "index.json":
                continue
            name = fn.split("_")[0]
            buckets[name] = buckets.get(name, 0) + 1
    _bucket_cache = buckets
    return buckets


def _first_existing(names):
    have = available_buckets()
    for n in names:
        if have.get(n):
            return n
    return None


def resolve_category(title, given=None, body=""):
    """제목(+본문)을 보고 최적 버킷을 정한다. 반환: (버킷명 or None, 사유)"""
    text = f"{title} {body}"

    # 0) 제목이 '사건'이면 모델보다 사건 사진이 맞다.
    #    (예: "현대차·기아 미국서 15만대" → 특정 차 사진보다 자동차 운반선이 정확)
    #    특정 모델명이 제목에 없을 때만 적용해 모델 기사를 가로채지 않는다.
    has_model = any(a in title for a in MODEL_ALIASES) or any(a in title for a in MODEL_FALLBACK)
    if not has_model:
        # '만대'만 보고 산업수출로 보내면 내수 판매 기사까지 운반선 사진이 붙는다(실측).
        # 수출·선적 맥락이 분명할 때만 잡는다.
        for pat, b in ((r"수출|선적|운반선|해외\s*판매|미국\s*판매|유럽\s*판매|글로벌\s*판매", "산업수출"),
                       (r"파업|노조|시위|집회|농성", "노조시위")):
            if re.search(pat, title) and available_buckets().get(b):
                return b, f"제목 사건 우선 '{b}'"

    # 1) 제목의 모델명 — 긴 별칭부터
    for alias in sorted(MODEL_ALIASES, key=len, reverse=True):
        if alias in text:
            b = MODEL_ALIASES[alias]
            if available_buckets().get(b):
                return b, f"제목 모델 '{alias}'"

    # 2) 미보유 모델 → 같은 브랜드 대체
    for alias in sorted(MODEL_FALLBACK, key=len, reverse=True):
        if alias in text:
            b = _first_existing(MODEL_FALLBACK[alias])
            if b:
                return b, f"'{alias}' 미보유 → 같은 브랜드 '{b}' 대체"

    # 3) 인물
    for alias in sorted(PEOPLE_ALIASES, key=len, reverse=True):
        if alias in text:
            b = PEOPLE_ALIASES[alias]
            if available_buckets().get(b):
                return b, f"제목 인물 '{alias}'"

    # 4) 상황어 — 제목이 사건 중심이면 지정값보다 우선한다.
    #    (제목만 보고 고른 게 에이전트의 '기억'보다 정확했다: 시위 기사에 사옥 사진이
    #     붙던 문제는 지정값을 먼저 존중해서 생겼다)
    for pat, b in SITUATION_RULES:
        if re.search(pat, title) and available_buckets().get(b):
            return b, f"제목 상황 매칭 '{b}'"

    # 5) 브랜드 — 제목에 여러 브랜드가 나오면 **먼저 나온 쪽이 주인공**이다.
    #    ("기아가 현대를 코앞까지" → 주어는 기아인데 사전순으로 현대를 잡으면 엉뚱해진다)
    hits = [(title.index(a), a) for a in BRAND_ALIASES if a in title]
    for _, alias in sorted(hits):
        b = _first_existing(BRAND_ALIASES[alias])
        if b:
            return b, f"제목 브랜드 '{alias}' → '{b}'"

    # 5.5) 맥락 소재(카카오톡·홈페이지·국기 등) — 브랜드·모델이 없을 때만 적용
    for pat, b in CONTEXT_RULES:
        if re.search(pat, title) and available_buckets().get(b):
            return b, f"제목 맥락 매칭 '{b}'"

    # 6) 에이전트가 준 값이 실제로 있으면 존중(제목에서 아무것도 못 읽었을 때)
    if given and available_buckets().get(given):
        return given, "지정값 유효"

    # 7) 본문 기준 상황어(제목이 추상적일 때)
    for pat, b in SITUATION_RULES:
        if re.search(pat, text) and available_buckets().get(b):
            return b, f"본문 상황 매칭 '{b}'"

    return (given or None), ("지정값 유지(매칭 실패)" if given else "매칭 실패")
