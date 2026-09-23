# 인수인계 현황 (STATUS)

> 2026-09-23 기준. 저장소를 처음 이어받는 사람이 **"지금 어디까지 왔고 무엇부터 손대면 되는가"** 를
> 30분 안에 파악하도록 쓴 문서다. 판단의 근거는 전부 다른 문서에 있고 여기서는 가리키기만 한다.
>
> 기준 커밋: `b5cc299` · 전체 테스트 **1117 passed / 105 skipped / 0 failed** (skip 은 GPU 없이
> 돌려서 실모델 측정이 자동으로 빠진 것). 실측 2026-09-23, 소요 20분 02초

---

## 1. S1~S6 — 어느 파일이 무엇을 하는가

파이프라인은 6단계이고, 각 단계가 앞 단계의 결과를 받아 다음으로 넘긴다.
**판정에 LLM 이 관여하는 곳은 한 군데도 없고, 사실을 읽는 데 LLM 을 쓰는 곳은 S1 뿐이다.**

```
기획서 PDF ──S1──> SpecDocument ──S2──> TestCase[] ──S3──> ElementLocation
                                                              │
   report.html <──S6── Verdict[] <──S5── StepResult[] <──S4───┘
```

| 단계 | 주 파일 | 하는 일 | LLM |
|---|---|---|---|
| **S1** | `src/prova/s1_spec_extractor/pdf_parser.py` (1173줄) | PDF 에서 텍스트와 표를 **결정적으로** 뽑는다. 표에 그대로 적힌 사실(요소 ID·유형·예시값·시나리오·문구·흐름 등 8종)은 여기서 읽어 LLM 에게 맡기지 않는다 | ✗ |
| | `src/prova/s1_spec_extractor/extractor.py` (1009줄) | 뽑은 텍스트를 `ScreenSpec` 으로 구조화하고, 위에서 읽은 사실로 LLM 출력을 교정·백필한다 | **○** |
| | `src/prova/s1_figma/figma_parser.py` · `extractor.py` | Figma API 응답 → `ScreenSpec`. 컴포넌트 이름으로만 읽고 **전부 결정적** | ✗ |
| | `src/prova/s1_merge.py` (182줄) | 기획서 + Figma 를 병합. 둘이 어긋나면 판정하지 않고 "발견" 으로 보고 (설계 판단 17) | ✗ |
| **S2** | `src/prova/s2_case_generator/rule_expander.py` (618줄) | 규칙(`min_length` 등) → **그 규칙 하나만 어기는 값**. 순수 함수. 이 프로젝트의 핵심 아이디어 | ✗ |
| | `src/prova/s2_case_generator/precondition.py` (123줄) | 전제(로그인 등) 스텝 생성. 순수 함수 | ✗ |
| | `src/prova/s2_case_generator/generator.py` (1122줄) | 위반값을 실행 가능한 `TestCase` 로 조립 + 기대값 결정 + 요소 유형별 액션 | 제목 다듬기만 |
| | `src/prova/s2_case_generator/selector.py` (612줄) | 자연어 요청 → 실행할 케이스 고르기. **부분집합만** 고를 수 있고 판정은 못 바꾼다 | **○** |
| | `src/prova/s2_case_generator/coverage.py` (125줄) | 기획서에 적혀 있는데 **아무 케이스도 확인하지 않는 것**을 찾아 리포트에 쓴다 | ✗ |
| **S3** | `src/prova/s3_grounder/dom_locator.py` (878줄) | 기획서의 라벨("이메일") → 화면의 실제 요소. **selector 먼저**, 실패하면 2차 경로(VLM) 진입 | 1차 ✗ |
| | `src/prova/vlm/qwen_vl.py` · `base.py` · `metrics.py` | 2차 경로 — 스크린샷에서 요소 좌표를 찾는 시각 모델 | **○** |
| **S4** | `src/prova/s4_executor/playwright_driver.py` (522줄) | Playwright 로 진짜 크롬을 조작. 스텝마다 증거(스크린샷·DOM·URL)를 남긴다 | ✗ |
| **S5** | `src/prova/s5_verifier/assertion_engine.py` (813줄) | 기대와 실제를 대조해 PASS/FAIL 판정 + 실패 원인 분류. **여기에 LLM 이 없는 것이 이 도구의 신뢰 근거** | ✗ |
| **S6** | `src/prova/s6_report/report_builder.py` (658줄) | 판정 결과 → `report.json` + `report.html` | ✗ |

### 단계를 잇는 것

| 파일 | 하는 일 |
|---|---|
| `src/prova/models.py` (720줄) | **데이터 계약.** 단계 사이에 흐르는 모든 타입. 여기를 알면 나머지가 읽힌다 — 제일 먼저 읽을 파일 |
| `src/prova/nodes.py` (644줄) | 각 단계를 `(state) -> state` 함수 하나로 감싼 것 |
| `src/prova/pipeline.py` (511줄) | `build_plan`(브라우저 없이 S1~S2) + `run_pipeline`(전체) |
| `src/prova/graph.py` (130줄) | 같은 노드를 LangGraph 로 배선한 것 (계획서 산출물 4번) |
| `src/prova/cli.py` (593줄) | `prova run` / `serve` / `check` / `login` |
| `src/prova/server/app.py` · `runner.py` | 로컬 웹 UI — 계획 확인 후 승인받고 실행 |
| `src/prova/plan_store.py` (158줄) | `--plan-only` / `--resume` 용 계획 저장·복원 (GPU 한 장으로 두 모델 쓰기) |

---

## 2. 아직 안 한 것 — 난이도별

출처는 [`docs/roadmap.md`](roadmap.md) (README 가 "아직 안 한 것" 으로 가리키는 문서).
**취소선 친 항목(이미 닫힌 것)은 뺐다.** 예상 작업량은 Python 을 처음 다루는 사람 기준이다.

| 난이도 | 남은 것 | 관련 파일 | 예상 작업량 | 메모 |
|---|---|---|---|---|
| **하** | `screen_name` 과 `<title>` 대조 | `s5_verifier/assertion_engine.py`, `models.py` | 0.5~1일 | **일부러 미뤄 둔 것.** 오탐 위험이 높다 — 손대려면 먼저 왜 미뤘는지 팀에 확인 |
| **하** | CI 연동 (`locator 캐시 · 병렬 실행 · CI 연동` 중) | `.github/workflows/` **(아직 없음)** | 0.5~1일 | GitHub Actions 로 `pytest` 를 돌리는 것. 코드를 안 건드리고 배울 수 있다 |
| **하~중** | 표 헤더 후보 넓히기 (`항목`·`필드`·`구분` 등) | `s1_spec_extractor/pdf_parser.py` | 1~2일 | 로드맵이 **"실물 문서를 본 뒤 결정한다"** 고 보류. 미리 넓히면 엉뚱한 표를 요소 표로 오독한다 |
| **중** | 셀렉트형 기간 (최근 1주일 등) | `s2_case_generator/generator.py` 의 `_filter_cases`, `sut/app.py` | 2~3일 | 날짜 필터의 남은 모양 하나. 앞의 O1~O6 이 전부 닫혀 있어 **따라 할 본보기가 많다** |
| **중** | 표 마크업의 나머지 모양 — colspan 머리글 · 머리글 없는 표 · `<div role="grid">` | `s3_grounder/dom_locator.py`, `sut/app.py` | 3~5일 | `<caption>`·`<th>` 경로는 이미 있다. 그 옆에 붙이는 일 |
| **중** | 확장프로그램 트리거 | 새 폴더 (Python 아님 — JS + manifest) | 2~4일 | 현재 탭 URL 을 `localhost:7007` 로 넘기는 얇은 것. **파이프라인을 안 건드려서 안전하다** |
| **중~상** | Figma 명시 매핑 override · 컴포넌트 이름 매핑 확장 | `s1_figma/figma_parser.py`, `s1_merge.py` | 3~5일 | 실물 디자인 시스템을 본 뒤 결정 |
| **상** | 요청 해석 — "화면 전반 점검" 에서 가드가 빠지는 모양 | `s2_case_generator/selector.py`, `scripts/probe_request_selection.py` | 5일~ | **GPU 필요.** 홀드아웃 B 9/10 에서 막혀 있고 실물 기획서에서 재측정해야 한다 |
| **상** | 우리가 안 만든 웹앱 — 로그인 외 화면(회원가입·검색·표) | `s3_grounder/`, `s1_spec_extractor/` | 5일~ | 2026-09-23 에 로그인 3곳 관통. 다음 화면은 새 오탐 원인이 또 나올 자리 |
| **상** | 7B 가 실패 조건 표를 의역해 내는 '모델 메모' 잡음 | `s1_spec_extractor/extractor.py` | 5일~ | **GPU 필요.** 판정에는 영향 없고 경고만 지저분해지는 문제 |
| **상 (막힘)** | **실물 기획서로 S1 확인** | — | — | **로드맵 최우선인데 외부 대기 중.** 코드로 풀 수 없다 — ㈜WITCHES/멘토에게 실물 화면기획서를 받아와야 한다 |

### 닫힌 항목에 남은 잔여 위험 (새로 시작할 일은 아니지만 알아 둘 것)

- **VLM 2차 경로 오탐** — 관문이 오탐을 전부 막았지만, *이름 없는 엉뚱한 요소* 위에 좌표가
  떨어지는 모양은 이 시험지에 없었다. 실물에서만 나올 수 있다
- **§9 IoU 57.1%** — 상자 **크기** 문제라 모델을 바꾸지 않으면 안 오른다 (아래 3장)

---

## 3. 계획서 4-6 성과 지표 6개 — 측정됐는가

계획서 [`docs/reference/하반기_계획서_초안.md`](reference/하반기_계획서_초안.md) 4-6절,
목표치는 명세서 [`docs/specs/Prova_서비스명세서.md`](specs/Prova_서비스명세서.md) §9.

### 측정된 것 (4개)

| # | 지표 | 목표 | 실측 | 출처 파일 |
|---|---|---|---|---|
| 1 | GUI 요소 탐지 성공률 (IoU≥0.5) | ≥ 90% | **36/63 = 57.1%** ❌ **미달** | `docs/measurements/vlm-iou-qwen-vl-2026-08-31.md` |
| | └ 적중률 (중심이 요소 안) — 병기 보고용 | — | **57/63 = 90.5%** | 〃 |
| | └ **selector vs VLM 비교** (§9 추가 요구) | — | 탐지 **96.8% vs 90.5%** · 오탐 **0% vs 71.4%** · 속도 **6.8ms vs 839ms (124배)** | `docs/measurements/grounding-selector-vs-vlm-2026-08-27.md` |
| 3 | 테스트 케이스 생성 품질 | 정성 평가 | **54/54 통과** (골든 데이터 대조, 세 화면) | `tests/test_s1_golden.py`, `fixtures/specs/*.golden.json` |
| 4 | Self-Healing 복구율 | 정량 측정 | `nolabel` 검색: 2차 경로 **끔 1P/9F → 켬 9P/1F** (이미지로 찾아 진행 8건) | `README.md` 결과 표, `tests/test_vlm_healing.py` |
| | └ 관문이 오탐을 막는가 | — | 오탐 **9/9 차단** · 정상 보정 오차단 **0** | `docs/measurements/identity-guard-replay-2026-08-31.md` |
| 7* | 실패 원인 자동 분류 (계획서 2장 목표 7번) | — | 8종 분류가 코드에 있다 — `element_not_found` / `input_error` / `assertion_mismatch` / `timeout` / `page_error` / `precondition_failed` / `unverifiable` / `unknown` | `src/prova/models.py` `FailureCategory` |

### 측정 안 된 것 / 지표로 집계되지 않은 것 (3개) — **여기가 회의에서 찔릴 자리다**

| # | 지표 | 목표 | 지금 상태 | 왜 문제인가 |
|---|---|---|---|---|
| 2 | **PASS/FAIL 판단 정확도** | ≥ 90% | **실질적으로는 증명돼 있으나 수치가 없다.** `good`/`bad` 대조에서 심은 결함을 전부 지목하고 오탐 0건이 반복 확인됨 (README 결과 표 20여 행) | `good`/`bad` 는 사실상 정답 라벨이다. 그런데 **"정확도 N%" 로 집계한 문서가 없다.** "정확도 얼마냐" 고 물으면 지금 당장 한 숫자로 못 댄다 |
| 5 | **리포트 완결성** | **100%** | 명세서가 "필드 체크리스트" 로 재라고 했는데 그 체크리스트 결과 문서가 없다. 리포트 관련 테스트는 여럿 있다 (`tests/test_report_*.py` 6개) | 목표가 100% 인데 100% 라고 말할 근거 문서가 없다 |
| 6 | **로컬 모델 vs 외부 API 정확도 비교** | 단계별 비교 | **비교 자체를 안 했다.** 저장소 결론은 "로컬 7B 가 54/54 뽑았으니 Claude API 가 필요 없다" (README, `docs/teaching/02-s1-spec-extraction.md`) | **"필요 없다" 는 관찰이지 비교가 아니다.** 명세서 §9 가 요구한 건 단계별(S1·S2·S6) 비교표다. 멘토가 짚으면 답할 자료가 없다 |

> **지표 2·5 는 새 측정 없이 이미 있는 데이터로 만들 수 있다.** 지표 6 은 외부 API 키가 필요하고,
> "기획서는 고객 자산이라 외부 API 로 보낼 수 없다"(`docs/study/README.md`)는 원칙과 충돌하므로
> **측정할지 말지부터 팀에서 정해야 한다.**

---

## 4. 초보자가 처음 손대기 좋은 항목 3개

고른 기준: **① 실패해도 파이프라인이 안 망가진다 ② GPU 가 필요 없다 ③ 따라 할 본보기가 저장소에 이미 있다.**

### ① 리포트 완결성 체크리스트 만들기 (지표 5)

- **왜 좋은가** — `src/prova/` 를 **하나도 고치지 않는다.** `runs/<run-id>/report.json` 을 열어
  명세서 §9 가 요구한 다섯 필드(로그·입력·기대·실제·원인)가 다 있는지 세는 스크립트 하나면 된다.
  Python 으로 JSON 읽기 연습이면서 동시에 **미측정 지표 하나를 닫는다.**
- **어디에** — `scripts/` 에 새 파일 (도구를 재는 것은 `prova` 패키지 밖에 두는 규칙),
  결과는 `docs/measurements/` 에
- **본보기** — `scripts/eval_selector_speed.py` 가 "재서 md 로 남기는" 같은 모양이다
- **예상** 1~2일

### ② GitHub Actions 로 테스트 자동 실행 (CI 연동)

- **왜 좋은가** — Python 코드가 아니라 YAML 이다. 망가뜨릴 코드가 없다. 그리고 예원님이
  이번에 겪은 문제(`uv` 없음 → `playwright install` 안 함 → E2E 232개 전멸)가 **다시는 조용히
  일어나지 않게** 만든다. 인수인계 직후에 가장 체감이 큰 기여다
- **어디에** — `.github/workflows/test.yml` (지금 `.github/` 자체가 없다)
- **주의** — 실모델 테스트 105개는 GPU 가 없으면 자동 skip 되므로 CI 에서도 그대로 skip 된다
- **예상** 0.5~1일

### ③ 셀렉트형 기간 필터 (최근 1주일 등)

- **왜 좋은가** — 파이프라인을 실제로 건드리는 첫 작업으로 적당하다. 같은 화면(주문조회)에서
  **O1~O6 여섯 개가 이미 같은 방식으로 닫혀 있어** 따라 쓸 코드와 테스트가 바로 옆에 있다.
  기간 역전(O5)·상태 필터(O6) 커밋을 그대로 흉내 내면 된다
- **어디에** — `sut/app.py` 에 화면 추가 → `fixtures/specs/orders_spec.md` 에 규칙 추가 →
  `s2_case_generator/generator.py` 의 `_filter_cases`
- **본보기** — `docs/teaching/20-date-filter.md` 와 설계 판단 15
- **예상** 2~3일

> **피해야 할 것:** 로드맵이 "실물 문서를 본 뒤 결정한다"(표 헤더 넓히기) 또는
> "일부러 미룬다"(`screen_name`↔`<title>`)고 적어 둔 항목. 쉬워 **보이지만** 미뤄 둔 이유가
> 오탐 위험이라, 초보자가 손대면 도구의 신뢰를 깎는 쪽으로 틀리기 쉽다.

---

## 5. 지금 환경 상태 (2026-09-23 확인)

| 항목 | 상태 |
|---|---|
| `uv` | pip 으로 설치함 (`C:\Users\dpdnj\AppData\Local\Python\pythoncore-3.14-64\Scripts`). **PATH 에 넣는 것이 남았다** |
| `uv sync --extra dev` | ✅ |
| `uv run playwright install chromium` | ✅ (안 하면 E2E 232개가 전부 ERROR) |
| `uv run pytest -q` | ✅ **1117 passed · 105 skipped · 0 failed** |
| `.env` (CHEETAH GPU 접속) | ❌ 없음 — `.env.example` 만 있다. 팀 채널에서 받아야 실모델 105개가 돈다 |
| `gh` (GitHub CLI) | ❌ 없음 (`git` 만으로도 작업에 지장 없다) |

---

## 6. 더 읽을 것

| 문서 | 언제 |
|---|---|
| [`docs/teaching/00-overview.md`](teaching/00-overview.md) | **가장 먼저.** 전체 그림 + 용어 사전 |
| [`docs/teaching/03-llm-vs-code.md`](teaching/03-llm-vs-code.md) | "AI 에 뭘 맡기고 뭘 안 맡기나" — 이 프로젝트의 핵심 판단 |
| [`docs/design-decisions.md`](design-decisions.md) | 명세서와 다르게 한 **21군데**. 코드를 고치기 전에 읽는다 |
| [`docs/lessons.md`](lessons.md) | 문서로는 예측 못 하고 돌려 보고 알게 된 것들 |
| [`docs/pr/00-reading-guide.md`](pr/00-reading-guide.md) | 큰 PR 을 읽는 순서 + 스스로 적은 한계 목록 |
| [`docs/measurements/`](measurements/) | **보고에 쓰는 숫자의 출처.** 회의 전에 여기 수치를 확인한다 |
