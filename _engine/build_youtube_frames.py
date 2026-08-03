# -*- coding: utf-8 -*-
"""유튜브 영상에서 고화질 프레임을 뽑아 사진 버킷에 넣는다.

Commons·스톡에 아직 없는 **미공개/신규 모델**(GV90 등)이나 스파이샷처럼
'영상에만 존재하는' 장면을 확보하기 위한 도구.

    python _engine/build_youtube_frames.py "제네시스 GV90 실물" --name GV90
    python _engine/build_youtube_frames.py "아이오닉9 실내" --name 아이오닉9 --keywords 실내,인테리어

동작:
  1) 유튜브 검색 → 상위 영상 선택(1080p 이상 우선)
  2) 한국어 자동자막을 받아 --keywords 가 나오는 구간의 타임스탬프를 뽑는다
     (예: '실내'가 언급되는 04:49 → 그 장면에 실내가 보일 확률이 높다)
  3) 그 시점 ±오프셋에서 프레임을 추출 → 정사각 1400px 로 가공
  4) 사람이 컨택트시트로 보고 쓸 것만 남긴다(자막·로고 박힌 컷 배제)

주의: 프레임은 화면에 자막·채널로고·편집그래픽이 박혀 있을 수 있다.
      반드시 눈으로 검수한 뒤 쓴다. 평상시 사진은 build_photo_library 쪽이 화질이 낫다.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse

DIR = os.path.join("assets", "photos")
INDEX = os.path.join(DIR, "index.json")
DEFAULT_KEYWORDS = "실내,인테리어,외관,디자인,전면,후면,측면,실물,디테일"


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


# ── 검증된 공식 채널 화이트리스트 (2026-08-03 yt-dlp로 구독자수 실측) ──────
# 키워드 검색만 쓰면 토크·화면녹화·ASMR 영상이 걸린다(실측 실패). 제조사 공식 채널은
# 자막·진행자 없는 깨끗한 B롤(주행·스튜디오·디테일)이 대부분이라 프레임 품질이 압도적이다.
# 사용: 브랜드가 특정되면 그 채널 안에서 검색 → 없으면 일반 검색으로 폴백.
OFFICIAL_CHANNELS = {
    "현대": ["HyundaiWorldwide", "hyundai"],      # 912K / 383K(USA)
    "제네시스": ["GenesisWorldwide"],              # 1.28M
    "기아": ["Kia"],                              # 161K(America)
    "테슬라": ["tesla"],                           # 2.95M
    "벤츠": ["mercedesbenz"],                      # 2.41M
    "BMW": ["BMW"],                                # 2.04M
    "아우디": ["Audi"],                            # 355K
    "폭스바겐": ["volkswagen"],                    # 335K
    "포르쉐": ["Porsche"],                         # 1.61M
    "볼보": ["volvocars"],                         # 329K
    "렉서스": ["Lexus"],                           # 278K
    "토요타": ["ToyotaUSA"],                       # 964K
    "BYD": ["BYDGlobal"],                          # 34.4K
}
# 브랜드 특정이 안 될 때 쓸 한국 자동차 전문 채널(실차 위주, 검증됨)
KR_AUTO_CHANNELS = ["motorgraph", "AutoTribune"]   # 371K / 102K

# 모델명 → 브랜드 (공식 채널 선택용)
MODEL_BRAND = {
    "아이오닉": "현대", "팰리세이드": "현대", "싼타페": "현대", "투싼": "현대",
    "코나": "현대", "그랜저": "현대", "쏘나타": "현대", "아반떼": "현대", "스타리아": "현대",
    "쏘렌토": "기아", "스포티지": "기아", "셀토스": "기아", "카니발": "기아",
    "EV6": "기아", "EV9": "기아", "EV3": "기아", "타스만": "기아",
    "GV": "제네시스", "G80": "제네시스", "G90": "제네시스", "제네시스": "제네시스",
    "테슬라": "테슬라", "모델Y": "테슬라", "모델3": "테슬라",
    "벤츠": "벤츠", "BMW": "BMW", "아우디": "아우디", "폭스바겐": "폭스바겐",
    "포르쉐": "포르쉐", "볼보": "볼보", "렉서스": "렉서스", "토요타": "토요타", "BYD": "BYD",
}

OFFICIAL_HINTS = ["공식", "official", "genesis", "hyundai", "kia", "motor", "모터스",
                  "현대자동차", "기아", "제네시스", "bmw", "mercedes", "audi", "volkswagen"]


def brand_of(text):
    """검색어/모델명에서 브랜드를 추정한다(긴 키부터)."""
    for k in sorted(MODEL_BRAND, key=len, reverse=True):
        if k.lower() in text.lower():
            return MODEL_BRAND[k]
    return None


def channel_search(handle, query, limit=4):
    """특정 채널 안에서 검색한다(공식 채널의 깨끗한 B롤을 직접 노린다)."""
    url = f"https://www.youtube.com/@{handle}/search?query={urllib.parse.quote(query)}"
    r = _run(["yt-dlp", url, "--skip-download", "--no-warnings", "--playlist-end", str(limit),
              "--print", "%(id)s\t%(duration)s\t%(channel)s\t%(title).70s"], timeout=180)
    out = []
    for line in (r.stdout or "").strip().splitlines():
        p = line.split("\t")
        if len(p) < 4:
            continue
        try:
            dur = int(float(p[1]))
        except ValueError:
            dur = 0
        if dur < 15 or dur > 1800:
            continue
        out.append({"id": p[0], "duration": dur, "channel": p[2], "title": p[3],
                    "score": -10})       # 공식 채널은 최우선
    return out
# 화면녹화·잡담 위주라 프레임 품질이 나쁜 유형
BAD_TITLE_HINTS = ["리뷰", "vlog", "브이로그", "썰", "라이브", "live", "정리", "뉴스"]


def search_videos(query, limit=6, prefer_official=True):
    """후보 영상을 '깨끗할 가능성' 순으로 돌려준다.

    ① 브랜드가 특정되면 그 브랜드 **공식 채널 안에서** 먼저 찾는다(B롤 = 자막·진행자 없음)
    ② 부족하면 한국 자동차 전문 채널
    ③ 그래도 부족하면 일반 유튜브 검색
    (403·DRM으로 막히는 영상이 있어 후보를 여러 개 들고 있어야 한다)"""
    cands = []
    if prefer_official:
        br = brand_of(query)
        handles = OFFICIAL_CHANNELS.get(br, []) if br else []
        for h in handles:
            cands += channel_search(h, query)
            if len(cands) >= limit:
                break
        if len(cands) < 2:
            for h in KR_AUTO_CHANNELS:
                cands += [dict(c, score=-4) for c in channel_search(h, query, limit=3)]
                if len(cands) >= limit:
                    break
    if cands:
        print(f"  공식/전문 채널 후보 {len(cands)}건")

    r = _run(["yt-dlp", f"ytsearch{limit}:{query}", "--skip-download", "--no-warnings",
              "--print", "%(id)s\t%(duration)s\t%(channel)s\t%(title).70s"])
    for line in (r.stdout or "").strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        vid, dur, ch, title = parts[0], parts[1], parts[2], parts[3]
        try:
            dur = int(float(dur))
        except ValueError:
            dur = 0
        if dur > 3600 or dur < 20:
            continue
        blob = f"{ch} {title}".lower()
        score = 0
        if any(h in blob for h in OFFICIAL_HINTS):
            score -= 5                      # 공식/제조사 채널 우대
        if any(h in blob for h in BAD_TITLE_HINTS):
            score += 3                      # 토크·리뷰형 감점
        if dur <= 180:
            score -= 2                      # 짧은 영상 = 대개 B롤·티저
        cands.append({"id": vid, "title": title, "channel": ch,
                      "duration": dur, "score": score})
    cands.sort(key=lambda c: c["score"])
    return cands


def search_video(query, min_height=1080, limit=6):
    c = search_videos(query, limit)
    return c[0] if c else None


def get_timestamps(vid, keywords, max_n=8, workdir="."):
    """한국어 자막에서 키워드가 나오는 지점의 초 단위 타임스탬프."""
    base = os.path.join(workdir, f"_sub_{vid}")
    _run(["yt-dlp", f"https://youtu.be/{vid}", "--write-auto-sub", "--sub-lang", "ko",
          "--sub-format", "vtt", "--skip-download", "-o", base, "--no-warnings"])
    path = base + ".ko.vtt"
    if not os.path.exists(path):
        return []
    text = open(path, encoding="utf-8", errors="replace").read()
    pat = re.compile("|".join(re.escape(k.strip()) for k in keywords if k.strip()))
    hits, seen = [], set()
    for ts, line in re.findall(r"(\d\d):(\d\d):(\d\d)\.\d+ --> .*?\n(.*?)\n", text) and \
            re.findall(r"(\d\d:\d\d:\d\d)\.\d+ --> .*?\n(.*?)\n", text):
        line = line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        if pat.search(line):
            h, m, s = (int(x) for x in ts.split(":"))
            sec = h * 3600 + m * 60 + s
            if all(abs(sec - x) > 12 for x in hits):   # 너무 붙은 구간은 하나만
                hits.append(sec)
    try:
        os.remove(path)
    except OSError:
        pass
    return hits[:max_n]


def grab_frames(vid, seconds, name, keep=6, height=1080, fan=(0, 2, 4, 6)):
    """자막 시점마다 여러 후보 프레임을 뽑아 '깨끗한 것'만 골라 저장한다.

    말하는 순간(자막 시점)엔 화면에 자막이 떠 있고 진행자 얼굴일 확률이 높다.
    그래서 각 시점에서 +0/2/4/6초로 여러 장을 뽑아 두고, frame_quality 점수가
    좋은 상위 keep장만 남긴다(자막·로고·블러·얼굴 감점)."""
    from frame_quality import score_frame, crop_clean_square
    ff = _ffmpeg()
    made = []
    with tempfile.TemporaryDirectory() as td:
        vpath = os.path.join(td, "v.mp4")
        # 구간만 받으면 빠르고 403도 덜 난다
        secs = sorted(set(s for s in seconds))
        ranges = [f"*{max(0, s - 1)}-{s + max(fan) + 2}" for s in secs]
        cmd = ["yt-dlp", f"https://youtu.be/{vid}",
               "-f", f"bestvideo[height>={height}]/bestvideo/best",
               "--ffmpeg-location", ff, "-o", vpath, "--no-warnings", "--no-playlist"]
        for r_ in ranges:
            cmd += ["--download-sections", r_]
        r = _run(cmd, timeout=1200)
        if not os.path.exists(vpath):
            print("   영상 다운로드 실패:", (r.stderr or "")[-160:])
            return made

        # 구간만 받으면 타임라인이 재정렬되므로, 받은 영상 전체를 균등 샘플링한다
        dur = _probe_duration(vpath, ff)
        n_cand = max(len(secs) * len(fan), keep * 3)
        cands = []
        for i in range(n_cand):
            t = dur * (i + 0.5) / n_cand
            raw = os.path.join(td, f"c{i}.jpg")
            _run([ff, "-y", "-ss", f"{t:.2f}", "-i", vpath, "-frames:v", "1",
                  "-q:v", "2", raw], timeout=90)
            if os.path.exists(raw):
                sc = score_frame(raw)
                cands.append((sc["penalty"], raw, sc))

        cands.sort(key=lambda x: x[0])
        # 임계: 자막·UI·차없음 같은 '치명적' 항목은 개별 감점이 크므로(각 25~60)
        # 30 이하면 '차가 찍힌 깨끗한 프레임'으로 본다. 너무 낮게 잡으면 전량 탈락한다(실측).
        good = [c for c in cands if c[0] <= 30]
        if cands:
            top = cands[0][2]
            print(f"   최고점 프레임: penalty={cands[0][0]} "
                  f"(자막{top.get('sub')} UI{top.get('ui')} 차{top.get('car')} 선명{top.get('sharp')})")
        print(f"   후보 {len(cands)}장 채점 → 합격 {len(good)}장, 상위 {min(keep,len(good))}장 채택")
        for rank, (pen, raw, sc) in enumerate(good[:keep]):
            out = os.path.join(DIR, f"{name}_yt{rank}.jpg")
            if crop_clean_square(raw, out):
                made.append(out)
                print(f"     {os.path.basename(out)}  penalty={pen} "
                      f"(자막{sc['sub']} 로고{sc['corner']} 선명{sc['sharp']} 얼굴{sc['face']})")
    return made


def _probe_duration(path, ff):
    """ffmpeg 로 길이(초)를 얻는다(ffprobe 없이)."""
    r = _run([ff, "-i", path], timeout=60)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", (r.stderr or ""))
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mi * 60 + s
    return 60.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help='유튜브 검색어. 예: "제네시스 GV90 실물"')
    ap.add_argument("--name", required=True, help="저장할 버킷명(모델명)")
    ap.add_argument("--keywords", default=DEFAULT_KEYWORDS, help="자막에서 찾을 키워드(쉼표)")
    ap.add_argument("--max", type=int, default=6, help="뽑을 프레임 수")
    ap.add_argument("--video", help="영상 ID 직접 지정(검색 건너뜀)")
    args = ap.parse_args()

    os.makedirs(DIR, exist_ok=True)

    if args.video:
        cands = [{"id": args.video, "title": "(직접 지정)", "channel": "", "duration": 600}]
    else:
        cands = search_videos(args.query)
        if not cands:
            print("검색 결과 없음")
            return 1

    made, title, vid = [], "", ""
    for v in cands[:4]:            # 403·DRM으로 막히는 영상이 있어 순차 시도
        vid, title = v["id"], v["title"]
        print(f"\n영상 시도: [{v.get('channel','')}] {title} (id={vid})")
        ts = get_timestamps(vid, args.keywords.split(","), max_n=args.max)
        if ts:
            print("  자막 구간: " + ", ".join(f"{t//60}:{t%60:02d}" for t in ts))
        else:
            dur = v.get("duration") or 600
            ts = [int(dur * (i + 1) / (args.max + 1)) for i in range(args.max)]
            print("  자막 없음 → 균등 분할")
        made = grab_frames(vid, ts, args.name, keep=args.max)
        if made:
            break
        print("  → 실패, 다음 영상으로")

    if not made:
        print("프레임 추출 실패(후보 영상 모두 막힘)")
        return 1

    # crop_clean_square 가 이미 정사각 1400px 로 만들었으므로 재가공하지 않는다
    idx = {}
    if os.path.exists(INDEX):
        try:
            idx = json.load(open(INDEX, encoding="utf-8"))
        except ValueError:
            idx = {}
    for p in made:
        idx[os.path.basename(p)] = {
            "카테고리": args.name,
            "license": f"YouTube frame ({vid}) — 사용자 책임 검수",
            "credit": title,
            "attribution_required": False,
            "처리": "유튜브 프레임 · 정사각 1400px",
            "검색어": args.query,
            "검수": "미확인 — 자막·로고 박힌 컷 배제 필요",
        }
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX)

    print(f"\n{len(made)}장 저장 -> {DIR}/  (버킷: {args.name})")
    print("컨택트시트로 확인하고 자막·로고 박힌 컷은 지우세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
