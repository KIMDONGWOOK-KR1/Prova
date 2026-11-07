"""모바일 화면 크기로 실행 (--device mobile).

반응형 사이트는 휴대폰 폭에서 메뉴를 햄버거 버튼 뒤로 숨기고 배치를 바꾼다. 데스크톱
크기로만 돌리면 모바일에서만 생기는 결함을 볼 수 없다. 같은 기획서를 모바일 크기로
한 번 더 돌릴 수 있게 하고, 그 사실을 리포트와 이력이 구별하게 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prova.cli import app
from prova.history import attach_history
from prova.llm.mock_backend import MockLLM
from prova.models import TestReport, Verdict
from prova.nodes import DEFAULT_VIEWPORT, MOBILE_VIEWPORT, note_viewport
from prova.pipeline import run_pipeline
from prova.s6_report.report_builder import render_html
from prova.sut_build import BuildCheck

runner = CliRunner()


def _report(run_id: str, viewport: str = "", created="2026-11-07T10:00:00+09:00"):
    cases = [Verdict(case_id="c1", title="제목", type="positive", verdict="PASS")]
    s = TestReport.summarize(cases)
    s["llm_backend"] = "vllm:m"
    if viewport:
        s["viewport"] = viewport
    return TestReport(run_id=run_id, target_url="http://x/good",
                      spec_source="fixtures/specs/login_spec.pdf", summary=s,
                      cases=cases, created_at=created)


def _save(root: Path, report: TestReport) -> None:
    d = root / report.run_id
    d.mkdir(parents=True)
    (d / "report.json").write_text(json.dumps(report.model_dump(), ensure_ascii=False),
                                   encoding="utf-8")


class TestNoteViewport:
    def test_데스크톱이면_칸을_만들지_않는다(self):
        summary: dict = {}
        note_viewport(summary, DEFAULT_VIEWPORT)
        note_viewport(summary, None)
        assert "viewport" not in summary

    def test_모바일이면_크기를_남긴다(self):
        summary: dict = {}
        note_viewport(summary, MOBILE_VIEWPORT)
        assert summary["viewport"] == "390x844"


def test_리포트_머리말에_화면_크기가_보인다():
    html = render_html(_report("m", viewport="390x844"))
    assert "화면 크기 <code>390x844</code>" in html
    assert "화면 크기" not in render_html(_report("d"))


class TestHistory:
    def test_모바일_실행은_데스크톱_실행과_차수를_잇지_않는다(self, tmp_path):
        _save(tmp_path, _report("desk"))
        r = _report("mob", viewport="390x844", created="2026-11-07T11:00:00+09:00")
        attach_history(r, tmp_path)
        assert r.summary["history"]["round"] == 1
        assert r.summary["history"]["previous_run"] is None

    def test_모바일끼리는_잇는다(self, tmp_path):
        _save(tmp_path, _report("mob1", viewport="390x844"))
        r = _report("mob2", viewport="390x844", created="2026-11-07T11:00:00+09:00")
        attach_history(r, tmp_path)
        assert r.summary["history"]["previous_run"] == "mob1"


class TestCli:
    @pytest.fixture(autouse=True)
    def fresh_target(self, monkeypatch):
        monkeypatch.setattr("prova.cli.check_sut_build",
                            lambda url, **kw: BuildCheck("match", "일치"))

    def test_없는_기기는_실행_전에_잡는다(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr("prova.llm.factory.make_llm", lambda *a: called.append(a))
        result = runner.invoke(app, [
            "run", "--pdf", "fixtures/specs/login_spec.pdf",
            "--url", "http://localhost:8100/good", "--device", "tablet",
            "--runs-root", str(tmp_path),
        ])
        assert result.exit_code == 2
        assert "tablet" in result.output
        assert called == []

    def test_계획만_만들_때는_받지_않는다(self, tmp_path):
        result = runner.invoke(app, [
            "run", "--pdf", "fixtures/specs/login_spec.pdf", "--backend", "mock",
            "--url", "http://localhost:8100/good", "--device", "mobile", "--plan-only",
            "--runs-root", str(tmp_path),
        ])
        assert result.exit_code == 2
        assert "--device" in result.output


def test_모바일_크기로_돌려도_SUT_판정이_같다(sut_base, tmp_path):
    """SUT 는 반응형이 아니다 — 크기만 바꿔서는 판정이 바뀌면 안 된다(도구 쪽 회귀 확인)."""
    runs = {}
    for name, viewport in [("desk", None), ("mob", MOBILE_VIEWPORT)]:
        report, _ = run_pipeline(
            pdf_path="fixtures/specs/login_spec.pdf", base_url=f"{sut_base}/bad",
            llm=MockLLM.with_login_fixtures(), run_id=name, runs_root=tmp_path / name,
            viewport=viewport, screenshot_every_step=False)
        runs[name] = report
    verdicts = {n: [(c.case_id, c.verdict) for c in r.cases] for n, r in runs.items()}
    assert verdicts["desk"] == verdicts["mob"]
    assert runs["mob"].summary["viewport"] == "390x844"
    assert "viewport" not in runs["desk"].summary
