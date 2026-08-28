"""CLI 가 낡은 대상을 상대로 실행을 시작하지 않는다.

## 왜 입구에서 막는가

낡은 대상에서 나온 FAIL 은 구현의 결함이 아니라 잰 대상이 옛것이라서 난
것인데, 리포트만 보면 둘은 구별되지 않는다. 실행이 끝난 뒤에 알려 주면 이미
사람이 그 FAIL 을 쫓기 시작한 뒤다 — 2026-08-27 에 두 번 그랬다.

## 무엇은 막지 않는가

`--plan-only` 는 대상을 건드리지 않는다. 두 단계 실행은 **서버를 교체하려고**
나눈 것이라 계획 시점에는 대상이 아직 없거나 다른 것이어도 정상이다. 여기서
물으면 정상적인 사용이 막힌다.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from prova.cli import app
from prova.sut_build import BuildCheck

SPEC_PDF = "fixtures/specs/login_spec.pdf"
runner = CliRunner()


@pytest.fixture
def spy(monkeypatch):
    """빌드 확인을 가로채 호출을 세고 정해진 결과를 돌려준다."""
    calls: list[str] = []
    box = {"result": BuildCheck("match", "SUT 빌드 확인: 일치")}

    def fake(base_url, **kw):
        calls.append(base_url)
        return box["result"]

    monkeypatch.setattr("prova.cli.check_sut_build", fake)
    fake.calls = calls  # type: ignore[attr-defined]
    fake.box = box  # type: ignore[attr-defined]
    return fake


def _run(tmp_path, *extra, run_id="cli-build"):
    return runner.invoke(app, [
        "run", "--pdf", SPEC_PDF, "--url", "http://localhost:8100/good",
        "--backend", "mock", "--run-id", run_id, "--runs-root", str(tmp_path),
        *extra,
    ])


class TestStale:
    def test_어긋나면_실행을_시작하지_않는다(self, tmp_path, spy):
        spy.box["result"] = BuildCheck(
            "stale", "SUT 가 자기 소스보다 낡았습니다 — 재시작하세요.")
        result = _run(tmp_path)
        assert result.exit_code != 0
        assert "재시작" in result.output
        assert not (tmp_path / "cli-build").exists()

    def test_대상_URL_로_묻는다(self, tmp_path, spy):
        spy.box["result"] = BuildCheck("stale", "낡았습니다 — 재시작하세요.")
        _run(tmp_path)
        assert spy.calls == ["http://localhost:8100/good"]


class TestPlanOnly:
    def test_계획만_만들_때는_묻지_않는다(self, tmp_path, spy):
        """대상이 아직 없어도 계획은 만들어져야 한다."""
        result = _run(tmp_path, "--plan-only", run_id="cli-build-plan")
        assert result.exit_code == 0, result.output
        assert spy.calls == []
