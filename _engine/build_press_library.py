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

# 제네시스는 Cloudflare 이미지 리사이저를 쓴다 — URL의 width 를 올리면 원본(최대 1920)까지 받힌다.
GEN_CDN = "https://dams.hyundai-autoever.com/cdn-cgi/image/width=2400,quality=92,format=jpeg/v1/openapi/hmg-presigned-url"


def genesis_urls(items):
    """items = [(자산ID, 파일명), ...] → 최대 해상도 URL"""
    return [f"{GEN_CDN}/{i}/{n}.png" for i, n in items]


# 테슬라: tesla.com 본문은 403(봇 차단)이지만 **이미지 CDN 은 열려 있다**(실측 2026-08-08).
# 그래서 모델 페이지를 훑는 대신 자산명을 직접 지정한다. 새 자산은 이름 규칙
#   {Model-Y|Model-3}-{Main|Interior|Exterior|Performance|Safety}-Hero-Desktop-{Global|LHD}[-v2]
# 을 찔러서 200 이 오는 것만 채택하면 된다.
TSL_CDN = "https://digitalassets.tesla.com/tesla-contents/image/upload/f_auto,q_auto"


def tesla_urls(names):
    return [f"{TSL_CDN}/{n}.jpg" for n in names]


# ── 수입 브랜드 (2026-08-08 3차) ─────────────────────────────────────────────
# 브랜드마다 CDN 이 달라서 한 방식으로 못 묶는다. 각 브랜드 한국 사이트 모델 페이지를
# 브라우저로 열고 img currentSrc 의 호스트를 보면 어느 CDN 인지 바로 나온다(실측):
#   벤츠  = media.oneweb.mercedes-benz.com/images/static/...  (해시 URL, 서명 없음 → 안 만료)
#           ※ 같은 페이지의 iris.png?q=COSY...&cp=... 는 **서명된 동적 렌더**라 쓰지 않는다.
#   BMW   = bmw.scene7.com/is/image/BMW/{자산명}  (Adobe Scene7 → wid/fmt 로 해상도 지정)
#           ※ prod.cosy.bmw.cloud 는 서명 URL이라 제외.
#   볼보  = volvocars.com/images/cs/v3/assets/...  (정적)
#   포르쉐 = a.storyblok.com / images.porsche.com  (경로의 /m/{w}x{h}/ 로 크기 지정,
#            filters:format(avif) 를 떼면 원래 png/jpg 로 받힌다)
#   아우디 = audi.co.kr 이 에러 페이지를 반환해 확보 실패(미해결).
MB = "https://media.oneweb.mercedes-benz.com/images/static/v1/24603"


def benz_urls(paths):
    return [f"{MB}/{p}?im=Resize,width=1920" for p in paths]


def bmw_urls(names):
    return [f"https://bmw.scene7.com/is/image/BMW/{n}?wid=1920&fmt=jpg&qlt=90" for n in names]


def storyblok(url_no_filter, size="1600x0"):
    return f"{url_no_filter}/m/{size}/smart/"

PRESS = {
    # ── 기아: /content/dam/kwp/kr/ko/vehicles/{모델}/{연식}/content/*_pc.jpg (1920px)
    #    현대와 달리 360 뷰가 아니라 '연출 컷'이라 각도 대신 장면(측면·야간·그릴 등)으로 고른다.
    # ── 제네시스: GV80 2027 프레스 컷(전신 위주, 그릴·휠 클로즈업 제외)
    "GV80": genesis_urls([
        ("50534b313031303030303030303030303131353930", "genesis-gv80-2027-key-visual-large"),
        ("50534b313031303030303030303030303131363039", "genesis-gv80-2027-exterior-large"),
        ("50534b313031303030303030303030303131353935", "genesis-gv80-2027-black-exterior-detail-sideprofile-large"),
        ("50534b313031303030303030303030303131353937", "genesis-gv80-2027-black-exterior-detail-rear-large"),
        ("50534b313031303030303030303030303131363031", "genesis-gv80-2027-black-interior-detail-main-large"),
        ("50534b313031303030303030303030303131363033", "genesis-gv80-2027-black-interior-detail-ccp-large"),
        ("50534b313031303030303030303030303133353937", "models/gv80/2027/exterior-color/genesis-gv80-uyuni-white-uyh-large"),
    ]),
    # 2026-08-08 2차 확장 — G80·G90·GV70. GV80과 같은 dams CDN 이고, 자산ID는
    # 모델 페이지(https://www.genesis.com/kr/ko/models/{g80|g90|gv70}) innerHTML 에서
    #   /hmg-presigned-url\/([0-9a-f]{20,})\/([\w\-\/]+)\.png/
    # 로 뽑았다. 그릴·휠·머플러 같은 **클로즈업은 제외**한다(썸네일에서 무슨 차인지 안 보인다).
    "G80": genesis_urls([
        ("50534b313031303030303030303030303133383537", "models/g80/2027/key-visual/genesis-g80-2027-key-visual-large"),
        ("50534b313031303030303030303030303039323031", "genesis-g80-2027-exterior-main-large"),
        ("50534b313031303030303030303030303039313334", "genesis-g80-2027-black-exterior-detail-front-large"),
        ("50534b313031303030303030303030303039313336", "genesis-g80-2027-black-exterior-detail-rear-large"),
        ("50534b313031303030303030303030303133343536", "models/g80/2027/exterior-color/standard/genesis-g80-standard-uyuni-white-uyh-large"),
        ("50534b313031303030303030303030303039313531", "genesis-g80-2027-black-interior-detail-design-large"),
        ("50534b313031303030303030303030303039313538", "genesis-g80-2027-black-interior-detail-ccpsbw-large"),
    ]),
    "G90": genesis_urls([
        ("50534b313031303030303030303030303133383630", "models/g90/2027/key-visual/genesis-g90-2027-key-visual-large"),
        ("50534b313031303030303030303030303131333334", "genesis-g90-2027-exterior-main-large"),
        ("50534b313031303030303030303030303131333337", "genesis-g90-2027-black-exterior-detail-front-large"),
        ("50534b313031303030303030303030303131333339", "genesis-g90-2027-black-exterior-detail-side-large"),
        ("50534b313031303030303030303030303131333431", "genesis-g90-2027-black-exterior-detail-rear-large"),
        ("50534b313031303030303030303030303133353635", "models/g90/2027/exterior-color/standard/genesis-g90-uyuni-white-uyh-large"),
        ("50534b313031303030303030303030303131333637", "genesis-g90-2027-interior-main-large"),
        ("50534b313031303030303030303030303131333639", "genesis-g90-2027-interior-main2-large"),
    ]),
    "GV70": genesis_urls([
        ("50534b313031303030303030303030303134363939", "models/gv70/2027/key-visual/genesis-gv70-key-visual-large"),
        ("50534b313031303030303030303030303134373031", "models/gv70/2027/exterior/genesis-gv70-exterior-large"),
        ("50534b313031303030303030303030303134373035", "models/gv70/2027/exterior/genesis-gv70-exterior-detail-sideprofile-large"),
        ("50534b313031303030303030303030303134373130", "models/gv70/2027/exterior/genesis-gv70-exterior-detail-rear-large"),
        ("50534b313031303030303030303030303133363934", "models/gv70/2027/exterior-color/standard/genesis-gv70-standard-uyuni-white-uyh-large"),
        ("50534b313031303030303030303030303134393130", "models/gv70/2027/graphite/genesis-gv70-graphite-main-large"),
        ("50534b313031303030303030303030303134373139", "models/gv70/2027/interior/genesis-gv70-interior-main1-large"),
        ("50534b313031303030303030303030303134373234", "models/gv70/2027/interior/genesis-gv70-interior-main2-large"),
    ]),
    "테슬라모델Y": tesla_urls([
        "Model-Y-Main-Hero-Desktop-Global",
        "Model-Y-Main-Hero-Desktop-Global-v2",
        "Model-Y-Interior-Hero-Desktop-LHD",
    ]),
    "테슬라모델3": tesla_urls([
        "Model-3-Main-Hero-Desktop-LHD",
        "Model-3-Main-Hero-Desktop-LHD-v2",
        "Model-3-Exterior-Hero-Desktop-LHD",
        "Model-3-Performance-Hero-Desktop-LHD",
        # Model-3-Safety-Hero 는 제외 — 실차가 아니라 **차체 골격 투시도**다(실측 폐기).
        "Model-3-Interior-Hero-Desktop-LHD",
    ]),
    # 벤츠는 미해결 — 페이지 innerHTML 의 /images/static/ 해시 URL 8건을 받아 보니
    # **전부 차가 없는 배경 그라데이션**이었다(회색·갈색·빨강 면). 실차 컷은 서명된
    # iris.png?q=COSY... 쪽에만 있는 것으로 보인다. 재시도할 때는 DevTools Network 에서
    # 실제 히어로 이미지 요청을 확인할 것. 벤츠 버킷은 당분간 wiki/stock 으로 간다.
    "BMW5시리즈": bmw_urls([
        "g60_ice_stage_ext-loop-alternative_dsk_sl_de",     # 외관 정측면
        "g60_ice_driving-dynamics_dsk_fb_en",               # 주행컷
        "g60_ice_ext-design-highlights_3_skyroof_dsk_fb_de",  # 지붕 부감
        "g60_ice_int-design-video-loop_dsk_fb-1_en",        # 실내 콕핏
        # int-design-highlights 1(인터랙션바)·2(사운드)는 스크린·스피커 클로즈업이라 제외.
    ]),
    # 볼보는 미해결 — innerHTML 에서 뽑은 정적 URL 이 서버에선 403/404 다.
    # (헤더를 브라우저와 똑같이 맞추면 403 -> 404 로만 바뀐다. 페이지가 쓰는 실제 URL 에
    #  쿼리나 리라이트가 더 붙는 것으로 보인다. 재시도할 때는 DevTools Network 로
    #  실제 요청 URL 을 그대로 복사해 올 것.) 볼보차 버킷은 당분간 wiki/stock 으로 간다.
    "포르쉐차": [
        storyblok("https://a.storyblok.com/f/322327/1720x1210/6c774c8370/cayenne-front.png", "1600x1126"),
        # cayenne-side(9600x3040)는 /m/ 크기를 어떻게 줘도 404 — 원본 비율 밖 요청은 거부된다.
        storyblok("https://a.storyblok.com/f/322327/2616x1473/c4982ccdc4/051-mosaic-editorial-desktop-i2.jpg", "1800x1013"),
        # ※ images.porsche.com 의 model-*-side-shot 은 5000x1795 **초광각**이라 정사각으로
        #   만들면 앞뒤가 다 날아가고 도어만 남는다(실측). 가로세로비 3:1 이 넘는 소스는 쓰지 말 것.
    ],
    "EV6": [
        f"{KIA}/ev6/pe/content/ev6_pe_exterior_front_style_pc.jpg",
        f"{KIA}/ev6/pe/content/ev6_pe_exterior_modern_contrast_side_veiw_pc.jpg",
        f"{KIA}/ev6/pe/content/ev6_pe_exterior_modern_contrast_rear_veiw_pc.jpg",
        f"{KIA}/ev6/pe/content/ev6_pe_gtl_exterior_pc.jpg",
        f"{KIA}/ev6/27my/content/ev6_pe_interior_pc.jpg",
        f"{KIA}/ev6/27my/content/ev6_pe_gtl_interior_pc.jpg",
    ],
    "EV9": [
        f"{KIA}/ev9/24my/content/ev9_exterior_flagship_pc.jpg",
        f"{KIA}/ev9/24my/content/ev9_exterior_side_profile_pc.jpg",
        f"{KIA}/ev9/26my/content/ev9_interior_front.jpg",
        f"{KIA}/ev9/26my/content/ev9_interior_side.jpg",
    ],
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
    "아이오닉9": exterior_urls("ME02", "A2B") + interior_urls("ME02", ["IA6", "IA5", "IA4"]),
    "아반떼": exterior_urls("FN01", "SAW", mid="") + interior_urls("FN01", ["IQ3", "IQ2", "IH5"]),
    "투싼": exterior_urls("NX17", "TW3", mid="") + interior_urls("NX17", ["IK0", "IJ8", "IJ9"]),
    "코나": exterior_urls("SX19", "RRR", mid="") + interior_urls("SX19", ["I54", "IC2", "IC1"]),
    "그랜저": exterior_urls("GN11", "WBP", mid="") + interior_urls("GN11", ["IN6", "IN5", "IN4"]),
    "싼타페": exterior_urls("MX07", "A2B") + interior_urls("MX07", ["II9", "IJ1", "IH0"]),
    # 2026-08-08 3차 추가. 스타리아만 exterior 중간 경로가 'TM/' 이다(모델마다 다르다).
    "쏘나타": exterior_urls("DN23", "T4M", mid="") + interior_urls("DN23", ["IK6", "IK7", "IK8"]),
    "스타리아": exterior_urls("US30", "YAC", mid="TM/") + interior_urls("US30", ["IL2", "IL3", "IL4"]),
    "팰리세이드": exterior_urls("FX01", "R8N") + [
        "https://www.hyundai.com/contents/vr360/FX01/interior/I93/img-interior.png",
        "https://www.hyundai.com/contents/vr360/FX01/interior/I96/img-interior.png",
        "https://www.hyundai.com/contents/vr360/FX01/interior/I94/img-interior.png",
        "https://www.hyundai.com/contents/vr360/FX01/interior/I85/img-interior.png",
        "https://www.hyundai.com/static/images/model/palisade/25fc/palisade_hyundai_ai_assistant_main.jpg",
        "https://www.hyundai.com/static/images/model/palisade/25fc/palisade_hyundai_ai_assistant_spot.jpg",
    ],
}


def _load_on_white(path):
    """투명 PNG는 **흰 배경에 합성**해서 연다.

    현대·기아 프레스 PNG는 배경이 투명이다. 그냥 convert("RGB") 하면 투명부가 **검게**
    변해 위아래 검은 띠가 생겼다(실측 2026-08-08). 흰 배경에 얹으면 스튜디오 컷처럼
    깔끔해지고, 피사체 경계 검출도 정확해진다."""
    from PIL import Image
    raw = Image.open(path)
    if raw.mode in ("RGBA", "LA") or (raw.mode == "P" and "transparency" in raw.info):
        rgba = raw.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[3])
        return canvas
    return raw.convert("RGB")


def _uniform_bg(im, tol=14):
    """네 모서리 색이 비슷하면 '단색 배경 스튜디오 컷'으로 보고 그 색을 돌려준다."""
    w, h = im.size
    k = max(2, min(w, h) // 60)
    pts = [im.crop((0, 0, k, k)), im.crop((w - k, 0, w, k)),
           im.crop((0, h - k, k, h)), im.crop((w - k, h - k, w, h))]
    cols = [p.resize((1, 1)).getpixel((0, 0)) for p in pts]
    for c in cols[1:]:
        if max(abs(a - b) for a, b in zip(c, cols[0])) > tol:
            return None
    return cols[0]


def _pad_to_square(im, blur=18):
    """비정사각 이미지를 **한 픽셀도 잘라내지 않고** 정사각으로 만든다.

    빈 자리는 맞닿은 가장자리 띠를 늘려 흐리게 채운다 — 단색으로 메우는 것보다
    이음매가 덜 보인다. 프레스 컷은 그 띠가 대개 흰 배경이라 티가 거의 안 난다."""
    from PIL import Image, ImageFilter
    w, h = im.size
    if w == h:
        return im
    s = max(w, h)
    canvas = Image.new("RGB", (s, s))
    ox, oy = (s - w) // 2, (s - h) // 2
    if h < s:                   # 위·아래 여백
        band = max(1, h // 14)
        top_h, bot_h = max(1, oy), max(1, s - oy - h)
        top = im.crop((0, 0, w, band)).resize((s, top_h), Image.LANCZOS)
        bot = im.crop((0, h - band, w, h)).resize((s, bot_h), Image.LANCZOS)
        canvas.paste(top.filter(ImageFilter.GaussianBlur(blur)), (0, 0))
        canvas.paste(bot.filter(ImageFilter.GaussianBlur(blur)), (0, oy + h))
    if w < s:                   # 좌·우 여백
        band = max(1, w // 14)
        left_w, right_w = max(1, ox), max(1, s - ox - w)
        left = im.crop((0, 0, band, h)).resize((left_w, s), Image.LANCZOS)
        right = im.crop((w - band, 0, w, h)).resize((right_w, s), Image.LANCZOS)
        canvas.paste(left.filter(ImageFilter.GaussianBlur(blur)), (0, 0))
        canvas.paste(right.filter(ImageFilter.GaussianBlur(blur)), (ox + w, 0))
    canvas.paste(im, (ox, oy))
    return canvas


def smart_fit(path, long_side=1400, fill=0.94):
    """차가 프레임을 꽉 채우게 다듬되 **원본 비율을 유지**한다.

    2026-08-20 사용자 지시로 정사각 강제를 폐기했다.
      "넣는 이미지가 꼭 정방향 정사각형일 필요 없어.
       자동차 이상하게 자르지 말고 포인트 잘 살려라."
    예전 smart_square 는 정사각 창이 원본보다 커지면 _pad_to_square 로 위아래를
    흐린 띠로 때웠다. 그 결과 실제 사진이 세로의 절반만 남고 차가 잘렸다
    (라이브러리 539장이 전부 1400x1400 으로 그렇게 저장돼 있었다).
    네이버 블로그는 어떤 비율이든 그대로 보여준다 — 정사각을 고집할 이유가 없다.

    창은 **원본과 같은 비율**로 잡는다. 그래야 어떤 경우에도 띠가 안 생긴다.
    """
    from PIL import Image
    im = _load_on_white(path)
    W, H = im.size
    box = _subject_bbox(im)
    if box:
        x0, y0, x1, y1 = box
        bw, bh = max(1, x1 - x0), max(1, y1 - y0)
        ar = W / H
        nw, nh = bw / fill, bh / fill
        if nw / nh > ar:
            win_w, win_h = nw, nw / ar
        else:
            win_h, win_w = nh, nh * ar
        win_w, win_h = min(win_w, W), min(win_h, H)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sx = int(max(0, min(W - win_w, cx - win_w / 2)))
        sy = int(max(0, min(H - win_h, cy - win_h / 2)))
        im = im.crop((sx, sy, sx + int(win_w), sy + int(win_h)))
    sc = long_side / max(im.size)
    if sc < 1:
        im = im.resize((max(1, round(im.width * sc)),
                        max(1, round(im.height * sc))), Image.LANCZOS)
    im.save(path, "JPEG", quality=94, subsampling=1)
    return im


def subject_cut_off(im, margin_ratio=200):
    """정사각 결과물에서 피사체가 프레임 가장자리에 닿는지 = 잘렸는지 본다.

    실내 컷은 원래 화면을 꽉 채우므로 항상 True 가 나온다 — 외관 컷에만 쓸 것."""
    box = _subject_bbox(im)
    if not box:
        return False
    w, h = im.size
    x0, y0, x1, y1 = box
    m = max(2, min(w, h) // margin_ratio)
    return x0 <= m or y0 <= m or x1 >= w - m or y1 >= h - m


def _subject_bbox(im, thresh=20):
    """배경이 단색이든 가로 그라데이션이든 '차'의 경계를 찾는다.
    각 행의 좌우 끝을 그 행의 배경색으로 보고, 그와 다른 픽셀만 피사체로 친다."""
    from PIL import Image
    small = im.resize((min(400, im.width), min(400, im.height)), Image.BILINEAR)
    px = small.load()
    w, h = small.size
    edge = max(2, w // 25)
    xs, ys = [], []
    for y in range(h):
        lo = [px[i, y] for i in range(edge)]
        hi = [px[w - 1 - i, y] for i in range(edge)]
        ref = tuple(sum(c[i] for c in lo + hi) // len(lo + hi) for i in range(3))
        for x in range(w):
            p = px[x, y]
            if max(abs(p[i] - ref[i]) for i in range(3)) > thresh:
                xs.append(x)
                ys.append(y)
    if len(xs) < 50:
        return None
    sx, sy = im.width / w, im.height / h
    return (int(min(xs) * sx), int(min(ys) * sy),
            int((max(xs) + 1) * sx), int((max(ys) + 1) * sy))


def fit_square_pad(path, size=1400):
    """차가 잘리지 않게 **전체를 담고** 남는 공간만 배경색으로 채워 정사각으로 만든다.

    기존엔 prepare_photo() 가 중앙을 잘라 정사각으로 만들었는데, 자동차 프레스 컷은
    가로로 길어서(16:9) 앞뒤 범퍼가 날아갔다(실측 2026-08-08). 프레스 사진은 배경이
    단색·그라데이션이라, 가장자리 색을 뽑아 채우면 이어 붙인 티가 거의 안 난다."""
    from PIL import Image, ImageFilter
    im = _load_on_white(path)
    w, h = im.size
    if w == h:
        return im.resize((size, size), Image.LANCZOS).save(path, "JPEG", quality=94)
    # 4:3 정도까지는 살짝 잘라서 채운다 — 완전히 다 담으려다 보면 16:9 사진이
    # 정사각 안에서 너무 작아져 위아래가 휑해진다(실측 2026-08-08).
    # 차의 앞뒤가 날아가지 않는 선(가로 최대 33% 크롭)까지만 crop 하고 나머지는 패딩.
    MAX_CROP = 1.34          # 허용 가로세로비. 이보다 길면 여기까지만 좌우를 잘라낸다
    if w / h > MAX_CROP:
        keep = int(h * MAX_CROP)
        left = (w - keep) // 2
        im = im.crop((left, 0, left + keep, h))
        w, h = im.size
    elif h / w > MAX_CROP:
        keep = int(w * MAX_CROP)
        top = (h - keep) // 2
        im = im.crop((0, top, w, top + keep))
        w, h = im.size

    # 남은 여백은 가장자리를 늘려 흐린 배경으로 채운다(단색보다 이질감이 적다)
    scale = size / max(w, h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    small = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size))
    ox, oy = (size - nw) // 2, (size - nh) // 2
    if nh < size:      # 위·아래 여백
        band = max(1, nh // 14)
        top = small.crop((0, 0, nw, band)).resize((size, max(1, oy)), Image.LANCZOS)
        bot_h = size - oy - nh
        bot = small.crop((0, nh - band, nw, nh)).resize((size, max(1, bot_h)), Image.LANCZOS)
        canvas.paste(top.filter(ImageFilter.GaussianBlur(18)), (0, 0))
        canvas.paste(bot.filter(ImageFilter.GaussianBlur(18)), (0, oy + nh))
    if nw < size:      # 좌·우 여백
        band = max(1, nw // 14)
        left = small.crop((0, 0, band, nh)).resize((max(1, ox), size), Image.LANCZOS)
        right_w = size - ox - nw
        right = small.crop((nw - band, 0, nw, nh)).resize((max(1, right_w), size), Image.LANCZOS)
        canvas.paste(left.filter(ImageFilter.GaussianBlur(18)), (0, 0))
        canvas.paste(right.filter(ImageFilter.GaussianBlur(18)), (ox + nw, 0))
    canvas.paste(small, (ox, oy))
    im = small
    canvas.save(path, "JPEG", quality=94, subsampling=1)
    return canvas


def fetch(url, dst, referer=None):
    # 브랜드별로 Referer 를 맞춰야 CDN 이 막지 않는다
    if referer is None:
        referer = ("https://www.kia.com/" if "kia.com" in url
                   else "https://www.genesis.com/" if "genesis.com" in url
                   else "https://www.tesla.com/" if "tesla.com" in url
                   else "https://www.mercedes-benz.co.kr/" if "mercedes-benz.com" in url
                   else "https://www.bmw.co.kr/" if "scene7.com" in url
                   else "https://www.volvocars.com/" if "volvocars.com" in url
                   else "https://www.porsche.com/" if ("porsche.com" in url
                                                       or "storyblok.com" in url)
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

    total = 0
    for model, urls in targets.items():
        print(f"\n=== {model}")
        # PRESS 목록에서 URL을 빼면 이전 실행이 만든 뒷번호 파일이 그대로 남아,
        # 새 번호와 **같은 사진이 두 장**이 된다(실측: 테슬라모델3 press4 == press5).
        # 어차피 전 URL을 다시 받으므로 그 모델 파일은 먼저 싹 지우고 시작한다.
        for fn in os.listdir(DIR):
            if fn.startswith(f"{model}_press"):
                try:
                    os.remove(os.path.join(DIR, fn))
                    idx.pop(fn, None)
                except OSError as e:
                    print(f"   [경고] 이전 파일 삭제 실패 {fn}: {e}")
        for i, u in enumerate(urls):
            ext = ".png" if u.lower().endswith(".png") else ".jpg"
            name = f"{model}_press{i}{ext}"
            path = os.path.join(DIR, name)
            try:
                time.sleep(0.6)
                n = fetch(u, path)
                # 2026-08-08 방향 전환: 누끼(배경 제거)를 하지 않는다.
                # 벤치마크 블로거들은 공장·모터쇼·야외 같은 '배경 있는 실사'를 쓴다.
                # 흰 배경 누끼는 밋밋하고, 합성 렌더는 잔재(떠 있는 루프레일 등)가 남았다.
                #
                # ★ 2026-08-14: 여기서 fit_square_pad 를 부르고 있었다 — 그 함수는 가로세로비
                #   1.34 까지 좌우를 잘라낸다. 현대 vr360 원본은 940x515(1.82)라 매번 최대치로
                #   잘렸고, 측면·후측면 컷은 앞뒤 범퍼가 통째로 날아갔다(사용자 신고, 0813/9
                #   그랜저). 차 경계를 찾아 절대 자르지 않는 smart_fit 가 이미 있었는데
                #   호출부에 연결이 안 된 죽은 코드였다.
                out = smart_fit(path, long_side=1400)
                if "interior" not in u.lower() and subject_cut_off(out):
                    print(f"   [경고] {name}: 차가 프레임 가장자리에 닿는다(잘렸을 수 있음)")
                idx[name] = {
                    "카테고리": model,
                    "license": "제조사 공식 이미지(사용자 책임)",
                    "credit": u,
                    "attribution_required": False,
                    "처리": "프레스 원본 → 피사체 기준 정사각 1400px(무크롭)",
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
