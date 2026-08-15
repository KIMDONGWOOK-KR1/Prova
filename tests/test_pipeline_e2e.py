"""파이프라인 관통 테스트 — 1차 목표의 수용 기준을 코드로 고정한다.

## 이 테스트가 지키는 것

계획서의 수용 기준 그대로다.

    1. good (기획서 준수 구현) -> 전 케이스 PASS
    2. bad  (의도적 불일치 구현) -> 심어둔 불일치를 정확히 FAIL 로 지목
    3. bad 에서 오탐 0건 — 심지 않은 항목이 FAIL 로 나오면 안 된다
    4. 리포트에 기대·실제·스크린샷이 모두 들어 있다

3번이 실질적으로 가장 중요하다. 오탐이 나오는 QA 도구는 개발자가 신뢰하지 않게
되고, 그러면 진짜 결함 보고까지 무시된다.

## SUT 를 테스트가 직접 띄운다

외부에서 띄워 둔 서버에 의존하면 테스트가 환경에 따라 통과·실패를 오간다.
uvicorn 을 스레드로 올려 테스트가 수명을 소유한다.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/login_spec.pdf"

# bad 변형에 심은 의도적 불일치 (sut/app.py 참고).
#
# B1  비밀번호 복잡도 검증 미구현 -> min_length·require_uppercase·require_special
# B2  이메일 형식 검증 누락      -> format
#
# required 는 bad 에도 구현돼 있으므로 이 목록에 없다. 그게 오탐 검증의 근거가
# 된다 — 구현된 규칙은 PASS 로 나와야 한다.
EXPECTED_BAD_FAILURES = {"format", "min_length", "require_uppercase", "require_special"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def sut_base() -> str:
    """SUT 를 백그라운드 스레드로 띄우고 base URL(변형 제외)을 돌려준다."""
    from sut.app import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("SUT 서버가 기동하지 않았습니다")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


def _run(variant: str, sut_base: str, tmp_path):
    report, run_dir = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.with_login_fixtures(),
        run_id=f"test-{variant}",
        runs_root=tmp_path,
    )
    return report, run_dir


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("bad"))


class TestGoodVariant:
    """기획서를 지킨 구현은 전부 통과해야 한다."""

    def test_전_케이스_통과(self, good_run):
        report, _ = good_run
        failures = [v for v in report.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.violates}: {v.failure_detail}" for v in failures)
        )
        assert report.summary["pass_rate"] == 100.0

    def test_케이스가_생성됐다(self, good_run):
        """0건 통과를 100% 통과로 착각하지 않게 한다."""
        report, _ = good_run
        assert report.summary["total"] == 7
        assert sum(1 for v in report.cases if v.type == "negative") == 6


class TestBadVariant:
    """의도적 불일치를 정확히 짚어내야 한다."""

    def test_심어둔_불일치를_모두_잡는다(self, bad_run):
        report, _ = bad_run
        failed_rules = {v.violates for v in report.cases if v.verdict == "FAIL"}
        missed = EXPECTED_BAD_FAILURES - failed_rules
        assert not missed, f"놓친 불일치(미탐): {missed}"

    def test_오탐이_없다(self, bad_run):
        """심지 않은 항목이 FAIL 로 나오면 안 된다. 오탐은 미탐보다 치명적이다."""
        report, _ = bad_run
        failed_rules = {v.violates for v in report.cases if v.verdict == "FAIL"}
        false_positives = failed_rules - EXPECTED_BAD_FAILURES
        assert not false_positives, f"오탐: {false_positives}"

    def test_구현된_규칙은_통과한다(self, bad_run):
        """bad 에도 required 검증은 있다. 같은 리포트 안에 '구현된 규칙은 PASS,
        누락된 규칙은 FAIL' 이 함께 나와야 판정을 신뢰할 수 있다."""
        report, _ = bad_run
        required_cases = [v for v in report.cases if v.violates == "required"]
        assert len(required_cases) == 2
        assert all(v.verdict == "PASS" for v in required_cases)

    def test_정상_로그인은_통과한다(self, bad_run):
        """검증 로직이 빠졌어도 정상 경로는 동작한다. 이게 FAIL 이면
        테스트 데이터나 탐지 문제이지 불일치 탐지가 아니다."""
        report, _ = bad_run
        positive = next(v for v in report.cases if v.type == "positive")
        assert positive.verdict == "PASS", positive.failure_detail

    def test_실패에_위반규칙과_분류가_붙는다(self, bad_run):
        """개발자가 어느 검증 로직을 추가해야 하는지 알 수 있어야 한다."""
        report, _ = bad_run
        for v in (c for c in report.cases if c.verdict == "FAIL"):
            assert v.violates, f"{v.case_id}: 위반 규칙이 없다"
            assert v.failure_category, f"{v.case_id}: 실패 분류가 없다"
            assert v.violates in v.failure_detail, f"{v.case_id}: 설명에 규칙이 없다"


class TestReportCompleteness:
    """명세서 §9 '리포트 완결성 100%'."""

    def test_모든_케이스에_근거가_있다(self, bad_run):
        report, _ = bad_run
        for v in report.cases:
            for key in ("expected", "actual", "url"):
                assert v.evidence.get(key), f"{v.case_id}: evidence.{key} 누락"

    def test_스텝마다_스크린샷이_남는다(self, bad_run):
        report, run_dir = bad_run
        for v in report.cases:
            assert v.step_results, f"{v.case_id}: 스텝 결과가 없다"
            for r in v.step_results:
                assert r.screenshot, f"{v.case_id} step{r.seq}: 스크린샷 없음"
                assert (run_dir / r.screenshot).exists(), (
                    f"{v.case_id} step{r.seq}: 파일이 실제로 없다 — {r.screenshot}"
                )

    def test_스크린샷_경로가_리포트_기준_상대경로다(self, bad_run):
        """report.html 에서 상대 링크로 열려야 한다. 절대 경로나 역슬래시가
        섞이면 브라우저에서 이미지가 깨진다."""
        report, _ = bad_run
        for v in report.cases:
            for r in v.step_results:
                assert not r.screenshot.startswith(("/", "C:", "c:"))
                assert "\\" not in r.screenshot

    def test_리포트_파일이_생성된다(self, bad_run):
        _, run_dir = bad_run
        assert (run_dir / "report.json").exists()
        html = (run_dir / "report.html").read_text(encoding="utf-8")
        assert "Prova 검증 리포트" in html
        assert "실패 케이스 (4)" in html

    def test_백엔드가_리포트에_기록된다(self, bad_run):
        """mock 으로 돌린 결과를 실제 검증 결과로 착각하는 사고를 막는다."""
        report, run_dir = bad_run
        assert report.summary["llm_backend"] == "mock"
        html = (run_dir / "report.html").read_text(encoding="utf-8")
        assert "mock 백엔드로 실행된 리포트입니다" in html


class TestGroundingQuality:
    """selector 탐지가 실제로 동작했는지 — 1차 목표의 전제."""

    def test_모든_조작_스텝이_요소를_찾았다(self, good_run):
        report, _ = good_run
        for v in report.cases:
            for r in v.step_results:
                if r.action in ("fill", "click"):
                    assert r.location is not None, f"{v.case_id} step{r.seq}"
                    assert r.location.method == "selector"

    def test_탐지_전략이_기록된다(self, good_run):
        """명세서 §9 의 'selector vs VLM 탐지 성공률 비교' 를 하려면 어느
        전략이 적중했는지 남아 있어야 한다."""
        report, _ = good_run
        strategies = {
            r.location.strategy
            for v in report.cases for r in v.step_results if r.location
        }
        assert strategies == {"label", "role"}
