"""dry-run — 쓰기 요청을 막고 실행한다 (A-4).

가로채기가 하나라도 새면 실무 사이트에 실제 접수가 들어간다. 그래서 브라우저 쪽 기록을
믿지 않고 **서버가 받은 쓰기 요청을 서버에서 센다.** 우리 SUT 를 세는 래퍼로 감싸 띄우고,
dry-run 실행 뒤 서버가 받은 쓰기 요청이 '전제(로그인) 단계에서 통과시킨 것' 과 정확히
같은지 본다 — 본 스텝의 요청은 하나도 서버에 닿으면 안 된다.
"""

from __future__ import annotations

import threading
import time

import pytest
import uvicorn

from prova.dry_run import UNVERIFIABLE_PREFIX, WriteGuard, _fields, mark_unverifiable
from prova.llm.mock_backend import MockLLM
from prova.models import Verdict
from prova.pipeline import run_pipeline

WRITE = {"POST", "PUT", "PATCH", "DELETE"}


class CountingApp:
    """ASGI 래퍼 — 서버에 닿은 쓰기 요청을 센다."""

    def __init__(self, app) -> None:
        self.app = app
        self.writes: list[str] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in WRITE:
            self.writes.append(f"{scope['method']} {scope['path']}")
        await self.app(scope, receive, send)


@pytest.fixture(scope="module")
def counted_sut():
    import socket

    from sut.app import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    counting = CountingApp(app)
    server = uvicorn.Server(uvicorn.Config(counting, host="127.0.0.1", port=port,
                                           log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "SUT 가 뜨지 않았습니다"
    yield f"http://127.0.0.1:{port}", counting
    server.should_exit = True
    thread.join(timeout=5)


def _run(base, spec, tmp_path, **kw):
    return run_pipeline(pdf_path=f"fixtures/specs/{spec}.pdf", base_url=base,
                        llm=MockLLM.for_spec(f"fixtures/specs/{spec}.pdf"),
                        run_id=spec, runs_root=tmp_path, **kw)


def test_막지_않으면_서버가_쓰기_요청을_받는다(counted_sut, tmp_path):
    """대조군 — 세는 장치가 실제로 센다."""
    base, counting = counted_sut
    counting.writes.clear()
    _run(f"{base}/good", "login_spec", tmp_path)
    assert counting.writes


@pytest.mark.parametrize("spec", ["login_spec", "signup_spec", "find_account_spec"])
def test_dry_run_이면_서버에_쓰기_요청이_하나도_닿지_않는다(counted_sut, tmp_path, spec):
    base, counting = counted_sut
    counting.writes.clear()
    report, _ = _run(f"{base}/good", spec, tmp_path, dry_run=True)
    assert counting.writes == []
    d = report.summary["dry_run"]
    assert d["requests_blocked"] > 0 and d["setup_allowed"] == 0
    # 막은 요청이 있는 케이스는 지어낸 결과로 판정하지 않는다.
    for v in report.cases:
        if v.evidence.get("dry_run_blocked"):
            assert v.verdict == "FAIL" and v.failure_category == "unverifiable"
            assert v.failure_detail.startswith(UNVERIFIABLE_PREFIX)


def test_전제_로그인만_서버에_닿고_본_스텝은_막힌다(counted_sut, tmp_path):
    base, counting = counted_sut
    counting.writes.clear()
    report, _ = _run(f"{base}/good", "product_spec", tmp_path, dry_run=True)
    allowed = report.summary["dry_run"]["setup_allowed"]
    assert allowed > 0
    assert len(counting.writes) == allowed
    assert all(w.endswith("/login") for w in counting.writes)
    assert report.summary["dry_run"]["requests_blocked"] > 0


def test_병렬로_돌려도_새지_않는다(counted_sut, tmp_path):
    base, counting = counted_sut
    counting.writes.clear()
    report, _ = _run(f"{base}/good", "signup_spec", tmp_path, dry_run=True, workers=3)
    assert counting.writes == []
    assert report.summary["dry_run"]["requests_blocked"] > 0


def test_보낸_칸_이름만_남기고_값은_남기지_않는다():
    class Req:
        post_data = "email=a%40b.c&password=Secret1%21"
        headers = {"content-type": "application/x-www-form-urlencoded"}

    assert _fields(Req()) == ["email", "password"]


def test_막은_요청이_없으면_판정을_바꾸지_않는다():
    v = Verdict(case_id="c", verdict="PASS")
    mark_unverifiable(v, WriteGuard())
    assert v.verdict == "PASS" and "dry_run_blocked" not in v.evidence


def test_막은_요청이_있으면_확인_불가로_바꾸고_원래_판정을_남긴다():
    guard = WriteGuard()
    guard.blocked.append({"method": "POST", "url": "http://x/login", "path": "/login",
                          "fields": ["email"]})
    v = Verdict(case_id="c", verdict="PASS")
    mark_unverifiable(v, guard)
    assert (v.verdict, v.failure_category) == ("FAIL", "unverifiable")
    assert v.evidence["dry_run_original"] == "PASS"
    assert v.evidence["dry_run_blocked"] == ["POST /login (email)"]


def test_리포트와_엑셀이_dry_run_이었다고_말한다(tmp_path):
    from openpyxl import load_workbook

    from prova.models import TestReport
    from prova.s6_report.report_builder import render_html
    from prova.s6_report.xlsx_export import save_xlsx

    guard = WriteGuard()
    guard.blocked.append({"method": "POST", "url": "http://x/login", "path": "/login",
                          "fields": ["email"]})
    v = Verdict(case_id="c", title="정상", verdict="PASS")
    mark_unverifiable(v, guard)
    from prova.dry_run import dry_run_summary

    s = TestReport.summarize([v])
    s["dry_run"] = dry_run_summary([v])
    report = TestReport(run_id="r", target_url="http://x", summary=s, cases=[v])
    html = render_html(report)
    assert "dry-run — 쓰기 요청을 막고 실행했습니다" in html
    assert "POST /login (email)" in html
    text = " ".join(str(c) for r in load_workbook(save_xlsx(report, tmp_path))["요약"]
                    .iter_rows(values_only=True) for c in r if c)
    assert "dry-run" in text and "웹소켓" in text


def test_CLI_dry_run_은_graph_와_함께_쓸_수_없다():
    from typer.testing import CliRunner

    from prova.cli import app

    result = CliRunner().invoke(app, ["run", "--pdf", "fixtures/specs/login_spec.pdf",
                                      "--url", "http://x", "--backend", "mock",
                                      "--engine", "graph", "--dry-run"])
    assert result.exit_code != 0 and "--dry-run" in result.output
