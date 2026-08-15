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


def _make_llm(backend: str, cfg: dict):
    """설정에 맞는 LLM 백엔드를 만든다."""
    llm_cfg = cfg.get("llm", {})

    if backend == "mock":
        from prova.llm.mock_backend import MockLLM

        typer.secho(
            "  mock 백엔드로 실행합니다 — 설계 문서 추출에 실제 모델을 쓰지 않습니다.",
            fg=typer.colors.YELLOW,
        )
        return MockLLM.with_login_fixtures()

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
) -> None:
    """설계 문서로 대상 URL 을 검증하고 리포트를 만든다."""
    if not pdf.exists():
        typer.secho(f"설계 문서를 찾을 수 없습니다: {pdf}", fg=typer.colors.RED)
        raise typer.Exit(2)

    cfg = _load_config(config)
    backend = backend or cfg.get("llm", {}).get("backend", "vllm")
    rid = run_id or f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    typer.secho(f"Prova 실행 {rid}", bold=True)
    typer.echo(f"  설계 문서 : {pdf}")
    typer.echo(f"  대상 URL  : {url}")
    typer.echo(f"  백엔드    : {backend}")
    typer.echo("")

    try:
        llm = _make_llm(backend, cfg)
    except LLMError as exc:
        typer.secho(f"\nLLM 백엔드를 준비할 수 없습니다:\n{exc}", fg=typer.colors.RED)
        typer.secho(
            "\nLLM 없이 파이프라인만 확인하려면 --backend mock 을 쓰세요.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    from prova.pipeline import run_pipeline

    exec_cfg = cfg.get("execution", {})
    report, run_dir = run_pipeline(
        pdf_path=str(pdf),
        base_url=url,
        llm=llm,
        run_id=rid,
        runs_root=runs_root,
        headless=not headed and exec_cfg.get("headless", True),
        viewport=exec_cfg.get("viewport"),
        step_timeout_ms=int(exec_cfg.get("step_timeout_ms", 10000)),
        on_progress=lambda m: typer.echo(f"  {m}"),
    )

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

    # 구조화 출력이 실제로 걸리는지 확인한다. 연결만 되고 guided_json 이
    # 동작하지 않으면 S1/S2 가 조용히 불안정해진다.
    typer.echo("guided_json 확인 중...")
    schema = {
        "title": "SmokeTest",
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "note": {"type": "string"}},
        "required": ["ok", "note"],
    }
    try:
        result = client.complete_json(
            system="당신은 JSON 만 출력합니다.",
            user="ok=true 로 하고 note 에 '정상' 이라고 써서 JSON 을 출력하세요.",
            schema=schema,
            max_tokens=128,
        )
    except LLMError as exc:
        typer.secho(f"guided_json 실패:\n{exc}", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.secho(f"guided_json 정상 · 응답 {result}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
