# Prova

**설계 문서를 읽어 테스트를 스스로 만들고, 실제 브라우저로 실행해 기획과 구현의 불일치를 찾아내는 웹 GUI QA 에이전트.**

팀 소인배 · 2026 하반기 WE-Meet · 의뢰: ㈜WITCHES

---

## 왜 만드는가

개발 현장에서 기획서와 실제 구현이 어긋나는 일이 잦고, 그걸 찾아 고치는 데 시간이 든다.
지금 그 확인은 QA 담당자가 화면기획서를 읽고 손으로 테스트 케이스를 만들어 하나씩 눌러보는 수작업이다.

Prova는 이 작업을 자동화한다. 증명하려는 명제는 하나다 —
**"기획서에 적힌 검증 규칙이 구현에 빠져 있으면 Prova가 그것을 짚어낸다."**

### 지금 동작하는 것

```
<화면>_spec.pdf ──S1──> SpecDocument ──S2──> TestCase[] ──S3+S4──> 브라우저 실행
                        (ScreenSpec[] + Flow[])                        │
                          report.html <──S6── Verdict[] <──S5─────────┘
```

로그인·회원가입·검색·비밀번호 찾기 네 화면을 각각 두 구현에 대해 검증한 결과, 그리고 세 화면을
한 문서에 담고 **화면 사이의 흐름**까지 검증한 결과
(CHEETAH의 로컬 Qwen2.5-7B-AWQ 사용, 2026-08-17 실측):

| 화면 | 대상 | 결과 |
|---|---|---|
| 로그인 | `good` — 기획서를 지킨 구현 | **10/10 PASS** (통과율 100%) |
| 로그인 | `bad` — 검증을 빠뜨린 구현 | **4 PASS / 6 FAIL** — 심은 결함 4종을 모두 지목, 오탐 0건 |
| 회원가입 | `good` | **17/17 PASS** |
| 회원가입 | `bad` | **13 PASS / 4 FAIL** — 심은 결함 4개를 정확히 지목, 오탐 0건 |
| 검색 | `good` | **10/10 PASS** |
| 검색 | `bad` | **6 PASS / 4 FAIL** — 심은 결함 3개를 지목(하나는 두 경로에서), 오탐 0건 |
| 비밀번호 찾기 | `good` | **9/9 PASS** |
| 비밀번호 찾기 | `bad` | **7 PASS / 2 FAIL** — 계정 존재 여부 노출(실제 취약점)을 두 관점에서 지목, 오탐 0건 |
| 통합 문서 (3화면+흐름 2) | `good` | **39/39 PASS** |
| 통합 문서 (3화면+흐름 2) | `bad` | **23 PASS / 16 FAIL** — 화면별 결과가 단일 문서와 동일, 오탐 0건 |
| 가입→로그인→상품등록 (3화면 흐름) | `good` | **39/39 PASS** — 세 화면을 이어 밟아 로그인 가드로 막힌 화면까지 닿는다 |
| 가입→로그인→상품등록 (3화면 흐름) | `bad` | **25 PASS / 14 FAIL** — 두 흐름이 각각 `login 도착`·`login 성공` 에서 끊긴다. 마지막 화면을 지목하지 않는다 |
| 검색 (`nolabel` — 아이콘 버튼) | 2차 경로 **끔** | **1 PASS / 9 FAIL** — 라벨이 없어 요소를 찾지 못한다 |
| 검색 (`nolabel` — 아이콘 버튼) | 2차 경로 **켬** (실물 Qwen2.5-VL-3B-AWQ) | **9 PASS / 1 FAIL** — 이미지로 찾아 진행하고, 라벨 결함 1건은 남는다 |
| 로그인 (`slow` — 결과가 400ms 뒤에 렌더) | 대기 **끔** | **3 PASS / 7 FAIL** — 못 기다린 것을 구현 결함으로 단정한다(오탐) |
| 로그인 (`slow` — 결과가 400ms 뒤에 렌더) | 대기 **켬** | **10 PASS / 0 FAIL** — `good` 과 같아진다. 기다린 케이스 7건을 리포트에 남긴다 |
| 로그인 (`spa` — URL 이 안 바뀜) | — | **9 PASS / 1 FAIL** — FAIL 이 맞다. 사유가 '경로 미이동 + 문구 노출 확인' 이라 라우팅 문제임을 바로 안다 |
| 로그인 (`hashed` — id 가 해시) | — | **10 PASS / 0 FAIL** — 라벨 전략이 먼저 통해 영향이 없다 |
| 로그인 (`native` — 브라우저가 제출을 막음) | — | **8 PASS / 2 FAIL** — FAIL 이 맞다. 사유를 '강제하지 않는다' 에서 '다른 방법으로 강제한다' 로 고쳤다 |
| 상품등록 (2화면 문서: 로그인+상품등록) | `good` — 전제(로그인)를 지킨 구현 | **20/20 PASS** |
| 상품등록 (2화면 문서) | `bad` | **12 PASS / 8 FAIL** — 로그인 화면 결함 6 + 심은 결함 2종(가격 숫자 검사 누락 P1, 로그인 가드 누락 P2)을 모두 지목, 오탐 0건 |
| 주문조회 (2화면 문서: 로그인+주문조회) | `good` — 실물 7B (2026-08-20) | **15/15 PASS** |
| 주문조회 (2화면 문서) | `bad` — 실물 7B (2026-08-20) | **7 PASS / 8 FAIL** — 로그인 화면 결함 6 + 심은 결함 2종(오래된순 정렬 O1, 합계 마지막 행 누락 O2)을 모두 지목, 오탐 0건 |
| 주문조회 (2화면 문서) | mock (2026-08-26) | **25/25 PASS** · `bad` 12 PASS / 13 FAIL — 날짜 필터·기간 역전이 더해져 케이스가 늘었다(아래 두 행). 화면별로 로그인 6 + 주문조회 7 |
| 주문조회 (`table` / `badtable` — aria-label 이 하나도 없는 순수 `<table>`) | mock (2026-08-22) | `good`/`bad` 와 **같은 판정** — 5/5 PASS · O1·O2 만 FAIL. 사유에 "표 머리글 '주문일' 2열로 찾음 (aria-label 없음)" 이 남는다 |
| 주문조회 (날짜+상태 필터 — **입력↔재조회**, `--only orders`) | mock (2026-08-27) | `good` **22/22 PASS** · `bad` 는 O1(무필터·필터 후)·O2·O3(경계일 제외)·O4(필터 후 합계 미재계산)·O5(기간 역전을 알리지 않음)·O6(취소 주문이 어느 상태 조회에도 섞임)의 **9건만 FAIL** — 조작한 뒤의 화면에 처음 판정이 걸렸다(설계 판단 15). `table`/`badtable` 쌍둥이도 같은 판정 |
| 로그인+회원가입 (**Figma 디자인** 입력 — 실물 API 응답, 2026-08-25) | LLM **미사용** (결정적 추출) | `good` **5/5 PASS** · `bad` 는 정적 대조가 잡을 수 있는 **둘만 FAIL**(로그인 placeholder 불일치 · C4 선택 항목 누락) — 디자인↔구현 정합성 QA. 규칙 검증은 이 입력의 범위 밖이고 리포트가 그 사실을 상자로 말한다(설계 판단 16). 흐름(가입→로그인)은 via 라벨과 함께 추출만 |
| 통합 문서 + 실물 Figma (**병합 모드**, 2026-08-25) | mock + 결정적 병합 | `good` **전부 PASS** (규칙 케이스·PDF 흐름 포함, 오탐 0) · 발견 목록 정확히 둘 — 검색 화면이 디자인에 없음, **디자인의 가입하기→로그인 흐름이 기획서 성공 조건(/welcome)과 모순** — 구현 코드를 보기 전에 잡은 기획↔디자인 모순이다(설계 판단 17) |
| **우리가 안 만든 웹앱** — practicetestautomation 로그인 (실물 7B, 2026-09-23) | 공개 연습 사이트 | 2 PASS · 2 **확인 불가** — 페이지가 기대 문구를 화면에 늘 보여 줘 그 문구로는 결과를 확인할 수 없다. 고치기 전에는 그중 하나가 **빈 통과**였다 |
| **우리가 안 만든 웹앱** — the-internet 로그인 | 공개 연습 사이트 | **4/4 PASS** — 고치기 전 1P/3F(아이콘 글리프가 붙은 버튼을 '유형 불일치' 로 오판) |
| **우리가 안 만든 웹앱** — saucedemo 로그인 (React SPA, `<label>` 없음) | 공개 연습 사이트 | **7/7 PASS** — 고치기 전 2P/5F(같은 이름의 폼을 버튼 대신 클릭). 첫 실패는 세 사이트 모두 '기획서와 다름' 으로 떴고 전부 오탐이었다 — `docs/measurements/external-sites-2026-09-23.md` |

위 네 행은 **CHEETAH 실물 7B 관통 실측**(2026-08-20)이다. 2026-08-19 의 mock
백엔드 E2E(`tests/test_product_e2e.py`·`tests/test_orders_e2e.py`)로 배관과 판정
로직을 먼저 증명한 뒤 실모델로 다시 쟀다. 첫 실측에서 7B 가 주문조회의 표시 전용
요소 4개(목록·텍스트)를 두 번 다 0개 추출해 O1·O2 를 실행조차 못 했다 — 입력·버튼
요소는 옮기면서 표시 요소는 통째로 빠뜨리는 경향이다. 요소 표는 파서가 이미 읽고
있었으므로(누락 경고가 "표에는 4개" 라고 알았다) 대조를 백필로 올려 해결했다:
모델이 빠뜨린 요소를 표에서 직접 채우고, 채운 사실을 경고로 남긴다
(`_backfill_declared_elements`, `tests/test_element_backfill.py`). 자유 서술인
검증 규칙 셀은 옮기지 않는다 — 규칙이 적힌 요소를 백필하면 위반 케이스가
생성되지 않는다는 경고를 따로 낸다.

2차 경로는 **실물 시각 모델(Qwen2.5-VL-3B-AWQ)로 굳은 시험지를 채점했다**
(2026-08-31, 화면 18장 · 항목 77개 · 있음 63 · 없음 14, `fixtures/iou/`). 그 전까지의
초록불은 정답을 아는 mock 이 낸 것이어서 배관만 증명했고 정확도는 측정되지 않은
상태였다.

| 지표 | 값 | 뜻 |
|---|---|---|
| 탐지 성공률 (IoU≥0.5) | **36/63 = 57.1%** | 명세서 §9 기준 — **미달** |
| 적중률 (중심이 요소 안) | **57/63 = 90.5%** | 실제로 클릭이 되는 비율 |
| 오탐 (없는 것을 찾았다고) | **10/14 = 71.4%** | 전부 신뢰도 0.8 이상 — 신뢰도 관문이 못 거른다 |
| 호출 시간 | 평균 839ms · 최대 2.5s | |

이 시험지는 08-22 의 13화면 50항목을 **그대로 품고** 넓힌 것이라, 그 부분만 떼어
채점할 수 있다. 떼어 보면 `21/40 = 52.5%` · 적중 `36/40 = 90.0%` · 오탐 `7/10 = 70.0%`
로 **08-22 와 화면별 표까지 완전히 같다** — 세 번 측정해 세 번 같았다. 그래서 다른
숫자가 움직이면 원인을 다른 곳에서 찾을 수 있다.

실제로 그렇게 썼다. 08-28 채점에서 새 화면이 `7/20 = 35.0%` 로 낮게 나와 "새 화면이
어렵다" 고 적었는데, 원인은 **시험지의 스크린샷이 앱보다 낡은 것**이었다(상태 필터가
붙어 화면이 바뀐 뒤였다). 다시 굳혀 채점하니 `15/23 = 65.2%` 다. 시험지가 `sut_build`
로 앱 도장을 들고 다니는 것은 그래서다.

세 숫자를 한 값으로 합치지 않는다. 적중과 IoU 의 차이는 상자 **크기**다(입력란을 라벨까지,
버튼을 여백까지 잡는다) — 클릭에 필요한 것은 위치뿐이라 실행 성패는 적중률이 말하고,
§9 의 IoU 기준으로는 미달이다. 오탐 70% 는 2차 경로의 진짜 위험이다 — 요소가 정말 없는
화면에서 좌표를 내면 탐지 실패가 구현 결함으로 둔갑한다. 좌표 아래 조작 가능 요소를
확인하는 관문(`_require_actionable`)이 빈 공간은 막지만 **다른 입력란 위에 떨어진 오탐은
통과**한다. 전체 표는 `docs/measurements/vlm-iou-qwen-vl-2026-08-31.md`, 해석은 노트 13.

§9 는 두 경로의 **비교**도 요구한다. 같은 시험지 74항목을 1차 경로로 재서 나란히
놓았다 (`scripts/eval_selector_speed.py`). 두 점수의 `dataset_id` 가 다르면 채점
스크립트가 **비교표를 만들지 않는다** — 모집단이 다른 수치를 나란히 놓는 것은
비교가 아니라 착시이고, 그 어긋남은 표에서 보이지 않기 때문이다.

| 지표 | selector (1차) | VLM (2차) |
|---|---|---|
| 탐지 성공률 | **61/63 = 96.8%** | 57/63 = 90.5% |
| 오탐 (없는 것을 찾았다고) | **0/14 = 0.0%** | 10/14 = 71.4% |
| 호출 시간 (평균) | **6.8ms** | 839ms (**124배**) |

'찾았다' 는 두 경로가 함께 답할 수 있는 질문으로 맞췄다 — 적중 + 관문 통과. IoU 는
1차 경로에 없는 개념이라 비교표에 쓸 수 없다.

1차 경로가 놓친 2건은 둘 다 `nolabel` 의 아이콘 전용 '검색' 버튼이다 — 항목을 54%
넓히고 표·날짜·목록·선택이 새로 들어왔는데도 **1차의 실패는 2차 경로를 만든 바로 그
모양 하나에 그대로 몰려 있다.**

호출 시간은 **탐지만** 잰 값이다. 화면을 여는 시간과 로그인은 타이머 밖이다 —
비교 상대인 2차 경로는 저장된 그림을 채점하므로 페이지 로드가 아예 없고, 1차에만
로드를 얹으면 표가 1차에 불리하게 기운다(08-31 까지 그랬다).

selector-first 는 취향이 아니라 측정 결과다: 더 정확하고, 없는 것을 지어내지 않고,
124배 빠르다. 2차는 1차가 닿지 못하는 자리에서만 값을 한다. 전체 표는
`docs/measurements/grounding-selector-vs-vlm-2026-08-27.md`.


`bad`에서도 구현돼 있는 검증은 PASS로 나온다. 한 리포트 안에
"구현된 규칙은 PASS, 누락된 규칙은 FAIL"이 함께 나오는 것이 판정을 신뢰할 근거다.

회원가입 화면이 이 점을 더 강하게 보여준다. `required` 규칙을 가진 요소가 6개인데
검증이 빠진 것은 약관 동의 하나뿐이고, Prova는 **그 하나만** FAIL로 지목한다.
닉네임도 `min_length`는 PASS, `max_length`만 FAIL이다 — 한 요소의 규칙 중 일부만
구현된 경우를 규칙 단위로 분리해 짚어낸다.

검색 화면은 검증 축이 다르다. 로그인·회원가입은 "규칙을 어긴 값에 에러가 뜨는가"였는데
검색은 "정상 입력에 정해진 결과가 나오는가"다. `bad`에 심은 **대소문자 구분** 결함이
그 차이를 보여준다 — 값에 흠이 없고 구현도 검사를 하는데 **검사 방법이 기획서와 다르다.**
위반값을 만드는 방식으로는 도달할 경로가 없고, 기획서가 입력-결과 짝을 제시해야 잡힌다.

그리고 검색은 결과를 **두 경로로** 확인한다. 화면에 "검색 결과 3건" 문구가 떴는지
보는 경로와, 결과 목록의 항목을 DOM 에서 직접 세는 경로다. 문구 경로는 화면이 건수를
말해 줄 때만 성립하므로, 건수를 문구로 보여주지 않는 화면에서는 아무것도 확인하지 못한
채 초록불이 된다. `bad`의 FAIL 4건 중 2건이 같은 결함(대소문자 구분)을 서로 다른 경로로
잡은 것이다 — 중복이 아니라, 한쪽만으로는 놓칠 수 있는 결함이 있기 때문에 둘을 둔다.

S1 추출 정확도도 골든 데이터와 대조해 확인했다 — 세 화면 **54/54 통과**.
로컬 7B가 `constraints` 키 이름(`min_length`, `require_uppercase`, `same_as` 등)까지
정확히 뽑아내므로, 계획 단계에서 우려했던 "7B가 검증 규칙을 놓칠 위험"은 해소됐다.
Claude API가 필요하지 않다.

---

## 저장소에 있는 다른 도구

`scripts/legacy/extract_auth_search_json.py`는 이 파이프라인보다 먼저 만들어진 독립
추출 도구다. **HWPX 파싱과 OCR**을 지원하는데 이 파이프라인에는 없는 능력이라 그대로
둔다. 이 도구만 쓰는 의존성은 `scripts/legacy/requirements.txt` 에 따로 뒀다 — easyocr 가
torch 를 끌고 오는데, 아무도 설치하지 않는 것을 프로젝트 락 파일이 들고 다닐 이유가 없다.

`feature/figma-extractor` 브랜치에는 Figma 추출기가 있다.
자세한 내용은 [docs/reference/legacy-extractors.md](docs/reference/legacy-extractors.md).

측정 스크립트는 `scripts/` 에 있다. 도구를 재는 것과 도구 자체를 구분해 두려고
`prova` 패키지 안에 넣지 않았다.

| 스크립트 | 하는 일 | GPU |
|---|---|---|
| `probe_s1_robustness.py` | 기획서가 훼손됐을 때 추출이 어떻게 깨지는가 (6종) | 필요 |
| `probe_request_selection.py` | 자연어 요청 해석 재현율 — 튜닝 세트 / `heldout` | 필요 |
| `build_iou_dataset.py` | — 탐지 시험지를 굳힌다 (`fixtures/iou`) | 불필요 |
| `eval_vlm_iou.py` | 화면 이미지에서 요소를 찾는 정확도 (IoU·적중·오탐·속도) | 필요 |
| `eval_selector_speed.py` | 같은 시험지를 1차 경로로 — §9 의 selector vs VLM 비교 | 불필요 (SUT 만) |
| `make_spec_pdf.py` · `make_multi_spec.py` | 픽스처 기획서 md → PDF, 통합 문서 조립 | 불필요 |
| `make_comparison.py` · `make_demo_gif.py` · `embed_media.py` | 티칭 페이지 자료(비교 이미지·GIF) 생성과 인라인 — 결과물은 `docs/teaching/media/` 에 이미 있다 | 불필요 |

---

## 코드를 처음 보는 사람은

`docs/teaching/overview.html`을 브라우저로 열면 파이프라인 구조와 결과를 그림으로 볼 수 있다.
그다음 `docs/teaching/00-overview.md`부터 번호 순으로 읽으면 각 단계의 설계 판단을 알 수 있다.

---

## 빨리 돌려보기

```powershell
# 1. 의존성
uv sync --extra dev
uv run playwright install chromium

# 2. 기획서 PDF 생성 (md -> pdf)
uv run python scripts/make_spec_pdf.py

# 3. 테스트 대상 웹앱 띄우기 (별 터미널)
uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut

# 4. 검증 — GPU 가 없으면 --backend mock (픽스처 기획서 전용 연습 모드).
#    GPU 서버가 있으면 --backend 를 빼고, 먼저 `uv run prova check` 로 연결을 확인한다
uv run prova run --pdf fixtures/specs/login_spec.pdf  --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/login_spec.pdf  --url http://localhost:8100/bad  --backend mock
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/bad  --backend mock
uv run prova run --pdf fixtures/specs/search_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/search_spec.pdf --url http://localhost:8100/bad  --backend mock

# 5. 리포트 열기
start runs/<run-id>/report.html
```

SUT 는 `--reload` 로 띄운다. **`sut/` 를 고치고 재시작을 잊으면 옛 코드를 상대로
재게 되고, 그 결과가 도구의 오탐처럼 보인다** — 실제로 겪었다(2026-08-26, 기간 역전을
구현한 직후 `good` 에서 없는 FAIL 을 쫓았다). 감시 범위를 `sut` 으로 좁히는 이유는
저장소 전체를 폴링하지 않기 위해서다(`runs/`·`.venv` 가 크다). `watchfiles` 가 없으면
uvicorn 이 `StatReload` 로 떨어지므로 의존성은 늘지 않는다.

**`--reload` 만으로는 부족하다.** 그것은 프로세스를 둘로 만든다 — 부모(감시자)가
파일을 보고 자식(일꾼)이 응답하는데, 부모가 죽으면 자식은 소켓을 물고 남는다.
포트는 열려 있고 응답도 정상인데 아무도 파일을 보지 않는 상태다(2026-08-27 에
두 번 속았다). 그래서 SUT 가 `GET /__build__` 로 자기 소스보다 낡았는지 스스로
답하고, `prova run` 이 실행 전에 물어 어긋나면 **시작하지 않는다**. 결과는
리포트 머리말에 `대상 빌드 일치` 로 남는다. 도장이 없는 대상(=실물 웹앱)에는
아무 말도 하지 않고 그대로 진행한다 — 자세한 이유는 티칭 노트 20 참고.

한 가지 알아 둘 것: 가입한 계정(`REGISTERED`)은 **프로세스 상태**라 리로드되면
지워진다. 실행 도중 `sut/` 를 고치면 '가입한 계정으로 로그인' 을 밟는 흐름 케이스가
그 영향을 받을 수 있다. 판정을 재는 중이라면 고치지 말고, 고쳤으면 다시 돌린다.

자연어로 무엇을 볼지 좁힐 수 있다. 무엇을 뺐는지는 리포트에 남는다.

```powershell
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad                  --request "비밀번호 규칙이 제대로 걸리는지 확인해줘"
```

화면으로 쓰려면 웹 UI 를 연다. 요청을 쓰면 **실행 전에 무엇을 테스트할지 보여주고
승인을 받는다.**

```powershell
uv run prova serve      # http://127.0.0.1:7007
```

한 GPU 에서 추출 모델(7B)과 탐지 모델(VL)을 시간분할로 쓸 때는 실행을 둘로
자른다 — 계획을 저장하고, 서버를 교체한 뒤, LLM 없이 이어 돈다(설계 판단 18).

```powershell
uv run prova run --pdf 기획서.pdf --url http://... --run-id two-model --plan-only
# (tmux 에서 7B 를 내리고 VL 을 올린다)
uv run prova run --resume runs/two-model --vlm http://localhost:8001/v1 --vlm-model Qwen2.5-VL-3B-AWQ
```

2026-08-26 에 실물 7B(추출) → 실물 VL(탐지)로 관통시켰다. `nolabel` 에서 2차
경로 없이 재개하면 1 PASS / 9 FAIL, 실물 VL 로 재개하면 **9 PASS / 1 FAIL**
(이미지로 찾아 진행 8건)이고, 남은 FAIL 1건은 심어 둔 라벨 결함 그대로다.
리포트는 재개 실행에 LLM 이 없는데도 추출 백엔드를 7B 로 기록한다 (노트 23).

실제 로컬 LLM으로 돌리려면 [docs/cheetah-setup.md](docs/cheetah-setup.md)를 따라
CHEETAH에 vLLM을 올리고 `--backend` 없이 실행한다.

```powershell
uv run prova check     # vLLM 연결 + 정형 출력 동작 확인
uv run pytest          # 전체 스위트 (vLLM 없으면 실모델 측정은 자동 skip)
```

---

## 구조

```
src/prova/
├── models.py                 데이터 계약 (명세서 §3) — 파이프라인 전체의 타입
├── theme.py                  디자인 토큰 — 웹 UI 와 리포트가 공유하는 단일 출처
├── text_utils.py             PDF 문구 ↔ 화면 문구 비교 규칙
├── llm/                      백엔드 추상화 (base / mock / vllm)
├── s1_spec_extractor/        PDF -> ScreenSpec
│   ├── pdf_parser.py           결정적 추출 (pdfplumber, LLM 없음)
│   └── extractor.py            LLM 구조화 + 표에서 읽은 사실로 교정
├── s1_figma/                 Figma API 응답 -> ScreenSpec (전부 결정적, LLM 없음)
├── s1_merge.py               기획서+Figma 병합 — 어긋남은 판정 대신 발견으로
│   ├── figma_parser.py         컴포넌트 기반 요소 인지 + 저장용 다듬기
│   └── extractor.py            SpecDocument 조립 — 경로는 --screen-url 매핑
├── s2_case_generator/        ScreenSpec -> TestCase[]
│   ├── rule_expander.py        규칙 -> 위반값 + 요소 간 의존 해석 (순수 함수, LLM 없음)
│   ├── precondition.py         전제(로그인) 스텝 생성 (순수 함수, LLM 없음)
│   ├── generator.py            케이스 조립 + 기대 결정 + 요소 유형별 액션
│   ├── selector.py             자연어 요청 -> 실행할 케이스 고르기 (부분집합만)
│   └── coverage.py             기획서에 적혀 있는데 확인하지 않는 것을 찾는다
├── s3_grounder/dom_locator.py  라벨 -> 실제 요소 (selector-first) + 2차 경로 진입점 (heal_with_vlm)
├── vlm/                      2차 경로의 시각 모델 (base / mock_backend / qwen_vl / metrics)
├── s4_executor/                Playwright 실행 + 스텝별 증거 수집
├── s5_verifier/                PASS/FAIL 판정
├── s6_report/                  JSON + HTML 리포트
├── nodes.py                  (state) -> state 노드
├── pipeline.py               build_plan (브라우저 없이 S1~S2+선택) + run_pipeline
├── graph.py                  같은 노드를 LangGraph 로 배선
├── server/                   로컬 웹 UI — 계획 확인 -> 실행
│   ├── app.py                  /api/plan (브라우저 없음) · /api/run (승인 목록) · /api/runs
│   ├── runner.py               워커 스레드 하나, 동시 실행 하나
│   └── static/                 작업 콘솔 (index.html · app.css · app.js, CDN 없음)
└── cli.py                    prova run / prova serve / prova check

sut/                          테스트 대상 미니 웹앱 — 6화면(로그인·회원가입·검색·비밀번호 찾기·상품등록·주문조회) good / bad + 도구를 시험하는 변형 8종
fixtures/specs/               화면기획서 md / pdf / 정답(golden) — 화면마다 한 벌
├── multi_spec.md               통합 문서 — 화면별 md 에서 조립한다 (직접 고치지 않는다)
├── onboarding_spec.md          가입→로그인→상품등록 — 화면 셋을 지나는 흐름이 사는 문서 (조립)
└── _multi_*.md · _onboarding_*.md  조립용 조각 ('_' 로 시작하면 PDF 로 만들지 않는다)
fixtures/figma/               Figma API 응답 픽스처 (합성 + 실물, 다듬기는 fetch 스크립트가)
scripts/                      기획서 PDF 생성 · 통합 문서 조립 · Figma fetch · 데모 자료 생성
└── legacy/                   파이프라인 이전에 만든 독립 추출 도구 (HWPX·OCR)
docs/
├── specs/                    Prova_서비스명세서.md (개발 기준 문서)
├── reference/                계획서·주제개요서·멘토링보고서 · 옛 추출기 안내
├── teaching/                 티칭 노트 24개 + overview.html (그림 자료)
├── measurements/             실측 결과 — 보고에 쓰는 숫자의 출처
├── pr/                       PR 읽기 안내
├── superpowers/              지난 설계·구현 계획서 (도구가 남긴 것)
├── cheetah-setup.md          GPU 서버 vLLM 세팅 절차
├── design-decisions.md       명세서와 다르게 한 22군데
├── lessons.md                코드를 돌려서 알게 된 것들
├── roadmap.md                아직 안 한 것
└── README.md                 문서 안내
```

---

## 더 읽을 것

| 문서 | 무엇이 있나 |
|---|---|
| [docs/design-decisions.md](docs/design-decisions.md) | 명세서와 다르게 구현한 **22군데**와 각각의 이유. 코드를 보기 전에 읽으면 왜 그렇게 생겼는지 알 수 있다 |
| [docs/lessons.md](docs/lessons.md) | 문서로 예측하지 못했고 코드를 돌려서 알게 된 것들. 각각 대응이 코드에 남아 있다 |
| [docs/roadmap.md](docs/roadmap.md) | 아직 안 한 것과 실측으로 확정된 GPU 제약 |
| [docs/README.md](docs/README.md) | 명세서·티칭 노트·측정 결과·배경 문서 전체 안내 |
