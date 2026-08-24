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
from prova.models import (
    CaseSelection,
    ScreenSpec,
    SpecDocument,
    StepResult,
    TestCase,
    TestReport,
    Verdict,
)
from prova.s1_spec_extractor.extractor import extract_document
from prova.s2_case_generator.coverage import coverage_gaps
from prova.s2_case_generator.generator import generate_cases, generate_flow_cases
from prova.s2_case_generator.rule_expander import spec_defects
from prova.s3_grounder.dom_locator import (
    CollectionCount,
    CollectionTexts,
    check_findable,
    collect_item_texts,
    count_items,
    read_options,
    read_placeholders,
)
from prova.s4_executor.playwright_driver import ExecutionContext, execute_case_steps
from prova.s5_verifier.assertion_engine import capture_page_state, verify
from prova.s6_report.report_builder import build_report


@dataclass
class AgentState:
    """파이프라인 전체가 공유하는 상태 (명세서 §4-1).

    **여기 있는 필드는 전부 누군가 읽는다.** '나중에 쓸 것' 을 미리 두지 않는다 —
    점검에서 `heal_count`·`retry_count`·`max_retry` 세 개가 선언만 되어 있었고,
    그중 `heal_count` 는 실행 컨텍스트에 같은 이름의 필드가 따로 있어서 어느
    쪽이 진짜인지 읽는 사람이 알 수 없었다.

    있는 것과 동작하는 것은 다르고, 그 구분을 흐리는 필드는 지운다.
    """

    # 입력
    pdf_path: str
    base_url: str
    run_id: str
    run_dir: Path
    llm: Optional[LLMClient] = None
    # 2차 경로. None 이면 접근성 속성으로 못 찾은 요소는 그대로 탐지 실패다.
    # 기본이 None 인 이유는 ExecutionContext.vlm 과 같다 — 보정은 선택 기능이다.
    vlm: Optional[object] = None
    page: Optional[Page] = None

    # 산출물
    #
    # doc 이 단일 진실이다. 화면 하나짜리 기획서도 screens 가 1개인 SpecDocument 로
    # 담긴다 — 화면 수에 따라 상태 모양이 갈리면 노드마다 분기가 생긴다.
    doc: Optional[SpecDocument] = None
    cases: list[TestCase] = field(default_factory=list)
    # 선택 전 전체 케이스 (생성 순서 그대로).
    #
    # cases 는 자연어 선택 뒤 살아남은 것만 담는다. 그런데 계획 확인 화면은
    # **제외된 것도 제목·화면·규칙과 함께** 보여야 한다 — 사람이 "이 제외가
    # 안전한가" 를 판단하는 자리이므로, 판단이 가장 필요한 행에 정보가 없으면
    # 확인 단계가 형식만 남는다.
    all_cases: list[TestCase] = field(default_factory=list)
    # 기획서에 적혀 있는데 어떤 케이스도 확인하지 않는 것. 판정이 아니라
    # **검증 범위**에 대한 사실이므로 verdicts 와 따로 담는다.
    coverage_gaps: list[str] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    report: Optional[TestReport] = None
    # 자연어 요청으로 케이스를 골랐다면 그 내역. 요청이 없었으면 None 이다.
    selection: Optional[CaseSelection] = None

    # 2차 경로(화면 이미지로 요소 찾기) 제어.
    #
    # 실제 보정 횟수는 케이스마다 세야 하므로 ExecutionContext 가 갖는다. 여기 있는
    # 것은 그 상한값이다.
    max_heal: int = 2
    #: 2차 경로가 받아들일 최소 신뢰도 (grounding.vlm_confidence_threshold)
    min_confidence: float = 0.5

    # 실행 설정
    step_timeout_ms: int = 10000
    screenshot_every_step: bool = True

    # 화면이 기대 상태에 도달하기를 기다리는 상한.
    #
    # 실물 웹앱은 제출하면 fetch 를 보내고 응답이 오면 화면을 갈아 끼운다. 그 사이
    # 화면에는 아무것도 없다. 클릭 직후 DOM 을 읽으면 그 빈 상태를 보고 '기획서가
    # 지정한 에러가 안 뜬다' 로 판정한다 — 구현이 올바른데 FAIL 이 나는 오탐이다.
    #
    # 0 으로 두면 기다리지 않는다(예전 동작).
    settle_timeout_ms: int = 2000


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
        cases.extend(generate_cases(screen, llm=state.llm, doc=state.doc))
    if all(s.source_kind == "document" for s in state.doc.screens):
        cases.extend(generate_flow_cases(state.doc))
    # figma 출처가 섞이면 흐름 케이스를 만들지 않는다 — 도착을 판정할
    # 근거(문구·경로)가 figma 에 없다. 흐름 자체는 doc.flows 에 추출돼
    # 리포트가 '추출했으나 검증하지 않음' 을 말할 수 있다.
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
        if case.precondition_unmet:
            # 전제(로그인)를 세울 스텝 자체를 만들지 못한 케이스다
            # (TestCase.precondition_unmet 설명 참고). 브라우저로 실행하면
            # 로그인 없이 본 스텝이 돌아 element_not_found 등으로 오분류되므로,
            # 아예 실행하지 않고 여기서 곧바로 precondition_failed 로 판정한다.
            state.verdicts.append(_precondition_unmet_verdict(state, case))
            continue
        # 케이스 격리 — 앞 케이스가 남긴 세션이 다음 판정을 오염시키지 않게 한다.
        # 가드 케이스(비로그인 전제)가 실행 순서와 무관하게 정직해지고, 전제가
        # 있는 케이스는 어차피 setup 으로 매번 로그인한다 — storage_state 를
        # 기본으로 채택하지 않은 스펙 §7 과 같은 판단이다.
        state.page.context.clear_cookies()
        ctx = ExecutionContext(
            page=state.page,
            base_url=state.base_url,
            specs=_specs_for(state, case),
            run_dir=state.run_dir,
            case_id=case.case_id,
            step_timeout_ms=state.step_timeout_ms,
            screenshot_every_step=state.screenshot_every_step,
            vlm=state.vlm,
            max_heal=state.max_heal,
            min_confidence=state.min_confidence,
        )
        step_results = _run_case_steps(ctx, case)
        state.verdicts.append(
            _verify_when_ready(state, case, step_results, console_errors))

    return state


def _precondition_unmet_verdict(state: AgentState, case: TestCase) -> Verdict:
    """실행 없이 precondition_failed 를 합성한다 (TestCase.precondition_unmet).

    ## 왜 실행하지 않는가

    setup_steps 가 비어 있으므로 그대로 두면 본 스텝이 로그인 없이 돈다.
    입력이야 채워지겠지만 제출은 인증되지 않은 상태로 처리되고, 그 결과가
    구현 결함 때문인지 전제가 없어서인지 구분할 수 없는 잡음이 된다. 그래서
    아예 실행하지 않는다 — '실행하지 않았음' 을 사유에 명시해, 이 FAIL 이
    화면을 조작해 본 결과가 아니라는 사실이 리포트에서 드러나게 한다.

    ## 사유를 어디서 가져오는가

    generator.generate_cases 가 expand_precondition 의 경고를 이미
    spec.warnings 에 남겨 뒀다(예: "로그인 화면(login)에서 이메일/비밀번호/
    제출 요소를 찾지 못해 전제 스텝을 만들지 못했습니다."). 그 문장을 다시
    찾아 쓴다 — 같은 사실을 두 곳에 다른 말로 적으면 언젠가 어긋난다.
    """
    screen = state.doc.screen_by_id(case.screen_id) if state.doc else None
    reason = next(
        (w for w in (screen.warnings if screen else [])
         if "전제 스텝을 만들지 못했습니다" in w),
        "전제 스텝을 만들지 못했습니다 (사유 미상)",
    )
    detail = f"전제(로그인)를 세울 수 없어 실행하지 않았습니다 — {reason}"
    return Verdict(
        case_id=case.case_id, title=case.title, type=case.type,
        screen_id=case.screen_id, flow_id=case.flow_id,
        violates=case.violates, target_element=case.target_element,
        verdict="FAIL",
        failure_category="precondition_failed",
        failure_detail=detail,
        evidence={"actual": detail},
        elapsed_ms=0,
        step_results=[],
    )


def _run_case_steps(ctx: ExecutionContext, case: TestCase) -> list[StepResult]:
    """전제(setup_steps)를 먼저 세운 뒤 본 스텝(steps)을 실행한다 (명세서 §3-6).

    같은 ExecutionContext 를 그대로 이어 쓴다 — 로그인 같은 전제는 브라우저의
    실제 페이지 상태(로그인된 세션, 이동한 URL)를 만드는 것이 목적이라, 별도
    컨텍스트로 실행하면 그 상태가 본 스텝으로 넘어가지 않는다.

    전제가 실패하면 본 스텝은 아예 실행하지 않는다. 로그인이 안 된 채로 이어
    스텝을 실행해 봐야 그 결과는 '전제가 없어서 안 됨' 과 구분되지 않는 잡음이다.
    판정(FAIL, category=precondition_failed)은 S5(verify)가 결정한다 — 여기서는
    phase 만 표시해 넘긴다.

    ## 스크린샷 파일명 충돌을 피하는 방법

    `execute_case_steps` 는 스텝의 스크린샷·DOM 스냅샷 파일명을 `TestStep.seq`
    로만 정한다(`step{seq}.png`, playwright_driver._capture 참고). setup_steps 와
    steps 는 각각 1부터 번호를 매기므로, 같은 case_dir 에 두 번 이어 실행하면
    본 스텝이 전제 스텝의 파일을 덮어써 증거가 사라진다.

    playwright_driver.py 는 이 작업의 수정 범위 밖이라 `_capture` 를 건드릴 수
    없다. 대신 case_dir 이 `ctx.case_id` 로부터 나온다는 점을 이용해, 전제를
    실행하는 동안만 `ctx.case_id` 에 접미사를 붙여 별도 폴더에 쌓이게 한다.
    같은 ExecutionContext 객체를 계속 쓰므로(브라우저 페이지·보정 횟수 등은
    그대로 유지) '같은 컨텍스트로 이어 실행한다' 는 설계와 어긋나지 않는다.
    """
    if not case.setup_steps:
        return execute_case_steps(ctx, case.steps)

    original_case_id = ctx.case_id
    ctx.case_id = f"{original_case_id}__setup"
    try:
        setup_results = execute_case_steps(ctx, case.setup_steps)
    finally:
        ctx.case_id = original_case_id
    for r in setup_results:
        r.phase = "setup"

    if any(r.status == "error" for r in setup_results):
        return setup_results

    test_results = execute_case_steps(ctx, case.steps)
    return setup_results + test_results


def _verify_when_ready(
    state: AgentState,
    case: TestCase,
    step_results: list,
    console_errors: list[str],
):
    """화면이 기대 상태에 도달할 때까지 기다렸다가 판정한다.

    ## 왜 기다려야 하는가 — 실측으로 확인한 오탐

    지금까지는 스텝이 끝나면 곧바로 DOM 을 읽고 판정했다. SUT 가 동기식 폼 POST 라
    응답 HTML 에 결과가 이미 들어 있어서 통했다. **실물 웹앱은 대개 그렇지 않다** —
    제출하면 fetch 를 보내고, 응답이 오면 화면을 갈아 끼운다. 그 사이 화면에는
    아무것도 없다.

    검증 로직이 `good` 과 한 줄도 다르지 않고 렌더 시점만 400ms 늦춘 `slow` 변형으로
    재 봤더니 **오탐 7건**이 났다. 그리고 실패 사유가 이렇게 나왔다.

        기획서에 적힌 'password' 의 'require_uppercase' 검증 규칙이 구현에서
        확인되지 않았습니다. (에러가 전혀 노출되지 않음 — 구현이 이 규칙을
        강제하지 않는다)

    구현은 그 규칙을 강제한다. **도구가 못 기다린 것을 구현 결함으로 단정했다.**

    ## 왜 'DOM 이 안정될 때까지' 가 아닌가

    그쪽이 판정과 독립적이라 더 깔끔해 보였다. 그런데 성립하지 않는다 — 400ms 뒤에
    렌더하는 화면은 그 전 250ms 동안 아무 변화가 없고, 그 정적을 '안정됐다' 로 읽는다.
    **아직 시작하지 않은 것과 끝난 것을 구분할 수 없다.**

    그래서 기대를 알고 기다린다. 판정이 통과하면 그때 멈추고, 통과하지 않으면 상한까지
    기다린 뒤 그 판정을 그대로 쓴다.

    ## 이 대기가 판정을 무르게 만들지 않는가

    한 방향으로만 바꾼다 — FAIL 을 PASS 로 바꿀 수 있고 그 반대는 없다. 그래서 두 가지를
    지킨다.

    - **상한이 있다.** 상한을 넘으면 마지막 판정을 그대로 보고한다. 통과할 때까지
      무한정 기다리지 않는다.
    - **기다린 시간을 근거에 남긴다.** 380ms 를 기다려 통과한 케이스는 '그 화면이
      결과를 늦게 보여준다' 는 사실을 담고 있다. 그걸 지우면 편의가 사실을 덮는다 —
      2차 경로의 `healed` 를 남기는 것과 같은 이유다.

    ## 스텝이 끊긴 케이스는 기다리지 않는다

    요소를 못 찾아 스텝이 실패한 케이스는 기다려도 달라지지 않는다. 그런데도 기다리면
    진짜로 깨진 케이스마다 상한만큼 시간을 버린다.
    """
    interval_ms = 100

    def judge():
        page_state = capture_page_state(
            state.page, console_errors,
            _count_for(state, case), _options_for(state, case),
            _placeholders_for(state, case), _findable_for(state, case),
            _texts_for(state, case),
        )
        return verify(case, step_results, page_state)

    verdict = judge()
    broke = any(r.status != "ok" for r in step_results)
    if broke or state.settle_timeout_ms <= 0:
        return verdict

    # 금지 문구(text_absent)는 기다리는 방향이 반대다.
    #
    # 다른 판정은 '있어야 할 것' 을 보므로 나타날 때까지 기다리고, 나타나면 멈춘다.
    # 금지 문구는 '없어야 할 것' 을 본다 — 첫 판정에서 통과했다고 멈추면 400ms 뒤에
    # 나타나는 문구를 **못 본다.** 비동기로 렌더하는 화면에서 계정 존재 여부 노출을
    # 놓치는 것이고, 대기를 넣은 것 때문에 새로 생기는 미탐이다.
    #
    # 그래서 이 판정만 창 전체를 감시하고 FAIL 이 나오는 순간 멈춘다. 나타나지
    # 않으면 상한까지 기다린 뒤 통과다.
    watching_for_leak = case.expected.type == "text_absent"
    if verdict.verdict == ("FAIL" if watching_for_leak else "PASS"):
        return verdict

    waited = 0
    while waited < state.settle_timeout_ms:
        state.page.wait_for_timeout(interval_ms)
        waited += interval_ms
        verdict = judge()
        if watching_for_leak:
            if verdict.verdict == "FAIL":
                # 늦게 나타난 것 자체가 정보다 — 즉시 노출과 구별된다.
                verdict.evidence["appeared_after_ms"] = waited
                return verdict
        elif verdict.verdict == "PASS":
            verdict.evidence["settled_ms"] = waited
            return verdict
    return verdict


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


def _texts_for(state: AgentState, case: TestCase) -> Optional[dict[str, CollectionTexts]]:
    """정렬·합계 검증 케이스면 필요한 라벨의 반복 목록 텍스트를 모은다.

    _count_for 와 같은 조건부 원칙이다 — 어떤 라벨을 모을지는 케이스 유형이
    정한다. sorted_desc 는 라벨 하나(order_target), sum_matches 는 둘
    (sum_row_target·sum_total_target)이 필요해서 유형별로 갈라 모은다.
    """
    expected = case.expected
    if expected.type == "sorted_desc":
        labels = [expected.order_target] if expected.order_target else []
    elif expected.type == "sum_matches":
        labels = [t for t in (expected.sum_row_target, expected.sum_total_target) if t]
    else:
        return None
    if not labels:
        return None

    out: dict[str, CollectionTexts] = {}
    for label in labels:
        hint = next(
            (e for screen in state.doc.screens for e in screen.elements
             if e.label == label), None
        )
        out[label] = collect_item_texts(state.page, label, hint)
    return out


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


def _placeholders_for(state: AgentState, case: TestCase) -> Optional[dict[str, str]]:
    """안내 문구 확인 케이스면 화면의 placeholder 를 읽는다. 그 외에는 읽지 않는다."""
    if case.expected.type != "placeholders_match" or not case.expected.placeholders:
        return None
    return read_placeholders(state.page, list(case.expected.placeholders))


def _findable_for(state: AgentState, case: TestCase) -> Optional[dict[str, str]]:
    """라벨 탐지 케이스면 라벨별로 찾을 수 있는지 확인한다.

    보정을 쓰지 않는다 — 여기서 보는 것은 '보정 없이 찾을 수 있는가' 이고, 그게
    기획서의 라벨이 구현과 이어져 있는지를 뜻한다.
    """
    if case.expected.type != "labels_findable" or not case.expected.labels:
        return None
    screen = state.doc.screen_by_id(case.screen_id)
    elements = screen.elements if screen else []
    return check_findable(state.page, elements, list(case.expected.labels))


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
        selection=state.selection,
    )
    return state
