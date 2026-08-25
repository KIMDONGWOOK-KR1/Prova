# Figma 2단계 (병합·불일치 발견) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기획서 PDF 와 Figma 응답을 한 실행에서 병합해 검증하되, 어긋나는 정보는 판정 대신 "기획↔디자인 불일치" 발견으로 리포트에 보고한다.

**Architecture:** 새 순수 모듈 `s1_merge.py` 가 두 `SpecDocument` 를 이름 매칭으로 병합하고 발견 목록을 낸다. 병합 화면은 `source_kind="document"`(규칙 보유 — S2 full 생성). Figma 흐름은 채택 규칙(link 채택 / button 은 성공 조건 경로 대조 / 불능이면 미채택+발견)으로만 들어간다. 발견은 경고와 별도 채널(`design_mismatches`)로 리포트 상자에 실린다.

**Tech Stack:** Python 3.11, pydantic, pytest. 병합은 LLM 없음(PDF 추출만 기존대로 LLM).

**Spec:** `docs/superpowers/specs/2026-08-25-figma-stage2-merge-design.md` (흐름 채택 규칙 보정 포함 — 계획과 함께 읽는다)

## Global Constraints

- 공개 저장소 — 비밀은 `.env` 만. 푸시 전 `git diff origin/main | grep -nE '168\.131|ssh -p [0-9]|jovyan@|kdw51@|PRIVATE KEY|figd_'`
- 오탐 0 · 어긋남은 판정이 아니라 발견 · 판정 불능이면 만들지 않고 알린다.
- 문구 비교는 `text_utils.loosen`(공백 무시) — 정확 비교로 소음을 만들지 않는다.
- 커밋 서술형 한국어, TDD. 전체 `uv run pytest -q` (현재 로컬 940 기준 — 잘린 표 잇기까지 반영, 마지막 풀스위트 931 + 신규 9).
- `C:\dev\prova`, 브랜치 `feature/prova-pipeline`.

## File Structure

```
src/prova/s1_merge.py                 merge_documents() — 순수 함수 (신설)
src/prova/nodes.py                    extract_spec 병합 분기 · AgentState.design_mismatches ·
                                      build_final_report 전달 · 흐름 게이트를 흐름 단위로
src/prova/s2_case_generator/generator.py  generate_flow_cases 흐름별 document 게이트
src/prova/pipeline.py                 (변경 없음 — figma_json+pdf_path 둘 다 이미 전달됨)
src/prova/cli.py                      --pdf + --figma-json 병용 허용(병합 모드)
src/prova/s6_report/report_builder.py summary["design_mismatches"] + HTML 상자
fixtures/figma/synthetic_mismatch.json 손제작 불일치 픽스처
tests/test_merge_documents.py         병합·발견·흐름 채택 단위
tests/test_figma_merge_e2e.py         multi_spec + 실물/불일치 응답 관통
```

---

### Task 1: `merge_documents` — 화면·요소 병합과 발견

**Files:**
- Create: `src/prova/s1_merge.py`
- Test: `tests/test_merge_documents.py`

**Interfaces:**
- Produces: `merge_documents(pdf_doc: SpecDocument, figma_doc: SpecDocument) -> tuple[SpecDocument, list[str]]`. 반환 문서는 새 객체(입력 불변). 발견 문장은 화면·요소·양쪽 값을 다 담는다.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_merge_documents.py` 신규:

```python
"""기획서+Figma 병합 — 어긋남은 판정이 아니라 발견이다 (specs/2026-08-25 2단계).

겹치는 정보가 어긋나면 그 항목을 검증에서 빼고 불일치로 보고한다. 틀린
근거로 판정하는 것보다, 입력끼리의 모순을 사람에게 보이는 것이 먼저다.
"""

from prova.models import Flow, ScreenSpec, SpecDocument, UIElement
from prova.s1_merge import merge_documents


def pdf_login(**over):
    base = dict(
        screen_id="login", screen_name="로그인", url_path="/login",
        success_condition="`/dashboard` 로 이동하고 \"환영합니다\" 문구를 노출한다",
        elements=[
            UIElement(element_id="email", type="input", label="이메일",
                      placeholder="이메일을 입력하세요",
                      constraints={"format": "email"}),
            UIElement(element_id="login_btn", type="button", label="로그인"),
        ],
    )
    base.update(over)
    return ScreenSpec(**base)


def figma_login(**over):
    base = dict(
        screen_id="로그인", screen_name="로그인", url_path="",
        source_kind="figma",
        elements=[
            UIElement(element_id="n1_3", type="input", label="이메일",
                      placeholder="이메일을 입력하세요"),
            UIElement(element_id="n1_9", type="button", label="로그인"),
        ],
    )
    base.update(over)
    return ScreenSpec(**base)


def docs(pdf_screens, figma_screens, pdf_flows=(), figma_flows=()):
    return (SpecDocument(source="p.pdf", screens=pdf_screens, flows=list(pdf_flows)),
            SpecDocument(source="f.json", screens=figma_screens, flows=list(figma_flows)))


class TestScreens:
    def test_이름이_같으면_기획서_기반으로_병합된다(self):
        merged, findings = merge_documents(*docs([pdf_login()], [figma_login()]))
        screen = merged.screens[0]
        assert screen.screen_id == "login"          # 기획서 정체성 유지
        assert screen.source_kind == "document"     # 규칙이 있으므로 full 생성
        assert screen.elements[0].constraints == {"format": "email"}
        assert findings == []                       # 전부 일치 — 발견 없음

    def test_기획서에만_있는_화면은_그대로_두고_발견(self):
        merged, findings = merge_documents(*docs([pdf_login()], []))
        assert merged.screens[0].screen_id == "login"
        assert any("디자인에 없" in f for f in findings)

    def test_디자인에만_있는_화면은_figma_모드_그대로_발견(self):
        merged, findings = merge_documents(*docs([], [figma_login()]))
        assert merged.screens[0].source_kind == "figma"
        assert any("기획서에 없" in f for f in findings)


class TestElements:
    def test_placeholder_가_어긋나면_검증에서_빼고_발견(self):
        fig = figma_login()
        fig.elements[0].placeholder = "아이디를 입력하세요"
        merged, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert merged.screens[0].elements[0].placeholder is None
        assert any("안내 문구" in f and "이메일을 입력하세요" in f
                   and "아이디를 입력하세요" in f for f in findings)

    def test_placeholder_는_공백_무시_비교다(self):
        fig = figma_login()
        fig.elements[0].placeholder = "이메일을  입력하세요"
        _, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert findings == []

    def test_유형이_어긋나면_기획서_유형을_유지하고_발견(self):
        fig = figma_login()
        fig.elements[1] = UIElement(element_id="n1_9", type="link", label="로그인")
        merged, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert merged.screens[0].element_by_id("login_btn").type == "button"
        assert any("유형" in f for f in findings)

    def test_디자인에만_있는_요소는_추가되고_발견(self):
        fig = figma_login()
        fig.elements.append(UIElement(element_id="n1_20", type="input", label="OTP"))
        merged, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert merged.screens[0].element_by_id("n1_20") is not None
        assert any("OTP" in f and "기획서에 없" in f for f in findings)

    def test_기획서에만_있는_요소는_유지되고_발견(self):
        fig = figma_login()
        fig.elements = fig.elements[:1]  # 로그인 버튼이 디자인에 없다
        merged, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert merged.screens[0].element_by_id("login_btn") is not None
        assert any("로그인" in f and "디자인에 없" in f for f in findings)

    def test_options_가_어긋나면_기획서_것을_유지하고_발견(self):
        pdf = pdf_login()
        pdf.elements.append(UIElement(element_id="path", type="select",
                                      label="가입 경로", options=["검색", "광고"]))
        fig = figma_login()
        fig.elements.append(UIElement(element_id="n1_30", type="select",
                                      label="가입 경로", options=["검색"]))
        merged, findings = merge_documents(*docs([pdf], [fig]))
        assert merged.screens[0].element_by_id("path").options == ["검색", "광고"]
        assert any("선택 항목" in f for f in findings)

    def test_입력_불변이다(self):
        pdf_doc, fig_doc = docs([pdf_login()], [figma_login()])
        before = pdf_doc.model_dump_json()
        merge_documents(pdf_doc, fig_doc)
        assert pdf_doc.model_dump_json() == before
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_merge_documents.py -x -q` → ModuleNotFoundError.
- [ ] **Step 3: 구현** — `src/prova/s1_merge.py`:

```python
"""기획서 + Figma 병합 — 어긋남은 판정이 아니라 발견이다 (specs/2026-08-25 2단계).

순수 함수, LLM 없음. 화면은 screen_name(정규화), 요소는 라벨 정확 일치로
짝짓는다. 겹치는 정보가 어긋나면 그 항목을 검증에서 빼고 발견으로 보고한다 —
틀린 근거로 판정하는 것보다 입력끼리의 모순을 사람에게 보이는 것이 먼저다.
발견은 경고(spec_warnings)가 아니라 별도 채널이다: 경고는 '추출이 덜 됐다',
발견은 '입력이 서로 모순이다' — 성격이 다른 사실을 한 목록에 섞으면 둘 다
묻힌다(coverage 모듈과 같은 원리).
"""

from __future__ import annotations

from prova.models import ScreenSpec, SpecDocument, UIElement
from prova.text_utils import loosen, normalize_ws


def merge_documents(
    pdf_doc: SpecDocument, figma_doc: SpecDocument
) -> tuple[SpecDocument, list[str]]:
    findings: list[str] = []
    merged = SpecDocument(
        source=f"{pdf_doc.source} + {figma_doc.source}",
        warnings=list(pdf_doc.warnings) + list(figma_doc.warnings),
    )
    figma_by_name = {normalize_ws(s.screen_name): s for s in figma_doc.screens}
    matched_names: set[str] = set()

    for pdf_screen in pdf_doc.screens:
        name = normalize_ws(pdf_screen.screen_name)
        figma_screen = figma_by_name.get(name)
        if figma_screen is None:
            findings.append(
                f"화면 {pdf_screen.screen_name!r} 이 디자인에 없습니다 — "
                "기획서 단독으로 검증합니다."
            )
            merged.screens.append(pdf_screen.model_copy(deep=True))
            continue
        matched_names.add(name)
        merged.screens.append(
            _merge_screen(pdf_screen, figma_screen, findings))

    for figma_screen in figma_doc.screens:
        if normalize_ws(figma_screen.screen_name) in matched_names:
            continue
        findings.append(
            f"화면 {figma_screen.screen_name!r} 이 기획서에 없습니다 — "
            "디자인 단독(정적 대조)으로 검증합니다."
        )
        merged.screens.append(figma_screen.model_copy(deep=True))

    _merge_flows(merged, pdf_doc, figma_doc, findings)
    return merged, findings


def _merge_screen(
    pdf_screen: ScreenSpec, figma_screen: ScreenSpec, findings: list[str]
) -> ScreenSpec:
    screen = pdf_screen.model_copy(deep=True)  # 규칙·성공조건·계정·시드·경로 유지
    figma_by_label = {e.label: e for e in figma_screen.elements}
    matched_labels: set[str] = set()

    for element in screen.elements:
        figma_el = figma_by_label.get(element.label)
        if figma_el is None:
            findings.append(
                f"{screen.screen_name} 화면의 요소 {element.label!r} 가 "
                "디자인에 없습니다."
            )
            continue
        matched_labels.add(element.label)
        _compare_element(screen.screen_name, element, figma_el, findings)

    for figma_el in figma_screen.elements:
        if figma_el.label in matched_labels:
            continue
        findings.append(
            f"{screen.screen_name} 화면의 요소 {figma_el.label!r} 는 "
            "기획서에 없습니다 — 디자인 기준으로 정적 대조에 넣습니다."
        )
        screen.elements.append(figma_el.model_copy(deep=True))
    return screen


def _compare_element(
    screen_name: str, pdf_el: UIElement, figma_el: UIElement, findings: list[str]
) -> None:
    if pdf_el.type != figma_el.type:
        findings.append(
            f"{screen_name} 화면 {pdf_el.label!r} 의 유형이 다릅니다: "
            f"기획서 {pdf_el.type} / 디자인 {figma_el.type} — 기획서 유형으로 "
            "검증합니다."
        )
    if pdf_el.placeholder and figma_el.placeholder and \
            loosen(pdf_el.placeholder) != loosen(figma_el.placeholder):
        findings.append(
            f"{screen_name} 화면 {pdf_el.label!r} 의 안내 문구가 다릅니다: "
            f"기획서 {pdf_el.placeholder!r} / 디자인 {figma_el.placeholder!r} — "
            "이 요소의 안내 문구는 검증에서 뺐습니다."
        )
        pdf_el.placeholder = None  # 어느 쪽이 진실인지 모른다 — 판정하지 않는다
    if pdf_el.options and figma_el.options and pdf_el.options != figma_el.options:
        findings.append(
            f"{screen_name} 화면 {pdf_el.label!r} 의 선택 항목이 다릅니다: "
            f"기획서 {pdf_el.options} / 디자인 {figma_el.options} — 기획서 "
            "항목으로 검증합니다(항목 검증까지 빼면 둘 다 안 보게 된다)."
        )
```

(`_merge_flows` 는 Task 2 에서 — 이 태스크에서는 `def _merge_flows(...): pass` 스텁으로 두고 Task 2 테스트가 채운다.)

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_merge_documents.py -q`
- [ ] **Step 5: 커밋** — `git add -A && git commit -m "기획서+Figma 병합 — 어긋난 항목은 검증에서 빼고 발견으로 남긴다"`

---

### Task 2: 흐름 채택 규칙

**Files:**
- Modify: `src/prova/s1_merge.py` (`_merge_flows` 구현)
- Test: `tests/test_merge_documents.py` (TestFlows 추가)

**Interfaces:**
- Consumes: `parse_success_expectation`(generator — 성공 조건에서 경로를 뽑는 기존 규칙 재사용; 새 정규식을 만들지 않는다).
- Produces: 병합 문서의 flows — PDF 흐름 전부 + 채택된 Figma 흐름(화면 id 재기입).

- [ ] **Step 1: 실패하는 테스트** — TestFlows:

```python
class TestFlows:
    def _pdf_signup(self, success="가입이 완료되면 `/welcome` 로 이동한다"):
        return ScreenSpec(
            screen_id="signup", screen_name="회원가입", url_path="/signup",
            success_condition=success,
            elements=[
                UIElement(element_id="submit", type="button", label="가입하기"),
                UIElement(element_id="to_login", type="link", label="로그인하러 가기"),
            ],
        )

    def _figma_flow(self, via_node="가입하기"):
        return Flow(flow_id="회원가입_to_로그인",
                    screen_ids=["회원가입", "로그인"], via=[via_node])

    def _merge(self, pdf_flows=(), figma_flows=(), success=None):
        pdf_screens = [self._pdf_signup(**({"success": success} if success else {})),
                       pdf_login()]
        figma_screens = [ScreenSpec(screen_id="회원가입", screen_name="회원가입",
                                    url_path="", source_kind="figma"),
                         figma_login()]
        return merge_documents(*docs(pdf_screens, figma_screens,
                                     pdf_flows=pdf_flows, figma_flows=figma_flows))

    def test_PDF_흐름은_그대로_남는다(self):
        pdf_flow = Flow(flow_id="signup_then_login",
                        screen_ids=["signup", "login"], via=[])
        merged, _ = self._merge(pdf_flows=[pdf_flow])
        assert any(f.flow_id == "signup_then_login" for f in merged.flows)

    def test_link_via_흐름은_재기입되어_채택된다(self):
        merged, findings = self._merge(
            figma_flows=[self._figma_flow(via_node="로그인하러 가기")])
        adopted = [f for f in merged.flows if f.via == ["로그인하러 가기"]]
        assert adopted and adopted[0].screen_ids == ["signup", "login"]
        assert findings == []

    def test_button_via_가_성공_조건_경로와_어긋나면_발견하고_미채택(self):
        merged, findings = self._merge(figma_flows=[self._figma_flow()])
        assert merged.flows == []
        assert any("가입하기" in f and "/welcome" in f for f in findings)

    def test_button_via_가_성공_조건_경로와_맞으면_채택(self):
        merged, findings = self._merge(
            figma_flows=[Flow(flow_id="회원가입_to_로그인",
                              screen_ids=["회원가입", "로그인"], via=["가입하기"])],
            success="가입이 완료되면 `/login` 으로 이동한다")
        assert [f.via for f in merged.flows] == [["가입하기"]]
        assert findings == []

    def test_성공_조건에_경로가_없으면_판정_불능으로_미채택(self):
        merged, findings = self._merge(
            figma_flows=[self._figma_flow()],
            success="가입이 완료되면 완료 문구를 노출한다")
        assert merged.flows == []
        assert any("확인할 수 없" in f for f in findings)

    def test_같은_흐름이_양쪽에_있으면_한_번만(self):
        pdf_flow = Flow(flow_id="signup_link_to_login",
                        screen_ids=["signup", "login"], via=["로그인하러 가기"])
        merged, _ = self._merge(
            pdf_flows=[pdf_flow],
            figma_flows=[self._figma_flow(via_node="로그인하러 가기")])
        assert len(merged.flows) == 1

    def test_미매칭_화면이_낀_흐름은_발견하고_미채택(self):
        merged, findings = self._merge(
            figma_flows=[Flow(flow_id="회원가입_to_설정",
                              screen_ids=["회원가입", "설정"], via=["설정"])])
        assert merged.flows == []
        assert any("설정" in f for f in findings)

    def test_via_요소가_병합_화면에_없으면_발견하고_미채택(self):
        merged, findings = self._merge(
            figma_flows=[self._figma_flow(via_node="없는 버튼")])
        assert merged.flows == []
        assert any("없는 버튼" in f for f in findings)
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_merge_documents.py -k Flows -x -q`
- [ ] **Step 3: 구현** — `_merge_flows`:

```python
def _merge_flows(
    merged: SpecDocument, pdf_doc: SpecDocument, figma_doc: SpecDocument,
    findings: list[str],
) -> None:
    """PDF 흐름은 그대로, Figma 흐름은 채택 규칙을 통과한 것만 (스펙 '흐름
    채택 규칙'). 채택 규칙이 필요한 이유: 디자인의 prototype 연결이 기획서
    성공 조건과 모순일 수 있다 — 그대로 실행하면 구현이 옳아도 FAIL(오탐)."""
    from prova.s2_case_generator.generator import parse_success_expectation

    merged.flows.extend(f.model_copy(deep=True) for f in pdf_doc.flows)
    name_to_id = {normalize_ws(s.screen_name): s.screen_id
                  for s in merged.screens if s.source_kind == "document"}

    for flow in figma_doc.flows:
        ids = [name_to_id.get(normalize_ws(sid)) for sid in flow.screen_ids]
        if any(i is None for i in ids):
            missing = [sid for sid, i in zip(flow.screen_ids, ids) if i is None]
            findings.append(
                f"디자인 흐름 {flow.flow_id!r} 이 병합되지 않은 화면"
                f"({', '.join(missing)})을 지나 실행하지 않습니다."
            )
            continue
        via = list(flow.via)
        if any(pf.screen_ids == ids and list(pf.via) == via
               for pf in merged.flows):
            continue  # 기획서가 이미 같은 흐름을 적었다

        src = merged.screen_by_id(ids[0])
        dst = merged.screen_by_id(ids[-1])
        via_el = next((e for e in src.elements if e.label == (via[0] if via else "")),
                      None) if via else None
        if via and via_el is None:
            findings.append(
                f"디자인 흐름의 이동 요소 {via[0]!r} 가 병합 화면에 없어 "
                "실행하지 않습니다."
            )
            continue
        if via_el is not None and via_el.type != "link":
            expected_path = parse_success_expectation(src).url_contains
            if expected_path is None:
                findings.append(
                    f"디자인은 {via[0]!r} 로 {dst.screen_name!r} 이동을 그렸지만 "
                    f"{src.screen_name!r} 성공 조건에 경로가 없어 맞는지 확인할 "
                    "수 없습니다 — 실행하지 않습니다."
                )
                continue
            if expected_path != dst.url_path:
                findings.append(
                    f"디자인은 {via[0]!r} 가 {dst.screen_name!r}"
                    f"({dst.url_path})로 간다고 그렸지만 기획서 성공 조건은 "
                    f"{expected_path} 로 갑니다 — 실행하지 않고 불일치로 "
                    "보고합니다."
                )
                continue
        merged.flows.append(Flow(
            flow_id=f"{ids[0]}_to_{ids[-1]}_figma",
            title=flow.title, screen_ids=ids, via=via,
        ))
```

(파일 상단 import 에 `Flow` 추가. generator import 는 함수 안에서 — 모듈 순환을 피한다. 순환이 실제로 없으면 상단으로 올린다.)

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_merge_documents.py -q`
- [ ] **Step 5: 커밋** — `git add -A && git commit -m "디자인 흐름은 채택 규칙으로만 들어온다 — 성공 조건과 모순이면 발견"`

---

### Task 3: 파이프라인·CLI·리포트 통합

**Files:**
- Modify: `src/prova/nodes.py` (extract_spec 병합 분기 · AgentState.design_mismatches · build_final_report)
- Modify: `src/prova/s2_case_generator/generator.py` (generate_flow_cases 흐름별 게이트)
- Modify: `src/prova/cli.py` (병용 허용)
- Modify: `src/prova/s6_report/report_builder.py` (summary + HTML 상자)
- Test: `tests/test_merge_documents.py` 는 그대로, 통합 검증은 Task 4 e2e 가 맡되 CLI 검증·게이트는 기존 테스트 파일에 추가

- [ ] **Step 1: 실패하는 테스트** — `tests/test_figma_cases.py` 에 추가:

```python
    def test_병합_문서에서는_document_화면만_지나는_흐름이_케이스가_된다(self):
        doc = SpecDocument(
            source="x",
            screens=[
                ScreenSpec(screen_id="login", screen_name="로그인",
                           url_path="/login", success_condition="`/d` 로 이동",
                           elements=[UIElement(element_id="b", type="button",
                                               label="로그인")]),
                figma_login_spec(),  # source_kind figma — 병합 안 된 화면
            ],
            flows=[
                Flow(flow_id="ok", screen_ids=["login", "login"], via=[]),
                Flow(flow_id="blocked", screen_ids=["login", "login"], via=[]),
            ],
        )
        # 흐름 게이트가 '문서 전체' 가 아니라 '흐름이 밟는 화면' 기준인지 —
        # figma 화면이 섞여 있어도 document 화면만 지나는 흐름은 살아야 한다.
        state = AgentState(pdf_path="", base_url="", run_id="t",
                           run_dir=Path("."), doc=doc)
        state = generate_test_cases(state)
        assert any(c.flow_id for c in state.cases)
```

(주의: `generate_flow_cases` 가 같은 화면 반복을 거부하면 두 번째 화면을 다른 document 화면으로 바꿔 구성한다 — 의도는 "figma 화면이 문서에 섞여도 document 흐름은 산다".)

- [ ] **Step 2: 실패 확인** 후 **구현**:

`generator.generate_flow_cases` — 흐름별 게이트(함수 첫머리 flows 순회부에서):

```python
        # 흐름이 밟는 화면 중 규칙 없는 출처(figma 단독)가 있으면 그 흐름만
        # 건너뛴다 — 문서 전체를 막으면 병합 문서에서 멀쩡한 흐름까지 죽는다.
        if any((s := doc.screen_by_id(sid)) is None or s.source_kind != "document"
               for sid in flow.screen_ids):
            continue
```

`nodes.py` — 기존 문서 전체 게이트(`if all(s.source_kind == "document" ...)`) 를 제거하고 `cases.extend(generate_flow_cases(state.doc))` 로 되돌린다(게이트가 generate_flow_cases 안으로 내려갔다). `AgentState` 에:

```python
    # 기획↔디자인 불일치 (병합 모드). 경고가 아니라 발견이다 — 리포트에서
    # 별도 상자로 보인다.
    design_mismatches: list[str] = field(default_factory=list)
```

`extract_spec` 분기 재구성 (figma 단독 분기 앞에):

```python
    if state.figma_json and state.pdf_path:
        # 병합 모드 — 기획서(LLM 추출) + Figma(결정적 추출)를 이름으로 잇는다.
        if state.llm is None:
            raise ValueError("병합 모드에는 LLM 백엔드가 필요합니다 (PDF 추출)")
        pdf_doc = extract_document(state.pdf_path, state.llm)
        figma_doc = extract_figma_document(state.figma_json, state.screen_urls)
        state.doc, state.design_mismatches = merge_documents(pdf_doc, figma_doc)
        for screen in state.doc.screens:
            screen.warnings.extend(spec_defects(screen))
        return state
```

(import: `from prova.s1_merge import merge_documents`.) `build_final_report` 의 `build_report(...)` 호출에 `design_mismatches=state.design_mismatches` 추가.

`report_builder.build_report` — 파라미터 `design_mismatches: list[str] | None = None` 추가, `if design_mismatches: summary["design_mismatches"] = list(design_mismatches)`. `render_html` — mock_warn 옆에:

```python
    mismatches = s.get("design_mismatches") or []
    if mismatches:
        items = "".join(f"<li>{_esc(m)}</li>" for m in mismatches)
        mock_warn += (
            f"<div class='warn'><b>기획↔디자인 불일치 {len(mismatches)}건</b>"
            f"<div>구현을 고치기 전에 두 입력 중 어느 쪽이 맞는지부터 정해야 "
            f"합니다.<ul>{items}</ul></div></div>"
        )
```

`cli.py` — 병용 금지 검사 제거, 병합 모드 안내로 교체:

```python
    if figma_json and pdf:
        typer.echo("  모드      : 병합 (기획서 규칙 + 디자인 문구·요소·흐름, 어긋나면 발견)")
```

(figma 단독일 때만 llm=None 이던 분기: `if figma_json and not pdf:` 로 조건 좁힘. `--request` 는 병합 모드에서 허용 — 금지 검사도 `figma_json and not pdf and request` 로 좁힌다. spec_source 는 `state.figma_json or state.pdf_path` 였다 — 병합 모드면 둘 다 있으므로 nodes 의 build_report 호출에서 `f"{pdf} + {figma}"` 형태가 되도록 `state.doc.source` 를 쓰는 편이 낫다: merge_documents 가 이미 `"p.pdf + f.json"` 을 만든다 — `spec_source=state.doc.source if state.doc else state.pdf_path` 로 교체.)

- [ ] **Step 3: 통과 확인** — `uv run pytest tests/test_figma_cases.py tests/test_figma_e2e.py tests/test_multi_screen_e2e.py tests/test_pipeline_e2e.py -q`
- [ ] **Step 4: 커밋** — `git add -A && git commit -m "병합 모드를 파이프라인에 잇는다 — 발견은 경고와 다른 채널로 리포트 상자에"`

---

### Task 4: e2e — 병합 관통과 불일치 발견

**Files:**
- Create: `fixtures/figma/synthetic_mismatch.json` (손제작 — `_note` 키로 합성임을 명시. 로그인 프레임만: 이메일 Input 의 placeholder 를 `아이디를 입력하세요` 로, 비밀번호 Input 은 없애고, `OTP` Input 을 추가)
- Create: `tests/test_figma_merge_e2e.py`

- [ ] **Step 1: 테스트** —

```python
"""병합 모드 관통 — multi 기획서 + 실물 Figma 응답 (specs/2026-08-25 2단계).

일치 시나리오(실물 응답)에서 good 은 전부 PASS 여야 하고, 발견 목록에는
'구현 결함' 이 아니라 '입력 사이의 사실' 만 실린다: search 화면이 디자인에
없다는 것, 디자인의 가입하기→로그인 흐름이 기획서 성공 조건(/welcome)과
모순이라는 것. 불일치 시나리오(손제작 응답)는 발견이 리포트에 실리고 어긋난
placeholder 가 판정에서 빠지는 것을 본다.
"""

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

MULTI_PDF = "fixtures/specs/multi_spec.pdf"
REAL_FIGMA = "fixtures/figma/login_signup.json"
MISMATCH_FIGMA = "fixtures/figma/synthetic_mismatch.json"


def _run(variant, figma, sut_base, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=MULTI_PDF, base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_document(MULTI_PDF),
        run_id=f"test-merge-{variant}", runs_root=tmp_path,
        figma_json=figma,
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", REAL_FIGMA, sut_base, tmp_path_factory.mktemp("merge-good"))


class TestMergedGood:
    def test_전부_통과한다(self, good_run):
        report, _ = good_run
        fails = [v for v in report.cases if v.verdict == "FAIL"]
        assert not fails, "\n".join(f"{v.case_id}: {v.failure_detail}" for v in fails)

    def test_발견_목록이_입력_사이의_사실만_말한다(self, good_run):
        report, _ = good_run
        found = report.summary.get("design_mismatches") or []
        assert any("검색" in f for f in found)          # 기획서 단독 화면
        assert any("가입하기" in f for f in found)       # 흐름 모순 (/welcome)
        assert not any("가짜 입력란" in f for f in found)  # 1단계 경고는 경고대로

    def test_리포트에_불일치_상자가_실린다(self, good_run):
        _, run_dir = good_run
        html = (run_dir / "report.html").read_text(encoding="utf-8")
        assert "기획↔디자인 불일치" in html

    def test_규칙_케이스가_병합에서도_만들어졌다(self, good_run):
        report, _ = good_run
        assert any(v.type == "negative" for v in report.cases)


class TestMismatch:
    def test_어긋난_placeholder_는_판정에서_빠지고_발견으로_남는다(
            self, sut_base, tmp_path_factory):
        report, _ = _run("good", MISMATCH_FIGMA, sut_base,
                         tmp_path_factory.mktemp("merge-mm"))
        found = report.summary.get("design_mismatches") or []
        assert any("안내 문구" in f and "아이디를 입력하세요" in f for f in found)
        assert any("OTP" in f for f in found)
        assert any("비밀번호" in f and "디자인에 없" in f for f in found)
        # 어긋난 placeholder 로 FAIL 이 나면 안 된다 — 뺐으니까
        ph = [v for v in report.cases
              if v.screen_id == "login" and "placeholders" in v.case_id]
        assert all(v.verdict == "PASS" for v in ph)
```

(주의: multi_spec 의 mock 경로가 `MockLLM.for_document(MULTI_PDF)` 한 인자로 되는지 기존 `test_multi_screen_e2e.py` 의 호출 모양을 먼저 보고 맞춘다. OTP 요소가 login 화면 정적 대조에 들어가 good 에서 labels FAIL 을 낼 수 있다 — 기획서에 없는 요소는 SUT 에도 없으므로 '디자인에만 있는 요소' 는 **정적 대조에 넣지 않고 발견만** 하는 것이 맞는지 실행으로 확인하고, FAIL 이 나면 스펙의 '추가' 를 '발견만' 으로 보정한다 — 구현이 그 요소를 안 가진 것이 결함인지 디자인이 앞서간 것인지 판정할 근거가 없기 때문이다.)

- [ ] **Step 2: 실행·기대 확정** — `uv run pytest tests/test_figma_merge_e2e.py -q`. TestMismatch 의 OTP 가 labels 케이스를 깨면 위 주의에 따라 merge 를 '발견만' 으로 고치고 Task 1 테스트(`test_디자인에만_있는_요소는_추가되고_발견`)를 '추가하지 않고 발견' 으로 갱신한다.
- [ ] **Step 3: 커밋** — `git add -A && git commit -m "병합 모드 관통 — 발견은 리포트에, 어긋난 항목은 판정 밖에"`

---

### Task 5: 문서·풀스위트·푸시

- [ ] **Step 1: 문서** — `docs/teaching/22-figma-merge.md` 신규(어긋남=발견 결정, 흐름 채택 규칙과 실물 사례(/welcome 모순), 발견 채널이 경고와 다른 이유). README: 결과 표 병합 행, 설계 판단 17, 남은 것 Figma 2단계 행 갱신(닫힘 — 남는 것은 웹 UI·명시 매핑·3화면 흐름), 노트 22개. `docs/README.md`·`00-overview.md` 노트 행, `overview.src.html` Figma 행 갱신 + 노트 22개 + 테스트 수(풀스위트 후) → embed_media 재생성. `docs/pr/00-reading-guide.md` 수.
- [ ] **Step 2: 풀스위트** — `uv run pytest -q` (터널 필요), skip 0 확인.
- [ ] **Step 3: 스캔+푸시** — Global Constraints 의 스캔 후 push + main ff-merge (잘린 표 잇기 커밋들 포함).
- [ ] **Step 4: 메모리** — `prova-implementation.md` 완료 기록, MEMORY.md 갱신.
