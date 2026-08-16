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
from prova.models import ScreenSpec, TestCase, TestReport, Verdict
from prova.s1_spec_extractor.extractor import extract_from_pdf
from prova.s2_case_generator.generator import generate_cases
from prova.s2_case_generator.rule_expander import spec_defects
from prova.s3_grounder.dom_locator import CollectionCount, count_items
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
    spec: Optional[ScreenSpec] = None
    cases: list[TestCase] = field(default_factory=list)
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
    """S1 — PDF 에서 ScreenSpec 을 추출한다.

    읽는 필드: pdf_path, llm
    쓰는 필드: spec
    """
    if state.llm is None:
        raise ValueError("extract_spec 에는 LLM 백엔드가 필요합니다")

    state.spec = extract_from_pdf(state.pdf_path, state.llm)

    # 기획서 내부 모순을 여기서 걸러 리포트로 올린다. 구현 결함이 아니라 기획
    # 결함이므로, 케이스 FAIL 이 아니라 경고로 알리는 것이 맞다.
    state.spec.warnings.extend(spec_defects(state.spec))
    return state


def generate_test_cases(state: AgentState) -> AgentState:
    """S2 — ScreenSpec 을 TestCase 목록으로 전개한다.

    읽는 필드: spec, llm
    쓰는 필드: cases
    """
    if state.spec is None:
        raise ValueError("generate_test_cases 전에 extract_spec 이 실행돼야 합니다")
    state.cases = generate_cases(state.spec, llm=state.llm)
    return state


def run_cases(state: AgentState) -> AgentState:
    """S3+S4+S5 — 케이스를 실행하고 판정한다.

    읽는 필드: cases, spec, page, base_url, run_dir
    쓰는 필드: verdicts

    한 케이스가 실패해도 다음 케이스를 계속 실행한다. 한 번 돌려서 전체 상태를
    파악할 수 있어야 리포트가 쓸모 있기 때문이다(명세서 §2-S6 실패 처리).

    LangGraph 로 옮길 때는 이 노드가 케이스 단위 루프(ground -> execute ->
    verify -> next_case)로 펼쳐진다. 1차에서는 self-heal 분기가 없어 루프를
    노드로 쪼갤 이득이 없으므로 한 노드에 담는다.
    """
    if state.page is None or state.spec is None:
        raise ValueError("run_cases 에는 page 와 spec 이 필요합니다")

    console_errors: list[str] = []
    state.page.on("console", lambda msg: (
        console_errors.append(msg.text) if msg.type == "error" else None
    ))

    for case in state.cases:
        console_errors.clear()
        ctx = ExecutionContext(
            page=state.page,
            base_url=state.base_url,
            spec=state.spec,
            run_dir=state.run_dir,
            case_id=case.case_id,
            step_timeout_ms=state.step_timeout_ms,
            screenshot_every_step=state.screenshot_every_step,
        )
        step_results = execute_case_steps(ctx, case.steps)
        page_state = capture_page_state(
            state.page, console_errors, _count_for(state, case)
        )
        state.verdicts.append(verify(case, step_results, page_state))

    return state


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
        (e for e in state.spec.elements if e.label == expected.count_target), None
    )
    return count_items(state.page, expected.count_target, hint)


def build_final_report(state: AgentState) -> AgentState:
    """S6 — 판정을 집계해 리포트를 만든다.

    읽는 필드: verdicts, spec, run_id, base_url, pdf_path, llm
    쓰는 필드: report
    """
    state.report = build_report(
        run_id=state.run_id,
        target_url=state.base_url,
        verdicts=state.verdicts,
        spec=state.spec,
        spec_source=state.pdf_path,
        backend=getattr(state.llm, "name", "") if state.llm else "",
    )
    return state
