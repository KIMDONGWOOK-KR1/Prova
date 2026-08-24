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

import time
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
from prova.s2_case_generator.selector import select_by_ids, select_cases
from prova.s6_report.report_builder import save_html, save_json


def filter_cases(cases: list, pattern: Optional[str]) -> list:
    """case_id 에 pattern 이 든 케이스만 남긴다.

    한 케이스만 골라 실행하는 용도다 — 데모 녹화를 짧게 만들 때, 그리고 개발 중 특정
    케이스만 재현할 때 쓴다.

    **아무 케이스도 고르지 못하면 예외를 던진다.** 빈 목록으로 진행하면 "전 케이스 통과,
    통과율 100%" 리포트가 나오는데 실제로는 아무것도 검증하지 않은 상태가 된다. QA 도구에서
    그건 가장 위험한 결과다.
    """
    if not pattern:
        return cases
    picked = [c for c in cases if pattern in c.case_id]
    if not picked:
        available = ", ".join(c.case_id for c in cases)
        raise ValueError(
            f"'{pattern}' 에 해당하는 케이스가 없습니다.\n  실행 가능한 케이스: {available}"
        )
    return picked


def build_plan(
    pdf_path: str,
    base_url: str,
    llm: LLMClient,
    run_id: str = "plan",
    run_dir: Optional[Path] = None,
    only: Optional[str] = None,
    request: Optional[str] = None,
    case_ids: Optional[list[str]] = None,
    reason: str = "",
    figma_json: Optional[str] = None,
    screen_urls: Optional[dict[str, str]] = None,
    on_progress=None,
    **state_kwargs,
) -> tuple[AgentState, int]:
    """브라우저를 열지 않고 S1~S2 와 케이스 선택까지만 수행한다.

    ## 왜 떼어냈는가

    UI 의 계획 확인 단계 때문이다. 사람이 "무엇을 테스트할지" 를 먼저 보고
    승인해야 하는데, 그러려면 브라우저를 열기 전에 케이스 목록이 나와야 한다.
    S1~S2 는 원래 브라우저가 필요 없으므로 경계가 이미 거기에 있었다.

    `run_pipeline` 도 이 함수를 쓴다. 계획 화면이 보는 목록과 실제로 실행되는
    목록이 **같은 코드에서 나와야** 사람이 승인한 것과 도는 것이 어긋나지 않는다.

    Args:
        case_ids: 사람이 승인한 목록. 주면 요청 해석(LLM 호출)을 건너뛴다 —
            승인 시점과 실행 시점 사이에 모델의 답이 달라지면 승인한 것과
            다른 것이 돌게 된다.
        reason: 계획 단계에서 모델이 밝힌 근거. case_ids 와 함께 넘겨 리포트에 남긴다.

    Returns:
        (선택까지 끝난 상태, 선택 전 전체 케이스 수)
    """
    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    state = AgentState(
        pdf_path=pdf_path,
        base_url=base_url,
        run_id=run_id,
        run_dir=run_dir if run_dir is not None else Path("runs") / run_id,
        llm=llm,
        figma_json=figma_json,
        screen_urls=screen_urls or {},
        **state_kwargs,
    )

    # --- S1: 설계 문서 -> ScreenSpec (브라우저 없이 가능) ---
    progress("S1 설계 문서 추출")
    state = extract_spec(state)
    for screen in state.doc.screens:
        progress(f"     화면 '{screen.screen_name}' · 요소 {len(screen.elements)}개")
    if state.doc.flows:
        progress(f"     흐름 {len(state.doc.flows)}개")

    # --- S2: ScreenSpec -> TestCase[] ---
    progress("S2 테스트 케이스 생성")
    state = generate_test_cases(state)
    n_all = len(state.cases)
    n_neg = sum(1 for c in state.cases if c.type == "negative")
    n_flow = sum(1 for c in state.cases if c.flow_id)
    progress(f"     케이스 {n_all}개 (정상 {n_all - n_neg - n_flow} · 위반 {n_neg}"
             + (f" · 흐름 {n_flow}" if n_flow else "") + ")")

    # 선택·필터로 잃기 전에 원본을 붙들어 둔다. 계획 화면이 제외된 케이스를
    # 제목·화면·규칙과 함께 보여주려면 본문이 필요하다. --only 보다 **앞**에
    # 잡는다 — 뒤에 잡으면 n_all(전체 수)과 all_cases(필터 후 목록)가 같은
    # 응답에서 어긋난다.
    state.all_cases = list(state.cases)

    state.cases = filter_cases(state.cases, only)
    if only:
        progress(f"     필터 '{only}' → {len(state.cases)}개만 실행")

    # 케이스를 좁히는 자리. 여기가 **미탐을 만들 수 있는 유일한 자리**이므로
    # 무엇을 왜 뺐는지를 state.selection 에 담아 리포트까지 실어 보낸다.
    if case_ids is not None:
        state.cases, state.selection = select_by_ids(
            state.cases, case_ids, request=(request or "").strip(), reason=reason,
            doc=state.doc,
        )
        progress(f"     승인 목록 → {len(state.selection.selected)}개 실행"
                 + (f" (제외 {len(state.selection.excluded)}개)"
                    if state.selection.excluded else ""))
    else:
        state.cases, state.selection = select_cases(
            state.cases, request, llm, doc=state.doc
        )
        sel = state.selection
        if sel.request:
            if sel.fallback:
                progress(f"     요청 '{sel.request}' 해석 실패 → 전체 {len(state.cases)}개 실행")
            else:
                progress(f"     요청 '{sel.request}' → {len(sel.selected)}개 실행"
                         + (f" (제외 {len(sel.excluded)}개)" if sel.excluded else ""))
    for w in state.selection.warnings:
        progress(f"     ! {w}")

    return state, n_all


def run_pipeline(
    pdf_path: str,
    base_url: str,
    llm: LLMClient,
    run_id: str,
    vlm: Optional[object] = None,
    runs_root: Path = Path("runs"),
    headless: bool = True,
    viewport: Optional[dict] = None,
    step_timeout_ms: int = 10000,
    settle_timeout_ms: int = 2000,
    screenshot_every_step: bool = True,
    max_heal: int = 2,
    min_confidence: float = 0.5,
    slow_mo: int = 0,
    record_video: bool = False,
    only: Optional[str] = None,
    request: Optional[str] = None,
    case_ids: Optional[list[str]] = None,
    reason: str = "",
    hold_sec: float = 0.0,
    figma_json: Optional[str] = None,
    screen_urls: Optional[dict[str, str]] = None,
    on_progress=None,
) -> tuple[TestReport, Path]:
    """설계 문서 하나로 검증을 끝까지 수행하고 리포트를 저장한다.

    Args:
        slow_mo: 동작 사이 지연(ms). 사람이 눈으로 따라가려면 400~600 정도가 적당하다.
        record_video: 실행 영상(webm) 녹화. run_dir/video/ 에 저장된다.
        vlm: 2차 경로 백엔드. None 이면 접근성 속성으로 못 찾은 요소는 그대로
            탐지 실패다. 기본을 None 으로 둔 이유: 보정을 기본으로 켜면 라벨
            연결이 깨진 화면에서도 케이스가 통과해 그 사실이 리포트에서 사라진다.
        only: case_id 에 이 문자열이 든 케이스만 실행 (filter_cases 참고).
        request: 사용자의 자연어 요청. 주면 이 요청에 해당하는 케이스만 실행하고
            무엇을 왜 제외했는지 리포트에 남긴다 (select_cases 참고). None 이면
            지금까지와 같이 전체를 실행한다.
        case_ids: 사람이 승인한 case_id 목록. 주면 요청 해석을 다시 하지 않고
            이 목록으로 좁힌다 (select_by_ids 참고). UI 의 계획 확인 단계가
            돌려주는 값이다.
        hold_sec: 마지막 케이스가 끝난 뒤 브라우저를 닫기 전 기다릴 초.
            판정의 근거가 되는 마지막 화면(에러 문구)을 사람이 읽을 시간을 준다.
            --headed 로 지켜볼 때만 의미가 있다.

    Returns:
        (TestReport, 리포트가 저장된 디렉터리)
    """
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    state, n_all = build_plan(
        pdf_path=pdf_path,
        base_url=base_url,
        llm=llm,
        run_id=run_id,
        run_dir=run_dir,
        only=only,
        request=request,
        case_ids=case_ids,
        reason=reason,
        figma_json=figma_json,
        screen_urls=screen_urls,
        vlm=vlm,
        step_timeout_ms=step_timeout_ms,
        settle_timeout_ms=settle_timeout_ms,
        screenshot_every_step=screenshot_every_step,
        max_heal=max_heal,
        min_confidence=min_confidence,
        on_progress=on_progress,
    )

    # --- S3~S5: 실행과 판정 (브라우저 필요) ---
    progress("S3~S5 브라우저 실행 및 판정")
    video_path: Optional[Path] = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(
            viewport=viewport or {"width": 1280, "height": 800},
            # 녹화 크기를 뷰포트보다 작게 잡는다. 1280x800 으로 녹화하면 webm 이 커지고
            # GIF 로 변환한 뒤 용량이 감당되지 않는다.
            record_video_dir=str(run_dir / "video") if record_video else None,
            record_video_size={"width": 960, "height": 600} if record_video else None,
        )
        page = context.new_page()
        state.page = page
        try:
            state = run_cases(state)
            if hold_sec > 0:
                # 마지막 클릭 직후 브라우저가 닫히면 정작 봐야 하는 화면(에러 문구)을
                # 놓친다. 지켜보는 사람을 위해 잠시 남겨 둔다.
                progress(f"     마지막 화면을 {hold_sec:g}초 유지합니다")
                time.sleep(hold_sec)
        finally:
            # 판정이 중간에 실패해도 브라우저를 반드시 닫는다.
            # 영상은 컨텍스트를 닫는 시점에 파일로 기록되므로, 경로 조회는 close() 뒤에
            # 해야 한다.
            context.close()
            if record_video and page.video:
                try:
                    video_path = Path(page.video.path())
                except Exception:
                    video_path = None
            browser.close()
            state.page = None

    if video_path and video_path.exists():
        progress(f"     영상 {video_path} ({video_path.stat().st_size // 1024} KB)")

    # --- S6: 리포트 ---
    progress("S6 리포트 생성")
    state = build_final_report(state)
    if only:
        # 부분 실행 결과를 전체 결과로 착각하지 않도록 리포트에 남긴다.
        state.report.summary["filtered_by"] = only
        state.report.summary["cases_available"] = n_all
    save_json(state.report, run_dir)
    save_html(state.report, run_dir)

    return state.report, run_dir
