"""Prova CLI.

    prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/good
    prova run --pdf ... --url ... --backend mock      # LLM 없이 파이프라인 확인
    prova check                                       # vLLM 연결 확인

## 백엔드를 조용히 폴백하지 않는다

vLLM 에 연결하지 못했을 때 mock 으로 자동 전환하면, 아무 추론도 하지 않은
리포트가 정상 결과처럼 보인다. QA 도구에서 그건 가장 위험한 실패다. 연결 실패는
명확한 오류로 알리고, mock 은 사용자가 --backend mock 으로 직접 고를 때만 쓴다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml

from prova.llm.base import LLMError

app = typer.Typer(add_completion=False, help="설계 문서 기반 웹 GUI QA 에이전트")

DEFAULT_CONFIG = Path("configs/default.yaml")


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _make_llm(backend: str, cfg: dict, pdf: Path):
    """설정에 맞는 LLM 백엔드를 만든다 (규칙은 llm/factory.py 가 갖는다).

    CLI 는 경고를 노란색으로 찍는 일만 한다. 웹 UI 는 같은 경고를 화면에 띄운다.
    """
    from prova.llm.factory import BackendError, make_llm

    try:
        client, warnings = make_llm(backend, cfg, pdf)
    except BackendError as exc:
        raise typer.BadParameter(str(exc))
    for w in warnings:
        typer.secho(f"  {w}", fg=typer.colors.YELLOW)
    return client


def _make_vlm(vlm_url: Optional[str], vlm_model: Optional[str]):
    """2차 경로 클라이언트를 만들고 연결을 확인한다.

    서버가 없으면 여기서 바로 실패시킨다 — 조용히 보정 없이 진행하면 '보정을
    켰다' 고 믿는 실행이 실제로는 그냥 1차 경로다.
    """
    if not vlm_url:
        return None
    from prova.vlm.base import VLMError
    from prova.vlm.qwen_vl import QwenVLClient

    vlm = (QwenVLClient(base_url=vlm_url, model=vlm_model) if vlm_model
           else QwenVLClient(base_url=vlm_url))
    try:
        vlm.health()
    except VLMError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(2)
    return vlm


@app.command()
def run(
    pdf: Optional[Path] = typer.Option(None, "--pdf", help="설계 문서 PDF 경로"),
    url: Optional[str] = typer.Option(None, "--url", help="테스트 대상 base URL"),
    figma_json: Optional[Path] = typer.Option(
        None, "--figma-json", metavar="경로",
        help="Figma API 응답(JSON)으로 실행한다 (scripts/fetch_figma.py 산출물). "
             "--pdf 와 함께 쓸 수 없다. LLM 을 부르지 않는다."),
    screen_url: list[str] = typer.Option(
        [], "--screen-url", metavar="화면=/경로",
        help="화면↔경로 매핑 (예: 로그인=/login). Figma 에는 경로가 없으므로 "
             "사용자가 준다. 반복 지정."),
    backend: Optional[str] = typer.Option(None, "--backend", help="vllm | mock"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    headed: bool = typer.Option(False, "--headed", help="브라우저 창을 띄워서 실행"),
    # 기본값을 None 으로 둔다 — "사용자가 줬는가" 를 알아야 --resume 과의 충돌을
    # 조용히 넘기지 않고 막을 수 있다 (재개는 run_dir 전체 경로를 받는다).
    runs_root: Optional[Path] = typer.Option(None, "--runs-root"),
    engine: str = typer.Option("pipeline", "--engine",
                               help="pipeline | graph (같은 노드를 LangGraph 로 실행)"),
    slow: int = typer.Option(0, "--slow", metavar="MS",
                             help="동작 사이 지연(ms). 눈으로 따라가려면 400~600"),
    video: bool = typer.Option(False, "--video", help="실행 영상(webm) 녹화"),
    only: Optional[str] = typer.Option(None, "--only", metavar="패턴",
                                       help="case_id 에 패턴이 든 케이스만 실행"),
    request: Optional[str] = typer.Option(
        None, "--request", "-r", metavar="요청",
        help="자연어 요청으로 케이스 고르기 (예: \"회원가입이 잘 되는지 확인해줘\")"),
    hold: float = typer.Option(0.0, "--hold", metavar="초",
                               help="끝난 뒤 마지막 화면을 유지할 초 (--headed 로 볼 때)"),
    vlm_url: Optional[str] = typer.Option(
        None, "--vlm", metavar="URL",
        help="2차 경로: 접근성 속성으로 못 찾은 요소를 화면 이미지로 찾는다 "
             "(예: http://localhost:8001/v1)"),
    vlm_model: Optional[str] = typer.Option(
        None, "--vlm-model", metavar="이름",
        help="VLM 서버가 서빙하는 모델 이름 (vLLM 의 --served-model-name 과 같게)"),
    session: Optional[Path] = typer.Option(
        None, "--session", metavar="경로",
        help="prova login 으로 저장한 로그인 세션(storage_state). 스크립트로 "
             "로그인할 수 없는 화면(SSO 등)용 — 비로그인 가드 검증은 세션 없는 "
             "별도 컨텍스트에서 수행된다"),
    plan_only: bool = typer.Option(
        False, "--plan-only",
        help="S1~S2 까지만 수행하고 계획을 runs/<id>/plan.json 으로 저장한다. "
             "한 GPU 에서 추출 모델(7B)과 탐지 모델(VL)을 시간분할로 쓸 때의 "
             "앞 절반 — 서버 교체 후 --resume 으로 잇는다"),
    resume: Optional[Path] = typer.Option(
        None, "--resume", metavar="RUN_DIR",
        help="--plan-only 로 저장한 계획을 이어 실행한다 (S3~S6, LLM 불필요). "
             "입력은 전부 계획에서 오고, 실행 조건(--vlm·--session 등)만 지금 받는다"),
) -> None:
    """설계 문서로 대상 URL 을 검증하고 리포트를 만든다."""
    # --- 재개 경로. 입력(pdf·URL·케이스 선택)은 전부 plan.json 에서 온다 ---
    if resume is not None:
        # 계획 시점 인자를 다시 받으면 승인된 계획과 다른 것이 돌 수 있다.
        # 조용히 무시하지 않고 에러로 막는다.
        given = [name for name, value in [
            ("--pdf", pdf), ("--figma-json", figma_json), ("--url", url),
            ("--screen-url", screen_url), ("--request", request),
            ("--only", only), ("--backend", backend), ("--run-id", run_id),
            ("--plan-only", plan_only), ("--runs-root", runs_root),
        ] if value]
        if given:
            typer.secho(
                f"--resume 은 저장된 계획의 값을 쓰므로 {', '.join(given)} 과 "
                "함께 쓸 수 없습니다.", fg=typer.colors.RED)
            raise typer.Exit(2)
        if engine == "graph":
            typer.secho("--resume 은 pipeline 엔진에서만 동작합니다.",
                        fg=typer.colors.RED)
            raise typer.Exit(2)
        if session and not session.exists():
            typer.secho(f"세션 파일을 찾을 수 없습니다: {session} — "
                        "prova login 으로 먼저 만드세요.", fg=typer.colors.RED)
            raise typer.Exit(2)

        from prova.plan_store import PlanError, load_plan

        try:
            plan = load_plan(resume)
        except PlanError as exc:
            typer.secho(str(exc), fg=typer.colors.RED)
            raise typer.Exit(2)

        cfg = _load_config(config)
        exec_cfg = cfg.get("execution", {})
        vlm = _make_vlm(vlm_url, vlm_model)

        typer.secho(f"Prova 재개 {resume.name}", bold=True)
        typer.echo(f"  계획      : {resume / 'plan.json'} "
                   f"(추출: {plan.backend or '?'} · {plan.created_at})")
        typer.echo(f"  대상 URL  : {plan.base_url}")
        if vlm:
            typer.echo(f"  2차 경로  : {vlm.name} @ {vlm_url} ({vlm.model})")
        typer.echo("")

        from prova.pipeline import resume_pipeline

        report, run_dir = resume_pipeline(
            resume,
            vlm=vlm,
            headless=not headed and exec_cfg.get("headless", True),
            viewport=exec_cfg.get("viewport"),
            step_timeout_ms=int(exec_cfg.get("step_timeout_ms", 10000)),
            settle_timeout_ms=int(exec_cfg.get("settle_timeout_ms", 2000)),
            screenshot_every_step=bool(exec_cfg.get("screenshot_every_step", True)),
            max_heal=int(cfg.get("agent", {}).get("max_heal", 2)),
            min_confidence=float(
                cfg.get("grounding", {}).get("vlm_confidence_threshold", 0.5)),
            slow_mo=slow,
            record_video=video,
            hold_sec=hold,
            storage_state=str(session) if session else None,
            on_progress=lambda m: typer.echo(f"  {m}"),
        )
        _print_summary(report, run_dir)
        raise typer.Exit(1 if report.summary.get("fail", 0) else 0)

    if plan_only:
        # 실행 단계 옵션은 --resume 시점에 준다 — 여기서 받으면 조용히 버려지는
        # 값이 생기고, 사용자는 그 옵션이 적용됐다고 믿는다.
        given = [name for name, value in [
            ("--vlm", vlm_url), ("--vlm-model", vlm_model),
            ("--session", session), ("--headed", headed), ("--slow", slow),
            ("--video", video), ("--hold", hold),
        ] if value]
        if given:
            typer.secho(
                f"--plan-only 는 실행 단계 옵션 {', '.join(given)} 과 함께 쓸 수 "
                "없습니다 — 실행 조건은 --resume 시점에 줍니다.",
                fg=typer.colors.RED)
            raise typer.Exit(2)
        if engine == "graph":
            typer.secho("--plan-only 는 pipeline 엔진에서만 동작합니다.",
                        fg=typer.colors.RED)
            raise typer.Exit(2)

    if not url:
        typer.secho("--url 이 필요합니다 (--resume 재개는 예외 — 계획에서 옵니다).",
                    fg=typer.colors.RED)
        raise typer.Exit(2)
    runs_root = runs_root or Path("runs")
    # Figma 경로 검증. --pdf 와 함께 주면 병합 모드다(기획서 규칙 + 디자인
    # 문구·요소·흐름, 어긋나면 발견) — 단독이면 정적 대조 모드.
    if not figma_json and not pdf:
        typer.secho("--pdf 또는 --figma-json 이 필요합니다.", fg=typer.colors.RED)
        raise typer.Exit(2)
    if figma_json and not pdf and request:
        typer.secho(
            "--figma-json 단독은 --request 와 함께 쓸 수 없습니다 — 요청 해석은 "
            "LLM 이 필요한데 figma 단독 경로는 LLM 을 쓰지 않습니다.",
            fg=typer.colors.RED)
        raise typer.Exit(2)
    if figma_json and engine == "graph":
        typer.secho("--figma-json 은 pipeline 엔진에서만 동작합니다.", fg=typer.colors.RED)
        raise typer.Exit(2)
    if figma_json and not figma_json.exists():
        typer.secho(f"Figma 응답 파일을 찾을 수 없습니다: {figma_json}", fg=typer.colors.RED)
        raise typer.Exit(2)
    screen_urls: dict[str, str] = {}
    for pair in screen_url:
        if "=" not in pair:
            typer.secho(f"--screen-url 형식은 '화면=/경로' 입니다: {pair!r}",
                        fg=typer.colors.RED)
            raise typer.Exit(2)
        k, _, v = pair.partition("=")
        screen_urls[k.strip()] = v.strip()

    if pdf and not pdf.exists():
        typer.secho(f"설계 문서를 찾을 수 없습니다: {pdf}", fg=typer.colors.RED)
        raise typer.Exit(2)
    if session and not session.exists():
        typer.secho(f"세션 파일을 찾을 수 없습니다: {session} — "
                    "prova login 으로 먼저 만드세요.", fg=typer.colors.RED)
        raise typer.Exit(2)
    if session and engine == "graph":
        typer.secho("--session 은 pipeline 엔진에서만 동작합니다.", fg=typer.colors.RED)
        raise typer.Exit(2)

    cfg = _load_config(config)
    backend = backend or cfg.get("llm", {}).get("backend", "vllm")
    rid = run_id or f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # 2차 경로는 명시적으로 켜야 한다.
    #
    # 기본으로 켜면 라벨 연결이 깨진 화면에서도 케이스가 통과해 그 사실이 리포트에서
    # 사라진다 (_make_vlm 참고).
    vlm = _make_vlm(vlm_url, vlm_model)

    typer.secho(f"Prova 실행 {rid}", bold=True)
    if figma_json and pdf:
        typer.echo(f"  설계 문서 : {pdf}")
        typer.echo(f"  Figma 응답: {figma_json}")
        typer.echo("  모드      : 병합 — 기획서 규칙 + 디자인 문구·요소·흐름, 어긋나면 발견")
    elif figma_json:
        typer.echo(f"  Figma 응답: {figma_json} (LLM 미사용 — 정적 대조만)")
    else:
        typer.echo(f"  설계 문서 : {pdf}")
    typer.echo(f"  대상 URL  : {url}")
    if pdf:
        typer.echo(f"  백엔드    : {backend}")
    typer.echo(f"  실행 엔진 : {engine}")
    if vlm:
        typer.echo(f"  2차 경로  : {vlm.name} @ {vlm_url} ({vlm.model})")
    typer.echo("")

    if figma_json and not pdf:
        llm = None  # figma 단독 경로는 LLM 을 부르지 않는다 — 추출이 결정적이다
    else:
        try:
            llm = _make_llm(backend, cfg, pdf)
        except LLMError as exc:
            typer.secho(f"\nLLM 백엔드를 준비할 수 없습니다:\n{exc}", fg=typer.colors.RED)
            typer.secho(
                "\nLLM 없이 파이프라인만 확인하려면 --backend mock 을 쓰세요.",
                fg=typer.colors.YELLOW,
            )
            raise typer.Exit(1)

    if plan_only:
        from prova.pipeline import plan_pipeline

        state, plan_path = plan_pipeline(
            pdf_path=str(pdf) if pdf else "",
            base_url=url,
            llm=llm,
            run_id=rid,
            runs_root=runs_root,
            only=only,
            request=request,
            figma_json=str(figma_json) if figma_json else None,
            screen_urls=screen_urls or None,
            on_progress=lambda m: typer.echo(f"  {m}"),
        )
        typer.echo("")
        typer.secho(f"  계획 저장: {plan_path}", bold=True)
        typer.echo("  서버를 교체한 뒤 이어서 실행:")
        typer.echo(f"    uv run prova run --resume {plan_path.parent} "
                   "[--vlm URL --vlm-model 이름]")
        raise typer.Exit(0)

    exec_cfg = cfg.get("execution", {})
    common = dict(
        pdf_path=str(pdf) if pdf else "",
        base_url=url,
        llm=llm,
        run_id=rid,
        runs_root=runs_root,
        headless=not headed and exec_cfg.get("headless", True),
        viewport=exec_cfg.get("viewport"),
        step_timeout_ms=int(exec_cfg.get("step_timeout_ms", 10000)),
        settle_timeout_ms=int(exec_cfg.get("settle_timeout_ms", 2000)),
        screenshot_every_step=bool(exec_cfg.get("screenshot_every_step", True)),
        max_heal=int(cfg.get("agent", {}).get("max_heal", 2)),
        min_confidence=float(
            cfg.get("grounding", {}).get("vlm_confidence_threshold", 0.5)),
    )

    # 관찰용 옵션은 pipeline 엔진만 지원한다. graph 엔진은 결과 동일성 대조가 목적이므로
    # 실행 조건을 바꾸는 옵션을 받지 않는다 — 두 경로를 같은 조건으로 비교해야 한다.
    if engine == "graph" and vlm:
        typer.secho(
            "--vlm 은 pipeline 엔진에서만 동작합니다 (graph 는 결과 동일성 대조용).",
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

    if engine == "graph" and (slow or video or only or hold or request):
        typer.secho(
            "--slow / --video / --only / --hold / --request 는 pipeline 엔진에서만 "
            "동작합니다 (graph 는 결과 동일성 대조용).",
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

    if engine == "graph":
        from prova.graph import run_graph

        report, run_dir = run_graph(**common)
    elif engine == "pipeline":
        from prova.pipeline import run_pipeline

        try:
            report, run_dir = run_pipeline(
                **common,
                vlm=vlm,
                slow_mo=slow,
                record_video=video,
                only=only,
                request=request,
                hold_sec=hold,
                figma_json=str(figma_json) if figma_json else None,
                screen_urls=screen_urls or None,
                storage_state=str(session) if session else None,
                on_progress=lambda m: typer.echo(f"  {m}"),
            )
        except ValueError as exc:
            # 케이스 필터가 아무것도 고르지 못한 경우가 대표적이다. 사용자 입력 실수에
            # 파이썬 스택을 보여줄 이유가 없으므로 메시지만 전달한다.
            typer.echo("")
            typer.secho(str(exc), fg=typer.colors.RED)
            raise typer.Exit(2)
    else:
        raise typer.BadParameter(f"지원하지 않는 엔진: {engine} (pipeline | graph)")

    _print_summary(report, run_dir)
    # 실패가 있으면 0 이 아닌 코드로 끝낸다. CI 에서 회귀 검증에 쓸 수 있게 하는
    # 최소 조건이다 (명세서 §11 의 CI 연동으로 이어진다).
    raise typer.Exit(1 if report.summary.get("fail", 0) else 0)


def _print_summary(report, run_dir: Path) -> None:
    s = report.summary
    typer.echo("")
    typer.secho(
        f"  결과: 전체 {s['total']} · 통과 {s['pass']} · 실패 {s['fail']} "
        f"· 통과율 {s['pass_rate']}%",
        bold=True,
    )

    if s.get("filtered_by"):
        typer.secho(
            f"  ! 부분 실행: 필터 '{s['filtered_by']}' 로 전체 "
            f"{s.get('cases_available', '?')}건 중 {s['total']}건만 실행했습니다.",
            fg=typer.colors.YELLOW,
        )

    for warning in s.get("spec_warnings", []):
        typer.secho(f"  ! 설계 문서 경고: {warning}", fg=typer.colors.YELLOW)

    fails = [v for v in report.cases if v.verdict == "FAIL"]
    if fails:
        typer.echo("")
        typer.secho("  실패 케이스", fg=typer.colors.RED, bold=True)
        for v in fails:
            rule = f"[{v.violates}] " if v.violates else ""
            typer.secho(f"    FAIL {rule}{v.title}", fg=typer.colors.RED)
            typer.echo(f"         {v.failure_detail}")

    typer.echo("")
    typer.echo(f"  리포트: {run_dir / 'report.html'}")


@app.command()
def login(
    url: str = typer.Option(..., "--url", help="로그인 화면(또는 시작) URL"),
    out: Path = typer.Option(Path("sessions/session.json"), "--out",
                             help="세션(storage_state) 저장 경로"),
) -> None:
    """브라우저를 열어 사람이 직접 로그인하면 그 상태를 저장한다.

    스크립트로 로그인할 수 없는 화면(SSO·캡차·2단계 인증)을 테스트하는 길이다.
    저장된 파일은 `prova run --session <경로>` 로 실어 쓴다.

    저장물에는 로그인 토큰(쿠키·localStorage)이 들어 있다 — 비밀이다.
    기본 경로 `sessions/` 는 gitignore 이고, 다른 곳에 저장하면 커밋되지
    않는지 스스로 확인해야 한다.
    """
    from playwright.sync_api import sync_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        typer.secho("브라우저에서 로그인을 마친 뒤, 여기로 돌아와 Enter 를 누르세요.",
                    bold=True)
        typer.prompt("완료되면 Enter", default="", show_default=False)
        context.storage_state(path=str(out))
        browser.close()
    typer.secho(f"세션 저장: {out}", fg=typer.colors.GREEN)
    typer.echo("이 파일에는 로그인 토큰이 들어 있습니다 — 공유·커밋 금지. "
               "만료되면 다시 만드세요.")


@app.command()
def serve(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
    host: str = typer.Option(None, "--host", help="바인딩 주소 (기본 127.0.0.1)"),
    port: int = typer.Option(None, "--port", help="포트 (기본 7007)"),
) -> None:
    """웹 UI 를 연다 — 자연어로 요청하고 계획을 승인한 뒤 실행한다.

    호스팅이 아니라 **이 기계에서** 돈다. 브라우저와 테스트 대상이 여기 있기
    때문이다 — 호스팅 서버는 localhost 나 사내 스테이징에 닿을 수 없다.
    """
    import uvicorn

    cfg = _load_config(config).get("server", {})
    bind = host or cfg.get("host", "127.0.0.1")
    where = port or int(cfg.get("port", 7007))

    if bind not in ("127.0.0.1", "localhost"):
        # 이 서버는 이 기계의 파일을 읽고 이 기계의 브라우저를 연다. 바깥에 열면
        # 그 두 가지가 그대로 남의 것이 된다.
        typer.secho(
            f"  경고: {bind} 로 바인딩합니다. 이 서버는 로컬 파일을 읽고 브라우저를 "
            "조작하므로 외부에 노출하지 마세요.",
            fg=typer.colors.RED,
        )

    typer.secho(f"Prova 웹 UI  http://{bind}:{where}", bold=True)
    typer.echo("  종료하려면 Ctrl+C")
    uvicorn.run("prova.server.app:app", host=bind, port=where, log_level="warning")


@app.command()
def check(config: Path = typer.Option(DEFAULT_CONFIG, "--config")) -> None:
    """vLLM 서버 연결과 모델 적재 상태를 확인한다."""
    cfg = _load_config(config)
    llm_cfg = cfg.get("llm", {})
    from prova.llm.vllm_backend import DEFAULT_BASE_URL, DEFAULT_MODEL, VLLMClient

    client = VLLMClient(
        base_url=llm_cfg.get("base_url", DEFAULT_BASE_URL),
        model=llm_cfg.get("model", DEFAULT_MODEL),
    )
    typer.echo(f"엔드포인트: {client.base_url}")
    try:
        model = client.health()
    except LLMError as exc:
        typer.secho(f"실패:\n{exc}", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.secho(f"연결 정상 · 모델 {model}", fg=typer.colors.GREEN)

    # 정형 출력이 실제로 걸리는지 확인한다. 연결만 되고 스키마가 무시되면
    # S1/S2 가 조용히 불안정해진다 — 그게 가장 위험한 실패다.
    typer.echo("정형 출력(response_format) 확인 중...")
    # 필드명을 모델이 자연스럽게 지어낼 이름과 다르게 잡는다. 스키마가 무시되면
    # 다른 이름이 돌아오므로 무시 여부를 확실히 판별할 수 있다.
    schema = {
        "title": "SmokeTest",
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "note_text": {"type": "string"}},
        "required": ["ok", "note_text"],
        "additionalProperties": False,
    }
    try:
        result = client.complete_json(
            system="당신은 JSON 만 출력합니다.",
            user="ok 은 true, note_text 는 '정상' 으로 채워 JSON 을 출력하세요.",
            schema=schema,
            max_tokens=128,
        )
    except LLMError as exc:
        typer.secho(f"정형 출력 실패:\n{exc}", fg=typer.colors.RED)
        raise typer.Exit(1)

    # 파싱이 됐다고 끝이 아니다. 스키마가 무시되면 모델이 지어낸 필드명이
    # 돌아오는데(note_text -> note 등) JSON 자체는 유효하다. 필드명을 대조해야
    # 정형 출력이 실제로 걸렸는지 알 수 있다.
    if set(result) != {"ok", "note_text"}:
        typer.secho(
            f"정형 출력이 무시된 것 같습니다 — 기대 필드 {{ok, note_text}}, "
            f"실제 {set(result)}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    typer.secho(f"정형 출력 정상 · 응답 {result}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
