"""두 단계 실행(계획 저장 → 재개) 관통 — 한 GPU 시간분할의 수용 기준.

## 지키는 것

1. 계획 저장 → 재개로 이은 실행이 **한 번에 돌린 실행과 같은 판정**을 낸다.
   저장·복원이 산출물을 바꾸면 승인한 계획과 다른 것이 도는 사고다.
2. 재개는 **LLM 없이** 성립한다 — S3~S6 은 LLM 을 쓰지 않는다는 사실이
   이 기능의 존재 근거다 (7B 를 내리고 VL 을 올린 뒤에 돌아야 한다).
3. 리포트가 두 단계 실행이라는 사실과 추출 백엔드를 말한다 — 어느 모델이
   추출했는지 모르는 리포트는 mock 실행을 실제로 착각하는 사고와 같은 부류다.

SUT 는 conftest.py 의 sut_base 픽스처가 띄운다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import plan_pipeline, resume_pipeline, run_pipeline
from prova.plan_store import PLAN_FILENAME

SPEC_PDF = "fixtures/specs/login_spec.pdf"


def _verdict_map(report):
    return {v.case_id: v.verdict for v in report.cases}


@pytest.fixture(scope="module")
def two_stage_run(sut_base, tmp_path_factory):
    """계획 저장 → (서버 교체 자리) → 재개."""
    runs_root = tmp_path_factory.mktemp("two-stage")
    state, plan_path = plan_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/bad",
        llm=MockLLM.with_login_fixtures(),
        run_id="two-stage",
        runs_root=runs_root,
    )
    # 여기서 실제 운용은 7B 를 내리고 VL 을 올린다 — 재개는 LLM 없이 돈다.
    report, run_dir = resume_pipeline(runs_root / "two-stage")
    return state, plan_path, report, run_dir


@pytest.fixture(scope="module")
def direct_run(sut_base, tmp_path_factory):
    report, run_dir = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/bad",
        llm=MockLLM.with_login_fixtures(),
        run_id="direct",
        runs_root=tmp_path_factory.mktemp("direct"),
    )
    return report, run_dir


class TestPlanOnly:
    def test_plan_json_이_남는다(self, two_stage_run):
        _, plan_path, _, _ = two_stage_run
        assert plan_path.name == PLAN_FILENAME
        assert plan_path.exists()

    def test_계획_단계는_브라우저를_열지_않는다(self, sut_base, tmp_path):
        """plan_pipeline 이 리포트를 만들면 안 된다 — 실행 전이다."""
        state, plan_path = plan_pipeline(
            pdf_path=SPEC_PDF,
            base_url=f"{sut_base}/good",
            llm=MockLLM.with_login_fixtures(),
            run_id="plan-no-browser",
            runs_root=tmp_path,
        )
        assert state.report is None
        assert not (plan_path.parent / "report.json").exists()


class TestResumeParity:
    def test_판정이_직접_실행과_동일(self, two_stage_run, direct_run):
        _, _, resumed_report, _ = two_stage_run
        direct_report, _ = direct_run
        assert _verdict_map(resumed_report) == _verdict_map(direct_report)

    def test_요약_수치도_동일(self, two_stage_run, direct_run):
        _, _, resumed_report, _ = two_stage_run
        direct_report, _ = direct_run
        for key in ("total", "pass", "fail", "pass_rate"):
            assert resumed_report.summary[key] == direct_report.summary[key]

    def test_리포트가_같은_run_dir_에_남는다(self, two_stage_run):
        """한 실행으로 남아야 한다 — 계획과 리포트가 한 디렉터리다."""
        _, plan_path, _, run_dir = two_stage_run
        assert plan_path.parent == run_dir
        assert (run_dir / "report.json").exists()
        assert (run_dir / "report.html").exists()


class TestProvenance:
    def test_추출_백엔드가_리포트에_남는다(self, two_stage_run):
        """재개는 llm=None 으로 돈다 — 그래도 리포트는 계획 시점 백엔드를 말해야 한다."""
        _, _, report, _ = two_stage_run
        assert report.summary["llm_backend"] == "mock"

    def test_두_단계_실행_사실이_리포트에_남는다(self, two_stage_run):
        _, _, report, _ = two_stage_run
        plan_info = report.summary["plan"]
        assert plan_info["backend"] == "mock"
        assert plan_info["created_at"]

    def test_직접_실행에는_plan_상자가_없다(self, direct_run):
        report, _ = direct_run
        assert "plan" not in report.summary

    def test_문서_변경_경고가_리포트까지_간다(self, sut_base, tmp_path):
        import json

        state, plan_path = plan_pipeline(
            pdf_path=SPEC_PDF,
            base_url=f"{sut_base}/good",
            llm=MockLLM.with_login_fixtures(),
            run_id="stale",
            runs_root=tmp_path,
        )
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        raw["pdf_sha256"] = "0" * 64
        plan_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        report, _ = resume_pipeline(tmp_path / "stale")

        assert any("바뀌었" in w for w in report.summary["plan"]["warnings"])
