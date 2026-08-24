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
