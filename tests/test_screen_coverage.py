"""화면별로 얼마나 확인했는지 남긴다.

## 왜 '몇 건 제외' 로는 부족한가

실모델 측정에서 "회원가입이 잘 되는지 확인해줘" 에 7B 가 17건 중 6건을 골랐다.
프롬프트를 두 번 고쳐도 이 한 건은 안 고쳐졌다 — **프롬프트만으로 7B 가 화면 하나의
케이스 17개를 빠짐없이 세게 만들지는 못한다.**

리포트에 남는 것은 "11건 제외" 뿐이다. 그것만 보면 회원가입 화면을 확인했다고
읽힌다. 실제로는 3분의 1만 봤다.

그래서 화면 단위로 센다. "회원가입 6/17" 이 되면 통과율이 그 화면의 상태를 뜻하지
않는다는 사실이 드러난다. 특히 **요청이 그 화면을 이름으로 지목했는데 일부만
골랐다면** 사람이 반드시 알아야 한다.
"""

import pytest

from prova.llm.mock_backend import MockLLM
from prova.models import (
    Expectation,
    ScreenSpec,
    SpecDocument,
    TestCase,
    TestStep,
    UIElement,
)
from prova.s2_case_generator.selector import select_by_ids, select_cases

DOC = SpecDocument(screens=[
    ScreenSpec(screen_id="signup", screen_name="회원가입", url_path="/signup", elements=[
        UIElement(element_id="email", type="input", label="이메일"),
        UIElement(element_id="nickname", type="input", label="닉네임"),
    ]),
    ScreenSpec(screen_id="login", screen_name="로그인", url_path="/login", elements=[
        UIElement(element_id="email", type="input", label="이메일"),
    ]),
])


def case(case_id: str, screen: str, flow: str | None = None) -> TestCase:
    return TestCase(
        case_id=case_id,
        screen_id=screen,
        title=case_id,
        type="negative",
        flow_id=flow,
        steps=[TestStep(seq=1, action="navigate", target=f"/{screen}")],
        expected=Expectation(type="error_shown"),
    )


@pytest.fixture
def cases() -> list[TestCase]:
    return [
        case("signup-valid-001", "signup"),
        case("signup-email-required-002", "signup"),
        case("signup-email-format-003", "signup"),
        case("signup-nickname-required-004", "signup"),
        case("login-valid-001", "login"),
        case("flow-signup-login-001", "login", flow="signup_then_login"),
    ]


def llm_picking(ids) -> MockLLM:
    llm = MockLLM()
    llm.register("CaseSelection", {"case_ids": list(ids), "reason": "테스트"})
    return llm


def by_key(sel):
    return {c.key: c for c in sel.coverage}


class TestCounts:
    def test_화면별로_몇_건_중_몇_건인지_센다(self, cases):
        _, sel = select_cases(
            cases, "회원가입 확인해줘",
            llm_picking(["signup-valid-001", "signup-email-required-002"]), doc=DOC)
        signup = by_key(sel)["signup"]
        assert (signup.selected, signup.total) == (2, 4)
        assert signup.name == "회원가입"

    def test_한_건도_안_고른_화면도_남는다(self, cases):
        """빠진 화면이 목록에서 사라지면 '안 봤다' 가 보이지 않는다."""
        _, sel = select_cases(
            cases, "회원가입 확인해줘", llm_picking(["signup-valid-001"]), doc=DOC)
        login = by_key(sel)["login"]
        assert (login.selected, login.total) == (0, 1)

    def test_흐름은_화면과_따로_센다(self, cases):
        """흐름 케이스의 screen_id 는 마지막 화면이다. 그 화면에 합치면
        그 화면에 케이스가 하나 더 있는 것처럼 읽힌다."""
        _, sel = select_cases(
            cases, "회원가입 확인해줘", llm_picking(["signup-valid-001"]), doc=DOC)
        flow = by_key(sel)["signup_then_login"]
        assert flow.kind == "flow"
        assert flow.total == 1
        assert by_key(sel)["login"].total == 1  # 흐름이 섞이지 않았다

    def test_전부_고르면_partial_이_아니다(self, cases):
        _, sel = select_cases(
            cases, "전부 다", llm_picking([c.case_id for c in cases]), doc=DOC)
        assert all(not c.partial for c in sel.coverage)

    def test_요청이_없으면_전부_고른_것으로_센다(self, cases):
        _, sel = select_cases(cases, None, llm_picking([]), doc=DOC)
        assert all(c.selected == c.total for c in sel.coverage)


class TestNamed:
    """요청이 화면을 이름으로 지목했는지 — 일부만 골랐을 때 위험도가 다르다."""

    def test_화면_이름을_쓰면_지목으로_본다(self, cases):
        _, sel = select_cases(
            cases, "회원가입이 잘 되는지 확인해줘",
            llm_picking(["signup-valid-001"]), doc=DOC)
        assert by_key(sel)["signup"].named is True
        assert by_key(sel)["login"].named is False

    def test_지목했는데_일부만_고른_경우를_짚어낼_수_있다(self, cases):
        _, sel = select_cases(
            cases, "회원가입이 잘 되는지 확인해줘",
            llm_picking(["signup-valid-001"]), doc=DOC)
        risky = [c for c in sel.coverage if c.named and c.partial]
        assert [c.key for c in risky] == ["signup"]

    def test_지목하고_전부_고르면_위험하지_않다(self, cases):
        _, sel = select_cases(
            cases, "회원가입 확인해줘",
            llm_picking([c.case_id for c in cases if c.screen_id == "signup"]), doc=DOC)
        assert not [c for c in sel.coverage if c.named and c.partial]


class TestApprovedPath:
    """사람이 승인한 경로도 같은 계산을 한다."""

    def test_승인_목록에도_범위가_남는다(self, cases):
        _, sel = select_by_ids(
            cases, ["signup-valid-001"], request="회원가입 확인", doc=DOC)
        signup = by_key(sel)["signup"]
        assert (signup.selected, signup.total) == (1, 4)
        assert signup.named is True


class TestWithoutDoc:
    def test_doc_없이도_센다(self, cases):
        _, sel = select_cases(
            cases, "signup 확인", llm_picking(["signup-valid-001"]))
        signup = by_key(sel)["signup"]
        assert (signup.selected, signup.total) == (1, 4)
        assert signup.name == "signup"  # 사람이 읽는 이름이 없으면 key 를 쓴다
