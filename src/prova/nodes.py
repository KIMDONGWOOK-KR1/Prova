"""파이프라인 노드 — 각 단계를 (state) -> state 형태로 감싼다.

## 왜 이 파일이 따로 있는가

1차 관통은 pipeline.py 가 이 함수들을 순서대로 부르는 방식으로 만든다.
LangGraph 는 관통이 초록불이 된 뒤에 도입한다(계획서의 판단). 혼자 개발하는
상황에서 파이프라인 로직과 그래프 배선을 동시에 디버깅하면, 버그가 났을 때
어느 쪽 문제인지 가리는 데 시간이 배로 든다.

그 도입을 값싸게 만드는 조건이 하나 있다. **노드가 처음부터 (state) -> state
시그니처를 가져야 한다.** LangGraph 의 노드가 정확히 그 모양이므로, 그래프로
옮길 때 add_node(name, 이 함수) 로 끝난다. 함수 본문을 고칠 일이 없다.

## 상태를 통째로 넘기는 대가

함수 시그니처만 보면 무엇을 읽고 쓰는지 알 수 없다는 단점이 있다. 그래서 각
노드의 docstring 에 읽는 필드와 쓰는 필드를 명시한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page

from prova.llm.base import LLMClient
from prova.models import ScreenSpec, SpecDocument, TestCase, TestReport, Verdict
from prova.s1_spec_extractor.extractor import extract_document
from prova.s2_case_generator.coverage import coverage_gaps
from prova.s2_case_generator.generator import generate_cases, generate_flow_cases
from prova.s2_case_generator.rule_expander import spec_defects
from prova.s3_grounder.dom_locator import CollectionCount, count_items, read_options
from prova.s4_executor.playwright_driver import ExecutionContext, execute_case_steps
from prova.s5_verifier.assertion_engine import capture_page_state, verify
from prova.s6_report.report_builder import build_report


@dataclass
class AgentState:
    """파이프라인 전체가 공유하는 상태 (명세서 §4-1).

    1차 범위에서는 heal_count / retry_count 를 쓰지 않지만 필드는 지금 둔다.
    2차에서 self_heal 노드를 추가할 때 상태 구조를 바꾸면 이미 작성한 노드들의
    시그니처가 함께 흔들리기 때문이다.
    """

    # 입력
    pdf_path: str
    base_url: str
    run_id: str
    run_dir: Path
    llm: Optional[LLMClient] = None
    page: Optional[Page] = None

    # 산출물
    #
    # doc 이 단일 진실이다. 화면 하나짜리 기획서도 screens 가 1개인 SpecDocument 로
    # 담긴다 — 화면 수에 따라 상태 모양이 갈리면 노드마다 분기가 생긴다.
    doc: Optional[SpecDocument] = None
    cases: list[TestCase] = field(default_factory=list)
    # 기획서에 적혀 있는데 어떤 케이스도 확인하지 않는 것. 판정이 아니라
    # **검증 범위**에 대한 사실이므로 verdicts 와 따로 담는다.
    coverage_gaps: list[str] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    report: Optional[TestReport] = None

    # 제어 (2차 self-healing 용)
    heal_count: int = 0
    retry_count: int = 0
    max_heal: int = 2
    max_retry: int = 1

    # 실행 설정
    step_timeout_ms: int = 10000
    screenshot_every_step: bool = True

    errors: list[str] = field(default_factory=list)


def extract_spec(state: AgentState) -> AgentState:
    """S1 — PDF 에서 SpecDocument 를 추출한다 (화면 하나 이상).

    읽는 필드: pdf_path, llm
    쓰는 필드: doc
    """
    if state.llm is None:
        raise ValueError("extract_spec 에는 LLM 백엔드가 필요합니다")

    state.doc = extract_document(state.pdf_path, state.llm)

    # 기획서 내부 모순을 여기서 걸러 리포트로 올린다. 구현 결함이 아니라 기획
    # 결함이므로, 케이스 FAIL 이 아니라 경고로 알리는 것이 맞다.
    # 화면별 경고는 그 화면에 남긴다 — 어디를 고쳐야 하는지가 경고의 위치로 드러난다.
    for screen in state.doc.screens:
        screen.warnings.extend(spec_defects(screen))
    return state


def generate_test_cases(state: AgentState) -> AgentState:
    """S2 — 화면마다 케이스를 전개하고, 흐름 케이스를 뒤에 붙인다.

    읽는 필드: doc, llm
    쓰는 필드: cases

    흐름을 마지막에 두는 이유: 흐름이 실패했을 때 그것이 화면 자체의 결함인지
    화면 사이의 결함인지는 앞선 화면별 결과를 봐야 판단할 수 있다. 리포트를 읽는
    사람이 위에서 아래로 읽으면 그 순서로 근거가 쌓인다.
    """
    if state.doc is None:
        raise ValueError("generate_test_cases 전에 extract_spec 이 실행돼야 합니다")
    cases: list[TestCase] = []
    for screen in state.doc.screens:
        cases.extend(generate_cases(screen, llm=state.llm))
    cases.extend(generate_flow_cases(state.doc))
    state.cases = cases

    # 기획서에 적혀 있는데 어떤 케이스도 확인하지 않는 것을 여기서 센다.
    #
    # 케이스가 다 만들어진 뒤여야 셀 수 있고, 실행 전에 알 수 있는 사실이다.
    # '31/31 통과' 인데 실은 기획서의 일부를 확인하지 않은 리포트가 이 도구가 낼 수
    # 있는 가장 위험한 결과다 (coverage 모듈 설명 참고).
    for screen in state.doc.screens:
        own = [c for c in cases if c.screen_id == screen.screen_id and not c.flow_id]
        state.coverage_gaps.extend(
            (f"[{screen.screen_id}] {g}" if len(state.doc.screens) > 1 else g)
            for g in coverage_gaps(screen, own)
        )
    return state


def run_cases(state: AgentState) -> AgentState:
    """S3+S4+S5 — 케이스를 실행하고 판정한다.

    읽는 필드: cases, doc, page, base_url, run_dir
    쓰는 필드: verdicts

    한 케이스가 실패해도 다음 케이스를 계속 실행한다. 한 번 돌려서 전체 상태를
    파악할 수 있어야 리포트가 쓸모 있기 때문이다(명세서 §2-S6 실패 처리).

    LangGraph 로 옮길 때는 이 노드가 케이스 단위 루프(ground -> execute ->
    verify -> next_case)로 펼쳐진다. 1차에서는 self-heal 분기가 없어 루프를
    노드로 쪼갤 이득이 없으므로 한 노드에 담는다.
    """
    if state.page is None or state.doc is None:
        raise ValueError("run_cases 에는 page 와 doc 이 필요합니다")

    console_errors: list[str] = []
    state.page.on("console", lambda msg: (
        console_errors.append(msg.text) if msg.type == "error" else None
    ))

    for case in state.cases:
        console_errors.clear()
        ctx = ExecutionContext(
            page=state.page,
            base_url=state.base_url,
            specs=_specs_for(state, case),
            run_dir=state.run_dir,
            case_id=case.case_id,
            step_timeout_ms=state.step_timeout_ms,
            screenshot_every_step=state.screenshot_every_step,
        )
        step_results = execute_case_steps(ctx, case.steps)
        page_state = capture_page_state(
            state.page, console_errors,
            _count_for(state, case), _options_for(state, case),
        )
        state.verdicts.append(verify(case, step_results, page_state))

    return state


def _specs_for(state: AgentState, case: TestCase) -> list[ScreenSpec]:
    """이 케이스가 밟는 화면들. 자기 화면이 첫 항목이다.

    흐름 케이스는 여러 화면을 밟으므로 뒤 화면의 요소도 힌트로 찾을 수 있어야
    한다. 자기 화면을 앞에 두는 이유는 라벨이 겹칠 때(로그인과 회원가입의
    '이메일') 자기 화면 것을 쓰게 하기 위해서다.
    """
    own = state.doc.screen_by_id(case.screen_id)
    ordered = [own] if own else []
    if case.flow_id:
        flow = next((f for f in state.doc.flows if f.flow_id == case.flow_id), None)
        if flow:
            for sid in flow.screen_ids:
                screen = state.doc.screen_by_id(sid)
                if screen is not None and screen not in ordered:
                    ordered.append(screen)
    return ordered or list(state.doc.screens)


def _count_for(state: AgentState, case: TestCase) -> Optional[CollectionCount]:
    """건수 검증 케이스면 반복 목록을 센다. 그 외에는 세지 않는다.

    조건부로 세는 이유는 비용이 아니라 의미다. 목록이 없는 화면(로그인 등)에서
    무조건 세면 status=absent 가 모든 케이스의 근거에 붙어, 리포트를 읽는 사람이
    '이 화면에 목록이 없는 게 문제인가' 를 매번 확인해야 한다.

    라벨로 요소를 찾는 이유: 기대값에는 라벨이 담겨 있고(S3 가 다루는 단위가
    라벨이다), 힌트로 넘길 UIElement 는 그 라벨로 되찾는다. element_id 를
    담았다면 여기서 되찾을 필요가 없지만, 그러면 S3 가 라벨과 ID 를 둘 다
    다뤄야 해서 '탐지는 라벨로 한다' 는 규칙이 흐려진다.
    """
    expected = case.expected
    if expected.type != "result_count" or not expected.count_target:
        return None
    hint = next(
        (e for screen in state.doc.screens for e in screen.elements
         if e.label == expected.count_target), None
    )
    return count_items(state.page, expected.count_target, hint)


def _options_for(state: AgentState, case: TestCase) -> Optional[list[str]]:
    """선택 목록 확인 케이스면 화면의 선택 항목을 읽는다. 그 외에는 읽지 않는다.

    _count_for 와 같은 이유로 조건부다. 목록 확인이 아닌 케이스에까지 붙이면
    근거에 늘 선택 항목이 실려, 리포트를 읽는 사람이 그게 뭔지 매번 확인해야 한다.
    """
    expected = case.expected
    if expected.type != "options_present" or not expected.option_target:
        return None
    hint = next(
        (e for screen in state.doc.screens for e in screen.elements
         if e.label == expected.option_target), None
    )
    return read_options(state.page, expected.option_target, hint)


def build_final_report(state: AgentState) -> AgentState:
    """S6 — 판정을 집계해 리포트를 만든다.

    읽는 필드: verdicts, doc, run_id, base_url, pdf_path, llm
    쓰는 필드: report
    """
    state.report = build_report(
        run_id=state.run_id,
        target_url=state.base_url,
        verdicts=state.verdicts,
        doc=state.doc,
        coverage=state.coverage_gaps,
        spec_source=state.pdf_path,
        backend=getattr(state.llm, "name", "") if state.llm else "",
    )
    return state
