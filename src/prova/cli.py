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
    """설정에 맞는 LLM 백엔드를 만든다.

    mock 은 어느 기획서를 검증하는지에 따라 다른 정답을 돌려줘야 하므로 PDF
    경로를 받는다. 화면이 늘어나도 여기에 분기가 생기지 않는다.
    """
    llm_cfg = cfg.get("llm", {})

    if backend == "mock":
        from prova.llm.mock_backend import MockLLM

        typer.secho(
            "  mock 백엔드로 실행합니다 — 설계 문서 추출에 실제 모델을 쓰지 않습니다.",
            fg=typer.colors.YELLOW,
        )
        return MockLLM.for_spec(pdf)

    if backend == "vllm":
        from prova.llm.vllm_backend import VLLMClient

        client = VLLMClient(
            base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
            model=llm_cfg.get("model", "Qwen/Qwen2.5-7B-Instruct-AWQ"),
            timeout=float(llm_cfg.get("timeout", 180)),
        )
        client.health()  # 실행 전에 연결을 확인한다
        return client

    raise typer.BadParameter(f"지원하지 않는 백엔드: {backend} (vllm | mock)")


@app.command()
def run(
    pdf: Path = typer.Option(..., "--pdf", help="설계 문서 PDF 경로"),
    url: str = typer.Option(..., "--url", help="테스트 대상 base URL"),
    backend: Optional[str] = typer.Option(None, "--backend", help="vllm | mock"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    headed: bool = typer.Option(False, "--headed", help="브라우저 창을 띄워서 실행"),
    runs_root: Path = typer.Option(Path("runs"), "--runs-root"),
    engine: str = typer.Option("pipeline", "--engine",
                               help="pipeline | graph (같은 노드를 LangGraph 로 실행)"),
    slow: int = typer.Option(0, "--slow", metavar="MS",
                             help="동작 사이 지연(ms). 눈으로 따라가려면 400~600"),
    video: bool = typer.Option(False, "--video", help="실행 영상(webm) 녹화"),
    only: Optional[str] = typer.Option(None, "--only", metavar="패턴",
                                       help="case_id 에 패턴이 든 케이스만 실행"),
    hold: float = typer.Option(0.0, "--hold", metavar="초",
                               help="끝난 뒤 마지막 화면을 유지할 초 (--headed 로 볼 때)"),
    vlm_url: Optional[str] = typer.Option(
        None, "--vlm", metavar="URL",
        help="2차 경로: 접근성 속성으로 못 찾은 요소를 화면 이미지로 찾는다 "
             "(예: http://localhost:8001/v1)"),
    vlm_model: Optional[str] = typer.Option(
        None, "--vlm-model", metavar="이름",
        help="VLM 서버가 서빙하는 모델 이름 (vLLM 의 --served-model-name 과 같게)"),
) -> None:
    """설계 문서로 대상 URL 을 검증하고 리포트를 만든다."""
    if not pdf.exists():
        typer.secho(f"설계 문서를 찾을 수 없습니다: {pdf}", fg=typer.colors.RED)
        raise typer.Exit(2)

    cfg = _load_config(config)
    backend = backend or cfg.get("llm", {}).get("backend", "vllm")
    rid = run_id or f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # 2차 경로는 명시적으로 켜야 한다.
    #
    # 기본으로 켜면 라벨 연결이 깨진 화면에서도 케이스가 통과해 그 사실이 리포트에서
    # 사라진다. 그리고 서버가 없으면 여기서 바로 실패시킨다 — 조용히 보정 없이
    # 진행하면 '보정을 켰다' 고 믿는 실행이 실제로는 그냥 1차 경로다.
    vlm = None
    if vlm_url:
        from prova.vlm.qwen_vl import QwenVLClient
        from prova.vlm.base import VLMError

        vlm = (QwenVLClient(base_url=vlm_url, model=vlm_model) if vlm_model
               else QwenVLClient(base_url=vlm_url))
        try:
            vlm.health()
        except VLMError as exc:
            typer.secho(str(exc), fg=typer.colors.RED)
            raise typer.Exit(2)

    typer.secho(f"Prova 실행 {rid}", bold=True)
    typer.echo(f"  설계 문서 : {pdf}")
    typer.echo(f"  대상 URL  : {url}")
    typer.echo(f"  백엔드    : {backend}")
    typer.echo(f"  실행 엔진 : {engine}")
    if vlm:
        typer.echo(f"  2차 경로  : {vlm.name} @ {vlm_url} ({vlm.model})")
    typer.echo("")

    try:
        llm = _make_llm(backend, cfg, pdf)
    except LLMError as exc:
        typer.secho(f"\nLLM 백엔드를 준비할 수 없습니다:\n{exc}", fg=typer.colors.RED)
        typer.secho(
            "\nLLM 없이 파이프라인만 확인하려면 --backend mock 을 쓰세요.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    exec_cfg = cfg.get("execution", {})
    common = dict(
        pdf_path=str(pdf),
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

    if engine == "graph" and (slow or video or only or hold):
        typer.secho(
            "--slow / --video / --only / --hold 는 pipeline 엔진에서만 동작합니다 "
            "(graph 는 결과 동일성 대조용).",
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
                hold_sec=hold,
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
def check(config: Path = typer.Option(DEFAULT_CONFIG, "--config")) -> None:
    """vLLM 서버 연결과 모델 적재 상태를 확인한다."""
    cfg = _load_config(config)
    llm_cfg = cfg.get("llm", {})
    from prova.llm.vllm_backend import VLLMClient

    client = VLLMClient(
        base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
        model=llm_cfg.get("model", "Qwen/Qwen2.5-7B-Instruct-AWQ"),
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
