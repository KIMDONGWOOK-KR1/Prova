"""Figma 경로 관통 — 합성 응답으로 계획 수립과 SUT 판정까지 (specs/2026-08-25).

MockLLM 조차 없다 — figma 경로는 LLM 을 부르지 않는 것이 계약이다.
합성 응답의 문구는 SUT good 과 일치한다 — 디자인이 구현과 다르면 FAIL 이
맞다는 것이 이 경로의 존재 이유이므로, good 픽스처는 구현과 일치해야 한다.
"""

import pytest

from prova.pipeline import build_plan, run_pipeline

FIXTURE = "fixtures/figma/synthetic_login_signup.json"
URLS = {"로그인": "/login", "회원가입": "/signup"}


class TestPlan:
    def test_LLM_없이_계획이_선다(self, tmp_path):
        state, n_all = build_plan(
            pdf_path="", base_url="http://x", llm=None, run_id="t",
            run_dir=tmp_path, figma_json=FIXTURE, screen_urls=URLS,
        )
        assert n_all > 0
        assert all(c.expected.type in
                   ("labels_findable", "placeholders_match", "options_present")
                   for c in state.cases)

    def test_흐름은_추출되지만_케이스는_없다(self, tmp_path):
        state, _ = build_plan(
            pdf_path="", base_url="http://x", llm=None, run_id="t",
            run_dir=tmp_path, figma_json=FIXTURE, screen_urls=URLS,
        )
        assert state.doc.flows  # 가입하기 -> 로그인 연결
        assert not any(c.flow_id for c in state.cases)

    def test_매핑_없는_화면의_케이스는_없고_경고가_남는다(self, tmp_path):
        state, _ = build_plan(
            pdf_path="", base_url="http://x", llm=None, run_id="t",
            run_dir=tmp_path, figma_json=FIXTURE,
            screen_urls={"로그인": "/login"},
        )
        assert not any(c.screen_id == "회원가입" for c in state.cases)
        assert any("경로 매핑" in w for w in state.doc.warnings)


def _run(variant: str, sut_base, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path="", base_url=f"{sut_base}/{variant}", llm=None,
        run_id=f"test-figma-{variant}", runs_root=tmp_path,
        figma_json=FIXTURE, screen_urls=URLS,
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("figma-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("figma-bad"))


class TestGood:
    def test_디자인과_구현이_일치하면_전부_통과한다(self, good_run):
        report, _ = good_run
        fails = [v for v in report.cases if v.verdict == "FAIL"]
        assert not fails, "\n".join(f"{v.case_id}: {v.failure_detail}" for v in fails)
        # 0건 통과가 아니라 실제로 정적 대조가 만들어졌는지까지 —
        # 로그인(labels·placeholders) + 회원가입(labels·placeholders·options)
        assert report.summary["total"] == 5, [c.case_id for c in report.cases]

    def test_리포트가_입력_출처를_말한다(self, good_run):
        _, run_dir = good_run
        html = (run_dir / "report.html").read_text(encoding="utf-8")
        assert "Figma" in html and "정적 대조" in html


class TestBad:
    def test_심은_문구_결함만_잡힌다(self, bad_run):
        """bad 에서 figma 정적 대조가 잡을 수 있는 심은 결함은 두 개다 —
        로그인 이메일 placeholder 가 다르고('아이디를 입력하세요'),
        가입 경로 선택 목록에서 한 항목이 빠졌다(C4). 그 둘만 FAIL 이어야
        한다 — 오탐 0건."""
        report, _ = bad_run
        fails = {v.case_id: v for v in report.cases if v.verdict == "FAIL"}
        assert set(fails) == {"로그인-placeholders-001", "회원가입-options-n2_14-001"}, \
            {cid: v.failure_detail for cid, v in fails.items()}

    def test_실패_사유가_어느_문구가_다른지_말한다(self, bad_run):
        report, _ = bad_run
        ph = next(v for v in report.cases if v.case_id == "로그인-placeholders-001")
        assert "이메일" in (ph.failure_detail or "")
