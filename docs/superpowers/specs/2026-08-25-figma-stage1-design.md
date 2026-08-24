# Figma 경로 1단계 — 설계

작성일: 2026-08-25 · 승인: 팀장 (같은 날)

## 목적

Figma 디자인 파일에서 화면·요소·문구·흐름을 **결정적으로** 추출해 PDF 경로와 같은
계약(`SpecDocument`/`ScreenSpec`)으로 파이프라인에 넣고, SUT 관통(디자인↔구현
정합성 판정)까지 증명한다. 옛 `feature/figma-extractor`(이름 키워드 스크래핑)는
폐기가 확정됐고, 이 설계는 백지에서 시작한다.

## 결정 사항 (승인됨)

1. **입력 실물 = 픽스처 Figma 파일 직접 제작** — 로그인+회원가입 2화면,
   prototype 연결 포함. 그리는 것은 사용자 수작업(아래 §픽스처 명세).
2. **1단계는 규칙 없이** — Figma 가 실제로 담는 것(라벨·안내 문구·요소 유형·
   선택 항목·화면 흐름)만 부분 ScreenSpec 으로. `constraints`·
   `success_condition`·`sample_value` 는 비우고, 확인 못 한 것은 coverage 가
   리포트에 남긴다. 문서(기획서) 병합은 2단계.
3. **요소 인지 = 컴포넌트 기반** — INSTANCE 노드의 원본 컴포넌트 이름으로
   유형을 결정적으로 판정. 컴포넌트가 아닌 요소형 노드는 추출하지 않고 경고
   (억측 금지).
4. **증명 목표 = SUT 관통** — `url_path` 는 Figma 에 없으므로 억측하지 않고
   실행 시 사용자 입력(화면↔경로 매핑 인자)으로 받는다.

## 통합 형태

별도 프론트엔드 모듈 `src/prova/s1_figma/`. LLM 을 거치지 않는다 — Figma 응답은
이미 구조화된 트리라 "구조에 그대로 적힌 사실은 결정적으로" 원칙이 전면 적용된다.
S2 이후 파이프라인은 무변경.

기각한 대안: Figma → 중간 문서(md/PDF) → 기존 S1 재사용(구조 → 문서 → LLM →
구조의 왕복에서 검증 불가능한 손실이 낀다), extractor 내 분기(한 모듈이 두 입력을
알게 된다).

## 데이터 흐름

```
[수작업]   Figma 앱에서 2화면 제작 (§픽스처 명세)
[스크립트] scripts/fetch_figma.py — .env 의 FIGMA_TOKEN·FIGMA_FILE_KEY 로
           GET /v1/files/{key} 를 받아 필요 노드만 다듬어
           fixtures/figma/login_signup.json 저장
[테스트]   저장본만 읽는다 — 네트워크 없이 결정적.
           기대 산출물은 fixtures/figma/login_signup.golden.json
[실행]     prova run --figma-json fixtures/figma/login_signup.json \
                     --screen-url login=/login --screen-url signup=/signup
```

- 토큰·file_key 는 `.env` 전용(공개 저장소). 푸시 전 스캔 패턴에 Figma 토큰
  접두어 `figd_` 를 추가한다.
- 저장본을 "다듬는" 기준: document 트리에서 최상위 프레임 이하의
  `id·name·type·characters·children·componentId`, `components` 맵,
  prototype 연결(`transitionNodeId`)만 남긴다 — 65k 줄짜리 원본을 그대로 두면
  픽스처가 읽을 수 없는 덩어리가 된다. 다듬기도 스크립트가 한다(손 편집 금지 —
  손으로 만지면 실물 응답이라는 증거가 사라진다).

## 추출 규칙 (전부 결정적)

| Figma 구조 | ScreenSpec | 비고 |
|---|---|---|
| document 바로 아래 페이지의 최상위 FRAME | 화면 1개, 프레임 이름 → `screen_name`, 소문자 슬러그 → `screen_id` | 프레임 이름이 겹치면 경고 + 뒤 프레임 무시 |
| INSTANCE 의 원본 컴포넌트 이름 `Input`/`Button`/`Checkbox`/`Select`/`List` | `UIElement.type` (`input`/`button`/`checkbox`/`select`/`list`) | 이름 비교는 정확 일치(공백 정규화만). 모르는 컴포넌트 이름은 경고 |
| Input 인스턴스 안 레이어 이름 `label` 인 TEXT | `label` | 없으면 경고 + 그 요소 제외 (라벨 없는 요소는 S3 가 찾을 수 없다) |
| Input 인스턴스 안 레이어 이름 `placeholder` 인 TEXT | `placeholder` | 없으면 None (안내 문구 없는 입력은 정상) |
| Button/Checkbox 인스턴스 안 첫 TEXT | `label` | |
| Select 인스턴스 안 레이어 이름 `option` 인 TEXT 들 | `options` (순서대로) | |
| 컴포넌트 아님 + 이름/모양이 요소 같아 보여도 | 추출하지 않는다 + **경고** ("컴포넌트가 아니라 유형을 알 수 없음") | 옛 브랜치의 키워드 스크래핑 실패를 반복하지 않는다 |
| prototype 연결 (노드 클릭 → 다른 최상위 프레임) | `SpecDocument.flows` 추출만 | 흐름 **케이스 생성은 2단계** — 성공 판정 근거(도착 문구·경로)가 Figma 에 없다 |
| `element_id` | 라벨의 영문 슬러그가 아니라 **Figma 노드 id** (`"12:34"` 형태를 `n12_34` 로) | 사람이 지은 id 가 없으므로 노드 정체성을 그대로 쓴다 — 억측한 영문명을 만들지 않는다 |

`constraints`·`success_condition`·`failure_conditions`·`required_message`·
`sample_value`·`seed_rows`·`date_filter`·`precondition` 은 전부 비운다 —
Figma 가 말하지 않는 것을 채우는 척하지 않는다.

## 1단계가 검증하는 것 (그리고 하지 않는 것)

부분 ScreenSpec 에서 기존 생성기가 자연히 만드는 것은 정적 대조 케이스다:

- `labels_findable` — 디자인의 요소가 구현 화면에 있다
- `placeholders_match` — 안내 문구가 디자인과 같다
- `options_present` — 셀렉트 항목이 디자인과 같다

이게 실무의 "디자인↔구현 정합성 QA" 다. valid·규칙 위반·흐름 케이스는 근거가
없어 만들지 않는다. **coverage 가 "검증 규칙·성공 조건은 이 입력(Figma)에 없어
확인하지 못했다" 를 리포트에 남긴다** — 초록불이 전부 확인됐다는 착각을 막는
기존 원칙 그대로.

주의: 기존 coverage 는 문구 기반이라 "규칙이 아예 없는 스펙" 에서 무엇을 보고할지
확인이 필요하다 — 구현 계획에서 리포트에 입력 출처("이 명세는 Figma 디자인에서
왔고 검증 규칙을 담지 않는다") 한 줄을 어디에 실을지 정한다.

e2e 증명: SUT `good` 은 만들어진 케이스 전부 PASS, `bad` 는 심은 문구·요소
결함(placeholder 불일치 등 기존 것)이 잡힌다. LLM 무관이므로 mock/실모델 구분이
없다.

## CLI / 웹 UI

- `--figma-json <path>` : 저장된 응답으로 실행 (PDF 인자와 상호 배타)
- `--screen-url <screen_id>=<path>` (반복 가능) : 화면↔경로 매핑. 매핑이 없는
  화면은 실행하지 않고 그 사실을 리포트에 남긴다 (해석 실패는 더 많이 알리는
  쪽으로).
- 웹 UI 는 1단계에서 건드리지 않는다 — CLI 로 증명 먼저.

## 픽스처 명세 (사용자 수작업 — Figma 앱에서)

파일 하나, 페이지 하나에 최상위 프레임 2개. **컴포넌트를 먼저 만들고 인스턴스로
배치한다** (컴포넌트 이름·내부 레이어 이름이 계약이다):

컴포넌트 4종:
- `Input` — 내부 레이어: `label`(TEXT), `placeholder`(TEXT), 배경 사각형
- `Button` — 내부 레이어: TEXT 하나
- `Checkbox` — 내부 레이어: TEXT 하나(라벨), 체크 박스 모양
- `Select` — 내부 레이어: `label`(TEXT), `option`(TEXT, 항목 수만큼 복제)

프레임 `로그인`:
- Input 인스턴스 2 — 라벨 `이메일`(placeholder `이메일을 입력하세요`),
  `비밀번호`(placeholder `비밀번호를 입력하세요`)
- Button 인스턴스 1 — `로그인`
- (의도적 함정 1개) 컴포넌트가 아닌 맨 프레임+텍스트로 그린 가짜 입력란 1개 —
  경고 경로("컴포넌트가 아니라 유형을 알 수 없음")를 골든으로 검증하기 위한 것

프레임 `회원가입`:
- Input 인스턴스 4 — `이메일`·`비밀번호`·`비밀번호 확인`·`닉네임`
  (placeholder 는 SUT signup 화면의 실제 안내 문구와 같게)
- Select 인스턴스 1 — 라벨 `가입 경로`, 항목은 SUT 와 동일하게
- Checkbox 인스턴스 1 — `약관에 동의합니다`
- Button 인스턴스 1 — `가입하기`
- prototype 연결: `가입하기` 버튼 → `로그인` 프레임 (흐름 추출 검증용)

문구는 SUT good 과 일치시킨다(그래야 good 전부 PASS 가 성립). bad 가 잡히는
것은 SUT 에 이미 심어 둔 문구·요소 결함으로 충분한지 계획 단계에서 대조하고,
부족하면 이 명세를 고치지 말고 검증 항목에서 뺀다 — 픽스처를 결함에 맞춰
구부리지 않는다.

## 검증 계획

TDD 순서: 응답 파서(저장 JSON → 노드 트리, 합성 최소 JSON 으로 단위 테스트) →
컴포넌트 인지·경고 → 부분 ScreenSpec 조립(실물 저장본 → 골든 대조) → 흐름 추출 →
CLI 인자 → SUT 관통 e2e. 합성 JSON 의 모양은 Figma REST 문서 기준으로 만들되,
실물 저장본이 도착하면 골든 대조가 진실이 된다 — 합성과 실물이 어긋나면 실물이
이긴다.

## 하지 않는 것 (2단계 이후)

- 검증 규칙 병합(문서+Figma 두 입력) · 흐름 케이스 생성 · 웹 UI 통합
- 좌표(absoluteBoundingBox) → S3 VLM IoU 시험지 연결 — 흥미롭지만 별개 일감
- 실물 디자인 파일(디자인 시스템이 다른) 대응 — 컴포넌트 이름 매핑표의 확장은
  실물을 본 뒤 결정한다(표 헤더 후보 넓히기와 같은 원칙)
