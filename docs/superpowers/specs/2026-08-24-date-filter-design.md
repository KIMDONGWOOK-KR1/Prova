# 날짜 필터·기간 조회 — 설계

작성일: 2026-08-24 · 승인: 팀장 (같은 날)

## 목적

주문 조회 화면에 날짜 필터(시작일·종료일 입력 → 조회 버튼 → 재조회)를 추가하고,
파이프라인이 **입력↔재조회 상호작용** 뒤의 화면을 검증하게 한다. 지금까지의 컬렉션
검증(정렬·합계·건수)은 전부 "진입 직후 화면"에 대한 것이었다 — 이 작업으로 "조작한
뒤의 화면"이 처음 검증 대상이 된다.

## 결정 사항 (승인됨)

1. **기대값 근거는 병행** — 시드 표 기반(S2가 기획서 §5 시드 표에서 특정 기간의
   기대 건수·포함/제외 주문번호를 결정적으로 계산)과 자기일관성(필터 후에도 기존
   정렬·합계 판정이 그대로 성립)을 함께 쓴다. 근거가 다른 두 층이 서로를 보강한다.
2. **bad 에 심는 결함은 두 개** — O3 경계일 제외(시작일 exclusive 비교),
   O4 필터 후 합계 미재계산.
3. **기획서 표현은 절 + 스키마 확장** — 기획서에 "날짜 필터" 절을 표로 명시하고
   `ScreenSpec.date_filter` 를 신설, LLM 스키마에 넣고 `declared_date_filter()`
   결정적 교정을 붙인다. `seed_rows`·`declared_*` 와 같은 패턴.

## 1. 기획서 확장 (`fixtures/specs/orders_spec.md`)

§2 요소 표에 세 줄 추가 — 검증 규칙 없음(빈 값 허용):

| 요소 ID | 유형 | 라벨 |
|---|---|---|
| start_date | 날짜 | 시작일 |
| end_date | 날짜 | 종료일 |
| filter_btn | 버튼 | 조회 |

**유형은 '입력'이 아니라 '날짜'다** (구현 중 보정, 2026-08-24): 유형 '입력' 으로
적으면 `_fillable_inputs` 가 정상 케이스에서 이 필드들을 자동으로 채우는데,
규칙 없는 입력의 견본값은 자유 문자열이라 `input[type=date]` fill 이 깨진다.
`ElementType` 에 `"date"` 를 신설하고 `ELEMENT_TYPE_WORDS` 에 `"날짜"` 를
매핑하며, 자동 채움(`input`/`select`/`checkbox`)에서 제외한다. 부수 효과:
orders 화면에 버튼이 처음 생기므로 정상 케이스가 navigate+click(조회)이 된다 —
빈 값 조회 = 전체 표시이므로 성공 조건 그대로 통과한다.

새 절 **"6. 날짜 필터"**:

| 항목 | 값 |
|---|---|
| 시작일 요소 | 시작일 |
| 종료일 요소 | 종료일 |
| 조회 버튼 | 조회 |
| 대상 목록 | 주문 목록 |
| 날짜 컬럼 | 주문일 |
| 빈 결과 문구 | 기간 내 주문이 없습니다. |

절 본문 산문으로 의미론을 명시한다: **경계일 포함**(시작일·종료일 당일 주문 포함),
**빈 값 = 전체 기간**, **필터 후에도 §5 의 정렬·합계 규칙이 그대로 유지**된다.

PDF 재생성(`scripts/make_spec_pdf.py`), `orders_spec.golden.json` 갱신 →
실모델 S1 골든 대조에 자동 편입.

## 2. 스펙 모델 + S1

- `models.py`: `DateFilter(start_label, end_label, submit_label, target_label,
  date_column, empty_message)`, `ScreenSpec.date_filter: Optional[DateFilter]`.
- S1 LLM json_schema 에 필드 추가(프롬프트 설명 한 줄).
- `pdf_parser.declared_date_filter()` 가 "날짜 필터" 절의 표를 결정적으로 읽고,
  extractor `_apply_declared_date_filter` 교정이 LLM 추출을 덮는다.

## 3. S2 — filter 케이스 생성

`date_filter` 가 있고 `seed_rows` 의 날짜 컬럼이 ISO 로 파싱되면 생성한다.
파싱 실패·고유 날짜 3개 미만이면 **경고 + 미생성** — 기존 sorted/sum 경고와 같은
모양. 조용히 넘어가지 않는다.

기간 산정은 결정적: 고유 날짜 오름차순 정렬 후 `start = dates[1]`,
`end = dates[-2]`. 양끝에 최소 1건씩 제외 행이 생기고, 경계가 실제 주문일이라
경계 포함 여부가 검증된다.

케이스 8개, 전부 kind `filter`(`orders-filter-001` …), 케이스당 기대 1개.
스텝은 공통으로 `fill(시작일) → fill(종료일) → click(조회)` (6·7은 빈 기간 값,
8은 fill 없이 click 만):

| # | 스텝 | 기대 | 근거 층 | 잡는 결함 |
|---|---|---|---|---|
| 1 | 기간 입력→조회 | `result_count` = 기간 내 시드 행 수 | 시드 | O3 |
| 2 | 〃 | `text_visible` 시작 경계일 주문번호 | 시드 | O3 |
| 3 | 〃 | `text_absent` 기간 밖 최신 주문번호 | 시드 | (필터 미적용류) |
| 4 | 〃 | `sum_matches` | 자기일관성 | O4 |
| 5 | 〃 | `sorted_desc` 유지 | 자기일관성 | O1 (필터 후에도) |
| 6 | 빈 기간(max+1d~max+2d) | `result_count` 0 | 시드 | |
| 7 | 〃 | `text_visible` 빈 결과 문구 | 기획서 | |
| 8 | 빈 값으로 조회 | `result_count` = 전체 시드 행 수 | 시드+기획서 | |

selector: `_GROUP_KINDS` += `"filter"`,
`_KIND_WORDS["filter"] = ("필터", "기간", "날짜")`.

## 4. SUT — 결함 O3·O4

`sut/templates/orders.html` 에 GET 폼(`input type=date`, aria-label
시작일/종료일, 조회 버튼). 폼은 목록 마크업 밖이라 list/table 쌍둥이가 공유한다.

- **good**: 경계 포함(`start <= d <= end`), 합계는 표시 행 재계산, 0건이면 빈 문구.
- **bad**: **O3** `start < d` (경계일 제외), **O4** 합계는 필터 전 값 유지.
  기존 O1(정렬)·O2(합계, 무필터 화면)는 그대로. 빈 값 전체·빈 문구는 bad 도
  올바르게 구현 — 결함 하나당 그 규칙의 케이스가 잡는다(결함 분리).
- **table/badtable**: 같은 템플릿 재사용으로 자동 동반. 쌍 판정 동일성 단언 유지.
- `sut/app.py` 헤더의 심은 결함 표에 O3·O4 추가.

## 5. S4/S5 — 신규 기계 없음

fill+click 후 컬렉션 판정은 기존 경로 그대로 (새 ActionType/ExpectedType 없음).
두 가정을 TDD 로 먼저 고정한다: (a) 컬렉션 판정이 스텝 실행 **후** 상태를 읽는다,
(b) `input[type=date]` 에 ISO 문자열 fill 이 동작한다.

## 6. 검증·문서

- TDD 순서: pdf_parser → extractor 교정 → S2 생성(기간 산정 포함) → selector →
  SUT 단위(필터 동작·쌍둥이) → e2e(good 8/8 PASS, bad 는 O1·O3·O4 의 케이스만
  FAIL, table 쌍 동일) → 실모델 골든.
- 풀스위트 858+신규, skip 0. 푸시 전 비밀 스캔
  (`168\.131|ssh -p [0-9]|jovyan@|kdw51@|PRIVATE KEY`).
- 문서는 구현 완료 후: teaching 노트 신규, README 결과 표·남은 것, overview 재생성.
- **홀드아웃 주의**: orders 화면의 케이스 집합이 커지므로
  `probe_request_selection.py` 의 "화면 전 케이스" 류 기대 목록에 filter 케이스가
  기계적으로 추가된다. 판정 기준 변경이 아니라 집합 정의의 갱신이지만, 갱신 후
  수치는 기존 B 9/10 과 1:1 비교할 수 없다 — 측정 기록에 그 사실을 남긴다.

## 범위에서 뺀 것

- **기간 역전(시작일>종료일) 검증** — 요소 간(cross-field) 규칙 기계가 없다.
  기획서에도 그 규칙을 적지 않는다(적고 검증 안 하면 그게 구멍이다).
- **날짜 형식 검증 규칙** — `type=date` 입력은 자유 텍스트가 불가능해 규칙이
  성립하지 않는다.
- 다른 화면으로의 필터 일반화, 상태(배송중 등) 필터 — 다음 일감.
