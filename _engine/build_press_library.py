# -*- coding: utf-8 -*-
"""제조사 공식 사이트에서 프레스급 스튜디오 사진을 수집한다.

배경: Commons/스톡 사진은 딜러 광고 문구·번호판·주차장 스냅샷이 섞여 홈판에서
"우와 이 차 뭐지?"가 안 나온다. 홈판 상위 블로그(아워오토·곰도라)는 제조사 공식
스튜디오 컷을 쓴다. 그래서 같은 급의 소스를 직접 확보한다.

    python _engine/build_press_library.py --list                 # 등록된 모델 보기
    python _engine/build_press_library.py 팰리세이드              # 한 모델
    python _engine/build_press_library.py --all                  # 전체

동작: 모델 페이지를 헤드리스 브라우저 없이 정적으로 훑을 수 없으므로(JS 렌더),
이미 확인된 이미지 URL 패턴을 직접 조회한다. 현대닷컴은
  /static/images/model/{model}/{code}/*.jpg   (외관·기능 컷, 1920px)
  /contents/vr360/{platform}/interior/*/img-interior.png (실내 360, 1680px)
형태로 CDN에 공개돼 있어 Referer만 붙이면 그대로 받힌다(실측 2026-08-08).

받은 뒤 반드시 컨택트시트로 눈 확인하고, 어울리지 않는 컷은 지운다.
"""

import argparse
import json
import os
import sys
import time
import urllib.request

DIR = os.path.join("assets", "photos")
INDEX = os.path.join(DIR, "index.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 모델명(버킷) -> 이미지 URL 목록. 현대닷컴 CDN 실측 경로.
# 새 모델을 추가하려면 해당 모델 페이지를 브라우저로 열어
#   document.querySelectorAll('img') 중 naturalWidth>=1000 인 currentSrc 를 모아 넣는다.
# 외관 360 뷰: /contents/vr360/{플랫폼}/exterior/C/{색상코드}/001~036.png (36각도)
# 그중 '보기 좋은 각도'만 고른다 — 001 정면, 005 전측면(가장 잘 나옴), 010 측면,
# 018 후측면, 025 후면. 전 각도를 다 받으면 비슷한 컷만 쌓인다.
EXTERIOR_ANGLES = ["001", "005", "010", "018", "025"]


def exterior_urls(platform, color, angles=None, mid="C/"):
    """외관 360 URL. 경로가 모델마다 다르다(실측):
       팰리세이드/싼타페 → /exterior/C/{색상}/001.png
       그랜저            → /exterior/{색상}/001.png   (mid="")"""
    base = f"https://www.hyundai.com/contents/vr360/{platform}/exterior/{mid}{color}"
    return [f"{base}/{a}.png" for a in (angles or EXTERIOR_ANGLES)]


def interior_urls(platform, codes):
    return [f"https://www.hyundai.com/contents/vr360/{platform}/interior/{c}/img-interior.png"
            for c in codes]


# ※ 플랫폼 코드(FX01, MX07…)는 추측이 안 된다. 모델 페이지를 브라우저로 열고
#   innerHTML 에서 /contents/vr360/([A-Z0-9]+)/ 를 뽑아 확인해야 한다(실측).
#   색상코드도 모델마다 달라 001~036 중 005 로 존재 여부를 찔러 확인한다.
KIA = "https://www.kia.com/content/dam/kwp/kr/ko/vehicles"

PRESS = {
    # ── 기아: /content/dam/kwp/kr/ko/vehicles/{모델}/{연식}/content/*_pc.jpg (1920px)
    #    현대와 달리 360 뷰가 아니라 '연출 컷'이라 각도 대신 장면(측면·야간·그릴 등)으로 고른다.
    # 디테일 컷(그릴·휠·엠블럼 클로즈업)은 제외 — 썸네일에서 무슨 차인지 안 보인다.
    "카니발": [
        f"{KIA}/carnival/26my/content/carnival_exterior_line-up_pc.jpg",
        f"{KIA}/carnival/24pe/content/carnival_exterior_front_view_pc.jpg",
        f"{KIA}/carnival/24pe/content/carnival_exterior_rear_view_pc.jpg",
        f"{KIA}/carnival/26my/content/carnival_xline_pc.jpg",
        f"{KIA}/carnival/26my/content/carnival_hi-roof_pc.jpg",
        f"{KIA}/carnival/26my/content/carnival_hi-roof_interior_pc.jpg",
    ],
    "스포티지": [
        f"{KIA}/sportage/pe/content/sportage_exterior_lineup_pc.jpg",
        f"{KIA}/sportage/pe/content/sportage_exterior_cover_pc.jpg",
        f"{KIA}/sportage/pe/content/sportage_x-line_pc.jpg",
        f"{KIA}/sportage/pe/content/sportage_x-line_black_interior_pc.jpg",
        f"{KIA}/sportage/pe/content/sportage_interior_maindash_pc.jpg",
        f"{KIA}/sportage/pe/content/sportage_interior_ambient_pc.jpg",
    ],
    "쏘렌토": [
        f"{KIA}/sorento/26my/content/sorento_exterior_line_up_pc.jpg",
        f"{KIA}/sorento/24pe/content/sorento_exterior_side_pc.jpg",
        f"{KIA}/sorento/24pe/content/sorento_exterior_night_view_main_pc.jpg",
        f"{KIA}/sorento/24pe/content/sorento_exterior_rear_pc.jpg",
        f"{KIA}/sorento/26my/content/sorento_xline_main_pc.jpg",
        f"{KIA}/sorento/26my/content/sorento_interior_brown_front.jpg",
        f"{KIA}/sorento/26my/content/sorento_interior_gray_front.jpg",
    ],
    # 실측 코드(2026-08-08, 모델 페이지 innerHTML 에서 추출)
    # ※ 아이오닉5는 외관(NE10)과 실내(NE09) 플랫폼 코드가 다르다.
    "아이오닉5": exterior_urls("NE10", "C5G", mid="") + interior_urls("NE09", ["IP0", "IP1", "IP2"]),
    "투싼": exterior_urls("NX17", "TW3", mid="") + interior_urls("NX17", ["IK0", "IJ8", "IJ9"]),
    "코나": exterior_urls("SX19", "RRR", mid="") + interior_urls("SX19", ["I54", "IC2", "IC1"]),
    "그랜저": exterior_urls("GN11", "WBP", mid="") + interior_urls("GN11", ["IN6", "IN5", "IN4"]),
    "싼타페": exterior_urls("MX07", "A2B") + interior_urls("MX07", ["II9", "IJ1", "IH0"]),
    "팰리세이드": exterior_urls("FX01", "R8N") + [
        "https://www.hyundai.com/contents/vr360/FX01/interior/I93/img-interior.png",
        "https://www.hyundai.com/contents/vr360/FX01/interior/I96/img-interior.png",
        "https://www.hyundai.com/contents/vr360/FX01/interior/I94/img-interior.png",
        "https://www.hyundai.com/contents/vr360/FX01/interior/I85/img-interior.png",
        "https://www.hyundai.com/static/images/model/palisade/25fc/palisade_hyundai_ai_assistant_main.jpg",
        "https://www.hyundai.com/static/images/model/palisade/25fc/palisade_hyundai_ai_assistant_spot.jpg",
    ],
}


def fetch(url, dst, referer=None):
    # 브랜드별로 Referer 를 맞춰야 CDN 이 막지 않는다
    if referer is None:
        referer = ("https://www.kia.com/" if "kia.com" in url
                   else "https://www.genesis.com/" if "genesis.com" in url
                   else "https://www.hyundai.com/")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    data = urllib.request.urlopen(req, timeout=30).read()
    with open(dst, "wb") as f:
        f.write(data)
    return len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?", help="모델명(버킷). 생략 시 --all 필요")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for m, u in PRESS.items():
            print(f"  {m:<12} {len(u)}장")
        return 0

    targets = PRESS if args.all else ({args.model: PRESS[args.model]}
                                      if args.model in PRESS else None)
    if targets is None:
        print("등록되지 않은 모델입니다. --list 로 확인하세요.")
        return 1

    os.makedirs(DIR, exist_ok=True)
    idx = {}
    if os.path.exists(INDEX):
        try:
            idx = json.load(open(INDEX, encoding="utf-8"))
        except ValueError:
            idx = {}

    from image_sourcing import prepare_photo
    total = 0
    for model, urls in targets.items():
        print(f"\n=== {model}")
        for i, u in enumerate(urls):
            ext = ".png" if u.lower().endswith(".png") else ".jpg"
            name = f"{model}_press{i}{ext}"
            path = os.path.join(DIR, name)
            try:
                time.sleep(0.6)
                n = fetch(u, path)
                prepare_photo(path, path, size=1400)
                idx[name] = {
                    "카테고리": model,
                    "license": "제조사 공식 이미지(사용자 책임)",
                    "credit": u,
                    "attribution_required": False,
                    "처리": "프레스 원본 → 정사각 1400px",
                    "검색어": "press",
                    "검수": "미확인 — 눈 확인 필요",
                }
                print(f"   OK {name:<26} {n//1024}KB")
                total += 1
            except Exception as e:
                print(f"   실패 {name}: {str(e)[:50]}")

    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX)
    print(f"\n총 {total}장 -> {DIR}/  (컨택트시트로 눈 확인 후 사용)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
