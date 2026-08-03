# 시스템 인수인계 메모 (새 대화에서 이 파일부터 읽으세요)

최종 업데이트: 2026-08-02

## 한 줄 요약
네이버 홈판 자동차 블로그(브랜드: **카카이슬**) 자동 생성 시스템.
economy-blog(경제비버) 엔진을 100% 재사용해 자동차 주제로 복제한 버전.
매일 새벽 클라우드 루틴이 기사→본문+이미지를 만들어 output/ 에 커밋 →
사용자가 GitHub Desktop으로 받아 네이버에 복붙 발행. (자동 발행은 네이버 정책상 불가)

## 지금 상태: GitHub 발행 완료(js940315/car-blog), 앱권한·루틴·발행테스트 대기
- 2026-08-03 초기 커밋 push 완료(293파일, 사진228). 원격 main 동기화됨.
- 엔진 코드/PROMPT/카테고리/종목로고/브랜드명 전부 자동차용으로 교체 완료.
- 자산 소싱·육안검수 1차 완료 (아래 자산 현황).
- **아직 안 된 것(사용자 작업):**
  1. GitHub Desktop으로 이 폴더를 새 repo로 **Publish** + 그 repo에 **Claude GitHub App 접근 권한** 부여
     (앱은 이미 설치돼 있으면 "Repository access"에 새 repo만 추가. 안 하면 클라우드 루틴 push가 403)
  2. **assets/photos 는 .gitignore 대상** — 검수 끝난 사진은 `git add -f assets/photos/<파일명>` 으로 개별 커밋해야 repo에 올라감 (tickers 로고는 자동 커밋됨)
  3. 제네시스 로고 **수동 추가** (아래)
- 자동 발행 루틴은 아직 **연결/활성화 안 함**.

## 자산 현황 (2026-08-02 소싱·육안검수 완료)
- 로고: assets/tickers/ — **21종 정상**(현대차·기아·테슬라·BYD·타이어3사·부품주 등).
  ※ **제네시스만 수동 추가 필요** — Commons에 자유이용 로고 없음(상표). 공식 프레스킷 로고를
     assets/tickers/genesis_0.png 로 저장 후 index.json 후보에 등록.
- 사진: assets/photos/ — **417장 / 58버킷** = 테마8 + 모델(국산·수입 30+) + 실내6 + 인물4 + 상황4.
  ※ **썸네일은 제목의 주인공과 반드시 일치**(모델·인물·소재). 어긋나면 낚시로 읽혀 이탈 → ROUTINE_AUTO 최상단 규칙 참조.
  ※ 인물 사진은 `python _engine/build_people_library.py --add "Elon Musk" --name 머스크` 로 추가(Commons PD/CC만).
  · 테마: 신차출시·전기차친환경·산업수출·리콜안전정책·모터스포츠·중고차시장·브랜드기업·셀럽차
  · 모델: 팰리세이드·싼타페·쏘렌토·스포티지·셀토스·카니발·그랜저·코나·아이오닉5·6·EV6·EV9·GV80·G80·테슬라Y·3·벤츠E·BMW5
  · 실내(6버킷 47장): 실내고급(제네시스)·실내운전석(현대기아EV)·실내벤츠·실내BMW·실내테슬라·실내수입(페라리·람보 등 프리미엄)
  ※ 이미지 = **6장 세트(썸네일1+사진5, 실내 최소1)**. 데이터카드는 원칙적으로 안 씀(자동차는 사진이 생명).
  ※ 속보용 수동 프레스 사진 투입: **_engine/MANUAL_PHOTOS.md** (방법A=`--register`로 풀 추가, 방법B=`photo`필드 핀).
  ※ 교훈: '브랜드+모델' 쿼리가 적중률 최고. '모터쇼/exhibition/car interior(일반)'는 부스모델·문서·올드카를 물어옴.
  ※ 한계: 현대적 실내는 무료 라이선스가 희소(제조사 저작권) → 제네시스·현대·기아 급만 확보. 실내는 브랜드 맞춰 사용.
  ※ **소싱 품질 3대 장치**(2026-08-03 도입):
     1) **버킷별 소스 라우팅**(SOURCE_ROUTING) — 스톡은 'interior' 같은 한정어를 무시하고 일반 고급차
        외관을 주므로 **실내 버킷은 wiki/openverse만** 쓴다(실측: 실내 6장 중 3장이 외관이었음).
        국산·중국 모델도 스톡에 실차가 없어 wiki 우선.
     2) **중복 자동 차단** — 소싱 시 해시 비교로 이미 있는 사진은 저장하지 않는다.
        (스톡 사진 1장이 그랜저·본사사옥·브랜드기업·스타리아·아반떼 5개 버킷에 퍼져 있었음)
     3) **감사/정리 명령** — `--audit`(중복·빈약버킷·미소싱 리포트), `--dedup`(중복 자동 정리,
        구체적 버킷 우선 유지). 무인 루틴엔 사람 눈이 없으므로 주기적으로 돌린다.
  ※ **소싱은 멀티소스**: `build_photo_library.py --sources wiki,openverse,stock`.
     - wiki=Commons, openverse=Flickr CC 등 집계, stock=Pexels/Unsplash/Pixabay(재게시 허용 라이선스).
     - stock은 환경변수 PEXELS_API_KEY/UNSPLASH_ACCESS_KEY/PIXABAY_API_KEY 필요(현재 3개 다 설정됨).
     - 소스를 늘리면 버킷당 사진이 크게 늘어 **반복(유사이미지) 위험이 근본 해소**됨(예: 셀럽차 1→16장).
     - 반복 방지 3중장치는 그대로: pick_photo 순환 + 최근3장 회피 + variation_seed 크롭·톤 변주.
  ※ **소싱 병목 제거**: build_photo_library가 (카테고리×검색어×소스)를 ThreadPoolExecutor로 병렬 처리
     (`--workers` 기본 8). 전 28버킷 재소싱이 **약 3분**(예전 순차·프로세스재시작 방식은 20~30분).
     한 번의 실행으로 전체 소싱: `python _engine/build_photo_library.py --per 2` (기본 소스 wiki,openverse,stock).

## economy-blog 대비 바뀐 것 (복제 시 딱 이 4가지 + 문서)
1. 브랜드명: `_engine/build_posts.py` `brand` 기본값 → "카카이슬", tagline "KAKAISLE AUTO",
   EDITOR_HEADING "📝 한눈에 보는 자동차 노트"
2. 사진 검색어: `_engine/build_photo_library.py` CATEGORIES → 자동차 8종
   (신차출시/전기차친환경/산업수출/리콜안전정책/모터스포츠/중고차시장/브랜드기업/셀럽차)
3. 종목 로고: `_engine/build_ticker_library.py` TICKERS → 자동차주
   (국내완성차/국내부품타이어/해외완성차, 22종)
4. 주제 규칙: `_engine/PROMPT_AUTO_V1.md` — 자동차 8개 카테고리(셀럽·연예인차 신설),
   4챕터 구조, 제목/가독성 규칙. **economy용 PROMPT_V1.md는 복제하지 않음.**

## 자동차 RSS 소스 (루틴 프롬프트에 넣을 것 — 유효성 실측 확인 2026-08-02)
- 모터그래프  https://www.motorgraph.com/rss/allArticle.xml
- 오토헤럴드  https://www.autoherald.co.kr/rss/allArticle.xml
- 오토데일리  https://www.autodaily.co.kr/rss/allArticle.xml
- 지피코리아  https://www.gpkorea.com/rss/allArticle.xml   (전기차·미래차 강세)
- (탑라이더 allArticle.xml 은 1건만 반환되어 제외)

## 빌드/실행 (반드시 저장소 루트에서)
```
python _engine/build_posts.py _engine/articles.json 0802
```
→ output/0802/{순번}/ 에 0번 본문.txt + N번 사진.jpg 생성. build_report.json에 검증 결과.

## 자산 재생성 (Publish 전/후 아무 때나, 네트워크 필요)
```
python _engine/build_ticker_library.py          # 자동차 로고 → assets/tickers/
python _engine/build_photo_library.py           # 카테고리 사진 → assets/photos/
```
받은 뒤 **반드시 Read 도구로 눈 확인**(상표·엉뚱한 사진 제거) 후 --prune.
※ 셀럽·연예인차: 연예인 사진·초상은 수집 금지(초상권). 차종 일반사진/로고로 대체.

## 확정된 규칙 (economy에서 계승 — 함부로 바꾸지 말 것)
- 문장 중간 줄바꿈 금지. 문단 사이 빈 줄 = 점자빈칸(⠀⠀⠀). 4줄 넘는 벽돌문단 금지.
- 소제목 📌 **볼드**, 밑에 구분선 ━×19. 이미지 1번은 반드시 썸네일(thumbnail/stock_thumbnail).
- 이미지 = 1080px JPG q92. 종목 썸네일은 한국식 색(상승 빨강/하락 파랑).
- 제목 태도 단정형, 질문형 금지. '댓글' 단어 금지. 여운형 질문은 글 맨끝.

## 다음 할 일 (우선순위)
1. [사용자] GitHub Desktop → 이 폴더 Publish(새 repo) → 해당 repo에 Claude GitHub App 설치
2. [사용자/AI] 자산 재생성(로고/사진) + 육안 검수
3. [AI] 샘플 기사 3~5건 build 검수 → 네이버 실제 1회 발행 테스트
4. 검증되면 자동화 루틴(RSS 4개) 연결 → 매일 06:00 KST 스케줄 (발행은 계속 수동 복붙)
   → 루틴 절차·articles.json 조립규칙은 **_engine/ROUTINE_AUTO.md** 에 문서화됨 (준비 완료, 미연결)
