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
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import sync_playwright

from prova.history import attach_history
from prova.llm.base import LLMClient
from prova.llm.cache import CachedLLM
from prova.models import SpecDocument, TestReport
from prova.spec_edits import settle
from prova.nodes import (
    AgentState,
    build_final_report,
    extract_spec,
    finish_titles,
    generate_test_cases,
    note_viewport,
    page_opener,
    run_cases,
)
from prova.plan_store import load_plan, plan_warnings, save_plan
from prova.s2_case_generator.selector import select_by_ids, select_cases
from prova.s6_report.report_builder import save_html, save_json


def strip_screen_path(base_url: str, doc) -> tuple[str, Optional[str]]:
    """대상 URL 끝에 기획서의 화면 경로가 붙어 있으면 떼어 낸다.

    도구는 기획서의 화면 경로(`/login`)를 대상 URL 뒤에 붙인다. 브라우저 주소창의
    `http://.../bad/login` 을 그대로 넣으면 `/bad/login/login` 을 열어 404 가
    나고 케이스가 전부 첫 스텝에서 멈춘다(2026-09-23 실제로 20건).

    떼는 것은 **경로 단위로 정확히 끝이 같을 때**뿐이다 — `/mylogin` 은 `/login`
    이 아니다. 화면 경로가 여럿이면 긴 것부터 본다(`/orders/list` 가 `/list` 보다
    먼저). 무엇을 뗐는지 돌려주고, 부르는 쪽이 그 사실을 남긴다.

    Returns:
        (고친 URL, 뗀 경로 또는 None)
    """
    parts = urlsplit(base_url)
    path = parts.path.rstrip("/")
    candidates = sorted({(s.url_path or "").rstrip("/") for s in doc.screens},
                        key=len, reverse=True)
    for screen_path in candidates:
        if screen_path.startswith("/") and path.endswith(screen_path):
            fixed = urlunsplit((parts.scheme, parts.netloc,
                                path[: -len(screen_path)], parts.query, ""))
            return fixed, screen_path
    return base_url, None


def _quiet(_message: str) -> None:
    """진행 보고를 받을 곳이 없을 때 쓴다."""


@contextmanager
def _run_log(run_dir: Path, on_progress=None, fresh: bool = True):
    """진행 메시지를 터미널·화면으로 보내면서 run_dir/run.log 에도 남긴다.

    터미널 출력은 창을 닫으면 사라지고, 웹 UI 의 진행 줄은 다음 실행에 밀려난다.
    '그때 무슨 일이 있었나' 를 나중에 물을 수 있어야 실행 기록이다. 그래서 한 줄씩
    바로 쓴다 — 도중에 죽은 실행이야말로 로그가 필요한 실행이다. 같은 이유로 예외도
    남기고 그대로 다시 던진다.

    Args:
        fresh: 같은 이름으로 다시 돌린 실행이면 옛 로그를 지운다. 재개(--resume)는
            계획 단계의 로그에 이어 쓴다.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run.log"
    if fresh:
        path.write_text("", encoding="utf-8")

    def write(message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        with path.open("a", encoding="utf-8") as out:
            out.write(f"{stamp} {message}\n")

    def progress(message: str) -> None:
        write(message)
        if on_progress:
            on_progress(message)

    try:
        yield progress
    except Exception as exc:
        write(f"! 실행 실패 — {type(exc).__name__}: {exc}")
        raise


def execution_options(cfg: dict, *, headed: bool = False) -> dict:
    """설정 파일에서 실행 조건(S3~S5)을 읽는다. CLI 와 웹 UI 가 함께 쓴다.

    한때 세 곳에 복사돼 있었고 이미 어긋나 있었다(웹 UI 만 bool 변환이 빠짐).
    값의 형을 여기서 맞춘다 — YAML 은 사람이 쓰는 파일이라 "5000" 도 온다.
    """
    exec_cfg = cfg.get("execution", {})
    return dict(
        headless=not headed and bool(exec_cfg.get("headless", True)),
        viewport=exec_cfg.get("viewport"),
        step_timeout_ms=int(exec_cfg.get("step_timeout_ms", 10000)),
        navigation_timeout_ms=int(exec_cfg.get("navigation_timeout_ms", 30000)),
        settle_timeout_ms=int(exec_cfg.get("settle_timeout_ms", 2000)),
        screenshot_every_step=bool(exec_cfg.get("screenshot_every_step", True)),
        max_heal=int(cfg.get("agent", {}).get("max_heal", 2)),
        min_confidence=float(cfg.get("grounding", {}).get("vlm_confidence_threshold", 0.5)),
    )


def configured_workers(cfg: dict) -> int:
    """설정의 병렬 수 (execution.workers). CLI 가 --workers 로 덮어쓴다."""
    workers = int(cfg.get("execution", {}).get("workers", 1))
    if workers < 1:
        raise ValueError(f"execution.workers 는 1 이상이어야 합니다: {workers}")
    return workers


def _check_workers(workers: int, *, storage_state, hold_sec, slow_mo, headless) -> None:
    """병렬과 함께 성립하지 않는 조건을 S1 을 쓰기 전에 막는다."""
    if workers <= 1:
        return
    if storage_state:
        raise ValueError("세션 파일 실행은 병렬로 돌 수 없습니다 — 한 작업자의 로그아웃 "
                         "케이스가 다른 작업자가 쓰는 세션을 끊습니다.")
    if hold_sec or slow_mo or not headless:
        raise ValueError("hold·slow·headed 는 사람이 지켜보는 실행이라 병렬과 함께 쓸 수 "
                         "없습니다.")


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
    doc: Optional[SpecDocument] = None,
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
        doc: 사람이 계획 화면에서 고친 추출 결과(prova.spec_edits). 주면 S1 을 건너뛰고
            이 문서로 S2 부터 돈다 — 기획서를 다시 읽으면 고친 것이 사라진다.

    Returns:
        (선택까지 끝난 상태, 선택 전 전체 케이스 수)
    """
    progress = on_progress or _quiet

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
    if doc is not None:
        progress("S1 사람이 고친 추출 결과를 씁니다 (기획서를 다시 읽지 않음)")
        state.doc = settle(doc.model_copy(deep=True))
    else:
        progress("S1 설계 문서 추출")
        state = extract_spec(state)
    for screen in state.doc.screens:
        progress(f"     화면 '{screen.screen_name}' · 요소 {len(screen.elements)}개")
    if state.doc.flows:
        progress(f"     흐름 {len(state.doc.flows)}개")

    # 대상 URL 에 화면 경로까지 넣은 흔한 실수를 고친다. 조용히 바꾸지 않는다 —
    # 대상 URL 은 판정의 전제라, 바뀐 사실이 리포트에 남아야 한다.
    fixed, removed = strip_screen_path(state.base_url, state.doc)
    if removed:
        state.url_note = (f"대상 URL 끝의 화면 경로 '{removed}' 를 뗐습니다: "
                          f"{state.base_url} → {fixed} (화면 경로는 기획서에서 붙입니다)")
        state.base_url = fixed
        progress(f"     ! {state.url_note}")

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
    navigation_timeout_ms: int = 30000,
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
    storage_state: Optional[str] = None,
    sut_build: str = "",
    project: str = "",
    workers: int = 1,
    on_progress=None,
    doc: Optional[SpecDocument] = None,
    spec_edits: Optional[list[str]] = None,
) -> tuple[TestReport, Path]:
    """설계 문서 하나로 검증을 끝까지 수행하고 리포트를 저장한다.

    Args:
        doc: 사람이 고친 추출 결과 (build_plan 참고). 주면 S1 을 건너뛴다.
        spec_edits: 그 문서가 원래 추출과 다른 점(prova.spec_edits.diff_docs). 리포트에 남는다.
        workers: 동시에 돌릴 브라우저 수. 기본은 1 이다 (_run_parallel 참고).
        project: 실행을 묶을 이름 (납품 건·외주사 등). 차수 계산의 기준이 된다
            (prova.history 참고). 비우면 기획서와 대상 URL 로 묶는다.
        slow_mo: 동작 사이 지연(ms). 사람이 눈으로 따라가려면 400~600 정도가 적당하다.
        record_video: 실행 영상(webm) 녹화. run_dir/video/ 에 케이스마다 하나씩 저장된다
            (세션 모드의 메인 컨텍스트는 하나로 이어진다).
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
    _check_workers(workers, storage_state=storage_state, hold_sec=hold_sec,
                   slow_mo=slow_mo, headless=headless)
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    with _run_log(run_dir, on_progress) as progress:
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
            doc=doc,
            vlm=vlm,
            step_timeout_ms=step_timeout_ms,
            navigation_timeout_ms=navigation_timeout_ms,
            settle_timeout_ms=settle_timeout_ms,
            screenshot_every_step=screenshot_every_step,
            max_heal=max_heal,
            min_confidence=min_confidence,
            sut_build=sut_build,
            on_progress=progress,
        )

        return _execute(
            state,
            run_dir=run_dir,
            n_all=n_all,
            headless=headless,
            viewport=viewport,
            slow_mo=slow_mo,
            record_video=record_video,
            only=only,
            hold_sec=hold_sec,
            storage_state=storage_state,
            project=project,
            workers=workers,
            on_progress=progress,
            spec_edits=spec_edits,
        )


def _browse(
    state: AgentState,
    *,
    headless: bool,
    viewport: Optional[dict],
    slow_mo: int,
    video_dir: Optional[Path],
    hold_sec: float,
    storage_state: Optional[str],
    progress,
) -> AgentState:
    """브라우저 하나를 열어 state.cases 를 돌리고 닫는다."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        # 케이스마다 새 컨텍스트를 연다(run_cases). 가드 케이스는 세션 모드에서도 이쪽이다.
        state.open_page = page_opener(browser, viewport, video_dir)
        if storage_state:
            # 로그인 세션 재사용(--session). 세션이 기준 상태라 이 컨텍스트 하나를 유지한다.
            state.page = state.open_page(storage_state)
            state.storage_state = storage_state
        state.on_progress = progress
        try:
            state = run_cases(state)
            if hold_sec > 0:
                # 마지막 클릭 직후 브라우저가 닫히면 정작 봐야 하는 화면(에러 문구)을
                # 놓친다. 지켜보는 사람을 위해 잠시 남겨 둔다.
                progress(f"     마지막 화면을 {hold_sec:g}초 유지합니다")
                time.sleep(hold_sec)
        finally:
            # 판정이 중간에 실패해도 브라우저를 반드시 닫는다.
            # 영상은 컨텍스트를 닫는 시점에 파일로 기록된다.
            for opened in (state.guard_page, state.page):
                if opened is not None:
                    opened.context.close()
            browser.close()
            state.page = state.guard_page = state.open_page = None
    return state


def _run_parallel(state: AgentState, workers: int, progress, **browser_options) -> AgentState:
    """케이스를 나눠 브라우저 여러 개로 돌리고 판정을 원래 순서로 모은다.

    ## 왜 스레드인가

    실행 시간의 대부분(login bad 86%)이 화면을 기다리는 유휴 시간이라 GIL 이 걸리지
    않는다. 프로세스로 가르면 VLM 클라이언트와 상태를 직렬화해야 한다. Playwright 의
    sync API 는 스레드를 넘어 공유할 수 없으므로 스레드마다 자기 것을 연다.

    ## 왜 기본이 1 인가

    케이스는 브라우저 저장소가 격리돼 있어도 **대상 서버**를 공유한다. SUT 6조합에서는
    판정 차이가 0 이었지만, 계정당 세션 하나만 허용하는 서비스나 장바구니처럼 서버에
    쌓이는 화면은 동시 실행이 판정을 바꾼다. 대상의 성질은 도구가 알 수 없으므로 켜는
    것은 사람이 고르고 리포트가 남긴다. 바꾼 대상에는 순차와 한 번 대조한 뒤 쓴다.
    """
    shards = [state.cases[i::workers] for i in range(workers)]

    def work(index: int) -> list:
        sub = replace(state, cases=shards[index], verdicts=[], page=None,
                      guard_page=None, open_page=None)
        tag = f"     [{index + 1}/{workers}]"
        return _browse(sub, progress=lambda m: progress(f"{tag} {m.strip()}"),
                       **browser_options).verdicts

    progress(f"     병렬 {workers}개로 실행")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        verdicts = [v for done in pool.map(work, range(workers)) for v in done]
    order = {c.case_id: i for i, c in enumerate(state.cases)}
    state.verdicts = sorted(verdicts, key=lambda v: order[v.case_id])
    return state


def _execute(
    state: AgentState,
    *,
    run_dir: Path,
    n_all: int,
    headless: bool = True,
    viewport: Optional[dict] = None,
    slow_mo: int = 0,
    record_video: bool = False,
    only: Optional[str] = None,
    hold_sec: float = 0.0,
    storage_state: Optional[str] = None,
    project: str = "",
    workers: int = 1,
    on_progress=None,
    spec_edits: Optional[list[str]] = None,
) -> tuple[TestReport, Path]:
    """S3~S6 — 계획이 끝난 상태를 받아 브라우저 실행과 리포트를 수행한다.

    run_pipeline(한 번에)과 resume_pipeline(저장된 계획 재개)이 공유한다.
    두 경로가 같은 코드로 실행돼야 "재개한 실행이 한 번에 돌린 실행과 같다"
    는 test_two_stage_e2e 의 계약이 코드 구조로 보장된다.
    """
    progress = on_progress or _quiet

    progress("S3~S5 브라우저 실행 및 판정")
    video_dir = run_dir / "video" if record_video else None
    workers = min(workers, len(state.cases))
    options = dict(headless=headless, viewport=viewport, slow_mo=slow_mo, video_dir=video_dir,
                   hold_sec=hold_sec, storage_state=storage_state)
    if workers > 1:
        state = _run_parallel(state, workers, progress, **options)
    else:
        state = _browse(state, progress=progress, **options)

    if video_dir:
        videos = list(video_dir.glob("*.webm"))
        if videos:
            # 케이스마다 컨텍스트가 달라 영상도 케이스마다 하나다.
            progress(f"     영상 {len(videos)}개 {video_dir} "
                     f"({sum(v.stat().st_size for v in videos) // 1024} KB)")

    # --- S6: 리포트 ---
    progress("S6 리포트 생성")
    state = build_final_report(state)
    if only:
        # 부분 실행 결과를 전체 결과로 착각하지 않도록 리포트에 남긴다.
        state.report.summary["filtered_by"] = only
        state.report.summary["cases_available"] = n_all
    if project:
        state.report.summary["project"] = project
    if workers > 1:
        # 판정의 전제다 — 동시 실행이 판정을 바꿀 수 있다 (_run_parallel).
        state.report.summary["workers"] = workers
    note_viewport(state.report.summary, viewport)
    if spec_edits:
        # 판정 근거의 일부가 기획서가 아니라 사람이 적은 값이다 (prova.spec_edits).
        state.report.summary["spec_edits"] = list(spec_edits)
    if isinstance(state.llm, CachedLLM):
        # 이번에 모델을 돌렸는가도 전제다 (llm/cache.py). 제목까지 거둔 뒤라야 수가 맞다.
        state.report.summary["llm_cache"] = {"hits": state.llm.hits,
                                             "misses": state.llm.misses}
    # 저장하기 전에 붙인다 — 비교 결과도 이 실행의 기록이다 (prova.history).
    attach_history(state.report, run_dir.parent)
    save_json(state.report, run_dir)
    save_html(state.report, run_dir)

    return state.report, run_dir


def plan_pipeline(
    pdf_path: str,
    base_url: str,
    llm: LLMClient,
    run_id: str,
    runs_root: Path = Path("runs"),
    only: Optional[str] = None,
    request: Optional[str] = None,
    figma_json: Optional[str] = None,
    screen_urls: Optional[dict[str, str]] = None,
    on_progress=None,
) -> tuple[AgentState, Path]:
    """S1~S2 만 수행하고 계획을 runs/<id>/plan.json 으로 저장한다 (--plan-only).

    한 GPU 가 7B(추출)와 VL(탐지)을 동시에 싣지 못할 때의 앞 절반이다.
    브라우저를 열지 않으며, 이어지는 절반은 resume_pipeline 이 맡는다.

    Returns:
        (계획이 끝난 상태, plan.json 경로)
    """
    run_dir = runs_root / run_id
    with _run_log(run_dir, on_progress) as progress:
        state, n_all = build_plan(
            pdf_path=pdf_path,
            base_url=base_url,
            llm=llm,
            run_id=run_id,
            run_dir=run_dir,
            only=only,
            request=request,
            figma_json=figma_json,
            screen_urls=screen_urls,
            on_progress=progress,
        )
        finish_titles(state)  # 계획에는 다듬은 제목이 실려야 한다
        plan_path = save_plan(state, n_all=n_all, only=only)
        progress(f"계획 저장: {plan_path}")
    return state, plan_path


def resume_pipeline(
    run_dir: Path,
    vlm: Optional[object] = None,
    headless: bool = True,
    viewport: Optional[dict] = None,
    step_timeout_ms: int = 10000,
    navigation_timeout_ms: int = 30000,
    settle_timeout_ms: int = 2000,
    screenshot_every_step: bool = True,
    max_heal: int = 2,
    min_confidence: float = 0.5,
    slow_mo: int = 0,
    record_video: bool = False,
    hold_sec: float = 0.0,
    storage_state: Optional[str] = None,
    sut_build: str = "",
    project: str = "",
    workers: int = 1,
    on_progress=None,
) -> tuple[TestReport, Path]:
    """저장된 계획(plan.json)으로 S3~S6 을 이어 실행한다 (--resume).

    **LLM 을 받지 않는다** — S3~S6 은 LLM 을 쓰지 않는다는 사실이 이 함수의
    존재 근거다. 7B 를 내리고 VL 을 올린 뒤에 돌아야 하므로, LLM 이 필요해지는
    변경은 이 경계를 깨는 변경이다.

    입력(pdf·URL·케이스 선택)은 전부 계획에서 온다. 실행 조건(vlm·타임아웃·
    세션 등)만 지금 받는다 — 계획 시점의 실행 조건은 의미가 없다.
    """
    _check_workers(workers, storage_state=storage_state, hold_sec=hold_sec,
                   slow_mo=slow_mo, headless=headless)
    run_dir = Path(run_dir)
    plan = load_plan(run_dir)
    with _run_log(run_dir, on_progress, fresh=False) as progress:
        warnings = plan_warnings(plan)
        for w in warnings:
            progress(f"! {w}")

        selected = set(plan.selected_case_ids)
        state = AgentState(
            pdf_path=plan.pdf_path,
            base_url=plan.base_url,
            run_id=run_dir.name,
            run_dir=run_dir,
            llm=None,
            vlm=vlm,
            figma_json=plan.figma_json,
            screen_urls=dict(plan.screen_urls),
            design_mismatches=list(plan.design_mismatches),
            sut_build=sut_build,
            doc=plan.doc,
            # 본문은 all_cases 가 단일 진실이다 — 선택 목록은 id 로만 저장된다.
            cases=[c for c in plan.all_cases if c.case_id in selected],
            all_cases=list(plan.all_cases),
            coverage_gaps=list(plan.coverage_gaps),
            selection=plan.selection,
            plan_meta={
                "backend": plan.backend,
                "created_at": plan.created_at,
                "warnings": warnings,
            },
            max_heal=max_heal,
            min_confidence=min_confidence,
            step_timeout_ms=step_timeout_ms,
            navigation_timeout_ms=navigation_timeout_ms,
            settle_timeout_ms=settle_timeout_ms,
            screenshot_every_step=screenshot_every_step,
        )
        progress(f"계획 복원: {run_dir / 'plan.json'} — 추출 {plan.backend or '?'} · "
                 f"케이스 {len(state.cases)}개")

        return _execute(
            state,
            run_dir=run_dir,
            n_all=plan.n_all,
            headless=headless,
            viewport=viewport,
            slow_mo=slow_mo,
            record_video=record_video,
            only=plan.only,
            hold_sec=hold_sec,
            storage_state=storage_state,
            project=project,
            workers=workers,
            on_progress=progress,
        )
