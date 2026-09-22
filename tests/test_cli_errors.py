"""CLI 가 흔한 실수를 한 줄로, 할 일과 함께 알린다.

## 왜 (2026-09-22 사용성 점검)

- vLLM 이 꺼져 있으면 typer 의 "Usage ... Invalid value" 상자가 떴다. 옵션을 잘못
  친 것처럼 보이고, `--backend mock` 을 권하던 블록은 예외 종류가 달라 한 번도
  실행되지 않았다.
- mock 에 골든이 없는 PDF(사용자 자기 기획서)나 스캔 PDF 는 파이썬 traceback 을
  쏟았다. 쓸모 있는 한 줄이 스택 사이에 묻힌다.
"""

from __future__ import annotations

import shutil

import pytest
from typer.testing import CliRunner

from prova.cli import app
from prova.llm.factory import BackendError
from prova.sut_build import BuildCheck

runner = CliRunner()


@pytest.fixture(autouse=True)
def fresh_target(monkeypatch):
    monkeypatch.setattr("prova.cli.check_sut_build",
                        lambda url, **kw: BuildCheck("match", "일치"))


def test_모델_서버가_꺼져_있으면_mock_을_권한다(tmp_path, monkeypatch):
    def down(backend, cfg, pdf):
        raise BackendError("vLLM 서버에 연결할 수 없습니다 (http://localhost:8000/v1)")

    monkeypatch.setattr("prova.llm.factory.make_llm", down)
    result = runner.invoke(app, [
        "run", "--pdf", "fixtures/specs/login_spec.pdf",
        "--url", "http://localhost:8100/good", "--runs-root", str(tmp_path),
    ])
    assert result.exit_code == 2
    assert "연결할 수 없습니다" in result.output
    assert "--backend mock" in result.output
    assert "Invalid value" not in result.output
    assert "Usage" not in result.output


def test_mock_에_정답이_없는_기획서는_한_줄로_알린다(tmp_path):
    mine = tmp_path / "my_spec.pdf"
    shutil.copy("fixtures/specs/login_spec.pdf", mine)
    result = runner.invoke(app, [
        "run", "--pdf", str(mine), "--url", "http://localhost:8100/good",
        "--backend", "mock", "--runs-root", str(tmp_path),
    ])
    assert result.exit_code == 2, result.output
    assert "fixtures/specs" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_계획만_만들_때도_같다(tmp_path):
    mine = tmp_path / "my_spec.pdf"
    shutil.copy("fixtures/specs/login_spec.pdf", mine)
    result = runner.invoke(app, [
        "run", "--pdf", str(mine), "--url", "http://localhost:8100/good",
        "--backend", "mock", "--runs-root", str(tmp_path), "--plan-only",
    ])
    assert result.exit_code == 2, result.output
    assert "fixtures/specs" in result.output


def test_mock_실행은_설계_문서_경고를_지어내지_않는다(tmp_path, monkeypatch):
    """mock 에 제목 다듬기 응답이 없어서 매 실행 끝에 '! 설계 문서 경고: 케이스
    제목 다듬기를 건너뛰었습니다' 가 떴다. 기획서에는 아무 문제가 없는데 문서를
    의심하게 만든다. 사용자가 고른 mock 은 제목을 다듬지 않을 뿐이다 — 그 사실은
    'mock 백엔드로 실행합니다' 안내가 이미 말한다."""
    from prova.llm.factory import make_llm

    llm, notes = make_llm("mock", {}, "fixtures/specs/login_spec.pdf")
    assert any("mock" in n for n in notes)
    raw = llm.complete_json(system="", user="",
                            schema={"title": "CaseTitles"}, max_tokens=10)
    assert raw == {"titles": []}


def test_직접_준_설정_파일이_없으면_멈춘다(tmp_path):
    """오타 난 --config 를 조용히 기본값으로 대신하면, 사용자는 자기 설정이
    적용됐다고 믿는다."""
    result = runner.invoke(app, [
        "run", "--pdf", "fixtures/specs/login_spec.pdf",
        "--url", "http://localhost:8100/good", "--backend", "mock",
        "--config", str(tmp_path / "nope.yaml"), "--runs-root", str(tmp_path),
    ])
    assert result.exit_code == 2
    assert "nope.yaml" in result.output


@pytest.mark.parametrize("flag,value", [("--backend", "vlm"), ("--engine", "graf")])
def test_선택지_오타는_실행_전에_잡는다(tmp_path, flag, value, monkeypatch):
    called = []
    monkeypatch.setattr("prova.llm.factory.make_llm",
                        lambda *a: called.append(a))
    result = runner.invoke(app, [
        "run", "--pdf", "fixtures/specs/login_spec.pdf",
        "--url", "http://localhost:8100/good", flag, value,
        "--runs-root", str(tmp_path),
    ])
    assert result.exit_code == 2
    assert value in result.output
    assert called == []  # 모델 서버 확인까지 가지 않는다


def test_로그인_화면에_닿지_않으면_한_줄로_알린다(tmp_path):
    result = runner.invoke(app, [
        "login", "--url", "http://127.0.0.1:9/login", "--out", str(tmp_path / "s.json"),
    ])
    assert result.exit_code == 2
    assert "연결할 수 없습니다" in result.output
