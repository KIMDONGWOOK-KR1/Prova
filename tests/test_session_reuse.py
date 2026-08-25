"""로그인 세션 재사용 — 스크립트로 로그인할 수 없는 화면을 여는 길 (README 남은 것).

세션(storage_state)을 실으면:
    1. 전제 스텝을 만들 수 없던 케이스(precondition_unmet)도 실행된다 —
       세션이 전제를 대신한다. 이것이 --session 의 존재 이유다(SSO·캡차).
    2. 가드(비로그인 차단) 케이스는 세션 없는 깨끗한 컨텍스트에서 돈다 —
       세션이 실린 페이지에서는 '비로그인 상태' 를 만들 수 없다.
    3. 메인 컨텍스트는 케이스 사이에 쿠키를 지우지 않는다 — 세션이 곧
       의도된 기준 상태다(지우면 세션 자체가 사라진다).
    4. 리포트가 세션 사용 사실을 말한다 — 판정의 전제 조건이므로.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

LOGIN_PDF = "fixtures/specs/login_spec.pdf"
ORDERS_PDF = "fixtures/specs/orders_spec.pdf"


@pytest.fixture(scope="module")
def session_file(sut_base, tmp_path_factory):
    """SUT 에 판매자로 로그인한 storage_state — 'prova login' 이 만드는 것과
    같은 산출물을 테스트에서 스크립트로 만든다."""
    from playwright.sync_api import sync_playwright

    path = tmp_path_factory.mktemp("sess") / "session.json"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{sut_base}/good/login")
        page.fill("input[name=email]", "seller@test.com")
        page.fill("input[name=password]", "Seller1!")
        page.click("button[type=submit]")
        page.wait_for_load_state()
        context.storage_state(path=str(path))
        browser.close()
    return str(path)


@pytest.fixture(scope="module")
def session_run(session_file, sut_base, tmp_path_factory):
    report, run_dir = run_pipeline(
        pdf_path=ORDERS_PDF,
        base_url=f"{sut_base}/good",
        llm=MockLLM.for_document(LOGIN_PDF, ORDERS_PDF),
        run_id="test-session-good",
        runs_root=tmp_path_factory.mktemp("session-run"),
        only="orders",
        storage_state=session_file,
    )
    return report, run_dir


class TestSessionRun:
    def test_세션을_실어도_전부_통과한다(self, session_run):
        report, _ = session_run
        fails = [v for v in report.cases if v.verdict == "FAIL"]
        assert not fails, "\n".join(f"{v.case_id}: {v.failure_detail}" for v in fails)

    def test_가드는_깨끗한_컨텍스트에서_여전히_성립한다(self, session_run):
        """세션이 실린 페이지라면 비로그인 리다이렉트가 일어나지 않아 가드가
        FAIL(오탐)이 된다 — 통과했다는 것이 곧 깨끗한 컨텍스트의 증거다."""
        report, _ = session_run
        guard = next(v for v in report.cases if "precondition-guard" in v.case_id)
        assert guard.verdict == "PASS", guard.failure_detail

    def test_리포트가_세션_사용을_말한다(self, session_run):
        report, run_dir = session_run
        assert report.summary["session_file"] == "session.json"
        html = (run_dir / "report.html").read_text(encoding="utf-8")
        assert "세션" in html and "비로그인" in html


class TestPreconditionUnmet:
    """전제 스텝을 만들 수 없던 케이스 — 세션이 있으면 실행된다."""

    def _unmet_case(self):
        from prova.models import Expectation, TestCase, TestStep
        return TestCase(
            case_id="orders-valid-001", screen_id="orders",
            title="정상 주문 조회", type="positive",
            precondition_unmet=True,
            steps=[TestStep(seq=1, action="navigate", target="/orders")],
            expected=Expectation(type="text_visible", value="주문조회"),
        )

    def _run_one(self, sut_base, tmp_path, storage_state):
        from playwright.sync_api import sync_playwright
        from prova.models import ScreenSpec
        from prova.nodes import AgentState, run_cases

        doc_screen = ScreenSpec(screen_id="orders", screen_name="주문 조회",
                                url_path="/orders")
        from prova.models import SpecDocument
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(storage_state=storage_state)
            state = AgentState(
                pdf_path="", base_url=f"{sut_base}/good", run_id="t",
                run_dir=tmp_path, page=context.new_page(),
                doc=SpecDocument(source="x", screens=[doc_screen]),
                cases=[self._unmet_case()],
                storage_state=storage_state,
            )
            state = run_cases(state)
            browser.close()
        return state.verdicts[0]

    def test_세션이_없으면_실행하지_않고_precondition_failed(self, sut_base, tmp_path):
        v = self._run_one(sut_base, tmp_path, storage_state=None)
        assert v.failure_category == "precondition_failed"

    def test_세션이_있으면_실행되고_통과한다(self, sut_base, tmp_path, session_file):
        v = self._run_one(sut_base, tmp_path, storage_state=session_file)
        assert v.verdict == "PASS", v.failure_detail
