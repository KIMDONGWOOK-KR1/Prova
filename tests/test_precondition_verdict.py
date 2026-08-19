"""전제 실패는 '이 화면의 결함' 이 아니다 (스펙 §3-6·§3-7).

로그인이 깨지면 로그인 화면 케이스가 이미 FAIL 을 낸다. 상품등록 케이스들의
전제 실패를 그 화면의 결함으로 합치면 같은 결함이 여러 화면의 결함처럼 읽힌다.
"""
from pathlib import Path

from prova.models import (Expectation, ScreenSpec, SpecDocument, StepResult,
                          TestCase, TestStep)
from prova.s5_verifier.assertion_engine import PageState, verify


def _case():
    return TestCase(case_id="product-price-numeric-001", screen_id="product",
                    title="가격 숫자 검증", type="negative",
                    setup_steps=[TestStep(seq=1, action="navigate", target="/login")],
                    steps=[TestStep(seq=1, action="navigate", target="/product")],
                    expected=Expectation(type="error_shown"))


def test_setup_실패는_precondition_failed_로_분류된다():
    results = [StepResult(seq=1, action="click", target="로그인",
                          status="error", phase="setup",
                          error_code="element_not_found")]
    verdict = verify(_case(), results, PageState(url="x", text=""))
    assert verdict.verdict == "FAIL"
    assert verdict.failure_category == "precondition_failed"
    assert "전제" in verdict.failure_detail


def test_test_스텝_실패는_기존_분류를_유지한다():
    results = [StepResult(seq=1, action="navigate", target="/product",
                          status="ok", phase="setup"),
               StepResult(seq=2, action="input", target="가격",
                          status="error", phase="test",
                          error_code="element_not_found")]
    verdict = verify(_case(), results, PageState(url="x", text=""))
    assert verdict.failure_category != "precondition_failed"


class TestPreconditionUnmetVerdict:
    """전제 스텝 자체를 만들 수 없었던 케이스(I2) — 브라우저 없이 판정을
    합성하는 nodes._precondition_unmet_verdict 를 값만으로 시험한다.

    run_cases 전체(브라우저·페이지 필요)는 여기서 돌리지 않는다 — 이 함수가
    실행 없이 만드는 Verdict 의 필드가 옳은지만 확인하면, '실행을 건너뛴다'
    는 사실 자체는 이 함수를 부르는 자리(nodes.run_cases 의 continue 분기)가
    한 줄로 보장한다.
    """

    def test_실행하지_않고_precondition_failed_를_합성한다(self):
        from prova.nodes import AgentState, _precondition_unmet_verdict

        screen = ScreenSpec(screen_id="product", screen_name="상품 등록",
                            url_path="/product")
        screen.warnings.append(
            "로그인 화면(login)에서 이메일/비밀번호/제출 요소를 찾지 못해 "
            "전제 스텝을 만들지 못했습니다."
        )
        doc = SpecDocument(screens=[screen])
        case = TestCase(
            case_id="product-valid-001", screen_id="product", title="정상 상품 등록",
            type="positive", precondition_unmet=True,
            expected=Expectation(type="toast_or_redirect"),
        )
        state = AgentState(pdf_path="x", base_url="http://x", run_id="r",
                           run_dir=Path("."), doc=doc)

        verdict = _precondition_unmet_verdict(state, case)

        assert verdict.verdict == "FAIL"
        assert verdict.failure_category == "precondition_failed"
        assert verdict.step_results == []
        assert verdict.elapsed_ms == 0
        assert "실행하지 않았습니다" in verdict.failure_detail
        assert "이메일/비밀번호/제출 요소를 찾지 못해" in verdict.failure_detail

    def test_해당하는_경고를_못_찾으면_사유_미상으로_남긴다(self):
        """screen.warnings 에 그 문장이 없어도(방어적 상황) 예외 없이 판정한다."""
        from prova.nodes import AgentState, _precondition_unmet_verdict

        screen = ScreenSpec(screen_id="product", screen_name="상품 등록",
                            url_path="/product")
        doc = SpecDocument(screens=[screen])
        case = TestCase(
            case_id="product-valid-001", screen_id="product", title="정상 상품 등록",
            type="positive", precondition_unmet=True,
            expected=Expectation(type="toast_or_redirect"),
        )
        state = AgentState(pdf_path="x", base_url="http://x", run_id="r",
                           run_dir=Path("."), doc=doc)

        verdict = _precondition_unmet_verdict(state, case)
        assert verdict.failure_category == "precondition_failed"
        assert "사유 미상" in verdict.failure_detail
