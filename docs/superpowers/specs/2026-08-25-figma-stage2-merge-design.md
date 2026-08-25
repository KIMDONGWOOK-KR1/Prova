# Figma 2단계 — 병합과 불일치 발견 · 설계

작성일: 2026-08-25 · 승인: 팀장 (같은 날)

## 목적

기획서 PDF(규칙·성공 조건·계정·시드·경로)와 Figma 디자인(요소·문구·흐름)을
**한 실행에서** 합쳐 검증하되, 겹치는 정보가 어긋나면 판정을 만들지 않고
**기획↔디자인 불일치**로 리포트에 보고한다 — 구현을 검증하기 전에 입력끼리
모순이면 그 자체가 QA 발견이다.

## 결정 사항 (승인됨)

1. **어긋남 = 발견** — 어느 쪽도 진실로 삼지 않는다. 어긋난 항목은 검증에서
   빼고 불일치로 보고, 일치하는 항목만 병합 스펙으로 검증한다.
2. **이름 자동 매칭** — 화면은 `screen_name`(정규화 비교), 요소는 라벨 정확
   일치. 짝 없는 화면·요소는 있는 쪽 단독으로 검증하고 그 사실을 보고한다.
3. **흐름 케이스 포함** — 병합 화면은 기획서의 성공 조건·경로를 가지므로
   Figma 흐름(via 라벨 포함)이 기존 `generate_flow_cases` 로 실행된다.

## 진입점

`prova run --pdf X.pdf --figma-json Y.json [--screen-url ...]` — 1단계에서
금지했던 병용이 병합 모드다. LLM 은 PDF 추출에만(기존), Figma 추출은
결정적(기존). 매칭된 화면의 경로는 기획서 것을 쓰고, `--screen-url` 은
**Figma 단독 화면에만** 적용된다. `--request` 는 허용(LLM 이 있으므로).

## 병합 규칙 (`src/prova/s1_merge.py` 신설)

`merge_documents(pdf_doc, figma_doc) -> tuple[SpecDocument, list[str]]`
(두 번째가 불일치 발견 목록). 순수 함수, LLM 없음.

| 상황 | 처리 |
|---|---|
| 화면 이름 일치 | 병합 — 기반은 기획서 화면 전체(규칙·성공조건·계정·시드·date_filter·url_path·source_kind="document") |
| 요소 라벨 일치 | 짝지음. placeholder·options·type 대조 — 일치: 그 값으로 검증. **어긋남: 그 항목을 검증에서 빼고**(placeholder→None, options→기획서 것 유지하되 발견 기록, type 불일치→기획서 유형 유지+발견) 발견 기록 |
| Figma 에만 있는 요소 | 병합 화면에 추가(element_id 는 Figma 노드 슬러그) + 발견 |
| 기획서에만 있는 요소 | 유지 + 발견 |
| Figma 단독 화면 | figma 정적 모드 그대로(source_kind="figma", `--screen-url` 필요) + 발견 |
| 기획서 단독 화면 | 기존 그대로 + 발견 |
| 흐름 | 합집합. Figma 흐름의 screen_ids 를 매칭된 기획서 screen_id 로 재기입. 미매칭 화면이 낀 Figma 흐름은 버리고 발견 기록. flow_id 충돌 시 Figma 쪽에 `-figma` 접미(같은 흐름을 두 입력이 다 적은 경우 — 중복 실행보다 한쪽 유지가 맞는지는 구현 중 판단하되, **같은 screen_ids 순열이면 하나로 접고 via 는 있는 쪽을 쓴다**) |

placeholder 대조의 '어긋남' 은 정확 비교가 아니라 기존 문구 비교 규칙
(`text_utils.loosen` — 공백 무시)을 쓴다 — 공백 배치 차이를 불일치라고
보고하면 발견 목록이 소음이 된다.

## 불일치는 경고가 아니라 발견이다

`spec_warnings` 에 섞지 않는다(coverage_gaps 와 같은 원리 — 성격이 다른
사실을 한 목록에 섞으면 둘 다 묻힌다). 경로:
`merge_documents` 반환 → `AgentState.design_mismatches` →
`summary["design_mismatches"]` → 리포트 HTML "기획↔디자인 불일치 N건" 상자
(케이스가 전부 초록이어도 보인다). 발견 문장에는 화면·요소·양쪽 값을 다 적는다
— "로그인 화면 '이메일' 의 안내 문구가 다릅니다: 기획서 'A' / 디자인 'B'".

## 증명 (SUT)

- **일치 시나리오**: 실물 Figma 응답(`fixtures/figma/login_signup.json`) +
  login/signup 기획서 병합 → 불일치 0 (함정 요소는 1단계 경고 그대로),
  good 에서 규칙 케이스 포함 전부 PASS. **Figma 흐름 회원가입→로그인(via
  가입하기)이 흐름 케이스로 실행**되어 bad 의 E1(계정 미등록 — 두 화면
  사이의 결함)을 잡는지가 핵심 증명이다.
- **불일치 시나리오**: `fixtures/figma/synthetic_mismatch.json`(손제작 —
  placeholder 하나 다르게, 요소 하나 없게, 요소 하나 더 있게) → 발견 3건이
  리포트에 실리고, 어긋난 placeholder 는 placeholders_match 대조에서 빠진다.
  실물 픽스처·골든은 건드리지 않는다.

## 주의 (구현 중 확인)

- signup 기획서와 login 기획서는 별개 문서다 — 병합 e2e 의 PDF 입력은 두
  화면이 함께 든 문서가 필요하다. `multi_spec`(login+signup+search)을 쓰거나
  login+signup 조합 문서를 조립한다 — 기존 `_multi_*.md` 조각 재사용.
- Figma 화면 이름('로그인')과 기획서 screen_name('로그인') 정규화 일치 확인.
- flow 케이스 게이트(`all(source_kind=="document")`)는 병합 문서에서 Figma
  단독 화면(source_kind="figma")이 섞이면 흐름 전체가 죽는다 — 게이트를
  "흐름이 밟는 화면이 전부 document 인가" 로 좁혀야 한다.

## 범위에서 뺀 것

- 명시 매핑 override · 3화면 이상 흐름 · 규칙의 Figma 표기 · 웹 UI 병합 지원
