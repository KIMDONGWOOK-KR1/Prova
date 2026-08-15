"""assertion_engine 테스트 — negative 케이스의 뒤집힌 판정을 못 박는다.

negative 케이스는 **에러가 떠야 PASS** 다. 규칙을 위반한 값을 넣었으니 기획서
대로면 에러가 노출돼야 하고, 그냥 통과됐다면 구현이 규칙을 강제하지 않는
것이므로 FAIL 이다. 직관과 반대라서 회귀가 나기 쉬운 지점이다.
"""

import pytest

from prova.models import Expectation, StepResult, TestCase, TestStep
from prova.s5_verifier.assertion_engine import PageState, verify

PW_MESSAGE = "비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다."


def steps_ok(n: int = 4) -> list[StepResult]:
    return [StepResult(seq=i, action="fill", target="t", status="ok", elapsed_ms=10,
                       screenshot=f"runs/x/step{i}.png")
            for i in range(1, n + 1)]


def negative_case(expected: Expectation, violates: str = "require_uppercase") -> TestCase:
    return TestCase(
        case_id="c-neg", screen_id="login", title="위반 케이스", type="negative",
        violates=violates, target_element="password",
        steps=[TestStep(seq=1, action="navigate", target="/login")],
        expected=expected,
    )


def positive_case(expected: Expectation) -> TestCase:
    return TestCase(
        case_id="c-pos", screen_id="login", title="정상 케이스", type="positive",
        steps=[TestStep(seq=1, action="navigate", target="/login")],
        expected=expected,
    )


def state(url="http://h/good/login", text="", errors=None, console=None) -> PageState:
    return PageState(url=url, text=text or "", error_texts=errors or [],
                     console_errors=console or [])


class TestNegativeErrorMessage:
    """기획서가 지정한 에러 문구가 떠야 PASS."""

    def test_기대_문구가_뜨면_PASS(self):
        case = negative_case(Expectation(type="error_message", value=PW_MESSAGE))
        v = verify(case, steps_ok(), state(text=f"로그인 {PW_MESSAGE}", errors=[PW_MESSAGE]))
        assert v.verdict == "PASS"

    def test_에러가_아예_안_뜨면_FAIL(self):
        """규칙 검증이 구현에 없다는 뜻 — Prova 가 잡아내야 하는 바로 그 상황."""
        case = negative_case(Expectation(type="error_message", value=PW_MESSAGE))
        v = verify(case, steps_ok(), state(url="http://h/bad/dashboard", text="환영합니다"))
        assert v.verdict == "FAIL"
        assert v.failure_category == "assertion_mismatch"
        assert "require_uppercase" in v.failure_detail
        assert "강제하지 않는다" in v.evidence["actual"]

    def test_다른_문구가_뜨면_FAIL하고_실제_문구를_남긴다(self):
        """구현이 기획서와 다른 메시지를 쓰는 경우. 개발자가 무엇을 고쳐야
        하는지 알려면 실제 문구가 리포트에 있어야 한다."""
        case = negative_case(Expectation(type="error_message", value=PW_MESSAGE))
        actual = "로그인 정보를 확인해주세요."
        v = verify(case, steps_ok(), state(text=actual, errors=[actual]))
        assert v.verdict == "FAIL"
        assert actual in v.evidence["actual"]

    def test_공백_배치가_달라도_같은_문구로_본다(self):
        """PDF 에서 뽑은 문구는 줄바꿈 위치가 화면과 다르다."""
        from_pdf = "비밀번호는 8자\n이상이며 대문자·\n특수문자를 각 1자 이상\n포함해야 합니다."
        case = negative_case(Expectation(type="error_message", value=from_pdf))
        v = verify(case, steps_ok(), state(text=PW_MESSAGE, errors=[PW_MESSAGE]))
        assert v.verdict == "PASS"

    def test_에러영역_밖에서_찾으면_근거_강도를_남긴다(self):
        case = negative_case(Expectation(type="error_message", value=PW_MESSAGE))
        v = verify(case, steps_ok(), state(text=PW_MESSAGE, errors=[]))
        assert v.verdict == "PASS"
        assert "에러 영역 밖" in v.evidence["actual"]


class TestNegativeErrorShown:
    """문구를 특정하지 않는 경우 — 에러가 떴는지만 본다."""

    def test_에러가_뜨면_PASS(self):
        case = negative_case(Expectation(type="error_shown"))
        v = verify(case, steps_ok(), state(errors=["아무 에러 문구"]))
        assert v.verdict == "PASS"

    def test_에러가_없으면_FAIL(self):
        case = negative_case(Expectation(type="error_shown"))
        v = verify(case, steps_ok(), state(url="http://h/bad/dashboard", text="환영합니다"))
        assert v.verdict == "FAIL"

    def test_화면텍스트만으로는_에러_노출로_보지_않는다(self):
        """기획서 문구가 안내문으로 상시 노출된 화면에서 미탐이 생기지 않게,
        error_shown 은 에러 영역만 본다."""
        case = negative_case(Expectation(type="error_shown"))
        v = verify(case, steps_ok(), state(text="비밀번호는 8자 이상 입력하세요", errors=[]))
        assert v.verdict == "FAIL"


class TestPositive:
    def test_경로와_문구를_모두_만족하면_PASS(self):
        case = positive_case(Expectation(type="toast_or_redirect", value="환영합니다",
                                         url_contains="/dashboard"))
        v = verify(case, steps_ok(), state(url="http://h/good/dashboard", text="환영합니다"))
        assert v.verdict == "PASS"

    def test_URL만_바뀌고_문구가_없으면_FAIL(self):
        """URL 은 전이했는데 화면이 빈 상태를 정상으로 보면 안 된다."""
        case = positive_case(Expectation(type="toast_or_redirect", value="환영합니다",
                                         url_contains="/dashboard"))
        v = verify(case, steps_ok(), state(url="http://h/good/dashboard", text=""))
        assert v.verdict == "FAIL"
        assert "미노출" in v.evidence["actual"]

    def test_이동하지_못하면_FAIL(self):
        case = positive_case(Expectation(type="toast_or_redirect", value="환영합니다",
                                         url_contains="/dashboard"))
        v = verify(case, steps_ok(),
                   state(url="http://h/good/login", errors=["이메일 또는 비밀번호가..."]))
        assert v.verdict == "FAIL"
        assert "미이동" in v.evidence["actual"]

    def test_성공조건이_없으면_에러_없음으로_판정한다(self):
        case = positive_case(Expectation(type="toast_or_redirect"))
        assert verify(case, steps_ok(), state()).verdict == "PASS"
        assert verify(case, steps_ok(), state(errors=["에러"])).verdict == "FAIL"


class TestStepFailure:
    def test_스텝이_끊기면_그_원인이_케이스_실패_원인이_된다(self):
        """화면이 기대 상태에 도달할 기회가 없었으므로 기대 대조는 무의미하다."""
        results = steps_ok(2) + [
            StepResult(seq=3, action="click", target="로그인", status="error",
                       error_code="element_not_found",
                       error_detail="일치하는 요소가 없음", elapsed_ms=5)
        ]
        case = negative_case(Expectation(type="error_message", value=PW_MESSAGE))
        v = verify(case, results, state())
        assert v.verdict == "FAIL"
        assert v.failure_category == "element_not_found"
        assert "스텝 3" in v.failure_detail

    def test_콘솔_오류가_있으면_page_error로_분류한다(self):
        case = negative_case(Expectation(type="error_message", value=PW_MESSAGE))
        v = verify(case, steps_ok(), state(text="", console=["Uncaught TypeError"]))
        assert v.verdict == "FAIL"
        assert v.failure_category == "page_error"


class TestEvidence:
    def test_PASS에도_근거를_남긴다(self):
        """왜 PASS 인지 확인할 수 없으면 그 PASS 를 신뢰할 근거가 없다."""
        case = negative_case(Expectation(type="error_message", value=PW_MESSAGE))
        v = verify(case, steps_ok(), state(errors=[PW_MESSAGE]))
        assert v.verdict == "PASS"
        for key in ("expected", "actual", "url", "screenshot"):
            assert key in v.evidence, key

    def test_소요시간을_합산한다(self):
        case = negative_case(Expectation(type="error_shown"))
        v = verify(case, steps_ok(4), state(errors=["e"]))
        assert v.elapsed_ms == 40
