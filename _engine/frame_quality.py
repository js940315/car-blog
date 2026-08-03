# -*- coding: utf-8 -*-
"""유튜브 프레임 품질 평가 — '자막·로고 없는 깨끗한 차 사진'만 골라내기.

유튜브 프레임은 화면에 자막(하단 중앙), 채널로고(모서리), 편집 그래픽이 박혀 있고
모션블러·인물 클로즈업도 섞인다. 그대로 쓰면 썸네일 품질이 무너지므로,
후보를 잔뜩 뽑아 놓고 아래 기준으로 점수를 매겨 상위만 채택한다.

점수(낮을수록 좋음 = penalty):
  1) 하단 자막 밴드 : 하단 중앙 띠의 글자 엣지 밀도 (자막 박스는 여기 몰린다)
  2) 모서리 로고    : 네 모서리 소영역의 엣지 밀도
  3) 선명도         : 라플라시안 분산이 낮으면 모션블러 → 감점
  4) 인물 얼굴      : 정면 얼굴이 크게 잡히면 차 사진이 아님 → 감점
  5) 단색/암전      : 표준편차가 너무 낮으면 장면전환 검은 화면 → 감점
"""

import os

import cv2
import numpy as np

# ── 차량 검출기(MobileNet-SSD) ────────────────────────────────────────────
# '자막·로고 없음'만 보면 무늬 없는 천 클로즈업이 만점을 받는다(실측 실패 사례).
# 프레임에 실제로 '차가 크게' 찍혔는지는 물체 검출로만 알 수 있다.
_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
_SSD_CLASSES = ['background', 'aeroplane', 'bicycle', 'bird', 'boat', 'bottle', 'bus',
                'car', 'cat', 'chair', 'cow', 'diningtable', 'dog', 'horse', 'motorbike',
                'person', 'pottedplant', 'sheep', 'sofa', 'train', 'tvmonitor']
_NET = None


def _net():
    """한글 경로에서도 열리도록 파일을 바이트로 읽어 로드한다(OpenCV 한글경로 이슈)."""
    global _NET
    if _NET is None:
        try:
            p = open(os.path.join(_MODEL_DIR, "MobileNetSSD_deploy.prototxt"), "rb").read()
            m = open(os.path.join(_MODEL_DIR, "MobileNetSSD_deploy.caffemodel"), "rb").read()
            _NET = cv2.dnn.readNetFromCaffe(np.frombuffer(p, np.uint8),
                                            np.frombuffer(m, np.uint8))
        except Exception:
            _NET = False
    return _NET


def car_presence(img):
    """프레임에서 차(car/bus/motorbike)의 최대 신뢰도와 화면 점유 면적을 돌려준다."""
    net = _net()
    if not net:
        return 1.0, 1.0          # 모델 없으면 검사를 건너뛴다(막지 않음)
    blob = cv2.dnn.blobFromImage(cv2.resize(img, (300, 300)), 0.007843, (300, 300), 127.5)
    net.setInput(blob)
    det = net.forward()
    best, area = 0.0, 0.0
    for i in range(det.shape[2]):
        conf = float(det[0, 0, i, 2])
        idx = int(det[0, 0, i, 1])
        if conf > 0.30 and _SSD_CLASSES[idx] in ("car", "bus", "motorbike"):
            x1, y1, x2, y2 = det[0, 0, i, 3:7]
            a = max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))
            if a > area:
                area, best = a, conf
    return best, area


def _edge_density(gray):
    e = cv2.Canny(gray, 80, 200)
    return float(e.mean())


_FACE = None


def _face_cascade():
    global _FACE
    if _FACE is None:
        try:
            _FACE = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        except Exception:
            _FACE = False
    return _FACE


def score_frame(path):
    """프레임 1장 평가. 반환 dict(penalty 낮을수록 좋음)."""
    img = cv2.imread(path)
    if img is None:
        return {"penalty": 999, "reason": "읽기 실패"}
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1) 하단 자막 밴드 (하단 22% 의 가운데 60%)
    band = gray[int(h * 0.78):, int(w * 0.20):int(w * 0.80)]
    band_edge = _edge_density(band)

    # 기준선: 화면 중앙부(자막이 없는 영역)의 엣지 밀도
    mid = gray[int(h * 0.25):int(h * 0.70), int(w * 0.15):int(w * 0.85)]
    mid_edge = _edge_density(mid) or 1.0
    sub_ratio = band_edge / mid_edge          # 1보다 크게 높으면 자막 가능성

    # 2) 모서리 로고 (각 모서리 14% 사각)
    cw, ch = int(w * 0.14), int(h * 0.14)
    corners = [gray[:ch, :cw], gray[:ch, -cw:], gray[-ch:, :cw], gray[-ch:, -cw:]]
    corner_edge = max(_edge_density(c) for c in corners)
    corner_ratio = corner_edge / mid_edge

    # 3) 선명도(모션블러)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # 4) 얼굴
    face_pen = 0.0
    fc = _face_cascade()
    if fc is not None and fc is not False:
        small = cv2.resize(gray, (480, int(480 * h / w)))
        faces = fc.detectMultiScale(small, 1.15, 5, minSize=(48, 48))
        if len(faces):
            biggest = max(f[2] * f[3] for f in faces)
            face_pen = min(40.0, biggest / (480 * (480 * h / w)) * 400)

    # 5) 단색/암전
    flat_pen = 25.0 if float(gray.std()) < 22 else 0.0

    # 6) 화면녹화·그래픽 판별 (실측 실패 사례: 유튜버가 블로그 웹페이지를 띄운 장면이
    #    '자막 없음·얼굴 없음·선명'이라 만점을 받았다). UI/문서 화면의 특징으로 잡는다:
    #    ① 화면 전체에 글자 엣지가 고르게 많다 ② 축에 평행한 긴 직선(창·표·박스)이 많다
    #    ③ 밝고 채도 낮은 큰 면적(흰 배경)
    ui_pen = 0.0
    edges = cv2.Canny(gray, 80, 200)
    global_edge = float(edges.mean())
    if global_edge > 26:                       # 글자·UI가 화면을 뒤덮음
        ui_pen += min(45.0, (global_edge - 26) * 2.2)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=110,
                            minLineLength=int(min(w, h) * 0.45), maxLineGap=6)
    if lines is not None:
        axis = 0
        for x1, y1, x2, y2 in lines[:, 0]:
            if abs(x1 - x2) < 3 or abs(y1 - y2) < 3:   # 수직·수평 직선
                axis += 1
        if axis >= 6:
            ui_pen += min(35.0, (axis - 5) * 3.5)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    bright_flat = float(((gray > 205) & (hsv[:, :, 1] < 40)).mean())
    if bright_flat > 0.18:                     # 흰 배경(문서·웹페이지)이 넓다
        ui_pen += min(30.0, (bright_flat - 0.18) * 120)

    penalty = 0.0
    penalty += max(0.0, (sub_ratio - 1.15)) * 30     # 자막 의심
    penalty += max(0.0, (corner_ratio - 1.30)) * 12  # 로고 의심
    penalty += 25.0 if sharp < 120 else (10.0 if sharp < 260 else 0.0)
    # 7) ★ 차가 실제로 찍혔는가 (가장 중요 — 이게 없으면 '깨끗한 쓰레기'가 통과한다)
    car_conf, car_area = car_presence(img)
    car_pen = 0.0
    if car_conf < 0.45:
        car_pen = 60.0                        # 차가 없음 → 사실상 탈락
    elif car_area < 0.06:
        car_pen = 25.0                        # 차가 너무 작게 나옴(멀리 있는 배경차)
    elif car_area < 0.12:
        car_pen = 10.0

    penalty += face_pen
    penalty += flat_pen
    penalty += ui_pen
    penalty += car_pen

    return {
        "penalty": round(penalty, 1),
        "sub": round(sub_ratio, 2),
        "corner": round(corner_ratio, 2),
        "sharp": round(sharp),
        "face": round(face_pen, 1),
        "ui": round(ui_pen, 1),
        "car": f"{car_conf:.2f}/{car_area:.2f}",
        "std": round(float(gray.std()), 1),
    }


def crop_clean_square(src, dst, size=1400, avoid_bottom=0.14, avoid_top=0.06):
    """자막(하단)·로고(상단)를 최대한 잘라내고 정사각으로 만든다.

    16:9 프레임에서 하단 자막 띠와 상단 로고 띠를 제외한 영역 중
    가장 큰 정사각형을 중앙에서 잘라 확대한다."""
    img = cv2.imread(src)
    if img is None:
        return False
    h, w = img.shape[:2]
    top = int(h * avoid_top)
    bot = int(h * (1.0 - avoid_bottom))
    usable_h = max(1, bot - top)
    side = min(usable_h, w)
    y0 = top + (usable_h - side) // 2
    x0 = (w - side) // 2
    sq = img[y0:y0 + side, x0:x0 + side]
    sq = cv2.resize(sq, (size, size), interpolation=cv2.INTER_LANCZOS4)
    return bool(cv2.imwrite(dst, sq, [int(cv2.IMWRITE_JPEG_QUALITY), 92]))
