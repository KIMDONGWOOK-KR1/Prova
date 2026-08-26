"""plan_store — 계획(S1~S2 산출물) 저장·복원.

## 왜 이 테스트가 있는가

한 GPU 에서 7B(추출)와 VL(탐지)을 시간분할로 쓰려면 서버 교체 사이에 S1~S2
산출물이 파일로 살아남아야 한다. 저장·복원이 산출물을 조금이라도 바꾸면
"승인한 계획과 다른 것이 도는" 사고가 되므로, 왕복 동등성이 첫 번째 계약이다.

## cases 를 본문으로 두 번 저장하지 않는다

plan.json 은 all_cases(전체 본문) + selected_case_ids(선택 목록)만 담는다.
선택된 케이스 본문을 따로 저장하면 두 목록이 어긋날 자리가 생긴다 — 복원은
항상 all_cases 에서 id 로 골라낸다.
"""

from __future__ import annotations

import json

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import build_plan
from prova.plan_store import PLAN_FILENAME, PlanError, load_plan, plan_warnings, save_plan

SPEC_PDF = "fixtures/specs/login_spec.pdf"


@pytest.fixture()
def planned_state(tmp_path):
    """MockLLM 으로 S1~S2 까지 돌린 상태 (브라우저 없음)."""
    state, n_all = build_plan(
        pdf_path=SPEC_PDF,
        base_url="http://localhost:8100/good",
        llm=MockLLM.with_login_fixtures(),
        run_id="plan-test",
        run_dir=tmp_path / "plan-test",
    )
    return state, n_all


class TestRoundTrip:
    def test_저장_복원_동등(self, planned_state, tmp_path):
        state, n_all = planned_state
        save_plan(state, n_all=n_all, only=None)

        plan = load_plan(state.run_dir)

        assert plan.doc == state.doc
        assert plan.all_cases == state.all_cases
        assert plan.selected_case_ids == [c.case_id for c in state.cases]
        assert plan.selection == state.selection
        assert plan.coverage_gaps == state.coverage_gaps
        assert plan.design_mismatches == state.design_mismatches
        assert plan.base_url == "http://localhost:8100/good"
        assert plan.pdf_path == SPEC_PDF
        assert plan.n_all == n_all

    def test_백엔드_이름과_시각이_남는다(self, planned_state):
        """리포트가 '추출을 누가 했는가' 를 말하려면 계획이 그 사실을 담아야 한다."""
        state, n_all = planned_state
        save_plan(state, n_all=n_all, only=None)

        plan = load_plan(state.run_dir)

        assert plan.backend == state.llm.name
        assert plan.created_at  # ISO 문자열이면 된다 — 형식은 리포트가 소비한다

    def test_pdf_해시가_저장된다(self, planned_state):
        state, n_all = planned_state
        save_plan(state, n_all=n_all, only=None)

        plan = load_plan(state.run_dir)

        assert len(plan.pdf_sha256) == 64  # sha256 hex

    def test_only_필터가_보존된다(self, tmp_path):
        """부분 실행 사실은 리포트까지 가야 한다 — 재개 시점엔 --only 를 다시 받지 않는다."""
        state, n_all = build_plan(
            pdf_path=SPEC_PDF,
            base_url="http://localhost:8100/good",
            llm=MockLLM.with_login_fixtures(),
            run_id="plan-only-test",
            run_dir=tmp_path / "plan-only-test",
            only="required",
        )
        save_plan(state, n_all=n_all, only="required")

        plan = load_plan(state.run_dir)

        assert plan.only == "required"
        assert len(plan.selected_case_ids) < n_all
        # 선택 목록은 all_cases 의 부분집합이어야 복원이 성립한다
        all_ids = {c.case_id for c in plan.all_cases}
        assert set(plan.selected_case_ids) <= all_ids


class TestErrors:
    def test_plan_json_부재는_명확한_에러(self, tmp_path):
        with pytest.raises(PlanError, match="plan.json"):
            load_plan(tmp_path)

    def test_스키마_버전_불일치는_에러(self, planned_state):
        state, n_all = planned_state
        path = save_plan(state, n_all=n_all, only=None)

        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["schema_version"] = 999
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(PlanError, match="버전"):
            load_plan(state.run_dir)


class TestStaleness:
    def test_pdf_가_바뀌면_경고(self, planned_state, tmp_path, monkeypatch):
        """재개는 pdf 를 다시 읽지 않는다 — 판정이 계획 시점 문서 기준이라는
        사실을 경고가 말해야 한다."""
        state, n_all = planned_state
        path = save_plan(state, n_all=n_all, only=None)

        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["pdf_sha256"] = "0" * 64  # 계획 시점 해시가 지금 파일과 다르다
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        warnings = plan_warnings(load_plan(state.run_dir))

        assert any("바뀌었" in w or "다릅니다" in w for w in warnings)

    def test_pdf_그대로면_경고_없음(self, planned_state):
        state, n_all = planned_state
        save_plan(state, n_all=n_all, only=None)

        assert plan_warnings(load_plan(state.run_dir)) == []

    def test_pdf_가_사라져도_경고만(self, planned_state):
        """파일 부재는 오류가 아니다 — 재개는 pdf 없이 성립한다."""
        state, n_all = planned_state
        save_plan(state, n_all=n_all, only=None)

        plan = load_plan(state.run_dir)
        plan.pdf_path = "없는/경로.pdf"

        warnings = plan_warnings(plan)
        assert warnings and any("찾을 수 없" in w for w in warnings)


def test_plan_파일_이름은_상수다(planned_state):
    """CLI·서버가 같은 이름을 봐야 한다."""
    state, n_all = planned_state
    path = save_plan(state, n_all=n_all, only=None)
    assert path.name == PLAN_FILENAME
