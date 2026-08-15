"""LangGraph 조립 — pipeline.py 와 같은 노드를 StateGraph 로 배선한다.

## 이식 비용이 거의 0인 이유

nodes.py 의 함수들이 처음부터 (state) -> state 시그니처를 갖고 있다. LangGraph
노드가 정확히 그 모양이므로 add_node(이름, 함수) 로 끝난다. 함수 본문은 한 줄도
고치지 않았다. 이것이 'LangGraph 를 관통 이후로 미루자' 는 판단을 값싸게 만든
유일한 조건이었다.

## 1차에서 그래프가 파이프라인보다 나은 점이 아직 없다

지금 그래프는 선형이다(extract -> generate -> run -> report). 조건 분기도
루프도 없으므로, 실행 결과는 pipeline.py 와 동일해야 한다. 그 동일성을 테스트로
고정해 두는 것이 이 파일의 현재 가치다 — 2차에서 self_heal 분기를 추가할 때,
리포트가 달라지면 그것이 분기 때문인지 배선 실수 때문인지 가릴 수 있다.

## 2차에서 여기에 붙을 것 (명세서 §4-3)

    ground_element --조건--> execute_step        (탐지 성공)
                   --조건--> self_heal           (탐지 실패)
    self_heal      --조건--> ground_element      (heal_count < max_heal)
                   --조건--> classify_failure    (한도 초과)

그때 run_cases 노드가 케이스·스텝 단위 루프로 펼쳐진다. 지금 한 노드에 담아둔
이유는 1차에 분기가 없어서 쪼갤 이득이 없기 때문이다. AgentState 에 heal_count /
max_heal 필드를 미리 둔 것은 그 확장에서 상태 구조가 흔들리지 않게 하기 위한
것이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from prova.llm.base import LLMClient
from prova.models import TestReport
from prova.nodes import (
    AgentState,
    build_final_report,
    extract_spec,
    generate_test_cases,
    run_cases,
)
from prova.s6_report.report_builder import save_html, save_json


def build_graph():
    """S1 -> S2 -> (S3+S4+S5) -> S6 선형 그래프를 만든다.

    상태 타입으로 dataclass 인 AgentState 를 그대로 쓴다. LangGraph 는 TypedDict
    와 dataclass 를 모두 받고, 노드가 상태를 제자리에서 갱신해 반환하므로
    리듀서를 따로 지정할 필요가 없다.
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("extract_spec", extract_spec)
    graph.add_node("generate_cases", generate_test_cases)
    graph.add_node("run_cases", run_cases)
    graph.add_node("build_report", build_final_report)

    graph.add_edge(START, "extract_spec")
    graph.add_edge("extract_spec", "generate_cases")
    graph.add_edge("generate_cases", "run_cases")
    graph.add_edge("run_cases", "build_report")
    graph.add_edge("build_report", END)

    return graph.compile()


def run_graph(
    pdf_path: str,
    base_url: str,
    llm: LLMClient,
    run_id: str,
    runs_root: Path = Path("runs"),
    headless: bool = True,
    viewport: Optional[dict] = None,
    step_timeout_ms: int = 10000,
) -> tuple[TestReport, Path]:
    """그래프로 파이프라인을 실행한다. run_pipeline 과 같은 결과를 내야 한다.

    브라우저 수명은 여기서 관리한다. 노드가 브라우저를 직접 열면 그래프를 부분
    실행하거나 노드를 단위 테스트하기 어려워진다.
    """
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state = AgentState(
        pdf_path=pdf_path,
        base_url=base_url,
        run_id=run_id,
        run_dir=run_dir,
        llm=llm,
        step_timeout_ms=step_timeout_ms,
    )

    app = build_graph()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport=viewport or {"width": 1280, "height": 800})
        state.page = context.new_page()
        try:
            result = app.invoke(state)
        finally:
            context.close()
            browser.close()

    # LangGraph 는 상태를 dict 로 돌려준다. 노드가 같은 객체를 갱신했으므로
    # 값은 동일하지만, 타입을 되살려 호출자가 TestReport 를 그대로 쓰게 한다.
    report = result["report"] if isinstance(result, dict) else result.report
    if report is None:
        raise RuntimeError("그래프 실행이 리포트를 만들지 못했습니다")

    save_json(report, run_dir)
    save_html(report, run_dir)
    return report, run_dir
