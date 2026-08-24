# Figma 경로 1단계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Figma API 응답(JSON)에서 화면·요소·문구·흐름을 결정적으로 추출해 부분 `ScreenSpec` 으로 만들고, SUT 관통(디자인↔구현 정합성 판정)까지 증명한다.

**Architecture:** 별도 프론트엔드 모듈 `src/prova/s1_figma/`(파서 + 조립기)가 저장된 Figma 응답을 읽어 PDF 경로와 같은 계약(`SpecDocument`)을 생산한다. LLM 무관. `ScreenSpec.source_kind="figma"` 가 S2 를 정적 대조 3종(labels·placeholders·options)으로 제한한다 — 성공 조건·규칙이 없는 스펙에서 valid/흐름 케이스는 오탐이 된다.

**Tech Stack:** Python 3.11, pydantic, requests(fetch 스크립트만), pytest. 네트워크는 fetch 스크립트만 쓴다 — 테스트는 저장본으로 결정적.

**Spec:** `docs/superpowers/specs/2026-08-25-figma-stage1-design.md`

## Global Constraints

- 공개 저장소 — `FIGMA_TOKEN`·`FIGMA_FILE_KEY` 는 `.env` 전용, 절대 커밋 금지. 푸시 전 스캔 패턴에 `figd_` 추가: `git diff origin/main | grep -nE '168\.131|ssh -p [0-9]|jovyan@|kdw51@|PRIVATE KEY|figd_'`
- 오탐 0 · 억측 금지(컴포넌트 아니면 유형 미상 경고, 경로는 사용자 입력) · 만들 수 없는 검증은 경고를 남기고 만들지 않는다.
- 추출은 전부 결정적 — LLM 을 부르지 않는다.
- 커밋 서술형 한국어, TDD. 전체 테스트 `uv run pytest -q` (현재 891 passed skip 0 기준).
- 작업 디렉터리 `C:\dev\prova`, 브랜치 `feature/prova-pipeline`.
- Task 6 은 사용자가 Figma 픽스처를 그려 `.env` 를 채운 뒤에만 가능 — 그 전 태스크는 합성 응답으로 진행한다.

## File Structure

```
src/prova/s1_figma/__init__.py        (빈 파일)
src/prova/s1_figma/figma_parser.py    응답 JSON 읽기 — 프레임·인스턴스·텍스트·흐름·트림 (순수 함수)
src/prova/s1_figma/extractor.py       extract_figma_document() — SpecDocument 조립 + 경고
scripts/fetch_figma.py                API fetch → trim → fixtures/figma/*.json 저장
fixtures/figma/synthetic_login_signup.json   합성 응답 (SUT 문구와 일치 — e2e 용)
fixtures/figma/login_signup.json      실물 응답 (Task 6, 사용자 파일에서 fetch)
fixtures/figma/login_signup.golden.json      실물 응답의 기대 SpecDocument
tests/test_figma_parser.py            파서·트림 단위 (합성 노드 트리)
tests/test_figma_extractor.py         조립·경고·흐름·경로 매핑
tests/test_figma_cases.py             S2 figma 분기 (정적 3종만·valid 없음·흐름 없음)
tests/test_figma_e2e.py               합성 응답 → SUT good/bad 관통
```

## Figma REST 응답의 모양 (합성 픽스처가 따를 계약)

`GET /v1/files/{key}` 응답에서 우리가 쓰는 부분:

```json
{
  "name": "prova-fixture",
  "document": {"id": "0:0", "type": "DOCUMENT", "children": [
    {"id": "0:1", "type": "CANVAS", "name": "Page 1", "children": [
      {"id": "1:2", "type": "FRAME", "name": "로그인", "children": [
        {"id": "1:3", "type": "INSTANCE", "componentId": "9:1", "name": "Input", "children": [
          {"id": "1:4", "type": "TEXT", "name": "label", "characters": "이메일"},
          {"id": "1:5", "type": "TEXT", "name": "placeholder", "characters": "이메일을 입력하세요"}
        ]},
        {"id": "1:9", "type": "INSTANCE", "componentId": "9:2", "name": "Button",
         "transitionNodeId": "2:1", "children": [
          {"id": "1:10", "type": "TEXT", "name": "text", "characters": "로그인"}
        ]}
      ]},
      {"id": "2:1", "type": "FRAME", "name": "회원가입", "children": ["..."]}
    ]}
  ]},
  "components": {"9:1": {"name": "Input"}, "9:2": {"name": "Button"}}
}
```

- INSTANCE 의 유형은 `componentId` → 최상위 `components` 맵의 `name` 으로 푼다.
- prototype 연결은 노드의 `transitionNodeId` (다른 최상위 프레임의 id).
- 실물 응답이 이 모양과 어긋나면 **실물이 이긴다** (Task 6 에서 파서를 고친다).

---

### Task 1: `ScreenSpec.source_kind` + S2 figma 분기

**Files:**
- Modify: `src/prova/models.py` (ScreenSpec)
- Modify: `src/prova/s2_case_generator/generator.py:220` (generate_cases 첫머리)
- Modify: `src/prova/nodes.py:156` (흐름 케이스 게이트)
- Modify: `src/prova/s1_spec_extractor/extractor.py` (PDF 경로 방어 한 줄)
- Test: `tests/test_figma_cases.py`

**Interfaces:**
- Produces: `ScreenSpec.source_kind: Literal["document", "figma"] = "document"`. `generate_cases` 는 figma 스펙에서 정적 3종만 돌려주고, `url_path` 가 비면 빈 목록. `generate_test_cases`(nodes)는 figma 출처만 있는 문서에서 흐름 케이스를 만들지 않는다.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_figma_cases.py` 신규:

```python
"""S2 — figma 출처 스펙은 정적 대조 3종만 만든다 (specs/2026-08-25).

figma 스펙에는 성공 조건·검증 규칙·테스트 계정이 없다. 그 근거 없이 valid
케이스를 만들면 임의 값 제출 → 에러 노출 → FAIL, 즉 구현이 옳아도 오탐이다.
흐름 케이스도 같다 — 도착을 판정할 근거(문구·경로)가 없다. 추출은 하되
케이스는 만들지 않는다.
"""

from prova.models import Flow, ScreenSpec, SpecDocument, UIElement
from prova.nodes import AgentState, generate_test_cases
from prova.s2_case_generator.generator import generate_cases


def figma_login_spec(url_path: str = "/login") -> ScreenSpec:
    return ScreenSpec(
        screen_id="login", screen_name="로그인", url_path=url_path,
        source_kind="figma",
        elements=[
            UIElement(element_id="n1_3", type="input", label="이메일",
                      placeholder="이메일을 입력하세요"),
            UIElement(element_id="n1_6", type="input", label="비밀번호",
                      placeholder="비밀번호를 입력하세요"),
            UIElement(element_id="n1_9", type="button", label="로그인"),
        ],
    )


class TestFigmaCases:
    def test_정적_대조_케이스만_만든다(self):
        cases = generate_cases(figma_login_spec())
        kinds = sorted(c.case_id for c in cases)
        assert kinds == ["login-labels-001", "login-placeholders-001"]

    def test_valid_케이스를_만들지_않는다(self):
        assert not any("-valid-" in c.case_id for c in generate_cases(figma_login_spec()))

    def test_select_가_있으면_options_케이스도_만든다(self):
        spec = figma_login_spec()
        spec.elements.append(UIElement(
            element_id="n2_1", type="select", label="가입 경로",
            options=["검색", "지인 추천", "광고"]))
        cases = generate_cases(spec)
        assert any(c.expected.type == "options_present" for c in cases)

    def test_경로_매핑이_없으면_케이스를_만들지_않는다(self):
        assert generate_cases(figma_login_spec(url_path="")) == []

    def test_figma_문서는_흐름_케이스를_만들지_않는다(self):
        doc = SpecDocument(
            source="fixtures/figma/x.json",
            screens=[figma_login_spec()],
            flows=[Flow(flow_id="signup_to_login", screen_ids=["signup", "login"])],
        )
        state = AgentState(pdf_path="", base_url="", run_id="t",
                           run_dir=__import__("pathlib").Path("."), doc=doc)
        state = generate_test_cases(state)
        assert not any(c.flow_id for c in state.cases)

    def test_document_출처는_기존_그대로다(self):
        spec = figma_login_spec()
        spec.source_kind = "document"
        assert any("-valid-" in c.case_id for c in generate_cases(spec))
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_figma_cases.py -x -q` → ValidationError(`source_kind` 필드 없음).
- [ ] **Step 3: 모델 구현** — `models.py` 의 ScreenSpec 필드에 추가 (`seed_rows`·`date_filter` 옆):

```python
    # 이 스펙이 어디서 왔는가. "figma" 출처는 검증 규칙·성공 조건·테스트 계정을
    # 담지 못한다 — S2 는 그 근거가 필요한 케이스(valid·위반·흐름)를 만들지 않고
    # 정적 대조(라벨·안내 문구·선택 항목)만 만든다. 근거 없이 만들면 구현이
    # 옳아도 FAIL 이 나는 오탐이 된다 (specs/2026-08-25).
    source_kind: Literal["document", "figma"] = "document"
```

- [ ] **Step 4: S2 분기 구현** — `generate_cases` 본문 첫머리(`cases: list[TestCase] = []` 앞)에:

```python
    if spec.source_kind == "figma":
        # figma 스펙에는 valid·위반 케이스의 근거(성공 조건·규칙·계정)가 없다.
        # 경로 매핑이 없는 화면은 navigate 대상이 없으므로 아무것도 만들지
        # 않는다 — 그 사실의 경고는 추출기가 문서 수준에 이미 남겼다.
        if not spec.url_path:
            return []
        static_cases: list[TestCase] = []
        static_cases.extend(_option_cases(spec, start_seq=1))
        static_cases.extend(_placeholder_case(spec))
        static_cases.extend(_label_case(spec))
        return static_cases
```

`nodes.py` `generate_test_cases` 의 `cases.extend(generate_flow_cases(state.doc))` 를:

```python
    if all(s.source_kind == "document" for s in state.doc.screens):
        cases.extend(generate_flow_cases(state.doc))
    # figma 출처가 섞이면 흐름 케이스를 만들지 않는다 — 도착을 판정할
    # 근거(문구·경로)가 figma 에 없다. 흐름 자체는 doc.flows 에 추출돼
    # 리포트가 '추출했으나 검증하지 않음' 을 말할 수 있다.
```

`s1_spec_extractor/extractor.py` 의 `spec = ScreenSpec.model_validate(raw)` 다음 줄에 방어 한 줄 (`source_kind` 가 LLM 스키마에 노출되므로 모델이 무엇을 내든 되돌린다):

```python
    spec.source_kind = "document"  # LLM 이 무엇을 냈든 이 경로의 출처는 문서다
```

- [ ] **Step 5: 통과 확인** — `uv run pytest tests/test_figma_cases.py tests/test_generator.py tests/test_orders_cases.py -q`
- [ ] **Step 6: 커밋** — `git add -A && git commit -m "figma 출처 스펙은 정적 대조만 만든다 — 근거 없는 케이스는 오탐이다"`

---

### Task 2: 응답 파서 `figma_parser.py`

**Files:**
- Create: `src/prova/s1_figma/__init__.py` (빈 파일)
- Create: `src/prova/s1_figma/figma_parser.py`
- Test: `tests/test_figma_parser.py`

**Interfaces:**
- Produces (Task 3·4·6 이 쓴다):

```python
@dataclass
class FigmaElement:
    node_id: str          # "1:3"
    type: str             # models.ElementType 값 ("input"·"button"·"checkbox"·"select"·"list")
    label: str
    placeholder: Optional[str]
    options: list[str]

@dataclass
class FigmaFrame:
    node_id: str
    name: str             # 프레임 이름 → screen_name
    elements: list[FigmaElement]
    warnings: list[str]   # 이 프레임 안에서 나온 경고
    transitions: list[tuple[str, str]]  # (출발 노드 id, 도착 프레임 id)

def parse_figma_file(raw: dict) -> tuple[list[FigmaFrame], list[str]]
def trim_figma_response(raw: dict) -> dict
COMPONENT_TYPES: dict[str, str]  # {"Input": "input", "Button": "button", ...}
```

- [ ] **Step 1: 실패하는 테스트** — `tests/test_figma_parser.py` 신규. 합성 트리 빌더를 파일 상단에 두고 전 테스트가 공유한다:

```python
"""Figma 응답 파서 — 구조에 적힌 사실만 결정적으로 읽는다 (specs/2026-08-25).

옛 브랜치는 노드 이름에 'button/입력' 이 들어가면 요소로 주웠고, 튜토리얼
파일의 본문 문장까지 버튼이 됐다. 여기서는 INSTANCE 의 원본 컴포넌트 이름만
믿는다 — 컴포넌트가 아닌 노드는 유형을 알 수 없으므로 줍지 않고 경고한다.
"""

from prova.s1_figma.figma_parser import parse_figma_file, trim_figma_response


def text(node_id, layer_name, chars):
    return {"id": node_id, "type": "TEXT", "name": layer_name, "characters": chars}


def instance(node_id, component_id, children, name="inst", **extra):
    return {"id": node_id, "type": "INSTANCE", "componentId": component_id,
            "name": name, "children": children, **extra}


def frame(node_id, name, children):
    return {"id": node_id, "type": "FRAME", "name": name, "children": children}


def figma_file(frames, components):
    return {
        "name": "prova-fixture",
        "document": {"id": "0:0", "type": "DOCUMENT", "children": [
            {"id": "0:1", "type": "CANVAS", "name": "Page 1", "children": frames},
        ]},
        "components": components,
    }


COMPONENTS = {"9:1": {"name": "Input"}, "9:2": {"name": "Button"},
              "9:3": {"name": "Checkbox"}, "9:4": {"name": "Select"}}

LOGIN = frame("1:2", "로그인", [
    instance("1:3", "9:1", [text("1:4", "label", "이메일"),
                            text("1:5", "placeholder", "이메일을 입력하세요")]),
    instance("1:6", "9:1", [text("1:7", "label", "비밀번호"),
                            text("1:8", "placeholder", "비밀번호를 입력하세요")]),
    instance("1:9", "9:2", [text("1:10", "text", "로그인")],
             transitionNodeId="2:1"),
])


class TestFrames:
    def test_최상위_프레임이_화면이다(self):
        frames, warnings = parse_figma_file(figma_file([LOGIN], COMPONENTS))
        assert [f.name for f in frames] == ["로그인"]
        assert warnings == []

    def test_프레임_이름이_겹치면_경고하고_뒤_프레임을_버린다(self):
        dup = frame("3:1", "로그인", [])
        frames, warnings = parse_figma_file(figma_file([LOGIN, dup], COMPONENTS))
        assert len(frames) == 1
        assert any("겹" in w for w in warnings)


class TestElements:
    def test_컴포넌트_이름으로_유형을_판정한다(self):
        frames, _ = parse_figma_file(figma_file([LOGIN], COMPONENTS))
        got = [(e.type, e.label) for e in frames[0].elements]
        assert got == [("input", "이메일"), ("input", "비밀번호"), ("button", "로그인")]

    def test_element_id_는_노드_id_다(self):
        frames, _ = parse_figma_file(figma_file([LOGIN], COMPONENTS))
        assert frames[0].elements[0].node_id == "1:3"

    def test_placeholder_는_레이어_이름으로_찾는다(self):
        frames, _ = parse_figma_file(figma_file([LOGIN], COMPONENTS))
        assert frames[0].elements[0].placeholder == "이메일을 입력하세요"
        assert frames[0].elements[2].placeholder is None

    def test_select_의_option_레이어들이_순서대로_options_다(self):
        sel = instance("4:1", "9:4", [
            text("4:2", "label", "가입 경로"),
            text("4:3", "option", "검색"), text("4:4", "option", "지인 추천"),
        ])
        frames, _ = parse_figma_file(figma_file([frame("4:0", "s", [sel])], COMPONENTS))
        e = frames[0].elements[0]
        assert (e.type, e.label, e.options) == ("select", "가입 경로", ["검색", "지인 추천"])

    def test_체크박스는_첫_텍스트가_라벨이다(self):
        cb = instance("5:1", "9:3", [text("5:2", "text", "약관에 동의합니다")])
        frames, _ = parse_figma_file(figma_file([frame("5:0", "s", [cb])], COMPONENTS))
        assert (frames[0].elements[0].type, frames[0].elements[0].label) == \
            ("checkbox", "약관에 동의합니다")


class TestWarnings:
    def test_컴포넌트가_아닌_요소형_노드는_줍지_않고_경고한다(self):
        fake = {"id": "6:1", "type": "FRAME", "name": "가짜 입력란",
                "children": [text("6:2", "text", "여기에 입력")]}
        frames, _ = parse_figma_file(
            figma_file([frame("6:0", "s", [fake])], COMPONENTS))
        assert frames[0].elements == []
        assert any("컴포넌트가 아니" in w for w in frames[0].warnings)

    def test_모르는_컴포넌트_이름은_경고한다(self):
        card = instance("7:1", "9:9", [text("7:2", "text", "x")])
        frames, _ = parse_figma_file(
            figma_file([frame("7:0", "s", [card])], {"9:9": {"name": "Card"}}))
        assert frames[0].elements == []
        assert any("Card" in w for w in frames[0].warnings)

    def test_라벨_없는_Input_은_제외하고_경고한다(self):
        no_label = instance("8:1", "9:1", [text("8:2", "placeholder", "값")])
        frames, _ = parse_figma_file(
            figma_file([frame("8:0", "s", [no_label])], COMPONENTS))
        assert frames[0].elements == []
        assert any("라벨" in w for w in frames[0].warnings)


class TestTransitions:
    def test_prototype_연결을_추출한다(self):
        frames, _ = parse_figma_file(
            figma_file([LOGIN, frame("2:1", "회원가입", [])], COMPONENTS))
        assert frames[0].transitions == [("1:9", "2:1")]


class TestTrim:
    def test_필요한_키만_남긴다(self):
        raw = figma_file([LOGIN], COMPONENTS)
        raw["styles"] = {"big": "junk"}
        raw["document"]["children"][0]["children"][0]["children"][0]["fills"] = [{"r": 1}]
        trimmed = trim_figma_response(raw)
        assert "styles" not in trimmed
        node = trimmed["document"]["children"][0]["children"][0]["children"][0]
        assert "fills" not in node
        # 다듬어도 파싱 결과는 같아야 한다 — 다듬기가 사실을 지우면 안 된다
        assert parse_figma_file(trimmed)[0][0].elements == \
            parse_figma_file(raw)[0][0].elements
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_figma_parser.py -x -q` → ModuleNotFoundError.
- [ ] **Step 3: 구현** — `src/prova/s1_figma/figma_parser.py`:

```python
"""Figma REST 응답 읽기 — 구조에 적힌 사실만, 결정적으로 (specs/2026-08-25).

## 왜 컴포넌트 이름만 믿는가

폐기된 첫 시도는 노드 이름에 'button/입력' 이 들어가면 요소로 주웠다. Figma
튜토리얼 파일에서 본문 문장 프레임까지 버튼이 됐다 — 이름은 디자이너의 자유
텍스트라서 유형의 근거가 못 된다. INSTANCE 노드의 componentId 가 가리키는
원본 컴포넌트 이름은 디자인 시스템의 구조라 근거가 된다. 컴포넌트가 아닌
노드는 유형을 알 수 없으므로 줍지 않고 경고한다 — 억측하지 않는다.

## LLM 을 부르지 않는 이유

PDF 는 자연어라 구조화에 모델이 필요했다. Figma 응답은 이미 트리다 — 여기서
모델을 부르면 검증 가능한 사실을 검증 불가능한 추측으로 바꾸는 셈이 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from prova.text_utils import normalize_ws

#: 컴포넌트 이름 -> models.ElementType. 정확 일치(공백 정규화만).
#: 여기 없는 이름은 매핑하지 않는다 — pdf_parser.ELEMENT_TYPE_WORDS 와 같은 원칙.
COMPONENT_TYPES: dict[str, str] = {
    "Input": "input",
    "Button": "button",
    "Checkbox": "checkbox",
    "Select": "select",
    "List": "list",
}

#: 요소로 착각하기 쉬운 컨테이너 노드 유형 — 컴포넌트가 아니면서 자식에
#: TEXT 를 가진 이런 노드는 '유형 미상' 경고 대상이다.
_CONTAINER_TYPES = frozenset({"FRAME", "GROUP", "RECTANGLE", "COMPONENT"})


@dataclass
class FigmaElement:
    node_id: str
    type: str
    label: str
    placeholder: Optional[str] = None
    options: list[str] = field(default_factory=list)


@dataclass
class FigmaFrame:
    node_id: str
    name: str
    elements: list[FigmaElement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    transitions: list[tuple[str, str]] = field(default_factory=list)


def parse_figma_file(raw: dict) -> tuple[list[FigmaFrame], list[str]]:
    """응답 전체 -> (최상위 프레임들, 문서 수준 경고)."""
    components = {
        cid: normalize_ws(c.get("name", ""))
        for cid, c in (raw.get("components") or {}).items()
    }
    warnings: list[str] = []
    frames: list[FigmaFrame] = []
    seen: set[str] = set()
    for page in (raw.get("document") or {}).get("children", []):
        for node in page.get("children", []):
            if node.get("type") != "FRAME":
                continue
            name = normalize_ws(node.get("name", ""))
            if name in seen:
                warnings.append(
                    f"최상위 프레임 이름 {name!r} 이 겹쳐 뒤의 것을 무시했습니다 — "
                    "화면 이름은 화면의 정체성이라 겹치면 어느 쪽인지 정할 수 없습니다."
                )
                continue
            seen.add(name)
            frames.append(_parse_frame(node, components))
    return frames, warnings


def _parse_frame(node: dict, components: dict[str, str]) -> FigmaFrame:
    f = FigmaFrame(node_id=node["id"], name=normalize_ws(node.get("name", "")))
    _walk(node, f, components, top_id=node["id"])
    return f


def _walk(node: dict, f: FigmaFrame, components: dict[str, str], top_id: str) -> None:
    for child in node.get("children", []):
        if child.get("type") == "INSTANCE":
            _parse_instance(child, f, components)
        else:
            if _looks_like_element(child):
                f.warnings.append(
                    f"{child.get('name', '?')!r} 은 컴포넌트가 아니라 유형을 알 수 "
                    "없어 요소로 줍지 않았습니다 — 디자인을 컴포넌트 인스턴스로 "
                    "그려야 추출됩니다."
                )
            _walk(child, f, components, top_id)
        dst = child.get("transitionNodeId")
        if dst:
            f.transitions.append((child["id"], dst))


def _looks_like_element(node: dict) -> bool:
    """컨테이너 안에 TEXT 를 직접 가진, 요소처럼 보이는 비컴포넌트 노드."""
    if node.get("type") not in _CONTAINER_TYPES:
        return False
    return any(c.get("type") == "TEXT" for c in node.get("children", []))


def _parse_instance(node: dict, f: FigmaFrame, components: dict[str, str]) -> None:
    comp_name = components.get(node.get("componentId", ""), "")
    el_type = COMPONENT_TYPES.get(comp_name)
    if el_type is None:
        f.warnings.append(
            f"컴포넌트 {comp_name or '?'!r} 은 아는 유형이 아니라 요소로 줍지 "
            f"않았습니다 (노드 {node['id']})."
        )
        return
    texts = [(normalize_ws(c.get("name", "")), c.get("characters", "").strip())
             for c in node.get("children", []) if c.get("type") == "TEXT"]
    by_layer: dict[str, str] = {}
    for layer, chars in texts:
        by_layer.setdefault(layer, chars)

    if el_type in ("input", "select"):
        label = by_layer.get("label", "")
    else:
        label = texts[0][1] if texts else ""
    if not label:
        f.warnings.append(
            f"{comp_name} 인스턴스(노드 {node['id']})에 라벨 텍스트가 없어 "
            "요소로 줍지 않았습니다 — 라벨 없는 요소는 화면에서 지목할 수 없습니다."
        )
        return

    f.elements.append(FigmaElement(
        node_id=node["id"],
        type=el_type,
        label=label,
        placeholder=by_layer.get("placeholder") or None,
        options=[chars for layer, chars in texts if layer == "option"],
    ))


_NODE_KEEP = ("id", "name", "type", "characters", "componentId", "transitionNodeId")


def trim_figma_response(raw: dict) -> dict:
    """저장할 응답에서 필요한 키만 남긴다.

    원본은 65k 줄이 넘어 픽스처로 읽을 수 없다. 다듬기는 손이 아니라 이 함수가
    한다 — 손으로 만지면 '실물 API 응답' 이라는 증거가 사라진다. 다듬은 결과의
    파싱이 원본과 같음을 테스트가 지킨다.
    """
    def trim_node(node: dict) -> dict:
        out = {k: node[k] for k in _NODE_KEEP if k in node}
        if "children" in node:
            out["children"] = [trim_node(c) for c in node["children"]]
        return out

    return {
        "name": raw.get("name", ""),
        "document": trim_node(raw.get("document") or {}),
        "components": {
            cid: {"name": c.get("name", "")}
            for cid, c in (raw.get("components") or {}).items()
        },
    }
```

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_figma_parser.py -q`
- [ ] **Step 5: 커밋** — `git add -A && git commit -m "Figma 응답 파서 — 컴포넌트 이름만 믿고, 아닌 것은 경고한다"`

---

### Task 3: 조립기 `extractor.py`

**Files:**
- Create: `src/prova/s1_figma/extractor.py`
- Test: `tests/test_figma_extractor.py`

**Interfaces:**
- Consumes: `parse_figma_file`, `FigmaFrame`, `FigmaElement` (Task 2), `SpecDocument`/`ScreenSpec`/`UIElement`/`Flow` (models).
- Produces: `extract_figma_document(json_path: str | Path, screen_urls: dict[str, str]) -> SpecDocument` — `screen_urls` 는 {screen_id: url_path}. screen_id 는 프레임 이름의 소문자 슬러그(한글 유지, 공백 → `_`).

- [ ] **Step 1: 실패하는 테스트** — `tests/test_figma_extractor.py` 신규 (Task 2 의 빌더 재사용을 위해 `from tests.test_figma_parser import ...` 가 아니라 — 테스트 간 import 는 하지 않는다, conftest 도 건드리지 않는다 — 같은 빌더 함수를 이 파일에도 둔다. 중복 6줄이 테스트 파일 간 결합보다 싸다):

```python
"""Figma 응답 -> SpecDocument 조립 (specs/2026-08-25).

경로(url_path)는 Figma 가 말하지 않는다 — 사용자가 준 매핑(screen_urls)만
쓰고, 매핑 없는 화면은 문서 경고로 남긴다(해석 실패는 더 많이 알리는 쪽으로).
"""

import json

from prova.s1_figma.extractor import extract_figma_document

# (Task 2 와 같은 text/instance/frame/figma_file/COMPONENTS/LOGIN 빌더를 여기 복사)


def write_fixture(tmp_path, raw) -> str:
    p = tmp_path / "figma.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return str(p)


class TestExtract:
    def test_프레임이_figma_출처_화면이_된다(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        doc = extract_figma_document(path, {"로그인": "/login"})
        screen = doc.screens[0]
        assert (screen.screen_id, screen.screen_name) == ("로그인", "로그인")
        assert screen.source_kind == "figma"
        assert screen.url_path == "/login"

    def test_요소가_옮겨진다(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        screen = extract_figma_document(path, {"로그인": "/login"}).screens[0]
        assert [(e.element_id, e.type, e.label) for e in screen.elements] == [
            ("n1_3", "input", "이메일"), ("n1_6", "input", "비밀번호"),
            ("n1_9", "button", "로그인"),
        ]
        assert screen.elements[0].placeholder == "이메일을 입력하세요"

    def test_규칙_필드는_전부_빈다(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        screen = extract_figma_document(path, {"로그인": "/login"}).screens[0]
        assert screen.success_condition == ""
        assert all(not e.constraints for e in screen.elements)
        assert screen.precondition is None and screen.seed_rows == []

    def test_매핑_없는_화면은_경로_없이_문서_경고(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        doc = extract_figma_document(path, {})
        assert doc.screens[0].url_path == ""
        assert any("경로" in w for w in doc.warnings)

    def test_프레임_경고가_화면_경고로_남는다(self, tmp_path):
        fake = {"id": "6:1", "type": "FRAME", "name": "가짜 입력란",
                "children": [text("6:2", "text", "여기에 입력")]}
        path = write_fixture(
            tmp_path, figma_file([frame("6:0", "로그인", [fake])], COMPONENTS))
        doc = extract_figma_document(path, {"로그인": "/login"})
        assert any("컴포넌트가 아니" in w for w in doc.screens[0].warnings)

    def test_prototype_연결이_흐름이_된다(self, tmp_path):
        signup = frame("2:1", "회원가입", [])
        path = write_fixture(tmp_path, figma_file([LOGIN, signup], COMPONENTS))
        doc = extract_figma_document(path, {"로그인": "/login", "회원가입": "/signup"})
        assert [f.screen_ids for f in doc.flows] == [["로그인", "회원가입"]]

    def test_알_수_없는_프레임으로의_연결은_경고(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        doc = extract_figma_document(path, {"로그인": "/login"})
        assert doc.flows == []
        assert any("연결" in w for w in doc.warnings)
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_figma_extractor.py -x -q` → ModuleNotFoundError.
- [ ] **Step 3: 구현** — `src/prova/s1_figma/extractor.py`:

```python
"""Figma 응답 -> SpecDocument. PDF 경로와 같은 계약, LLM 없음 (specs/2026-08-25)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from prova.models import Flow, ScreenSpec, SpecDocument, UIElement
from prova.s1_figma.figma_parser import FigmaFrame, parse_figma_file


def _slug(name: str) -> str:
    return re.sub(r"\s+", "_", name.strip()).lower()


def _node_slug(node_id: str) -> str:
    """Figma 노드 id("1:3") -> element_id("n1_3"). 사람이 지은 id 가 없으므로
    노드 정체성을 그대로 쓴다 — 억측한 영문명을 만들지 않는다."""
    return "n" + re.sub(r"[^0-9]+", "_", node_id)


def extract_figma_document(
    json_path: str | Path, screen_urls: dict[str, str]
) -> SpecDocument:
    raw = json.loads(Path(json_path).read_text(encoding="utf-8"))
    frames, doc_warnings = parse_figma_file(raw)

    doc = SpecDocument(source=str(json_path), warnings=doc_warnings)
    frame_id_to_screen: dict[str, str] = {}
    for f in frames:
        screen_id = _slug(f.name)
        frame_id_to_screen[f.node_id] = screen_id
        url = screen_urls.get(screen_id, "")
        if not url:
            doc.warnings.append(
                f"화면 {f.name!r} 의 경로 매핑이 없어 실행하지 않습니다 — "
                "--screen-url 로 화면↔경로를 지정하세요. Figma 에는 경로가 "
                "없으므로 추측하지 않습니다."
            )
        doc.screens.append(ScreenSpec(
            screen_id=screen_id,
            screen_name=f.name,
            url_path=url,
            source_kind="figma",
            elements=[UIElement(
                element_id=_node_slug(e.node_id), type=e.type, label=e.label,
                placeholder=e.placeholder, options=e.options,
            ) for e in f.elements],
            warnings=list(f.warnings),
        ))

    for f in frames:
        for _src_node, dst_frame in f.transitions:
            dst = frame_id_to_screen.get(dst_frame)
            if dst is None:
                doc.warnings.append(
                    f"화면 {f.name!r} 의 prototype 연결이 알 수 없는 프레임"
                    f"({dst_frame})을 가리켜 흐름으로 추출하지 않았습니다."
                )
                continue
            src = frame_id_to_screen[f.node_id]
            doc.flows.append(Flow(
                flow_id=f"{src}_to_{dst}", screen_ids=[src, dst],
            ))
    return doc
```

(주의: `Flow` 의 실제 필수 필드를 models 에서 확인하고 맞춘다 — `screen_ids` 외에 링크 라벨 등이 필수면 추출 가능한 값으로 채우되, 추측이 필요한 필드가 있으면 흐름 추출을 경고로 낮춘다.)

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_figma_extractor.py tests/test_figma_parser.py -q`
- [ ] **Step 5: 커밋** — `git add -A && git commit -m "Figma 응답을 SpecDocument 로 조립한다 — 경로는 사용자 매핑, 없으면 경고"`

---

### Task 4: 파이프라인·CLI 통합 + 리포트 출처 표기

**Files:**
- Modify: `src/prova/nodes.py:57` (AgentState 입력 필드) · `:122` (extract_spec 분기)
- Modify: `src/prova/pipeline.py:58` (build_plan) · `:158` (run_pipeline) — `figma_json`·`screen_urls` 파라미터 전달
- Modify: `src/prova/cli.py:52` (run 커맨드 — pdf 인자 선택화, `--figma-json`, `--screen-url`)
- Modify: `src/prova/s6_report/report_builder.py` (출처 표기 한 줄)
- Test: `tests/test_figma_e2e.py` (계획 수립 부분), CLI 검증은 `tests/test_figma_extractor.py` 에 추가하지 않고 cli 함수 단위로

**Interfaces:**
- Produces: `AgentState.figma_json: Optional[str] = None`, `AgentState.screen_urls: dict[str, str]`. `build_plan(..., figma_json=None, screen_urls=None)` / `run_pipeline(...)` 동일. CLI: `prova run --figma-json <path> --screen-url 로그인=/login --screen-url 회원가입=/signup <base_url>` (pdf 인자와 상호 배타, `--request` 와 병용 불가).

- [ ] **Step 1: 실패하는 테스트** — `tests/test_figma_e2e.py` 신규, 우선 계획 수립(브라우저 불필요)만:

```python
"""Figma 경로 관통 — 합성 응답으로 계획 수립과 SUT 판정까지 (specs/2026-08-25).

MockLLM 조차 없다 — figma 경로는 LLM 을 부르지 않는 것이 계약이다.
"""

import json

import pytest

from prova.pipeline import build_plan, run_pipeline

FIXTURE = "fixtures/figma/synthetic_login_signup.json"
URLS = {"로그인": "/login", "회원가입": "/signup"}


class TestPlan:
    def test_LLM_없이_계획이_선다(self, tmp_path):
        state, n_all = build_plan(
            pdf_path="", base_url="http://x", llm=None, run_id="t",
            run_dir=tmp_path, figma_json=FIXTURE, screen_urls=URLS,
        )
        assert n_all > 0
        assert all(c.expected.type in
                   ("labels_findable", "placeholders_match", "options_present")
                   for c in state.cases)

    def test_흐름은_추출되지만_케이스는_없다(self, tmp_path):
        state, _ = build_plan(
            pdf_path="", base_url="http://x", llm=None, run_id="t",
            run_dir=tmp_path, figma_json=FIXTURE, screen_urls=URLS,
        )
        assert state.doc.flows        # 가입하기 -> 로그인 연결
        assert not any(c.flow_id for c in state.cases)

    def test_매핑_없는_화면의_케이스는_없고_경고가_남는다(self, tmp_path):
        state, _ = build_plan(
            pdf_path="", base_url="http://x", llm=None, run_id="t",
            run_dir=tmp_path, figma_json=FIXTURE,
            screen_urls={"로그인": "/login"},
        )
        assert not any(c.screen_id == "회원가입" for c in state.cases)
        assert any("경로 매핑" in w for w in state.doc.warnings)
```

합성 픽스처 `fixtures/figma/synthetic_login_signup.json` 을 이 태스크에서 만든다 — Task 2 테스트 빌더와 같은 모양으로, **문구는 SUT good 과 일치**시킨다 (`sut/templates/login.html`·`signup.html` 의 실제 라벨·placeholder 를 열어 확인하고 그대로 옮긴다. 파일 첫 키로 `"_note": "합성 응답 — Figma REST 모양을 따라 손으로 작성. 실물 응답은 login_signup.json (Task 6)"` 을 넣어 실물로 오인되지 않게 한다). 회원가입 프레임의 `가입하기` Button 인스턴스에 `transitionNodeId` 로 로그인 프레임을 가리키게 한다.

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_figma_e2e.py -x -q` → TypeError(`figma_json` 인자 없음).
- [ ] **Step 3: 구현** —

`nodes.py` AgentState 입력부(`vlm` 옆)에:

```python
    # Figma 경로 입력. figma_json 이 있으면 extract_spec 이 PDF 대신 이것을 읽는다.
    # screen_urls 는 {screen_id: url_path} — Figma 에는 경로가 없으므로 사용자가 준다.
    figma_json: Optional[str] = None
    screen_urls: dict[str, str] = field(default_factory=dict)
```

`extract_spec` 분기 (`if state.llm is None` 검사 **앞**):

```python
    if state.figma_json:
        # Figma 경로 — LLM 을 부르지 않는다. 응답은 이미 구조화된 트리라서
        # 모델을 거치면 검증 가능한 사실이 검증 불가능한 추측이 된다.
        state.doc = extract_figma_document(state.figma_json, state.screen_urls)
        for screen in state.doc.screens:
            screen.warnings.extend(spec_defects(screen))
        return state
```

(파일 상단 import 에 `from prova.s1_figma.extractor import extract_figma_document` 추가. `spec_defects` 가 규칙 없는 스펙에서 소음 경고를 내면 — 실행해 보고 실제로 나는 경고만 — figma 스펙에 부적절한 항목을 spec_defects 쪽에서 `source_kind` 로 거른다.)

`pipeline.py` — `build_plan`·`run_pipeline` 시그니처에 `figma_json: Optional[str] = None, screen_urls: Optional[dict[str, str]] = None` 추가, AgentState 생성에 `figma_json=figma_json, screen_urls=screen_urls or {}` 전달, run_pipeline 은 build_plan 으로 그대로 전달.

`cli.py` run 커맨드 — pdf 인자를 `Optional` 로 바꾸고:

```python
    figma_json: Optional[str] = typer.Option(
        None, "--figma-json",
        help="Figma API 응답(JSON)으로 실행한다. PDF 인자와 함께 쓸 수 없다."),
    screen_url: list[str] = typer.Option(
        [], "--screen-url",
        help="화면↔경로 매핑 (예: 로그인=/login). 반복 지정."),
```

검증 로직 (LLM 클라이언트 생성 **앞**):

```python
    if figma_json and pdf:
        raise typer.BadParameter("--figma-json 과 PDF 인자는 함께 쓸 수 없습니다.")
    if not figma_json and not pdf:
        raise typer.BadParameter("PDF 경로 또는 --figma-json 이 필요합니다.")
    if figma_json and request:
        raise typer.BadParameter(
            "--figma-json 은 --request 와 함께 쓸 수 없습니다 (1단계 미지원 — "
            "요청 해석은 LLM 이 필요한데 figma 경로는 LLM 을 쓰지 않습니다).")
    screen_urls = {}
    for pair in screen_url:
        if "=" not in pair:
            raise typer.BadParameter(f"--screen-url 형식은 '화면=/경로' 입니다: {pair!r}")
        k, _, v = pair.partition("=")
        screen_urls[k.strip()] = v.strip()
```

figma 경로에서는 LLM 클라이언트를 만들지 않고 `llm=None` 으로 run_pipeline 을 부른다 (기존 pdf 경로는 무변경).

`report_builder.py` — 리포트 헤더에서 `spec_source` 를 표기하는 줄을 찾아(grep `spec_source`) 바로 옆에:

```python
    if any(s.source_kind == "figma" for s in doc.screens):
        # 입력 출처를 리포트가 말해야 한다 — figma 입력은 검증 규칙·성공 조건을
        # 담지 않으므로, 초록불이 '전부 확인됨' 으로 읽히면 안 된다.
        (헤더에 한 줄 추가: "입력: Figma 디자인 — 검증 규칙·성공 조건이 없어 "
         "정적 대조(라벨·안내 문구·선택 항목)만 수행했습니다")
```

(report_builder 의 실제 구조에 맞춰 같은 문구를 넣는다 — doc 접근이 안 되는 위치면 TestReport 에 이미 있는 필드로 판별하거나 build 인자로 받는다. 문구 자체는 위 그대로.)

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_figma_e2e.py::TestPlan tests/test_pipeline_e2e.py -q` (기존 pdf 경로 회귀 포함).
- [ ] **Step 5: 커밋** — `git add -A && git commit -m "Figma 경로를 파이프라인·CLI 에 잇는다 — LLM 없이, 경로는 사용자 매핑으로"`

---

### Task 5: SUT 관통 e2e

**Files:**
- Modify: `tests/test_figma_e2e.py` (TestGood/TestBad 추가)
- Modify: `fixtures/figma/synthetic_login_signup.json` (문구가 SUT 와 안 맞으면 여기부터 의심)

**Interfaces:**
- Consumes: `run_pipeline(figma_json=..., screen_urls=...)` (Task 4), SUT `sut_base` 픽스처(tests/conftest.py — 기존 e2e 들이 쓰는 것 그대로).

- [ ] **Step 1: 실패하는(또는 처음 도는) 테스트** — `tests/test_figma_e2e.py` 에 추가:

```python
def _run(variant: str, sut_base, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path="", base_url=f"{sut_base}/{variant}", llm=None,
        run_id=f"test-figma-{variant}", runs_root=tmp_path,
        figma_json=FIXTURE, screen_urls=URLS,
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("figma-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("figma-bad"))


class TestGood:
    def test_디자인과_구현이_일치하면_전부_통과한다(self, good_run):
        report, _ = good_run
        fails = [v for v in report.cases if v.verdict == "FAIL"]
        assert not fails, "\n".join(f"{v.case_id}: {v.failure_detail}" for v in fails)
        # 0건 통과가 아니라 실제로 정적 3종이 만들어졌는지까지
        assert report.summary["total"] >= 4  # 화면 2 × (labels+placeholders) 최소

    def test_리포트가_입력_출처를_말한다(self, good_run):
        _, run_dir = good_run
        html = (run_dir / "report.html").read_text(encoding="utf-8")
        assert "Figma" in html and "정적 대조" in html


class TestBad:
    def test_심은_문구_결함이_잡힌다(self, bad_run):
        """SUT bad 의 기존 문구·요소 결함 중 figma 정적 대조가 잡을 수 있는 것을
        실행 전에 sut/app.py 헤더 결함 표와 대조해 확정하고, 그 케이스가 FAIL
        인지 단언한다. 잡을 것이 하나도 없으면 이 테스트를 '전부 PASS + 그
        사실을 문서에 기록' 으로 바꾼다 — 픽스처를 결함에 맞춰 구부리지 않는다."""
        report, _ = bad_run
        assert report.summary["total"] >= 4
```

(주의: `report.html` 의 실제 파일명은 run_dir 에서 확인해 맞춘다. TestBad 의 단언은 Step 2 에서 실측으로 확정한다 — bad 로그인/회원가입에 placeholder·라벨 결함이 심겨 있는지는 `sut/app.py` 헤더 표가 진실이다.)

- [ ] **Step 2: 실측으로 기대 확정** — `uv run pytest tests/test_figma_e2e.py -q` 를 돌리고, good 이 전부 PASS 가 아니면 **픽스처 문구 vs SUT 문구**를 대조해 픽스처를 고친다(SUT·검증 코드는 건드리지 않는다 — 디자인이 구현과 다르면 FAIL 이 맞다는 것이 이 경로의 존재 이유이므로, good 픽스처는 구현과 일치해야 한다). bad 의 FAIL 목록을 보고 TestBad 단언을 실제 결함으로 채운다.
- [ ] **Step 3: 통과 확인** — `uv run pytest tests/test_figma_e2e.py -q`
- [ ] **Step 4: 커밋** — `git add -A && git commit -m "Figma 경로 SUT 관통 — 디자인↔구현 정합성 판정이 실제로 돈다"`

---

### Task 6: 실물 픽스처 수용 (사용자 Figma 파일 도착 후)

**Files:**
- Create: `scripts/fetch_figma.py`
- Create: `fixtures/figma/login_signup.json` (스크립트 산출물)
- Create: `fixtures/figma/login_signup.golden.json` (기대 SpecDocument)
- Test: `tests/test_figma_extractor.py` 에 골든 대조 클래스 추가

**전제:** 사용자가 스펙 §픽스처 명세대로 그렸고 `.env` 에 `FIGMA_TOKEN`·`FIGMA_FILE_KEY` 가 있다.

- [ ] **Step 1: fetch 스크립트** — `scripts/fetch_figma.py`:

```python
"""Figma API 응답을 받아 다듬어 저장한다.

사용법:
    uv run python scripts/fetch_figma.py fixtures/figma/login_signup.json

.env 의 FIGMA_TOKEN·FIGMA_FILE_KEY 를 쓴다. 저장 전에 trim_figma_response 로
필요한 키만 남긴다 — 다듬기를 손으로 하면 '실물 응답' 이라는 증거가 사라지므로
반드시 이 스크립트로 한다. 토큰은 절대 저장물에 남지 않는다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prova.s1_figma.figma_parser import trim_figma_response  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "fixtures/figma/login_signup.json")
    token = os.environ.get("FIGMA_TOKEN", "")
    file_key = os.environ.get("FIGMA_FILE_KEY", "")
    if not token or not file_key:
        raise SystemExit(".env 의 FIGMA_TOKEN·FIGMA_FILE_KEY 가 필요합니다 — "
                         "set -a && . ./.env && set +a 후 다시 실행하세요.")
    resp = requests.get(
        f"https://api.figma.com/v1/files/{file_key}",
        headers={"X-Figma-Token": token}, timeout=60)
    resp.raise_for_status()
    trimmed = trim_figma_response(resp.json())
    out.write_text(json.dumps(trimmed, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: fetch 실행** — `cd /c/dev/prova && set -a && . ./.env && set +a && uv run python scripts/fetch_figma.py fixtures/figma/login_signup.json`. 저장물에 토큰·file_key 가 없는지 육안 + `grep -c figd_ fixtures/figma/login_signup.json` = 0 확인.
- [ ] **Step 3: 실물로 파서 검증** — `uv run python -c "from prova.s1_figma.extractor import extract_figma_document; d = extract_figma_document('fixtures/figma/login_signup.json', {'로그인': '/login', '회원가입': '/signup'}); [print(s.screen_id, [(e.type, e.label) for e in s.elements], s.warnings) for s in d.screens]; print(d.flows, d.warnings)"` — 실물 응답이 합성 모양과 어긋나면(레이어 이름·중첩 구조 등) **실물이 이긴다**: 파서를 고치고 Task 2 테스트를 실물 모양으로 갱신한다. 스펙 §픽스처 명세와 다르게 그려진 것이면 어느 쪽이 맞는지 사용자와 확인.
- [ ] **Step 4: 골든 작성 + 대조 테스트** — Step 3 출력을 검수한 뒤 `fixtures/figma/login_signup.golden.json` 에 `SpecDocument.model_dump()` 를 저장하고, `tests/test_figma_extractor.py` 에:

```python
class TestRealFixture:
    """실물 Figma 응답 대조 — 합성과 실물이 어긋나면 실물이 이긴다."""

    def test_실물_응답이_골든과_같다(self):
        import json
        from pathlib import Path
        fixture = Path("fixtures/figma/login_signup.json")
        if not fixture.exists():
            pytest.skip("실물 픽스처 없음 — scripts/fetch_figma.py 를 먼저 실행")
        doc = extract_figma_document(fixture, {"로그인": "/login", "회원가입": "/signup"})
        golden = json.loads(Path("fixtures/figma/login_signup.golden.json")
                            .read_text(encoding="utf-8"))
        assert json.loads(doc.model_dump_json()) == golden

    def test_의도적_함정이_경고로_남았다(self):
        fixture = Path("fixtures/figma/login_signup.json")
        if not fixture.exists():
            pytest.skip("실물 픽스처 없음")
        doc = extract_figma_document(fixture, {"로그인": "/login", "회원가입": "/signup"})
        login = doc.screen_by_id("로그인")
        assert any("컴포넌트가 아니" in w for w in login.warnings)
```

- [ ] **Step 5: e2e 를 실물로 승격** — `tests/test_figma_e2e.py` 의 `FIXTURE` 를 실물(`login_signup.json`)로 바꾸고 합성 파일은 파서 단위 테스트 용으로만 남긴다 (실물이 없으면 skip 하지 말고 합성으로 폴백? — 아니다: e2e 는 실물로 바꾸되 파일 부재 시 합성으로 **폴백하고 그 사실을 테스트 이름/주석에 명시**한다. 조용한 폴백은 금지 — `FIXTURE = real if Path(real).exists() else SYNTHETIC` 에 주석으로 이유를 적는다).
- [ ] **Step 6: 커밋** — `git add -A && git commit -m "실물 Figma 픽스처를 받아 골든으로 굳힌다 — 합성과 어긋나면 실물이 이긴다"`

---

### Task 7: 문서·풀스위트·푸시

- [ ] **Step 1: 문서** — `README.md`: 결과 표에 Figma 행(good 전부 PASS · bad 실측 결과), 남은 것 표에서 "Figma 연동" 항목을 1단계 닫힘으로 갱신(2단계 — 규칙 병합·흐름 케이스·웹 UI — 를 남은 것으로), 설계 판단 16(컴포넌트 기반·규칙 없이·경로는 사용자 입력 — 왜 LLM 을 안 쓰는가). 트리에 `s1_figma/`·`fixtures/figma/` 추가. `docs/teaching/21-figma-path.md` 신규(노트 스타일: 옛 브랜치가 왜 실패했는가 → 컴포넌트 기반 → 부분 스펙과 오탐 → 관통 결과). `docs/README.md`·`docs/teaching/00-overview.md` 노트 목록, `overview.src.html` 남은 것 표 + 테스트 수 → `uv run python scripts/embed_media.py`. `docs/pr/00-reading-guide.md` 테스트 수.
- [ ] **Step 2: 풀스위트** — `uv run pytest -q` (터널 필요 — 실모델 골든 skip 0). 기대: 891 + 신규 전부 PASS.
- [ ] **Step 3: 비밀 스캔 + 푸시** — `git diff origin/main | grep -nE '168\.131|ssh -p [0-9]|jovyan@|kdw51@|PRIVATE KEY|figd_'` 0건(계획·스펙 문서 안의 스캔 명령 문자열 제외) 확인 후 `git push origin feature/prova-pipeline` → `git checkout main && git merge --ff-only feature/prova-pipeline && git push origin main && git checkout feature/prova-pipeline`.
- [ ] **Step 4: 메모리 갱신** — `prova-implementation.md` 에 완료 기록(커밋 해시·수치·2단계 후보), `MEMORY.md` 인덱스 줄 갱신.
