"""assertion_engine 테스트 — negative 케이스의 뒤집힌 판정을 못 박는다.

negative 케이스는 **에러가 떠야 PASS** 다. 규칙을 위반한 값을 넣었으니 기획서
대로면 에러가 노출돼야 하고, 그냥 통과됐다면 구현이 규칙을 강제하지 않는
것이므로 FAIL 이다. 직관과 반대라서 회귀가 나기 쉬운 지점이다.
"""

import pytest

from prova.models import Expectation, StepResult, TestCase, TestStep
from prova.s3_grounder.dom_locator import CollectionCount
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


def state(url="http://h/good/login", text="", errors=None, console=None,
          collection=None, options=None) -> PageState:
    return PageState(url=url, text=text or "", error_texts=errors or [],
                     console_errors=console or [], collection=collection,
                     options=options)


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


class TestResultCount:
    """건수 판정 — 목록의 부재와 0건을 구분하는 것이 핵심이다.

    검색 결과 0건일 때 목록을 렌더하지 않는 것은 정상 구현이다. 그걸 탐지 실패로
    처리하면 완벽한 화면에서 '0건이어야 한다' 는 케이스가 오탐으로 FAIL 이 된다.
    반대로 3건이 나와야 하는데 목록이 없는 것은 진짜 실패다. 같은 status=absent
    인데 기대값에 따라 판정이 갈린다 — 그 갈림을 여기서 못 박는다.
    """

    def count_case(self, want: int) -> TestCase:
        return positive_case(Expectation(
            type="result_count", count=want, count_target="검색 결과 목록"))

    def counted(self, status: str, n: int = 0) -> CollectionCount:
        return CollectionCount(target="검색 결과 목록", status=status, count=n,
                               detail="테스트")

    def test_개수가_같으면_PASS(self):
        v = verify(self.count_case(3), steps_ok(), state(collection=self.counted("ok", 3)))
        assert v.verdict == "PASS"

    def test_개수가_다르면_FAIL(self):
        v = verify(self.count_case(3), steps_ok(), state(collection=self.counted("ok", 2)))
        assert v.verdict == "FAIL"
        assert "2개" in v.evidence["actual"] and "3건" in v.evidence["actual"]

    def test_목록이_없고_0건_기대면_PASS(self):
        """조건부 렌더링이 정상 구현이다. 여기서 FAIL 을 내면 오탐이 된다."""
        v = verify(self.count_case(0), steps_ok(),
                   state(collection=self.counted("absent")))
        assert v.verdict == "PASS"

    def test_목록이_없고_1건_이상_기대면_FAIL(self):
        v = verify(self.count_case(3), steps_ok(),
                   state(collection=self.counted("absent")))
        assert v.verdict == "FAIL"

    def test_목록이_없을때_원인을_단정하지_않는다(self):
        """구현이 결과를 못 찾은 것인지, 목록에 접근성 이름이 없어 도구가 못 찾은
        것인지 화면만 보고는 알 수 없다. 하나로 단정하면 개발자가 엉뚱한 곳을
        고친다."""
        v = verify(self.count_case(3), steps_ok(),
                   state(collection=self.counted("absent")))
        assert "0건" in v.evidence["actual"] and "접근성 이름" in v.evidence["actual"]

    def test_목록이_여러개면_FAIL(self):
        """컨테이너의 '정확히 1개' 계약은 세는 경로에서도 유지된다. 어느 목록을
        세야 하는지 모르는 채로 센 숫자는 신뢰할 수 없다."""
        v = verify(self.count_case(0), steps_ok(),
                   state(collection=self.counted("ambiguous", 2)))
        assert v.verdict == "FAIL", "기대값이 0 이어도 모호함은 통과가 아니다"

    def test_세지_않았으면_FAIL(self):
        """수집이 안 된 채로 통과시키면 '확인하지 않은 것' 이 '통과' 로 보고된다."""
        v = verify(self.count_case(3), steps_ok(), state(collection=None))
        assert v.verdict == "FAIL"

    def test_센_결과가_근거에_숫자로_남는다(self):
        v = verify(self.count_case(3), steps_ok(), state(collection=self.counted("ok", 3)))
        assert v.evidence["counted"] == {
            "target": "검색 결과 목록", "status": "ok", "count": 3}

    def test_다른_기대유형에는_근거가_붙지_않는다(self):
        """목록이 없는 화면(로그인 등)에서 status=absent 가 모든 케이스의 근거에
        붙으면, 리포트를 읽는 사람이 매번 그게 문제인지 확인해야 한다."""
        case = positive_case(Expectation(type="text_visible", value="환영합니다"))
        v = verify(case, steps_ok(), state(text="환영합니다"))
        assert "counted" not in v.evidence


class TestFlowVerdict:
    """흐름 케이스의 판정 — 원인을 어느 화면에 돌리는가가 이 기능의 신뢰 근거다."""

    def flow_case(self, expected: Expectation) -> TestCase:
        return TestCase(
            case_id="flow-signup-login-001", screen_id="login",
            flow_id="signup_then_login", title="흐름", type="positive",
            steps=[TestStep(seq=1, action="navigate", target="/signup")],
            expected=expected,
        )

    def test_중간_도착_실패는_그_화면을_지목한다(self):
        """마지막 화면이 애먼 소리를 듣지 않아야 한다. 흐름의 FAIL 이 '검색이
        실패했다' 로 읽히면 개발자가 검색 코드를 뒤진다."""
        results = steps_ok(4) + [
            StepResult(seq=5, action="assert", target="signup 성공", status="error",
                       error_code="assertion_mismatch",
                       error_detail="경로 '/welcome' 미이동", elapsed_ms=3)
        ]
        v = verify(self.flow_case(Expectation(type="toast_or_redirect",
                                             url_contains="/dashboard")),
                   results, state())
        assert v.verdict == "FAIL"
        assert v.failure_category == "assertion_mismatch"
        assert "signup 성공" in v.failure_detail
        assert "흐름 'signup_then_login'" in v.failure_detail

    def test_마지막에서_어긋나면_화면_사이를_가리킨다(self):
        """중간 도착은 다 통과했다 — 각 화면이 제 몫을 했는데 결과가 틀렸다면
        결함은 화면 안이 아니라 화면 사이에 있을 수 있다."""
        v = verify(self.flow_case(Expectation(type="toast_or_redirect",
                                             url_contains="/dashboard",
                                             value="환영합니다")),
                   steps_ok(), state(url="http://h/bad/login"))
        assert v.verdict == "FAIL"
        assert "화면 사이" in v.failure_detail

    def test_판정에_흐름_정보가_남는다(self):
        v = verify(self.flow_case(Expectation(type="text_visible", value="환영합니다")),
                   steps_ok(), state(text="환영합니다"))
        assert v.verdict == "PASS"
        assert v.flow_id == "signup_then_login" and v.screen_id == "login"


class TestSummaryBuckets:
    """화면별·흐름별 집계 — 흐름 실패를 화면 실패와 섞으면 진단이 틀린다."""

    def verdicts(self):
        from prova.models import TestReport

        return TestReport, [
            verify(positive_case(Expectation(type="text_visible", value="ok")),
                   steps_ok(), state(text="ok")),
        ]

    def test_흐름은_화면_칸에_들어가지_않는다(self):
        from prova.models import TestReport

        screen_v = verify(
            TestCase(case_id="login-valid-001", screen_id="login", title="t",
                     type="positive",
                     steps=[TestStep(seq=1, action="navigate", target="/login")],
                     expected=Expectation(type="text_visible", value="ok")),
            steps_ok(), state(text="ok"))
        flow_v = verify(
            TestCase(case_id="flow-f-001", screen_id="login", flow_id="f", title="t",
                     type="positive",
                     steps=[TestStep(seq=1, action="navigate", target="/login")],
                     expected=Expectation(type="text_visible", value="ok")),
            steps_ok(), state(text=""))

        s = TestReport.summarize([screen_v, flow_v])
        assert s["by_screen"]["login"] == {"total": 1, "pass": 1, "fail": 0}
        assert s["by_flow"]["f"] == {"total": 1, "pass": 0, "fail": 1}
        assert s["total"] == 2 and s["fail"] == 1


class TestOptionsPresent:
    """선택 항목 판정 — 빠진 것만 본다."""

    def case(self, want: list[str]) -> TestCase:
        return positive_case(Expectation(
            type="options_present", options=want, option_target="가입 경로"))

    def test_다_있으면_PASS(self):
        v = verify(self.case(["검색", "지인 추천", "광고"]), steps_ok(),
                   state(options=["선택하세요", "검색", "지인 추천", "광고"]))
        assert v.verdict == "PASS"

    def test_빠지면_FAIL하고_무엇이_빠졌는지_남긴다(self):
        v = verify(self.case(["검색", "지인 추천", "광고"]), steps_ok(),
                   state(options=["선택하세요", "검색", "광고"]))
        assert v.verdict == "FAIL"
        assert "지인 추천" in v.evidence["actual"]

    def test_항목이_더_있어도_PASS(self):
        """안내용 첫 항목을 걸러내려면 무엇이 안내인지 추측해야 하고, 추측하면
        기획서에 있는 항목을 안내로 착각해 없다고 보고할 수 있다."""
        v = verify(self.case(["검색"]), steps_ok(),
                   state(options=["선택하세요", "검색", "기타"]))
        assert v.verdict == "PASS"

    def test_읽지_못했으면_FAIL(self):
        """None 은 '읽지 못했다' 이고 빈 목록은 '항목이 하나도 없다' 다."""
        v = verify(self.case(["검색"]), steps_ok(), state(options=None))
        assert v.verdict == "FAIL"
        assert "읽지 못했습니다" in v.evidence["actual"]

    def test_항목이_하나도_없으면_FAIL(self):
        v = verify(self.case(["검색"]), steps_ok(), state(options=[]))
        assert v.verdict == "FAIL"
        assert "검색" in v.evidence["actual"]

    def test_화면의_항목을_근거에_남긴다(self):
        v = verify(self.case(["검색"]), steps_ok(), state(options=["검색", "광고"]))
        assert v.evidence["screen_options"] == ["검색", "광고"]

    def test_다른_기대유형에는_근거가_붙지_않는다(self):
        case = positive_case(Expectation(type="text_visible", value="환영합니다"))
        v = verify(case, steps_ok(), state(text="환영합니다"))
        assert "screen_options" not in v.evidence
