"""1차 파이프라인 — 노드를 순서대로 부른다.

LangGraph 없이 S1 -> S2 -> (S3+S4+S5) -> S6 를 관통시킨다. 노드가 이미
(state) -> state 시그니처이므로, 이 파일은 순서를 정하는 얇은 층에 불과하다.
M6 에서 graph.py 가 같은 노드들을 StateGraph 로 재조립하고, 두 실행 경로가
같은 리포트를 내는지 대조한다.

## 브라우저 수명 관리

Playwright 는 컨텍스트 매니저로 열고 닫아야 프로세스가 남지 않는다. 그 관리를
파이프라인이 맡고, 노드는 이미 열린 Page 를 받는다. 노드가 브라우저를 직접
열면 케이스마다 브라우저가 뜨고 지는 비용이 생기고, 테스트에서 노드만 떼어
호출하기도 어려워진다.
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


def run_pipeline(
    pdf_path: str,
    base_url: str,
    llm: LLMClient,
    run_id: str,
    runs_root: Path = Path("runs"),
    headless: bool = True,
    viewport: Optional[dict] = None,
    step_timeout_ms: int = 10000,
    on_progress=None,
) -> tuple[TestReport, Path]:
    """설계 문서 하나로 검증을 끝까지 수행하고 리포트를 저장한다.

    Returns:
        (TestReport, 리포트가 저장된 디렉터리)
    """
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    state = AgentState(
        pdf_path=pdf_path,
        base_url=base_url,
        run_id=run_id,
        run_dir=run_dir,
        llm=llm,
        step_timeout_ms=step_timeout_ms,
    )

    # --- S1: 설계 문서 -> ScreenSpec (브라우저 없이 가능) ---
    progress("S1 설계 문서 추출")
    state = extract_spec(state)
    progress(f"     화면 '{state.spec.screen_name}' · 요소 {len(state.spec.elements)}개")

    # --- S2: ScreenSpec -> TestCase[] ---
    progress("S2 테스트 케이스 생성")
    state = generate_test_cases(state)
    n_neg = sum(1 for c in state.cases if c.type == "negative")
    progress(f"     케이스 {len(state.cases)}개 (정상 {len(state.cases) - n_neg} · 위반 {n_neg})")

    # --- S3~S5: 실행과 판정 (브라우저 필요) ---
    progress("S3~S5 브라우저 실행 및 판정")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport=viewport or {"width": 1280, "height": 800})
        state.page = context.new_page()
        try:
            state = run_cases(state)
        finally:
            # 판정이 중간에 실패해도 브라우저를 반드시 닫는다.
            context.close()
            browser.close()
            state.page = None

    # --- S6: 리포트 ---
    progress("S6 리포트 생성")
    state = build_final_report(state)
    save_json(state.report, run_dir)
    save_html(state.report, run_dir)

    return state.report, run_dir
