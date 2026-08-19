"""전제 실패는 '이 화면의 결함' 이 아니다 (스펙 §3-6·§3-7).

로그인이 깨지면 로그인 화면 케이스가 이미 FAIL 을 낸다. 상품등록 케이스들의
전제 실패를 그 화면의 결함으로 합치면 같은 결함이 여러 화면의 결함처럼 읽힌다.
"""
from prova.models import Expectation, StepResult, TestCase, TestStep
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
    assert verdict.category == "precondition_failed"
    assert "전제" in verdict.reason


def test_test_스텝_실패는_기존_분류를_유지한다():
    results = [StepResult(seq=1, action="navigate", target="/product",
                          status="ok", phase="setup"),
               StepResult(seq=2, action="input", target="가격",
                          status="error", phase="test",
                          error_code="element_not_found")]
    verdict = verify(_case(), results, PageState(url="x", text=""))
    assert verdict.category != "precondition_failed"
