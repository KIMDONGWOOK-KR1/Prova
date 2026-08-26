"""CLI 의 두 단계 실행 배선 — --plan-only 와 --resume.

## 왜 CLI 검증이 따로 있는가

파이프라인 관통은 test_two_stage_e2e 가 지킨다. 여기는 CLI 가 지켜야 하는
것들이다: 계획 시점 인자를 재개에 다시 주면 **조용히 무시하지 않고 에러**로
막는다 — 승인한 계획과 다른 것이 도는 사고를 입구에서 끊는 자리다.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from prova.cli import app

SPEC_PDF = "fixtures/specs/login_spec.pdf"

runner = CliRunner()


def _plan_only(tmp_path, run_id="cli-plan"):
    return runner.invoke(app, [
        "run", "--pdf", SPEC_PDF, "--url", "http://localhost:8100/good",
        "--backend", "mock", "--plan-only",
        "--run-id", run_id, "--runs-root", str(tmp_path),
    ])


class TestPlanOnly:
    def test_plan_json_을_남기고_리포트_없이_끝난다(self, tmp_path):
        result = _plan_only(tmp_path)
        assert result.exit_code == 0, result.output
        assert (tmp_path / "cli-plan" / "plan.json").exists()
        assert not (tmp_path / "cli-plan" / "report.json").exists()

    def test_다음_명령을_안내한다(self, tmp_path):
        """서버 교체 후 무엇을 치면 되는지가 출력에 있어야 한다."""
        result = _plan_only(tmp_path)
        assert "--resume" in result.output

    def test_vlm_과_함께_쓸_수_없다(self, tmp_path):
        result = runner.invoke(app, [
            "run", "--pdf", SPEC_PDF, "--url", "http://x", "--backend", "mock",
            "--plan-only", "--vlm", "http://localhost:8001/v1",
        ])
        assert result.exit_code == 2
        assert "함께 쓸 수 없습니다" in result.output

    def test_graph_엔진과_함께_쓸_수_없다(self, tmp_path):
        result = runner.invoke(app, [
            "run", "--pdf", SPEC_PDF, "--url", "http://x", "--backend", "mock",
            "--plan-only", "--engine", "graph",
        ])
        assert result.exit_code == 2
        assert "pipeline 엔진" in result.output


class TestResumeConflicts:
    """계획 시점 인자는 재개에서 다시 받지 않는다 — 조용한 무시가 아니라 에러다."""

    @pytest.mark.parametrize("extra", [
        ["--pdf", SPEC_PDF],
        ["--url", "http://localhost:8100/good"],
        ["--request", "로그인 확인"],
        ["--only", "required"],
        ["--backend", "mock"],
        ["--run-id", "other"],
        ["--plan-only"],
    ])
    def test_계획_시점_인자는_에러(self, tmp_path, extra):
        result = runner.invoke(app, ["run", "--resume", str(tmp_path)] + extra)
        assert result.exit_code == 2
        assert "함께 쓸 수 없습니다" in result.output

    def test_plan_json_이_없으면_명확한_에러(self, tmp_path):
        result = runner.invoke(app, ["run", "--resume", str(tmp_path)])
        assert result.exit_code == 2
        assert "plan.json" in result.output


class TestUrlRequired:
    def test_resume_아니면_url_필수(self):
        result = runner.invoke(app, ["run", "--pdf", SPEC_PDF, "--backend", "mock"])
        assert result.exit_code == 2
        assert "--url" in result.output


class TestResumeRun:
    def test_계획_저장_후_재개가_리포트를_만든다(self, sut_base, tmp_path):
        plan = runner.invoke(app, [
            "run", "--pdf", SPEC_PDF, "--url", f"{sut_base}/good",
            "--backend", "mock", "--plan-only",
            "--run-id", "cli-two-stage", "--runs-root", str(tmp_path),
        ])
        assert plan.exit_code == 0, plan.output

        result = runner.invoke(app, [
            "run", "--resume", str(tmp_path / "cli-two-stage"),
        ])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "cli-two-stage" / "report.json").exists()
        # 재개 실행이 계획의 대상 URL 을 그대로 쓴다는 사실이 출력에 보인다
        assert f"{sut_base}/good" in result.output
