"""병렬 실행 — 빨라져도 판정은 같아야 한다.

브라우저 대기가 실행 시간의 대부분이라 스레드로 충분하다. 각 스레드가 자기 Playwright 를
연다 (sync API 는 스레드를 넘어 공유할 수 없다).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from prova.cli import app
from prova.llm.mock_backend import MockLLM
from prova.pipeline import configured_workers, run_pipeline

PDF = "fixtures/specs/login_spec.pdf"


def _run(sut_base, tmp_path, rid, workers, **kw):
    return run_pipeline(PDF, f"{sut_base}/bad", MockLLM.for_document(PDF), run_id=rid,
                        runs_root=tmp_path, workers=workers, **kw)[0]


def _key(report):
    return [(v.case_id, v.verdict, v.failure_category) for v in report.cases]


def test_병렬과_순차의_판정과_순서가_같다(sut_base, tmp_path):
    assert _key(_run(sut_base, tmp_path, "w3", 3)) == _key(_run(sut_base, tmp_path, "w1", 1))


def test_병렬로_돌렸다는_사실을_리포트가_말한다(sut_base, tmp_path):
    from prova.s6_report.report_builder import render_html

    report = _run(sut_base, tmp_path, "w2", 2)
    assert report.summary["workers"] == 2
    assert "병렬 2" in render_html(report)


def test_순차_실행에는_병렬_칸을_만들지_않는다(sut_base, tmp_path):
    report = _run(sut_base, tmp_path, "w1", 1, only="login-valid")
    assert "workers" not in report.summary


def test_케이스보다_많이_띄우지_않는다(sut_base, tmp_path):
    report = _run(sut_base, tmp_path, "w4", 4, only="login-valid")
    assert "workers" not in report.summary and len(report.cases) == 1


def test_세션_파일과_함께_쓰지_못한다(tmp_path):
    # 한쪽의 로그아웃 케이스가 다른 쪽이 쓰는 세션을 끊을 수 있다
    with pytest.raises(ValueError, match="세션"):
        _run("http://127.0.0.1:1", tmp_path, "s", 2, storage_state="x.json")


def test_보고_따라가는_옵션과_함께_쓰지_못한다(tmp_path):
    with pytest.raises(ValueError, match="hold"):
        _run("http://127.0.0.1:1", tmp_path, "h", 2, hold_sec=1.0)


def test_설정의_기본은_순차다():
    assert configured_workers({}) == 1
    assert configured_workers({"execution": {"workers": "3"}}) == 3


def test_0_이하의_설정은_오류다():
    with pytest.raises(ValueError, match="workers"):
        configured_workers({"execution": {"workers": 0}})


@pytest.mark.parametrize("extra", [["--session", "x.json"], ["--headed"], ["--hold", "1"],
                                   ["--engine", "graph"], ["--plan-only"]])
def test_CLI_가_함께_못_쓰는_옵션을_막는다(extra):
    args = ["run", "--pdf", PDF, "--url", "http://x/", "--backend", "mock", "--workers", "2", *extra]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2 and "--workers" in result.output
