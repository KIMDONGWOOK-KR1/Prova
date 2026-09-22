"""조작 전부터 같은 화면에 있던 문구는 판정의 근거가 아니다 (2026-09-23).

practicetestautomation 의 로그인 화면은 **아무것도 누르기 전부터** 본문 텍스트에
"Your username is invalid!"(숨은 오류 칸)와 "Congratulations"(안내문)를 담고
있었다. 문구 판정은 조작 뒤 화면 전체에서 찾으므로, 로그인 기능이 망가져 있어도
그 케이스는 통과했다 — 빈 통과다.

PASS 로 두면 확인하지 않은 것을 확인했다고 말하는 것이고, '기획서와 다름' 으로
두면 없는 결함을 보고하는 것이다. 둘 다 아니다: **확인 불가**(unverifiable)로
FAIL 하고, '실행 문제' 쪽에 묶인다.

좁게 적용한다. 화면이 바뀌었으면(이동) 기준선은 다른 화면의 것이라 상관없고,
이미 FAIL 인 판정은 건드리지 않는다.
"""

from prova.models import Expectation, StepResult, TestCase, TestStep
from prova.s5_verifier.assertion_engine import PageState, verify

URL = "https://pta/practice-test-login/"
MSG = "Your username is invalid!"


def _case(expected, type_="negative"):
    return TestCase(case_id="c", screen_id="login", title="t", type=type_,
                    steps=[TestStep(seq=1, action="navigate", target="/login")],
                    expected=expected)


def _steps():
    return [StepResult(seq=1, action="navigate", target="/login", status="ok"),
            StepResult(seq=2, action="click", target="Submit", status="ok")]


def _state(url=URL, text=MSG, baseline_url=URL, baseline_text=MSG):
    return PageState(url=url, text=text, baseline_url=baseline_url,
                     baseline_text=baseline_text)


def test_같은_화면에_원래_있던_문구로는_통과시키지_않는다():
    v = verify(_case(Expectation(type="error_message", value=MSG)), _steps(), _state())
    assert v.verdict == "FAIL"
    assert v.failure_category == "unverifiable"
    assert "조작 전부터" in v.failure_detail


def test_정상_케이스의_문구만_보는_성공_조건도_같다():
    exp = Expectation(type="toast_or_redirect", value="Congratulations")
    v = verify(_case(exp, "positive"), _steps(),
               _state(text="... Congratulations ...", baseline_text="... Congratulations ..."))
    assert v.failure_category == "unverifiable"


def test_화면이_바뀌었으면_기준선과_무관하다():
    exp = Expectation(type="toast_or_redirect", value="Congratulations",
                      url_contains="/logged-in-successfully/")
    v = verify(_case(exp, "positive"), _steps(),
               _state(url="https://pta/logged-in-successfully/",
                      text="Congratulations student", baseline_text="Congratulations"))
    assert v.verdict == "PASS"


def test_조작_뒤에_새로_나타난_문구는_근거다():
    v = verify(_case(Expectation(type="error_message", value=MSG)), _steps(),
               _state(baseline_text="Test login Username Password"))
    assert v.verdict == "PASS"


def test_이미_FAIL_이면_그대로_둔다():
    """기준선은 통과를 의심할 때만 쓴다 — FAIL 을 다른 분류로 바꾸지 않는다."""
    v = verify(_case(Expectation(type="error_message", value="Your password is invalid!")),
               _steps(), _state())
    assert v.failure_category == "assertion_mismatch"


def test_기준선이_없으면_예전과_같다():
    v = verify(_case(Expectation(type="error_message", value=MSG)), _steps(),
               PageState(url=URL, text=MSG))
    assert v.verdict == "PASS"
